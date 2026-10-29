"""Application configuration loaded from environment variables and the repository-root `.env`."""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
INSECURE_SECRET_VALUES = {"", "CHANGE_ME"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HCAI_", env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    secret_key: str = "CHANGE_ME"
    demo_password: str = "CHANGE_ME_DEMO_PASSWORD"
    testing: bool = False

    data_dir: Path = Path("data")
    reference_dir: Path = Path("reference")

    demo_mode: bool = True
    facility_code: str = "SYNTHETIC-FACILITY-01"

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "phi4-mini"
    ollama_timeout_seconds: float = 180.0
    llm_enabled: bool = True

    mcp_transport: str = Field(default="stdio", pattern="^(stdio|inprocess)$")
    node_executable: str = "node"
    filesystem_mcp_entry: Path = Path(
        "mcp-filesystem/node_modules/@modelcontextprotocol/server-filesystem/dist/index.js"
    )

    session_ttl_minutes: int = 480
    delegation_ttl_minutes: int = 15
    recurrence_lookback_days: int = 365

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    def resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else (REPO_ROOT / path).resolve()

    @property
    def data_path(self) -> Path:
        return self.resolve(self.data_dir)

    @property
    def reference_path(self) -> Path:
        return self.resolve(self.reference_dir)

    @property
    def protocols_path(self) -> Path:
        return self.reference_path / "protocols"

    @property
    def database_path(self) -> Path:
        return self.data_path / "hospitalcare.sqlite"

    @property
    def checkpoint_path(self) -> Path:
        return self.data_path / "workflow_checkpoints.sqlite"

    @property
    def filesystem_mcp_entry_path(self) -> Path:
        return self.resolve(self.filesystem_mcp_entry)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ollama_is_loopback(self) -> bool:
        host = urlparse(self.ollama_url).hostname or ""
        if host == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def validate_for_runtime(self) -> list[str]:
        """Return fatal configuration problems; empty list means OK."""
        problems: list[str] = []
        if not self.testing and self.secret_key in INSECURE_SECRET_VALUES:
            problems.append("HCAI_SECRET_KEY is not set (copy .env.example to .env and set a random value).")
        if not self.testing and len(self.secret_key) < 32:
            problems.append("HCAI_SECRET_KEY must be at least 32 characters.")
        if not self.ollama_is_loopback():
            problems.append(
                "HCAI_OLLAMA_URL must point to a loopback address; patient content must not leave this machine."
            )
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
