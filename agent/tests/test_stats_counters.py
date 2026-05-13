"""Tests for the trust-signal counters surfaced via /api/stats.

The PR #9 class of regression is: every TX is silently a MOCK on prod, but
/api/stats keeps reporting a climbing `total_disbursed_sol` and the dashboard
shows green verdicts. These tests pin the contract:

  - MOCK or degraded-MOCK signatures DO NOT credit `total_disbursed_sol`.
  - `mock_tx_count` / `live_tx_count` / `degraded_tx_count` reflect what
    actually happened on-chain.
  - `fallback_eval_count` ticks whenever the AI agent ran in fallback mode.

The pipeline calls real `weather_service`, `ndvi_service`, `scoring_engine`,
`ai_agent`, and `solana_bridge`. We monkeypatch those to deterministic
behaviour so we can drive the accounting paths from a unit test.
"""

import asyncio
import os

os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

import pytest

import main
from models import EvaluationResult


@pytest.fixture(autouse=True)
def _reset_main_state(monkeypatch):
    """Reset module-level counters before every test."""
    main.farmers_db.clear()
    main.evaluations_db.clear()
    main.total_disbursed_sol = 0.0
    main.live_tx_count = 0
    main.mock_tx_count = 0
    main.degraded_tx_count = 0
    main.fallback_eval_count = 0

    async def _fake_weather(_lat, _lon):
        return {"temperature": 35, "humidity": 12, "description": "drought", "rain_1h": 0}

    async def _fake_ndvi(_lat, _lon):
        return {
            "current_ndvi": 0.12,
            "historical_avg": 0.55,
            "alert": "severe_drought",
            "deviation_pct": -78,
        }

    async def _fake_stream(*_args, **_kwargs):
        # No streamed entries — fine for the accounting tests.
        if False:
            yield None

    monkeypatch.setattr(main, "fetch_weather_data", _fake_weather)
    monkeypatch.setattr(main, "fetch_historical_ndvi", _fake_ndvi)
    monkeypatch.setattr(main, "stream_ai_evaluation", _fake_stream)


class _FakeBridge:
    def __init__(self, signature, is_mock, amount_sol, is_degraded=False, failure_reason=None):
        self.signature = signature
        self.is_mock = is_mock
        self.amount_sol = amount_sol
        self.is_degraded = is_degraded
        self.failure_reason = failure_reason
        self.explorer_url = f"https://explorer.solana.com/tx/{signature}?cluster=devnet"


def _make_verdict(approved: bool, is_fallback: bool = False, score: int = 72):
    async def _verdict(*_args, **_kwargs):
        return EvaluationResult(
            approved=approved,
            score=score,
            reasoning="test verdict",
            is_fallback=is_fallback,
        )

    return _verdict


def _start_eval(wallet: str = "4pMnsypmRtd94bK94LXjFPWghpXN5WfCcLvnJhoUdX5z"):
    evaluation_id = "eval-test"
    main.evaluations_db[evaluation_id] = {
        "evaluation_id": evaluation_id,
        "wallet": wallet,
        "logs": [],
        "result": None,
        "status": "in-progress",
        "started_at": "now",
    }
    return evaluation_id, wallet


def test_live_tx_credits_total_disbursed_and_live_counter(monkeypatch):
    evaluation_id, wallet = _start_eval()

    async def _bridge(*_args, **_kwargs):
        return _FakeBridge("sig-live", is_mock=False, amount_sol=1.5)

    monkeypatch.setattr(main, "get_ai_verdict", _make_verdict(approved=True))
    monkeypatch.setattr(main, "release_subsidy", _bridge)

    asyncio.run(main.run_evaluation_pipeline(evaluation_id, wallet, 45.5, 59.0))

    assert main.live_tx_count == 1
    assert main.mock_tx_count == 0
    assert main.degraded_tx_count == 0
    assert main.total_disbursed_sol == pytest.approx(1.5)


def test_mock_tx_does_not_credit_total_disbursed(monkeypatch):
    """Demo MOCK (PROGRAM_ID empty) must NOT inflate the on-chain ledger."""
    evaluation_id, wallet = _start_eval()

    async def _bridge(*_args, **_kwargs):
        return _FakeBridge("sig-mock", is_mock=True, amount_sol=1.5)

    monkeypatch.setattr(main, "get_ai_verdict", _make_verdict(approved=True))
    monkeypatch.setattr(main, "release_subsidy", _bridge)

    asyncio.run(main.run_evaluation_pipeline(evaluation_id, wallet, 45.5, 59.0))

    assert main.mock_tx_count == 1
    assert main.live_tx_count == 0
    assert main.degraded_tx_count == 0
    # No on-chain settlement => no climb of the public total.
    assert main.total_disbursed_sol == 0.0


def test_degraded_mock_increments_degraded_counter(monkeypatch):
    """A PR #9 regression: PROGRAM_ID set but LIVE failed -> degraded MOCK.
    Both mock_tx_count and degraded_tx_count must tick; total stays at 0.
    """
    evaluation_id, wallet = _start_eval()

    async def _bridge(*_args, **_kwargs):
        return _FakeBridge(
            "sig-degraded",
            is_mock=True,
            amount_sol=1.5,
            is_degraded=True,
            failure_reason="RuntimeError: RPC error: blockhash not found",
        )

    monkeypatch.setattr(main, "get_ai_verdict", _make_verdict(approved=True))
    monkeypatch.setattr(main, "release_subsidy", _bridge)

    asyncio.run(main.run_evaluation_pipeline(evaluation_id, wallet, 45.5, 59.0))

    assert main.mock_tx_count == 1
    assert main.degraded_tx_count == 1
    assert main.live_tx_count == 0
    assert main.total_disbursed_sol == 0.0


def test_fallback_eval_count_ticks_on_fallback_verdict(monkeypatch):
    evaluation_id, wallet = _start_eval()

    async def _bridge(*_args, **_kwargs):
        return _FakeBridge("sig-fb", is_mock=True, amount_sol=1.5)

    monkeypatch.setattr(
        main, "get_ai_verdict", _make_verdict(approved=True, is_fallback=True)
    )
    monkeypatch.setattr(main, "release_subsidy", _bridge)

    asyncio.run(main.run_evaluation_pipeline(evaluation_id, wallet, 45.5, 59.0))

    assert main.fallback_eval_count == 1


def test_fallback_count_ticks_even_when_rejected(monkeypatch):
    """If the AI agent ran in fallback and rejected, the fallback counter must
    still tick so operators can correlate rejection rate with fallback rate.
    """
    evaluation_id, wallet = _start_eval()

    async def _bridge(*_args, **_kwargs):
        raise AssertionError("release_subsidy should not be called on a rejection")

    monkeypatch.setattr(
        main, "get_ai_verdict", _make_verdict(approved=False, is_fallback=True)
    )
    monkeypatch.setattr(main, "release_subsidy", _bridge)

    asyncio.run(main.run_evaluation_pipeline(evaluation_id, wallet, 45.5, 59.0))

    assert main.fallback_eval_count == 1
    assert main.live_tx_count == 0
    assert main.mock_tx_count == 0


def test_result_payload_includes_tx_block_for_dashboard(monkeypatch):
    """The dashboard reads `result.tx.is_mock` / `is_degraded` to render the
    Simulated-TX chip. The /done SSE event must include that block.
    """
    evaluation_id, wallet = _start_eval()

    async def _bridge(*_args, **_kwargs):
        return _FakeBridge(
            "sig-degraded",
            is_mock=True,
            amount_sol=1.5,
            is_degraded=True,
            failure_reason="RuntimeError: blockhash not found",
        )

    monkeypatch.setattr(main, "get_ai_verdict", _make_verdict(approved=True))
    monkeypatch.setattr(main, "release_subsidy", _bridge)

    asyncio.run(main.run_evaluation_pipeline(evaluation_id, wallet, 45.5, 59.0))

    stored = main.evaluations_db[evaluation_id]["result"]
    assert "tx" in stored
    assert stored["tx"]["is_mock"] is True
    assert stored["tx"]["is_degraded"] is True
    assert "blockhash" in stored["tx"]["failure_reason"]


def test_stats_endpoint_exposes_counters(monkeypatch):
    """End-to-end: hit /api/stats after a MOCK approval and verify the new
    counter fields are present and non-zero where expected.
    """
    from fastapi.testclient import TestClient

    evaluation_id, wallet = _start_eval()

    async def _bridge(*_args, **_kwargs):
        return _FakeBridge("sig-mock", is_mock=True, amount_sol=1.5)

    monkeypatch.setattr(main, "get_ai_verdict", _make_verdict(approved=True))
    monkeypatch.setattr(main, "release_subsidy", _bridge)

    asyncio.run(main.run_evaluation_pipeline(evaluation_id, wallet, 45.5, 59.0))

    client = TestClient(main.app)
    payload = client.get("/api/stats").json()
    assert payload["total_disbursed_sol"] == 0.0
    assert payload["mock_tx_count"] == 1
    assert payload["live_tx_count"] == 0
    assert payload["degraded_tx_count"] == 0
    assert "fallback_eval_count" in payload
