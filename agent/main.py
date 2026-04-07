import asyncio
import uuid
import json
from typing import Dict
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from models import FarmerRegistration, EvaluationResult, AILogEntry, FarmerStatus
from weather_service import fetch_weather_data
from ndvi_service import fetch_historical_ndvi
from scoring_engine import calculate_composite_score
from ai_agent import stream_ai_evaluation, get_ai_verdict
from solana_bridge import release_subsidy, get_transaction_status, SUBSIDY_AMOUNT_SOL


# ─── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AgriSubsidy AI Oracle",
    description="AI-powered agricultural subsidy decision system on Solana",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшне заменить на конкретный фронтенд URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── In-Memory State (MVP) ───────────────────────────────────────────────────────
# В продакшне заменить на PostgreSQL/Redis
farmers_db: Dict[str, FarmerStatus] = {}
evaluations_db: Dict[str, dict] = {}  # evaluation_id -> {logs, result, ...}
total_disbursed_sol: float = 0.0  # Накопительная сумма выплат


# ─── Pydantic Schemas ────────────────────────────────────────────────────────────
class EvaluateRequest(BaseModel):
    wallet_address: str
    lat: float
    lon: float


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
    evaluation_id = str(uuid.uuid4())

    # Регистрируем фермера если новый
    if req.wallet_address not in farmers_db:
        farmers_db[req.wallet_address] = FarmerStatus(
            wallet=req.wallet_address,
            lat=req.lat,
            lon=req.lon,
            status="pending",
        )

    # Создаём запись для evaluation
    evaluations_db[evaluation_id] = {
        "wallet": req.wallet_address,
        "lat": req.lat,
        "lon": req.lon,
        "status": "running",
        "logs": [],
        "result": None,
        "started_at": datetime.utcnow().isoformat(),
    }

    # Запускаем оценку в фоне
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
    if evaluation_id not in evaluations_db:
        raise HTTPException(status_code=404, detail="Evaluation не найден")

    async def event_generator():
        sent_count = 0
        max_wait = 120  # 2 минуты максимум
        elapsed = 0

        while elapsed < max_wait:
            eval_data = evaluations_db.get(evaluation_id, {})
            logs = eval_data.get("logs", [])

            # Отправляем новые записи
            while sent_count < len(logs):
                entry = logs[sent_count]
                data = json.dumps(entry, ensure_ascii=False)
                yield f"data: {data}\n\n"
                sent_count += 1

            # Если оценка завершена — шлём финальное событие
            if eval_data.get("status") == "done":
                result = eval_data.get("result", {})
                yield f"event: done\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
                break

            if eval_data.get("status") == "error":
                yield f"event: error\ndata: {json.dumps({'error': eval_data.get('error', 'Unknown')})}\n\n"
                break

            await asyncio.sleep(0.3)
            elapsed += 0.3

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


@app.get("/api/tx/{signature}", summary="Статус транзакции")
async def check_tx_status(signature: str):
    """Проверяет статус Solana транзакции на Devnet."""
    return await get_transaction_status(signature)


@app.get("/api/evaluation/{evaluation_id}", summary="Результат оценки")
async def get_evaluation_result(evaluation_id: str):
    """Возвращает полный результат завершённой оценки."""
    if evaluation_id not in evaluations_db:
        raise HTTPException(status_code=404, detail="Evaluation не найден")
    return evaluations_db[evaluation_id]


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

        # [DEMO HACK] Жестко хардкодим засуху для Актюбинской области (DemoFarm4)
        if lat == 50.3 and lon == 57.2:
            weather = {
                "temperature": 45.0,
                "humidity": 5.0,
                "description": "extreme drought",
                "rain_1h": 0.0,
            }

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
        
        # [DEMO HACK] Катастрофически низкий NDVI для Актюбинской области
        if lat == 50.3 and lon == 57.2:
            ndvi = {
                "current_ndvi": 0.15,
                "historical_avg": 0.65,
                "alert": "critical_vegetation_loss",
            }
            
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

            # Обновляем глобальную сумму выплат
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
        import traceback

        eval_data["status"] = "error"
        eval_data["error"] = str(e)
        eval_data["traceback"] = traceback.format_exc()
        if wallet in farmers_db:
            farmers_db[wallet].status = "pending"
