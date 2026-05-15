"""Tests for the durable-storage backend.

These tests target ``agent/db.py`` directly (SQLAlchemy 2.0 + aiosqlite,
file-backed SQLite). They focus on the production-relevant guarantees:

1. ``DATABASE_URL`` unset means the module is a no-op (no implicit file
   creation, no implicit table creation, no surprises for tests that only
   exercise the in-memory paths).
2. ``DATABASE_URL`` set to a SQLite file:
   - tables are auto-created on the first ``init_db()`` call
   - farmer rows survive a full engine restart
   - the disbursement ledger is append-only with a UNIQUE constraint on
     ``signature`` so retries cannot inflate ``total_disbursed_sol``
3. ``disbursement_stats`` aggregates exactly what the public ``/api/stats``
   endpoint promises: LIVE TXs credit ``total_disbursed_sol``, MOCK and
   degraded-MOCK do not, and the LIVE/MOCK/degraded counters reflect the
   on-chain reality.
"""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point DATABASE_URL at a per-test SQLite file and reset the module.

    The engine is cached at module scope, so we have to reload ``db`` per
    test to make sure each test gets a fresh engine bound to its own file.
    """
    path = tmp_path / "agri-test.db"
    url = f"sqlite+aiosqlite:///{path}"
    monkeypatch.setenv("DATABASE_URL", url)

    import db as _db

    # Force a clean slate even if a previous test left the engine cached.
    asyncio.run(_db.shutdown_db())
    importlib.reload(_db)
    yield _db
    asyncio.run(_db.shutdown_db())


def test_disabled_when_database_url_unset(monkeypatch: pytest.MonkeyPatch):
    """The module must stay completely dormant unless DATABASE_URL is set.

    No table creation, no implicit file on disk, every helper short-circuits
    to a sensible empty default. This is the contract the existing
    in-memory tests rely on.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import db as _db

    importlib.reload(_db)
    assert _db.is_enabled() is False

    async def go():
        await _db.init_db()  # no-op; should not raise
        await _db.upsert_farmer(wallet="x", lat=0, lon=0)
        assert await _db.list_farmers() == []
        assert await _db.get_evaluation("nope") is None
        inserted = await _db.record_disbursement(
            evaluation_id="e",
            wallet="x",
            signature="sig",
            amount_sol=1.0,
            is_mock=False,
            is_degraded=False,
            is_fallback_eval=False,
            failure_reason=None,
            explorer_url=None,
        )
        assert inserted is False
        stats = await _db.disbursement_stats()
        assert stats == {
            "total_disbursed_sol": 0.0,
            "live_tx_count": 0,
            "mock_tx_count": 0,
            "degraded_tx_count": 0,
            "fallback_eval_count": 0,
        }

    asyncio.run(go())


def test_farmer_upsert_round_trip(db_url):
    async def go():
        await db_url.init_db()
        await db_url.upsert_farmer(
            wallet="WAL1", lat=45.5, lon=59.0, status="pending", label="Aralkum"
        )
        rows = await db_url.list_farmers()
        assert len(rows) == 1
        assert rows[0].wallet == "WAL1"
        assert rows[0].label == "Aralkum"
        # second upsert: mutate status + add score
        await db_url.upsert_farmer(
            wallet="WAL1", lat=45.5, lon=59.0, status="approved", score=82
        )
        rows = await db_url.list_farmers()
        assert len(rows) == 1
        assert rows[0].status == "approved"
        assert rows[0].score == 82
        # original label preserved (we did not pass it again)
        assert rows[0].label == "Aralkum"

    asyncio.run(go())


def test_state_survives_engine_restart(db_url):
    """After ``shutdown_db`` + ``init_db`` the rows must reappear.

    This is the production-relevant guarantee: a Railway / fly.io redeploy
    no longer wipes the audit trail.
    """

    async def go():
        await db_url.init_db()
        await db_url.upsert_farmer(
            wallet="WAL_PERSIST", lat=1.0, lon=2.0, status="approved", score=99
        )
        await db_url.create_evaluation(
            evaluation_id="eval-1", wallet="WAL_PERSIST", lat=1.0, lon=2.0
        )
        await db_url.record_disbursement(
            evaluation_id="eval-1",
            wallet="WAL_PERSIST",
            signature="SIG_LIVE",
            amount_sol=1.5,
            is_mock=False,
            is_degraded=False,
            is_fallback_eval=False,
            failure_reason=None,
            explorer_url="https://explorer/sig",
        )

        # Full engine restart, same file:
        await db_url.shutdown_db()
        await db_url.init_db()

        rows = await db_url.list_farmers()
        assert [r.wallet for r in rows] == ["WAL_PERSIST"]
        assert rows[0].status == "approved"

        stats = await db_url.disbursement_stats()
        assert stats["total_disbursed_sol"] == pytest.approx(1.5)
        assert stats["live_tx_count"] == 1
        assert stats["mock_tx_count"] == 0

    asyncio.run(go())


def test_disbursement_unique_signature_blocks_double_credit(db_url):
    """The same signature must only credit ``total_disbursed_sol`` once.

    Real-world failure mode: agent restarts mid-pipeline, retries an
    evaluation that already settled on chain. Without this guard the
    public ledger would silently double.
    """

    async def go():
        await db_url.init_db()
        kwargs = dict(
            evaluation_id="eval-1",
            wallet="WAL_X",
            signature="SIG_ONCE",
            amount_sol=1.5,
            is_mock=False,
            is_degraded=False,
            is_fallback_eval=False,
            failure_reason=None,
            explorer_url=None,
        )
        first = await db_url.record_disbursement(**kwargs)
        second = await db_url.record_disbursement(**kwargs)
        assert first is True
        assert second is False
        stats = await db_url.disbursement_stats()
        assert stats["live_tx_count"] == 1
        assert stats["total_disbursed_sol"] == pytest.approx(1.5)

    asyncio.run(go())


def test_disbursement_stats_separate_live_mock_degraded(db_url):
    """Aggregated counters must match the PR #13 honesty contract.

    LIVE credits ``total_disbursed_sol``. MOCK and degraded-MOCK
    increment their own counters but never touch the public total.
    Fallback-evaluation flag is independent of the LIVE/MOCK split.
    """

    async def go():
        await db_url.init_db()
        rows = [
            dict(evaluation_id="e1", wallet="W1", signature="SIG_L1",
                 amount_sol=1.5, is_mock=False, is_degraded=False,
                 is_fallback_eval=False, failure_reason=None, explorer_url=None),
            dict(evaluation_id="e2", wallet="W2", signature="SIG_L2",
                 amount_sol=1.5, is_mock=False, is_degraded=False,
                 is_fallback_eval=True, failure_reason=None, explorer_url=None),
            dict(evaluation_id="e3", wallet="W3", signature="SIG_M1",
                 amount_sol=1.5, is_mock=True, is_degraded=False,
                 is_fallback_eval=False, failure_reason=None, explorer_url=None),
            dict(evaluation_id="e4", wallet="W4", signature="SIG_D1",
                 amount_sol=1.5, is_mock=True, is_degraded=True,
                 is_fallback_eval=False,
                 failure_reason="blockhash not found", explorer_url=None),
        ]
        for r in rows:
            assert await db_url.record_disbursement(**r) is True

        stats = await db_url.disbursement_stats()
        assert stats["total_disbursed_sol"] == pytest.approx(3.0)  # 2 × LIVE
        assert stats["live_tx_count"] == 2
        assert stats["mock_tx_count"] == 2
        assert stats["degraded_tx_count"] == 1
        assert stats["fallback_eval_count"] == 1

    asyncio.run(go())


def test_evaluation_update_persists_logs_and_result(db_url):
    """Evaluations table must round-trip the SSE log array and the verdict.

    Useful for replaying an evaluation after a redeploy (dashboard polls
    ``GET /api/evaluation/<id>`` to backfill the SSE log if the user opens
    the page mid-pipeline).
    """

    async def go():
        await db_url.init_db()
        await db_url.create_evaluation(
            evaluation_id="ev-100", wallet="W", lat=10.0, lon=20.0
        )
        await db_url.update_evaluation(
            evaluation_id="ev-100",
            status="done",
            logs=[{"step": "weather", "content": "fetched"}],
            result={"approved": True, "score": 75},
            completed=True,
        )
        row = await db_url.get_evaluation("ev-100")
        assert row is not None
        assert row.status == "done"
        assert row.logs == [{"step": "weather", "content": "fetched"}]
        assert row.result == {"approved": True, "score": 75}
        assert row.completed_at is not None

    asyncio.run(go())


def test_url_normalisation():
    """Operators should be able to set the canonical ``sqlite:///`` and
    ``postgresql://`` URLs without remembering the async driver suffix.
    """
    import db as _db

    assert _db._normalise_url("sqlite:///foo.db") == "sqlite+aiosqlite:///foo.db"
    assert (
        _db._normalise_url("postgresql://u:p@h/db")
        == "postgresql+asyncpg://u:p@h/db"
    )
    assert (
        _db._normalise_url("postgres://u:p@h/db")
        == "postgresql+asyncpg://u:p@h/db"
    )
    # Pre-async-driver URL stays untouched.
    assert (
        _db._normalise_url("postgresql+asyncpg://u:p@h/db")
        == "postgresql+asyncpg://u:p@h/db"
    )
    # Password redaction:
    assert (
        _db._safe_log_url("postgresql+asyncpg://user:secret@h/db")
        == "postgresql+asyncpg://user:***@h/db"
    )
