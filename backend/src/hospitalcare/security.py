"""Passwords, session tokens, agent delegation tokens and role permissions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .config import get_settings
from .db import utcnow

# --- Roles and permissions -------------------------------------------------

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "intake_clerk": frozenset({"patient:read_basic", "patient:create", "encounter:create", "symptom:record", "queue:read"}),
    "nurse": frozenset({
        "patient:read_basic", "patient:read_history", "patient:create", "encounter:create",
        "observation:record", "observation:verify", "symptom:record", "triage:run",
        "review:read", "review:decide", "queue:read",
    }),
    "clinician": frozenset({
        "patient:read_basic", "patient:read_history", "observation:record", "observation:verify",
        "symptom:record", "triage:run", "review:read", "review:decide", "queue:read",
    }),
    "auditor": frozenset({"audit:read"}),
    "admin": frozenset({"system:read", "audit:read"}),
}

# Scopes an agent delegation token may carry. `review:decide` is deliberately absent:
# the agent can never record a human decision.
DELEGABLE_SCOPES = {
    "context:read": "patient:read_history",
    "triage:evaluate": "triage:run",
    "review:create": "triage:run",
    "review:read": "review:read",
    "review:execute": "review:decide",
}


def permissions_for(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for(role)


# --- Passwords --------------------------------------------------------------

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(digest.hex(), digest_hex)


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


# --- Principals ---------------------------------------------------------------


@dataclass(frozen=True)
class Principal:
    """An authenticated actor. `scopes` is set only for agent delegation tokens."""

    user_id: str
    username: str
    role: str
    display_name: str
    via: str  # "session" or "delegation"
    scopes: frozenset[str] = field(default_factory=frozenset)
    encounter_id: str | None = None

    def can(self, permission: str) -> bool:
        return has_permission(self.role, permission)


class AuthError(Exception):
    """Authentication failed (401)."""


class PermissionDenied(Exception):
    """Authenticated but not authorized (403)."""


# --- Sessions -----------------------------------------------------------------


def create_session(conn: sqlite3.Connection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=get_settings().session_ttl_minutes)
    conn.execute(
        "INSERT INTO sessions (id, user_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, sha256_hex(token), now.isoformat(timespec="seconds"),
         expires.isoformat(timespec="seconds")),
    )
    return token


def revoke_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("UPDATE sessions SET revoked = 1 WHERE token_hash = ?", (sha256_hex(token),))


def principal_from_session(conn: sqlite3.Connection, token: str) -> Principal:
    row = conn.execute(
        """SELECT u.id, u.username, u.role, u.display_name, u.active, s.expires_at, s.revoked
           FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?""",
        (sha256_hex(token),),
    ).fetchone()
    if row is None or row["revoked"] or not row["active"]:
        raise AuthError("invalid or revoked session")
    if row["expires_at"] <= utcnow():
        raise AuthError("session expired")
    return Principal(row["id"], row["username"], row["role"], row["display_name"], via="session")


# --- Delegation tokens (agent -> MCP) ---------------------------------------------


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_delegation_token(principal: Principal, encounter_id: str, scopes: set[str]) -> str:
    """Mint a short-lived token letting the agent act for `principal` on one encounter.

    Only scopes whose underlying permission the user actually holds are granted.
    """
    unknown = scopes - DELEGABLE_SCOPES.keys()
    if unknown:
        raise PermissionDenied(f"non-delegable scopes requested: {sorted(unknown)}")
    granted = sorted(s for s in scopes if principal.can(DELEGABLE_SCOPES[s]))
    payload = {
        "sub": principal.user_id,
        "enc": encounter_id,
        "scp": granted,
        "exp": int(time.time()) + get_settings().delegation_ttl_minutes * 60,
        "jti": secrets.token_hex(8),
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(get_settings().secret_key.encode(), body.encode(), hashlib.sha256).digest())
    return f"dlg.{body}.{sig}"


def principal_from_delegation(conn: sqlite3.Connection, token: str) -> Principal:
    try:
        prefix, body, sig = token.split(".")
    except ValueError as exc:
        raise AuthError("malformed delegation token") from exc
    expected = _b64(hmac.new(get_settings().secret_key.encode(), body.encode(), hashlib.sha256).digest())
    if prefix != "dlg" or not hmac.compare_digest(sig, expected):
        raise AuthError("invalid delegation token signature")
    payload = json.loads(_unb64(body))
    if payload["exp"] < time.time():
        raise AuthError("delegation token expired")
    row = conn.execute(
        "SELECT id, username, role, display_name, active FROM users WHERE id = ?", (payload["sub"],)
    ).fetchone()
    if row is None or not row["active"]:
        raise AuthError("delegating user is not active")
    # Re-check permissions against the user's *current* role.
    scopes = frozenset(s for s in payload["scp"] if has_permission(row["role"], DELEGABLE_SCOPES[s]))
    return Principal(row["id"], row["username"], row["role"], row["display_name"], via="delegation",
                     scopes=scopes, encounter_id=payload["enc"])


def authenticate_token(conn: sqlite3.Connection, token: str) -> Principal:
    if not token:
        raise AuthError("missing token")
    if token.startswith("dlg."):
        return principal_from_delegation(conn, token)
    return principal_from_session(conn, token)


def require(principal: Principal, permission: str, *, scope: str | None = None,
            encounter_id: str | None = None) -> None:
    """Raise PermissionDenied unless the principal may perform the operation.

    Session principals are checked by role permission. Delegation principals must
    additionally carry the named scope and be bound to the same encounter.
    """
    if not principal.can(permission):
        raise PermissionDenied(f"role '{principal.role}' lacks permission '{permission}'")
    if principal.via == "delegation":
        if scope is None or scope not in principal.scopes:
            raise PermissionDenied(f"delegation token lacks scope '{scope}'")
        if encounter_id is not None and principal.encounter_id != encounter_id:
            raise PermissionDenied("delegation token is bound to a different encounter")
