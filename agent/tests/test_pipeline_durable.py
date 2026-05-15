"""End-to-end test: the run_evaluation_pipeline writes a disbursement row,
and /api/stats reads its counters from the SQL ledger after a process
restart.

This is the integration that closes the investor-due-diligence-blocking
hole described in MEMORY.md Strategic Shift: every redeploy used to wipe
the ledger. After this PR, ``total_disbursed_sol`` lives in SQL and
survives a restart of the agent process.
"""

from __future__ import annotations

import asyncio
import importlib
import os
from pathlib import Path

import pytest

os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

from models import EvaluationResult


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "agri-pipeline.db"
    url = f"sqlite+aiosqlite:///{path}"
    monkeypatch.setenv("DATABASE_URL", url)
    import db as _db
    asyncio.run(_db.shutdown_db())
    importlib.reload(_db)
    yield _db
    asyncio.run(_db.shutdown_db())


class _FakeBridge:
    def __init__(self, signature, is_mock, amount_sol, is_degraded=False, failure_reason=None):
        self.signature = signature
        self.is_mock = is_mock
        self.amount_sol = amount_sol
        self.is_degraded = is_degraded
        self.failure_reason = failure_reason
        self.explorer_url = f"https://explorer.solana.com/tx/{signature}?cluster=devnet"


def _patch_main_with_fakes(monkeypatch, *, bridge, approved=True, is_fallback=False):
    """Wire the pipeline against deterministic dependencies.

    The pipeline calls real ``weather_service``, ``ndvi_service``,
    ``ai_agent``, and ``solana_bridge`` — we replace each with a stub so
    the test only exercises the accounting paths.
    """
    import main

    async def _fake_weather(_lat, _lon):
        return {"temperature": 35, "humidity": 12, "description": "drought", "rain_1h": 0}

    async def _fake_ndvi(_lat, _lon):
        return {"current_ndvi": 0.12, "historical_avg": 0.55,
                "alert": "severe_drought", "deviation_pct": -78}

    async def _fake_stream(*_a, **_kw):
        if False:
            yield None

    async def _fake_verdict(*_a, **_kw):
        return EvaluationResult(
            approved=approved,
            score=72,
            reasoning="test",
            is_fallback=is_fallback,
        )

    async def _fake_bridge(*_a, **_kw):
        return bridge

    monkeypatch.setattr(main, "fetch_weather_data", _fake_weather)
    monkeypatch.setattr(main, "fetch_historical_ndvi", _fake_ndvi)
    monkeypatch.setattr(main, "stream_ai_evaluation", _fake_stream)
    monkeypatch.setattr(main, "get_ai_verdict", _fake_verdict)
    monkeypatch.setattr(main, "release_subsidy", _fake_bridge)

    # Reset in-memory counters so the test starts clean.
    main.farmers_db.clear()
    main.evaluations_db.clear()
    main.total_disbursed_sol = 0.0
    main.live_tx_count = 0
    main.mock_tx_count = 0
    main.degraded_tx_count = 0
    main.fallback_eval_count = 0


def _seed_eval(main_mod, wallet: str = "FAKE_WALLET", evaluation_id: str = "ev-pipe"):
    main_mod.evaluations_db[evaluation_id] = {
        "evaluation_id": evaluation_id,
        "wallet": wallet,
        "logs": [],
        "result": None,
        "status": "running",
        "started_at": "now",
    }
    main_mod.farmers_db[wallet] = main_mod.FarmerStatus(
        wallet=wallet, lat=45.5, lon=59.0, status="pending"
    )
    return evaluation_id, wallet


def test_live_tx_disbursement_persists_across_restart(db_url, monkeypatch):
    """Run a LIVE evaluation, then simulate an agent restart and verify the
    public ``/api/stats`` counters come from the SQL ledger, not from the
    in-memory globals (which would have been wiped)."""
    import main
    import db as _db

    asyncio.run(_db.init_db())
    _patch_main_with_fakes(
        monkeypatch,
        bridge=_FakeBridge("SIG_LIVE_PIPE", is_mock=False, amount_sol=1.5),
    )
    eval_id, wallet = _seed_eval(main)

    asyncio.run(main.run_evaluation_pipeline(eval_id, wallet, 45.5, 59.0))

    # In-memory counters reflect the LIVE TX.
    assert main.live_tx_count == 1
    assert main.total_disbursed_sol == pytest.approx(1.5)

    # ─── Simulate an agent restart ──────────────────────────────────────
    # Counters go back to zero in memory (that's the whole point of
    # durable storage), but /api/stats is now backed by SQL.
    main.total_disbursed_sol = 0.0
    main.live_tx_count = 0
    main.mock_tx_count = 0
    main.degraded_tx_count = 0
    main.fallback_eval_count = 0

    stats = asyncio.run(main.get_stats())
    assert stats.live_tx_count == 1
    assert stats.total_disbursed_sol == pytest.approx(1.5)
    assert stats.mock_tx_count == 0


def test_mock_tx_does_not_credit_durable_total(db_url, monkeypatch):
    """MOCK and degraded-MOCK rows are persisted, but the public
    ``total_disbursed_sol`` stays at zero — same PR #13 honesty contract,
    enforced now at the SQL layer.
    """
    import main
    import db as _db

    asyncio.run(_db.init_db())
    _patch_main_with_fakes(
        monkeypatch,
        bridge=_FakeBridge(
            "SIG_DEGRADED",
            is_mock=True,
            amount_sol=1.5,
            is_degraded=True,
            failure_reason="simulated rpc error",
        ),
    )
    eval_id, wallet = _seed_eval(main)

    asyncio.run(main.run_evaluation_pipeline(eval_id, wallet, 45.5, 59.0))

    stats = asyncio.run(main.get_stats())
    assert stats.live_tx_count == 0
    assert stats.mock_tx_count == 1
    assert stats.degraded_tx_count == 1
    assert stats.total_disbursed_sol == 0.0


def test_pipeline_retry_same_signature_does_not_double_credit(db_url, monkeypatch):
    """Run two pipeline invocations that emit the same TX signature.

    Mirrors the at-least-once delivery class of bug: an agent restart that
    rebroadcasts a confirmed signature must not climb ``total_disbursed_sol``
    a second time.
    """
    import main
    import db as _db

    asyncio.run(_db.init_db())
    _patch_main_with_fakes(
        monkeypatch,
        bridge=_FakeBridge("SIG_REPEATED", is_mock=False, amount_sol=1.5),
    )
    eval_id1, wallet = _seed_eval(main, evaluation_id="ev-A")
    asyncio.run(main.run_evaluation_pipeline(eval_id1, wallet, 45.5, 59.0))

    # Same wallet, same bridge result, fresh evaluation row — emulates
    # "retry of an already-settled payout from a different pipeline run".
    eval_id2 = "ev-B"
    main.evaluations_db[eval_id2] = {
        "evaluation_id": eval_id2,
        "wallet": wallet,
        "logs": [],
        "result": None,
        "status": "running",
        "started_at": "now",
    }
    asyncio.run(main.run_evaluation_pipeline(eval_id2, wallet, 45.5, 59.0))

    stats = asyncio.run(main.get_stats())
    # SQL UNIQUE on signature prevents the second insert; LIVE total stays
    # at exactly one payout.
    assert stats.live_tx_count == 1
    assert stats.total_disbursed_sol == pytest.approx(1.5)
