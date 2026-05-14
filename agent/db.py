"""Durable storage layer for the Dala Network drought-oracle agent.

The previous build kept farmers, evaluations, and the disbursement ledger in
process memory: every Railway / fly.io redeploy wiped the audit trail. That's
investor-due-diligence-blocking for a parametric-payouts product.

This module introduces an SQLAlchemy 2.0 async backend that survives restarts.
It is intentionally opt-in via the ``DATABASE_URL`` environment variable so
the legacy in-memory mode keeps working for unit tests and quick smoke runs:

- ``DATABASE_URL`` unset            → durable storage disabled, agent falls
                                      back to the in-memory ``main.farmers_db``
                                      and ``main.evaluations_db`` it has
                                      always used.
- ``DATABASE_URL`` set              → durable storage enabled. SQLite is the
                                      default driver (``sqlite+aiosqlite://``)
                                      so no external infra is required to ship
                                      the feature; the same code path swaps to
                                      ``postgresql+asyncpg://`` for a hosted
                                      Postgres (Supabase, fly.io, Railway).

Schema
~~~~~~
``farmers``
    One row per Solana wallet that we have ever registered. Holds the latest
    status / score / tx_signature snapshot displayed in the dashboard.

``evaluations``
    One row per ``/api/evaluate`` request. Stores the SSE log array (JSON) and
    the final verdict so a session can be resumed or replayed after a restart.

``disbursements``
    Append-only audit ledger. One row per real bridge call (LIVE *or* MOCK)
    with a UNIQUE constraint on ``signature`` to make double-credit impossible
    under retries. Aggregated reads here power
    ``GET /api/stats.total_disbursed_sol`` (LIVE only).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import AsyncIterator, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
    select,
    func,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class FarmerRow(Base):
    __tablename__ = "farmers"

    wallet: Mapped[str] = mapped_column(String(64), primary_key=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tx_signature: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class EvaluationRow(Base):
    __tablename__ = "evaluations"

    evaluation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    wallet: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    logs: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class DisbursementRow(Base):
    """Append-only audit ledger of every bridge call (LIVE or MOCK).

    A row is written *after* ``release_subsidy`` returns, regardless of
    whether the TX was real or simulated. Aggregations against this table
    (``SUM(amount_sol) WHERE is_mock=False``) power the public
    ``total_disbursed_sol`` counter so the figure can no longer drift on a
    restart and so duplicate retries cannot inflate it.
    """

    __tablename__ = "disbursements"
    __table_args__ = (UniqueConstraint("signature", name="uq_disbursements_signature"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    wallet: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    amount_sol: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_degraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_fallback_eval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    explorer_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )


# ─── Engine / Session ────────────────────────────────────────────────────────


_engine = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _normalise_url(url: str) -> str:
    """Allow operators to set ``DATABASE_URL=sqlite:///foo.db`` (no driver) and
    rewrite it to ``sqlite+aiosqlite:///foo.db`` so async engines work."""
    if url.startswith("sqlite:///"):
        return "sqlite+aiosqlite:///" + url[len("sqlite:///") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        # Heroku-style alias.
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


def is_enabled() -> bool:
    """True iff ``DATABASE_URL`` is set; gates all DB writes."""
    return bool(os.getenv("DATABASE_URL", "").strip())


async def init_db() -> None:
    """Initialise the async engine and create tables if needed.

    Safe to call multiple times; the engine is cached at module scope.
    Called on FastAPI startup; tests can also call it explicitly with
    ``DATABASE_URL`` pointing at a temporary file.
    """
    global _engine, _session_factory
    if not is_enabled():
        logger.info("DATABASE_URL not set, durable storage stays disabled")
        return
    if _engine is not None:
        return

    url = _normalise_url(os.environ["DATABASE_URL"].strip())
    logger.info("Initialising durable storage engine (%s)", _safe_log_url(url))
    _engine = create_async_engine(url, future=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def shutdown_db() -> None:
    """Dispose of the engine. Called on FastAPI shutdown / between tests."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def _safe_log_url(url: str) -> str:
    """Strip the password out of a URL before logging."""
    if "@" not in url:
        return url
    scheme_split = url.split("://", 1)
    if len(scheme_split) != 2:
        return url
    scheme, rest = scheme_split
    creds, host = rest.split("@", 1)
    if ":" in creds:
        user = creds.split(":", 1)[0]
        creds = f"{user}:***"
    return f"{scheme}://{creds}@{host}"


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError(
            "durable storage is not initialised; call init_db() first or "
            "guard the call site with db.is_enabled()"
        )
    return _session_factory


# ─── Repository helpers ──────────────────────────────────────────────────────


async def upsert_farmer(
    *,
    wallet: str,
    lat: float,
    lon: float,
    status: str = "pending",
    score: Optional[int] = None,
    tx_signature: Optional[str] = None,
    label: Optional[str] = None,
) -> None:
    if not is_enabled():
        return
    async with session_factory()() as session:
        row = await session.get(FarmerRow, wallet)
        if row is None:
            row = FarmerRow(
                wallet=wallet,
                lat=lat,
                lon=lon,
                status=status,
                score=score,
                tx_signature=tx_signature,
                label=label,
            )
            session.add(row)
        else:
            row.lat = lat
            row.lon = lon
            row.status = status
            if score is not None:
                row.score = score
            if tx_signature is not None:
                row.tx_signature = tx_signature
            if label is not None:
                row.label = label
        await session.commit()


async def list_farmers() -> list[FarmerRow]:
    if not is_enabled():
        return []
    async with session_factory()() as session:
        result = await session.execute(select(FarmerRow).order_by(FarmerRow.created_at))
        return list(result.scalars().all())


async def create_evaluation(
    *,
    evaluation_id: str,
    wallet: str,
    lat: float,
    lon: float,
) -> None:
    if not is_enabled():
        return
    async with session_factory()() as session:
        row = EvaluationRow(
            evaluation_id=evaluation_id,
            wallet=wallet,
            lat=lat,
            lon=lon,
            status="running",
            logs=[],
        )
        session.add(row)
        await session.commit()


async def update_evaluation(
    *,
    evaluation_id: str,
    status: Optional[str] = None,
    logs: Optional[list] = None,
    result: Optional[dict] = None,
    error: Optional[str] = None,
    completed: bool = False,
) -> None:
    if not is_enabled():
        return
    async with session_factory()() as session:
        row = await session.get(EvaluationRow, evaluation_id)
        if row is None:
            return
        if status is not None:
            row.status = status
        if logs is not None:
            row.logs = list(logs)
        if result is not None:
            row.result = result
        if error is not None:
            row.error = error
        if completed:
            row.completed_at = datetime.utcnow()
        await session.commit()


async def get_evaluation(evaluation_id: str) -> Optional[EvaluationRow]:
    if not is_enabled():
        return None
    async with session_factory()() as session:
        return await session.get(EvaluationRow, evaluation_id)


async def record_disbursement(
    *,
    evaluation_id: str,
    wallet: str,
    signature: str,
    amount_sol: float,
    is_mock: bool,
    is_degraded: bool,
    is_fallback_eval: bool,
    failure_reason: Optional[str],
    explorer_url: Optional[str],
) -> bool:
    """Insert one disbursement row.

    Returns True if a new row was inserted, False if the signature already
    existed (idempotency under retries: e.g. an evaluator restart that
    re-emits a previously confirmed signature must not double-credit
    ``total_disbursed_sol``).
    """
    if not is_enabled():
        return False
    async with session_factory()() as session:
        existing = await session.execute(
            select(DisbursementRow).where(DisbursementRow.signature == signature)
        )
        if existing.scalar_one_or_none() is not None:
            return False
        row = DisbursementRow(
            evaluation_id=evaluation_id,
            wallet=wallet,
            signature=signature,
            amount_sol=amount_sol,
            is_mock=is_mock,
            is_degraded=is_degraded,
            is_fallback_eval=is_fallback_eval,
            failure_reason=failure_reason,
            explorer_url=explorer_url,
        )
        session.add(row)
        try:
            await session.commit()
            return True
        except Exception:
            await session.rollback()
            # Concurrent insert won the UNIQUE race — caller treats this
            # exactly like a hit on the dedupe path above.
            return False


async def disbursement_stats() -> dict:
    """Aggregated counters used by ``/api/stats``.

    Returns a dict with ``total_disbursed_sol`` (LIVE only),
    ``live_tx_count``, ``mock_tx_count``, ``degraded_tx_count``,
    ``fallback_eval_count``. Values are 0/0.0 when the table is empty so
    callers don't need to special-case the empty deploy.
    """
    if not is_enabled():
        return {
            "total_disbursed_sol": 0.0,
            "live_tx_count": 0,
            "mock_tx_count": 0,
            "degraded_tx_count": 0,
            "fallback_eval_count": 0,
        }
    async with session_factory()() as session:
        total = await session.execute(
            select(func.coalesce(func.sum(DisbursementRow.amount_sol), 0.0)).where(
                DisbursementRow.is_mock.is_(False)
            )
        )
        live = await session.execute(
            select(func.count()).select_from(DisbursementRow).where(
                DisbursementRow.is_mock.is_(False)
            )
        )
        mock = await session.execute(
            select(func.count()).select_from(DisbursementRow).where(
                DisbursementRow.is_mock.is_(True)
            )
        )
        degraded = await session.execute(
            select(func.count()).select_from(DisbursementRow).where(
                DisbursementRow.is_degraded.is_(True)
            )
        )
        fallback = await session.execute(
            select(func.count()).select_from(DisbursementRow).where(
                DisbursementRow.is_fallback_eval.is_(True)
            )
        )
        return {
            "total_disbursed_sol": float(total.scalar_one() or 0.0),
            "live_tx_count": int(live.scalar_one() or 0),
            "mock_tx_count": int(mock.scalar_one() or 0),
            "degraded_tx_count": int(degraded.scalar_one() or 0),
            "fallback_eval_count": int(fallback.scalar_one() or 0),
        }


async def hydrate_farmers_from_db() -> AsyncIterator[FarmerRow]:
    """Yield every persisted farmer row.

    The agent uses this on startup to rehydrate the in-memory
    ``farmers_db`` cache that SSE handlers read from, so the dashboard
    immediately reflects the persisted state instead of looking like a
    fresh deploy.
    """
    if not is_enabled():
        return
    async with session_factory()() as session:
        result = await session.execute(select(FarmerRow))
        for row in result.scalars().all():
            yield row
