import asyncio
import os
import re
import uuid
import json
import logging
from collections import OrderedDict
from typing import Dict
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from models import FarmerRegistration, EvaluationResult, AILogEntry, FarmerStatus
from weather_service import fetch_weather_data
from ndvi_service import fetch_historical_ndvi
from scoring_engine import calculate_composite_score
from ai_agent import stream_ai_evaluation, get_ai_verdict
from solana_bridge import release_subsidy, get_transaction_status, SUBSIDY_AMOUNT_SOL

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

_allowed_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
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
total_disbursed_sol: float = 0.0  # Накопительная сумма выплат
_eval_lock = asyncio.Lock()


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


# ─── Demo Seed Data ──────────────────────────────────────────────────────────────
DEMO_FARMERS = [
    {
        "wallet": "4pMnsypmRtd94bK94LXjFPWghpXN5WfCcLvnJhoUdX5z",
        "lat": 53.2,
        "lon": 63.6,
    },  # Kostanay Region
    {
        "wallet": "EeqwDr7kNxp4y9vj4MaQijv4BmgAm3WXArzZM5WikD6U",
        "lat": 54.9,
        "lon": 69.1,
    },  # North Kazakhstan Region
    {
        "wallet": "CHaGvsfMx5YKE3mYq7huQM6keRN2UUsfhwAZMypWw7KC",
        "lat": 51.1,
        "lon": 71.4,
    },  # Akmola Region
    {
        "wallet": "FZA62o7rNFBmx5g1hFyCmpRYWhpxAHTiqnYUaRd7EGfL",
        "lat": 50.3,
        "lon": 57.2,
    },  # Aktobe Region
    {
        "wallet": "8jm7bVG8CiqxDmohHUuMk5R3WZkucTrXPUDsDhzvLQ3p",
        "lat": 43.8,
        "lon": 77.1,
    },  # Almaty Region
]


# ─── Endpoints ────────────────────────────────────────────────────────────────────


@app.post("/api/demo/seed", summary="Засеять демо-данными")
async def seed_demo_data():
    """Инициализирует 5 демо-фермеров для демонстрации."""
    if os.getenv("DISABLE_DEMO", "").lower() in ("1", "true"):
        raise HTTPException(status_code=403, detail="Demo endpoints disabled in production")
    for f in DEMO_FARMERS:
        farmers_db[f["wallet"]] = FarmerStatus(
            wallet=f["wallet"],
            lat=f["lat"],
            lon=f["lon"],
            status="pending",
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
    return farmer


@app.post("/api/evaluate", response_model=EvaluateResponse, summary="Запустить оценку")
async def start_evaluation(req: EvaluateRequest):
    """
    Запускает асинхронный цикл оценки фермера.
    Возвращает evaluation_id для подключения к SSE-стриму.
    """
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

    evaluations_db[evaluation_id] = {
        "wallet": req.wallet_address,
        "lat": req.lat,
        "lon": req.lon,
        "status": "running",
        "logs": [],
        "result": None,
        "started_at": datetime.utcnow().isoformat(),
    }

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
    """Агрегированная статистика по всем оценкам."""
    global total_disbursed_sol
    all_farmers = list(farmers_db.values())
    approved = sum(1 for f in all_farmers if f.status == "approved")
    rejected = sum(1 for f in all_farmers if f.status == "rejected")
    pending = sum(1 for f in all_farmers if f.status == "pending")

    return StatsResponse(
        total=len(all_farmers),
        approved=approved,
        rejected=rejected,
        pending=pending,
        total_disbursed_sol=round(total_disbursed_sol, 3),
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

        # Шаг 6: Solana Bridge — отправляем субсидию если одобрено
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

            async with _eval_lock:
                global total_disbursed_sol
                total_disbursed_sol += bridge_result.amount_sol

            mode_label = "[MOCK]" if bridge_result.is_mock else "[LIVE]"
            log(
                "✅ TX Confirmed",
                f"{mode_label} TX: {bridge_result.signature[:20]}... | "
                f"{bridge_result.amount_sol} SOL disbursed | "
                f"Explorer: {bridge_result.explorer_url}",
            )
        else:
            log("❌ TX Skipped", "Субсидия не одобрена — транзакция не отправлена.")

        eval_data["result"] = result.model_dump()
        eval_data["status"] = "done"
        eval_data["completed_at"] = datetime.utcnow().isoformat()

    except Exception as e:
        import traceback as tb

        logger.error("Evaluation %s failed: %s", evaluation_id, e, exc_info=True)
        eval_data["status"] = "error"
        eval_data["error"] = "Internal evaluation error"
        if wallet in farmers_db:
            farmers_db[wallet].status = "pending"
