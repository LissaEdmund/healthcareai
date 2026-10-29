"""Shared fixtures. Every test gets its own temporary database seeded with synthetic data."""

from __future__ import annotations

import os
import shutil

import pytest

from hospitalcare import config
from hospitalcare.config import REPO_ROOT

TEST_SECRET = "test-secret-key-0123456789-abcdefghijklmnopqrstuvwxyz"
DEMO_PASSWORD = "synthetic-demo-pw"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    ref = tmp_path / "reference"
    shutil.copytree(REPO_ROOT / "reference", ref)
    values = {
        "HCAI_TESTING": "true",
        "HCAI_SECRET_KEY": TEST_SECRET,
        "HCAI_DEMO_PASSWORD": DEMO_PASSWORD,
        "HCAI_DATA_DIR": str(tmp_path / "data"),
        "HCAI_REFERENCE_DIR": str(ref),
        "HCAI_MCP_TRANSPORT": "inprocess",
        "HCAI_LLM_ENABLED": "false",
        "HCAI_DEMO_MODE": "true",
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    config.get_settings.cache_clear()
    yield values
    config.get_settings.cache_clear()


@pytest.fixture
def conn(env):
    from hospitalcare.db import connect, migrate
    from hospitalcare.seed import seed

    c = connect()
    migrate(c)
    seed(c)
    yield c
    c.close()


def session_for(conn, username: str):
    from hospitalcare import repositories as repo
    from hospitalcare.security import create_session, principal_from_session

    user = repo.get_user_by_username(conn, username)
    token = create_session(conn, user["id"])
    return token, principal_from_session(conn, token)


@pytest.fixture
def nurse(conn):
    return session_for(conn, "nurse.demo")


@pytest.fixture
def nurse2(conn):
    return session_for(conn, "nurse2.demo")


@pytest.fixture
def intake(conn):
    return session_for(conn, "intake.demo")


@pytest.fixture
def auditor(conn):
    return session_for(conn, "auditor.demo")


def model_tests_enabled() -> bool:
    return os.environ.get("HCAI_SKIP_MODEL_TESTS") != "1"
