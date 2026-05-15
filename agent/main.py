import asyncio
import hashlib
import os
import re
import uuid
import json
import logging
from collections import OrderedDict
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from models import FarmerRegistration, AILogEntry, FarmerStatus
from weather_service import fetch_weather_data
from ndvi_service import fetch_historical_ndvi
from scoring_engine import calculate_composite_score
from ai_agent import stream_ai_evaluation, get_ai_verdict
from solana_bridge import release_subsidy, get_transaction_status, SUBSIDY_AMOUNT_SOL
import db as durable_storage
import monitoring

logger = logging.getLogger(__name__)

# Base58 alphabet used by Solana
_B58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def _is_valid_solana_address(addr: str) -> bool:
    return bool(_B58_RE.match(addr))


# ─── Capacity Limits ─────────────────────────────────────────────────────────────
MAX_FARMERS = int(os.getenv("MAX_FARMERS", "10000"))
MAX_EVALUATIONS = int(os.getenv("MAX_EVALUATIONS", "50000"))
MAX_CONCURRENT_SSE = int(os.getenv("MAX_CONCURRENT_SSE", "200"))
_active_sse_connections = 0


# ─── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AgriSubsidy AI Oracle",
    description="AI-powered agricultural subsidy decision system on Solana",
    version="0.1.0",
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "").lower() in ("1", "true") else None,
    redoc_url=None,
    openapi_url=(
        "/openapi.json"
        if os.getenv("ENABLE_DOCS", "").lower() in ("1", "true")
        else None
    ),
)


@app.on_event("startup")
async def _startup_monitoring():
    """Initialise Sentry SDK when SENTRY_DSN is set; otherwise a no-op.

    Mirrors the durable-storage / RPC-fallback opt-in pattern: code lands
    once, the host activates by exporting the env var. With Sentry off the
    only cost is one function call at boot. Discord notifier needs no init
    — it is checked at emission time.
    """
    monitoring.init_sentry()


@app.on_event("startup")
async def _startup_durable_storage():
    """Initialise the durable-storage backend and rehydrate in-memory caches.

    No-op when ``DATABASE_URL`` is unset — the agent then keeps using the
    purely in-memory state it has always used (suitable for tests and quick
    local smoke runs). When the env var is set, this creates tables on first
    boot, then walks every persisted farmer row into ``farmers_db`` so the
    dashboard reflects the persisted state immediately after a redeploy.
    """
    if not durable_storage.is_enabled():
        return
    await durable_storage.init_db()
    async for row in durable_storage.hydrate_farmers_from_db():
        farmers_db[row.wallet] = FarmerStatus(
            wallet=row.wallet,
            lat=row.lat,
            lon=row.lon,
            status=row.status,
            score=row.score,
            tx_signature=row.tx_signature,
            label=row.label,
        )
    logger.info(
        "Durable storage initialised, hydrated %d farmer(s) from DB",
        len(farmers_db),
    )


@app.on_event("shutdown")
async def _shutdown_durable_storage():
    await durable_storage.shutdown_db()

# Explicit origins (exact match) — local dev + the canonical Vercel deploy.
# Override via CORS_ORIGINS for additional domains (custom hostnames, staging).
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173,"
    "http://127.0.0.1:5173,"
    "https://agri-subsidy.vercel.app"
)
_allowed_origins = [
    o.strip() for o in os.getenv("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",") if o.strip()
]

# Vercel preview deploys use rotating subdomains (`agri-subsidy-git-*.vercel.app`),
# so we also match them via regex. Ops can override with CORS_ORIGIN_REGEX.
_allowed_origin_regex = os.getenv(
    "CORS_ORIGIN_REGEX",
    r"https://agri-subsidy(-[a-z0-9-]+)?\.vercel\.app",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=_allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
)


# ─── In-Memory State (MVP) ───────────────────────────────────────────────────────
# В продакшне заменить на PostgreSQL/Redis
farmers_db: Dict[str, FarmerStatus] = {}


class _LRUEvalDB(OrderedDict):
    """Bounded dict that only evicts completed evaluations when full."""

    def __init__(self, maxsize: int = MAX_EVALUATIONS):
        super().__init__()
        self._maxsize = maxsize

    def try_make_room(self) -> bool:
        """Evict oldest *completed* evaluations until under capacity.

        Returns True if room is available, False if all slots hold
        in-flight evaluations (safe to reject with 429).
        """
        while len(self) >= self._maxsize:
            evicted = False
            for key in list(self):
                entry = self[key]
                if isinstance(entry, dict) and entry.get("status") in ("done", "error"):
                    del self[key]
                    evicted = True
                    break
            if not evicted:
                return False
        return True


evaluations_db: _LRUEvalDB = _LRUEvalDB()  # evaluation_id -> {logs, result, ...}
# total_disbursed_sol counts SOL that actually settled on-chain (LIVE TX only).
# MOCK / degraded-MOCK signatures do not credit this counter — they would create
# a silent ledger drift where the API reports payouts that never happened.
total_disbursed_sol: float = 0.0
# Trust counters surfaced via /api/stats so operators / external monitors can
# detect a regression like PR #9 (everything looks green in the UI but every
# TX is actually MOCK).
live_tx_count: int = 0
mock_tx_count: int = 0
degraded_tx_count: int = 0  # subset of mock_tx_count where PROGRAM_ID was set but LIVE failed
fallback_eval_count: int = 0  # evaluations that ran in AI fallback mode
_eval_lock = asyncio.Lock()

# Idempotency: dedupe identical evaluation requests within a short window.
# Maps fingerprint -> (evaluation_id, expires_at). Cleaned lazily on lookup.
IDEMPOTENCY_WINDOW_SECONDS = int(os.getenv("IDEMPOTENCY_WINDOW_SECONDS", "60"))
_idempotency_cache: Dict[str, Tuple[str, datetime]] = {}


def _evaluation_fingerprint(
    wallet: str, lat: float, lon: float, idempotency_key: Optional[str] = None
) -> str:
    """Stable hash of the evaluation request for dedupe purposes.

    If the client supplies an explicit Idempotency-Key, we honour it as-is.
    Otherwise we hash (wallet, rounded coords) so reload-spamming the same
    farmer card does not start parallel pipelines.
    """
    if idempotency_key:
        return f"key:{idempotency_key.strip()}"
    payload = f"{wallet}|{round(lat, 4)}|{round(lon, 4)}".encode()
    return "req:" + hashlib.sha256(payload).hexdigest()[:16]


def _idempotency_lookup(fingerprint: str) -> Optional[str]:
    """Return a cached evaluation_id for this fingerprint, or None."""
    now = datetime.utcnow()
    expired = [k for k, (_, exp) in _idempotency_cache.items() if exp <= now]
    for k in expired:
        _idempotency_cache.pop(k, None)
    entry = _idempotency_cache.get(fingerprint)
    if entry is None:
        return None
    eval_id, _ = entry
    if eval_id not in evaluations_db:
        _idempotency_cache.pop(fingerprint, None)
        return None
    return eval_id


def _idempotency_record(fingerprint: str, evaluation_id: str) -> None:
    """Cache an evaluation_id for the configured window."""
    expires = datetime.utcnow() + timedelta(seconds=IDEMPOTENCY_WINDOW_SECONDS)
    _idempotency_cache[fingerprint] = (evaluation_id, expires)


# ─── Pydantic Schemas ────────────────────────────────────────────────────────────
class EvaluateRequest(BaseModel):
    wallet_address: str
    lat: float
    lon: float

    @field_validator("wallet_address")
    @classmethod
    def validate_wallet(cls, v: str) -> str:
        v = v.strip()
        if not _is_valid_solana_address(v):
            raise ValueError("Invalid Solana wallet address")
        return v

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("lon")
    @classmethod
    def validate_lon(cls, v: float) -> float:
        if not -180 <= v <= 180:
            raise ValueError("Longitude must be between -180 and 180")
        return v


class EvaluateResponse(BaseModel):
    evaluation_id: str
    message: str


class StatsResponse(BaseModel):
    total: int
    approved: int
    rejected: int
    pending: int
    total_disbursed_sol: float
    # Trust signals: a healthy production deploy has live_tx_count > 0 and
    # degraded_tx_count == 0. Any climb in degraded_tx_count or in
    # fallback_eval_count means the system is silently downgrading and the
    # operator should investigate before pitching against the dashboard.
    live_tx_count: int = 0
    mock_tx_count: int = 0
    degraded_tx_count: int = 0
    fallback_eval_count: int = 0


# ─── Demo Seed Data ──────────────────────────────────────────────────────────────
# The first five farmers cover Kazakh agricultural regions and produce a
# realistic mix of approved/rejected outcomes depending on the evaluation
# month and live weather. The last two are picked from the simulator's
# arid-biome bounding boxes — they trigger severe_drought year-round so
# pitch demos always have a guaranteed-approve path to walk through.
DEMO_FARMERS = [
    {
        "wallet": "4pMnsypmRtd94bK94LXjFPWghpXN5WfCcLvnJhoUdX5z",
        "lat": 53.2,
        "lon": 63.6,
        "label": "Kostanay Region (KZ)",
    },
    {
        "wallet": "EeqwDr7kNxp4y9vj4MaQijv4BmgAm3WXArzZM5WikD6U",
        "lat": 54.9,
        "lon": 69.1,
        "label": "North Kazakhstan Region (KZ)",
    },
    {
        "wallet": "CHaGvsfMx5YKE3mYq7huQM6keRN2UUsfhwAZMypWw7KC",
        "lat": 51.1,
        "lon": 71.4,
        "label": "Akmola Region (KZ)",
    },
    {
        "wallet": "FZA62o7rNFBmx5g1hFyCmpRYWhpxAHTiqnYUaRd7EGfL",
        "lat": 50.3,
        "lon": 57.2,
        "label": "Aktobe Region (KZ)",
    },
    {
        "wallet": "8jm7bVG8CiqxDmohHUuMk5R3WZkucTrXPUDsDhzvLQ3p",
        "lat": 43.8,
        "lon": 77.1,
        "label": "Almaty Region (KZ)",
    },
    # ── Drought-scenario seed farmers (always severe_drought + approved) ──
    {
        "wallet": "6zMppjRuXGdUqe9LU51wvCo8ZgbKEAbJv4ke85rY8LD8",
        "lat": 45.5,
        "lon": 59.0,
        "label": "Aralkum / former Aral Sea (KZ side) — drought scenario",
    },
    {
        "wallet": "7V9GTiEGej451eo11fpYPR4xe5BDE6QDBNGjyRwCt76W",
        "lat": 39.5,
        "lon": 60.0,
        "label": "Karakum desert (TM) — drought scenario",
    },
]


# ─── Endpoints ────────────────────────────────────────────────────────────────────


@app.post("/api/demo/seed", summary="Засеять демо-данными")
async def seed_demo_data():
    """Инициализирует демо-фермеров для презентаций (включает гарантированно severe_drought сценарии)."""
    if os.getenv("DISABLE_DEMO", "").lower() in ("1", "true"):
        raise HTTPException(status_code=403, detail="Demo endpoints disabled in production")
    for f in DEMO_FARMERS:
        farmers_db[f["wallet"]] = FarmerStatus(
            wallet=f["wallet"],
            lat=f["lat"],
            lon=f["lon"],
            status="pending",
            label=f.get("label"),
        )
        await durable_storage.upsert_farmer(
            wallet=f["wallet"],
            lat=f["lat"],
            lon=f["lon"],
            status="pending",
            label=f.get("label"),
        )
    return {
        "message": f"Загружено {len(DEMO_FARMERS)} демо-фермеров",
        "count": len(farmers_db),
    }


@app.get("/api/farmers", response_model=list[FarmerStatus], summary="Список фермеров")
async def get_farmers():
    """Возвращает всех зарегистрированных фермеров со статусами."""
    return list(farmers_db.values())


@app.post(
    "/api/farmers/register", response_model=FarmerStatus, summary="Регистрация фермера"
)
async def register_farmer(data: FarmerRegistration):
    """Регистрирует нового фермера (или обновляет существующего)."""
    if len(farmers_db) >= MAX_FARMERS and data.wallet_address not in farmers_db:
        raise HTTPException(status_code=429, detail="Farmer limit reached")
    farmer = FarmerStatus(
        wallet=data.wallet_address,
        lat=data.region_lat,
        lon=data.region_lon,
        status="pending",
    )
    farmers_db[data.wallet_address] = farmer
    await durable_storage.upsert_farmer(
        wallet=data.wallet_address,
        lat=data.region_lat,
        lon=data.region_lon,
        status="pending",
    )
    return farmer


@app.post("/api/evaluate", response_model=EvaluateResponse, summary="Запустить оценку")
async def start_evaluation(req: EvaluateRequest, request: Request):
    """Kick off an asynchronous evaluation pipeline for a farmer.

    Returns an `evaluation_id` that the client uses to subscribe to the SSE
    stream. Requests are deduplicated within `IDEMPOTENCY_WINDOW_SECONDS`
    against either an explicit `Idempotency-Key` header or the
    `(wallet, rounded coords)` tuple, so quick double-clicks don't spawn
    parallel pipelines.
    """
    idempotency_key = request.headers.get("Idempotency-Key")
    fingerprint = _evaluation_fingerprint(
        req.wallet_address, req.lat, req.lon, idempotency_key
    )
    cached = _idempotency_lookup(fingerprint)
    if cached is not None:
        return EvaluateResponse(
            evaluation_id=cached,
            message="Идемпотентность: возвращаю ранее запущенный evaluation_id.",
        )

    if not evaluations_db.try_make_room():
        raise HTTPException(status_code=429, detail="Evaluation capacity reached, try later")

    evaluation_id = str(uuid.uuid4())

    if req.wallet_address not in farmers_db:
        if len(farmers_db) >= MAX_FARMERS:
            raise HTTPException(status_code=429, detail="Farmer limit reached")
        farmers_db[req.wallet_address] = FarmerStatus(
            wallet=req.wallet_address,
            lat=req.lat,
            lon=req.lon,
            status="pending",
        )
        await durable_storage.upsert_farmer(
            wallet=req.wallet_address,
            lat=req.lat,
            lon=req.lon,
            status="pending",
        )

    evaluations_db[evaluation_id] = {
        "wallet": req.wallet_address,
        "lat": req.lat,
        "lon": req.lon,
        "status": "running",
        "logs": [],
        "result": None,
        "started_at": datetime.utcnow().isoformat(),
    }
    await durable_storage.create_evaluation(
        evaluation_id=evaluation_id,
        wallet=req.wallet_address,
        lat=req.lat,
        lon=req.lon,
    )

    _idempotency_record(fingerprint, evaluation_id)

    asyncio.create_task(
        run_evaluation_pipeline(evaluation_id, req.wallet_address, req.lat, req.lon)
    )

    return EvaluateResponse(
        evaluation_id=evaluation_id,
        message="Оценка запущена. Подключитесь к /api/stream/{evaluation_id} для лога.",
    )


@app.get("/api/stream/{evaluation_id}", summary="SSE поток мыслей ИИ")
async def stream_evaluation(evaluation_id: str):
    """
    Server-Sent Events endpoint.
    Стримит пошаговые рассуждения ИИ в реальном времени.
    """
    global _active_sse_connections
    if evaluation_id not in evaluations_db:
        raise HTTPException(status_code=404, detail="Evaluation не найден")
    if _active_sse_connections >= MAX_CONCURRENT_SSE:
        raise HTTPException(status_code=429, detail="Too many SSE connections")

    async def event_generator():
        global _active_sse_connections
        _active_sse_connections += 1
        try:
            sent_count = 0
            max_wait = 120
            elapsed = 0

            while elapsed < max_wait:
                eval_data = evaluations_db.get(evaluation_id, {})
                logs = eval_data.get("logs", [])

                while sent_count < len(logs):
                    entry = logs[sent_count]
                    data = json.dumps(entry, ensure_ascii=False)
                    yield f"data: {data}\n\n"
                    sent_count += 1

                if eval_data.get("status") == "done":
                    result = eval_data.get("result", {})
                    yield f"event: done\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
                    break

                if eval_data.get("status") == "error":
                    yield f"event: error\ndata: {json.dumps({'error': 'Evaluation failed'})}\n\n"
                    break

                await asyncio.sleep(0.3)
                elapsed += 0.3
        finally:
            _active_sse_connections -= 1

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/stats", response_model=StatsResponse, summary="Статистика")
async def get_stats():
    """Агрегированная статистика по всем оценкам.

    When durable storage is enabled, the disbursement-derived counters are
    sourced from the SQL ``disbursements`` ledger so they survive restarts.
    Otherwise we fall back to the in-process counters that the agent has
    always maintained.
    """
    global total_disbursed_sol
    all_farmers = list(farmers_db.values())
    approved = sum(1 for f in all_farmers if f.status == "approved")
    rejected = sum(1 for f in all_farmers if f.status == "rejected")
    pending = sum(1 for f in all_farmers if f.status == "pending")

    if durable_storage.is_enabled():
        stats = await durable_storage.disbursement_stats()
        return StatsResponse(
            total=len(all_farmers),
            approved=approved,
            rejected=rejected,
            pending=pending,
            total_disbursed_sol=round(stats["total_disbursed_sol"], 3),
            live_tx_count=stats["live_tx_count"],
            mock_tx_count=stats["mock_tx_count"],
            degraded_tx_count=stats["degraded_tx_count"],
            fallback_eval_count=stats["fallback_eval_count"],
        )

    return StatsResponse(
        total=len(all_farmers),
        approved=approved,
        rejected=rejected,
        pending=pending,
        total_disbursed_sol=round(total_disbursed_sol, 3),
        live_tx_count=live_tx_count,
        mock_tx_count=mock_tx_count,
        degraded_tx_count=degraded_tx_count,
        fallback_eval_count=fallback_eval_count,
    )


_TX_SIG_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{64,88}$")


@app.get("/api/tx/{signature}", summary="Статус транзакции")
async def check_tx_status(signature: str):
    """Проверяет статус Solana транзакции на Devnet."""
    if not _TX_SIG_RE.match(signature):
        raise HTTPException(status_code=400, detail="Invalid transaction signature")
    return await get_transaction_status(signature)


@app.get("/api/evaluation/{evaluation_id}", summary="Результат оценки")
async def get_evaluation_result(evaluation_id: str):
    """Возвращает полный результат завершённой оценки."""
    if evaluation_id not in evaluations_db:
        raise HTTPException(status_code=404, detail="Evaluation не найден")
    data = evaluations_db[evaluation_id]
    safe = {
        k: v for k, v in data.items()
        if k not in ("traceback",)
    }
    return safe


@app.get("/health", summary="Health check")
async def health():
    return {"status": "ok", "farmers_count": len(farmers_db)}


# ─── Background Pipeline ──────────────────────────────────────────────────────────


async def run_evaluation_pipeline(
    evaluation_id: str,
    wallet: str,
    lat: float,
    lon: float,
):
    """
    Полный цикл оценки:
    1. Получение погодных данных
    2. Получение NDVI данных
    3. Расчёт composite score
    4. Стриминг AI-рассуждений
    5. Обновление статуса фермера
    """
    global total_disbursed_sol, live_tx_count, mock_tx_count
    global degraded_tx_count, fallback_eval_count

    eval_data = evaluations_db[evaluation_id]

    def log(step: str, content: str):
        """Добавляет запись в лог оценки."""
        eval_data["logs"].append({"step": step, "content": content})

    try:
        # Шаг 1: Погода
        log(
            "🌍 Запрос данных",
            f"Запрашиваю актуальную погоду для координат {lat}, {lon}...",
        )
        weather = await fetch_weather_data(lat, lon)

        if "error" in weather:
            log(
                "⚠️ Погода",
                f"Ошибка API: {weather['error']}. Использую резервные данные.",
            )
            weather = {
                "temperature": 25,
                "humidity": 45,
                "description": "no data",
                "rain_1h": 0,
            }
        else:
            log(
                "🌤️ Погода получена",
                f"T={weather['temperature']}°C, влажность={weather['humidity']}%, "
                f"описание: {weather['description']}, осадки: {weather.get('rain_1h', 0)} мм/ч",
            )

        await asyncio.sleep(0.5)

        # Шаг 2: NDVI
        log("🛰️ Запрос NDVI", "Получаю спутниковые данные NDVI...")
        ndvi = await fetch_historical_ndvi(lat, lon)

        log(
            "🌿 NDVI получен",
            f"Текущий NDVI: {ndvi['current_ndvi']}, историческая норма: {ndvi['historical_avg']}, "
            f"статус: {ndvi['alert']}",
        )

        await asyncio.sleep(0.3)

        # Шаг 3: Scoring
        log("⚙️ Расчёт скора", "Запускаю алгоритм composite scoring...")
        scores = calculate_composite_score(weather, ndvi)
        log(
            "📊 Composite Score",
            f"weather_score={scores['weather_score']}, ndvi_score={scores['ndvi_score']}, "
            f"composite={scores['composite_score']}/100 | Алгоритм: {'ОДОБРИТЬ' if scores['approved'] else 'ОТКЛОНИТЬ'}",
        )

        await asyncio.sleep(0.3)

        # Шаг 4: AI Agent
        log("🤖 AI Агент", "Передаю данные OpenAI для финального анализа...")

        farmer_data = {"wallet": wallet, "lat": lat, "lon": lon}
        ai_logs: list[AILogEntry] = []

        async for entry in stream_ai_evaluation(farmer_data, weather, ndvi, scores):
            log(entry.step, entry.content)
            ai_logs.append(entry)
            await asyncio.sleep(0.05)  # Небольшая задержка для плавного стриминга

        # Шаг 5: Финальный вердикт
        result = await get_ai_verdict(farmer_data, weather, ndvi, scores, ai_logs)

        # Обновляем статус фермера
        if wallet in farmers_db:
            farmers_db[wallet].status = "approved" if result.approved else "rejected"
            farmers_db[wallet].score = result.score
            await durable_storage.upsert_farmer(
                wallet=wallet,
                lat=farmers_db[wallet].lat,
                lon=farmers_db[wallet].lon,
                status=farmers_db[wallet].status,
                score=farmers_db[wallet].score,
                label=farmers_db[wallet].label,
            )

        # Шаг 6: Solana Bridge — отправляем субсидию если одобрено
        result_dict = result.model_dump()
        if result.approved:
            log(
                "⛓️ Solana Bridge",
                f"Отправляю субсидию {SUBSIDY_AMOUNT_SOL} SOL → {wallet[:16]}...",
            )
            bridge_result = await release_subsidy(
                farmer_pubkey=wallet,
                ai_score=result.score,
                amount_sol=SUBSIDY_AMOUNT_SOL,
            )

            if wallet in farmers_db:
                farmers_db[wallet].tx_signature = bridge_result.signature
                await durable_storage.upsert_farmer(
                    wallet=wallet,
                    lat=farmers_db[wallet].lat,
                    lon=farmers_db[wallet].lon,
                    status=farmers_db[wallet].status,
                    score=farmers_db[wallet].score,
                    tx_signature=bridge_result.signature,
                    label=farmers_db[wallet].label,
                )

            inserted = await durable_storage.record_disbursement(
                evaluation_id=evaluation_id,
                wallet=wallet,
                signature=bridge_result.signature,
                amount_sol=bridge_result.amount_sol,
                is_mock=bridge_result.is_mock,
                is_degraded=bridge_result.is_degraded,
                is_fallback_eval=bool(result.is_fallback),
                failure_reason=bridge_result.failure_reason,
                explorer_url=bridge_result.explorer_url,
            )
            # When durable storage is enabled and the row was already present
            # (a retry that re-uses the same signature), skip the in-memory
            # counter bump so the LIVE total cannot drift on duplicate writes.
            should_count = (not durable_storage.is_enabled()) or inserted

            async with _eval_lock:
                if bridge_result.is_mock:
                    if should_count:
                        mock_tx_count += 1
                        if bridge_result.is_degraded:
                            degraded_tx_count += 1
                else:
                    # Only credit on-chain settled SOL to the disbursed total.
                    # MOCK / degraded MOCK never moved real lamports and must
                    # not climb the public ledger.
                    if should_count:
                        total_disbursed_sol += bridge_result.amount_sol
                        live_tx_count += 1
                if result.is_fallback and should_count:
                    fallback_eval_count += 1

            if bridge_result.is_degraded:
                # Fire-and-forget Discord alert. No-op when
                # DISCORD_WEBHOOK_URL is unset; never blocks the SSE stream
                # or the verdict response. PR #9 honesty contract is
                # preserved — the result dict already carries is_degraded /
                # failure_reason regardless of whether the alert lands.
                monitoring.fire_and_forget(
                    monitoring.notify_degraded_mock(
                        wallet=wallet,
                        signature=bridge_result.signature,
                        failure_reason=bridge_result.failure_reason,
                        amount_sol=bridge_result.amount_sol,
                        evaluation_id=evaluation_id,
                    )
                )

            if bridge_result.is_degraded:
                mode_label = "[DEGRADED_MOCK]"
            elif bridge_result.is_mock:
                mode_label = "[MOCK]"
            else:
                mode_label = "[LIVE]"
            log(
                "✅ TX Confirmed" if not bridge_result.is_mock else "⚠️ TX Simulated",
                f"{mode_label} TX: {bridge_result.signature[:20]}... | "
                f"{bridge_result.amount_sol} SOL disbursed | "
                f"Explorer: {bridge_result.explorer_url}"
                + (
                    f" | reason={bridge_result.failure_reason}"
                    if bridge_result.failure_reason
                    else ""
                ),
            )

            # Surface the bridge state on the verdict payload so the dashboard
            # can render distinct chips for LIVE / MOCK / DEGRADED_MOCK instead
            # of treating every TX as a green success.
            result_dict["tx"] = {
                "signature": bridge_result.signature,
                "explorer_url": bridge_result.explorer_url,
                "amount_sol": bridge_result.amount_sol,
                "is_mock": bridge_result.is_mock,
                "is_degraded": bridge_result.is_degraded,
                "failure_reason": bridge_result.failure_reason,
            }
        else:
            log("❌ TX Skipped", "Субсидия не одобрена — транзакция не отправлена.")
            if result.is_fallback:
                async with _eval_lock:
                    fallback_eval_count += 1

        eval_data["result"] = result_dict
        eval_data["status"] = "done"
        eval_data["completed_at"] = datetime.utcnow().isoformat()

        await durable_storage.update_evaluation(
            evaluation_id=evaluation_id,
            status="done",
            logs=eval_data["logs"],
            result=result_dict,
            completed=True,
        )

    except Exception as e:

        logger.error("Evaluation %s failed: %s", evaluation_id, e, exc_info=True)
        # Sentry will capture e automatically via the FastAPI integration
        # (init'd in _startup_monitoring). Discord gets a fire-and-forget
        # alert so the operator channel surfaces unhandled exceptions even
        # without opening Sentry. Both are no-op when the env vars are unset.
        monitoring.fire_and_forget(
            monitoring.notify_critical(where=evaluation_id, error=e)
        )
        eval_data["status"] = "error"
        eval_data["error"] = "Internal evaluation error"
        if wallet in farmers_db:
            farmers_db[wallet].status = "pending"
        await durable_storage.update_evaluation(
            evaluation_id=evaluation_id,
            status="error",
            error="Internal evaluation error",
            completed=True,
        )
