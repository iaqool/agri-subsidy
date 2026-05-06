"""Tests for evaluation request idempotency."""

import os
from datetime import datetime, timedelta

# Use mock mode for solana bridge so we don't try to talk to Devnet during tests.
os.environ.setdefault("MOCK_MODE", "1")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

from fastapi.testclient import TestClient

import main
from main import app, _idempotency_cache, _evaluation_fingerprint

client = TestClient(app)

VALID_WALLET = "4pMnsypmRtd94bK94LXjFPWghpXN5WfCcLvnJhoUdX5z"


def setup_function(_fn):
    main.farmers_db.clear()
    main.evaluations_db.clear()
    _idempotency_cache.clear()


def _evaluate(wallet: str, lat: float, lon: float, key: str | None = None):
    headers = {}
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post(
        "/api/evaluate",
        json={"wallet_address": wallet, "lat": lat, "lon": lon},
        headers=headers,
    )


def test_repeated_request_returns_same_evaluation_id():
    r1 = _evaluate(VALID_WALLET, 53.2, 63.6)
    assert r1.status_code == 200
    eval_id_1 = r1.json()["evaluation_id"]

    r2 = _evaluate(VALID_WALLET, 53.2, 63.6)
    assert r2.status_code == 200
    eval_id_2 = r2.json()["evaluation_id"]

    assert eval_id_1 == eval_id_2


def test_explicit_idempotency_key_takes_precedence():
    r1 = _evaluate(VALID_WALLET, 53.2, 63.6, key="custom-key-1")
    eval_id_1 = r1.json()["evaluation_id"]

    # Different coords, same explicit key — must dedupe to the first call
    r2 = _evaluate(VALID_WALLET, 10.0, 10.0, key="custom-key-1")
    eval_id_2 = r2.json()["evaluation_id"]

    assert eval_id_1 == eval_id_2


def test_different_coords_get_different_evaluation_ids():
    r1 = _evaluate(VALID_WALLET, 53.2, 63.6)
    r2 = _evaluate(VALID_WALLET, 43.8, 77.1)
    assert r1.json()["evaluation_id"] != r2.json()["evaluation_id"]


def test_idempotency_cache_expires():
    r1 = _evaluate(VALID_WALLET, 53.2, 63.6)
    eval_id_1 = r1.json()["evaluation_id"]

    fingerprint = _evaluation_fingerprint(VALID_WALLET, 53.2, 63.6)
    assert fingerprint in _idempotency_cache

    # Force expiry by rewinding the entry
    eval_id, _expires = _idempotency_cache[fingerprint]
    _idempotency_cache[fingerprint] = (eval_id, datetime.utcnow() - timedelta(seconds=1))

    r2 = _evaluate(VALID_WALLET, 53.2, 63.6)
    eval_id_2 = r2.json()["evaluation_id"]
    assert eval_id_2 != eval_id_1


def test_evaluate_rejects_invalid_wallet():
    r = _evaluate("not-a-real-wallet", 53.2, 63.6)
    assert r.status_code == 422


def test_evaluate_rejects_out_of_range_coords():
    r = _evaluate(VALID_WALLET, 200.0, 0.0)
    assert r.status_code == 422
