"""Tests for CORS configuration on the FastAPI app."""

import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient


def _reload_main_with_env(env_overrides: dict[str, str]) -> object:
    """Reimport `main` with the given env overrides so middleware re-binds."""
    for key, value in env_overrides.items():
        os.environ[key] = value
    if "main" in sys.modules:
        del sys.modules["main"]
    return importlib.import_module("main")


def _preflight(client: TestClient, origin: str) -> int:
    """Send a CORS preflight for POST /api/evaluate and return the status code."""
    response = client.options(
        "/api/evaluate",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    return response.status_code


@pytest.fixture(autouse=True)
def _reset_main():
    yield
    if "main" in sys.modules:
        del sys.modules["main"]


def test_default_origins_allow_localhost_and_canonical_vercel():
    main = _reload_main_with_env({"MOCK_MODE": "1"})
    for env_var in ("CORS_ORIGINS", "CORS_ORIGIN_REGEX"):
        os.environ.pop(env_var, None)
    main = _reload_main_with_env({"MOCK_MODE": "1"})
    client = TestClient(main.app)

    assert _preflight(client, "http://localhost:5173") == 200
    assert _preflight(client, "https://agri-subsidy.vercel.app") == 200


def test_default_regex_matches_vercel_preview_domains():
    main = _reload_main_with_env({"MOCK_MODE": "1"})
    for env_var in ("CORS_ORIGINS", "CORS_ORIGIN_REGEX"):
        os.environ.pop(env_var, None)
    main = _reload_main_with_env({"MOCK_MODE": "1"})
    client = TestClient(main.app)

    preview = "https://agri-subsidy-git-devin-1234-gelos-projects.vercel.app"
    assert _preflight(client, preview) == 200


def test_unknown_origin_is_rejected():
    main = _reload_main_with_env({"MOCK_MODE": "1"})
    for env_var in ("CORS_ORIGINS", "CORS_ORIGIN_REGEX"):
        os.environ.pop(env_var, None)
    main = _reload_main_with_env({"MOCK_MODE": "1"})
    client = TestClient(main.app)

    response = client.options(
        "/api/evaluate",
        headers={
            "Origin": "https://attacker.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    # FastAPI/Starlette returns 400 with no allow-origin header for disallowed origins.
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_env_override_replaces_default_list():
    main = _reload_main_with_env(
        {
            "MOCK_MODE": "1",
            "CORS_ORIGINS": "https://staging.example.com",
            "CORS_ORIGIN_REGEX": r"^$",  # disable regex match
        }
    )
    client = TestClient(main.app)

    assert _preflight(client, "https://staging.example.com") == 200
    # The previously-default Vercel origin is no longer allowed.
    assert _preflight(client, "https://agri-subsidy.vercel.app") == 400
