import asyncio
import json
from typing import AsyncGenerator, Dict, Any, Optional

from openai import AsyncOpenAI
from config import OPENAI_API_KEY
from models import EvaluationResult, AILogEntry
from fallback_agent import evaluate_with_fallback, get_fallback_result


SYSTEM_PROMPT = """Ты — ИИ-агент AgriOracle, специализированная система анализа агрорисков для автоматизации государственных субсидий.

Твоя задача: на основе объективных погодных данных и NDVI-индекса вегетации принять взвешенное решение о выплате агросубсидии фермеру.

## Правила анализа

1. **Погода**: Оцени температурный стресс, дефицит влаги, экстремальные осадки.
2. **NDVI**: Индекс 0.0–1.0. Значения < 0.3 = критический стресс, 0.3–0.5 = умеренный, > 0.6 = здоровая растительность.
3. **Composite Score** уже вычислен — используй его как базу, но можешь скорректировать итоговый вердикт, если видишь аномалии.
4. Порог одобрения субсидии: 55/100.

## Формат рассуждения

Думай вслух, пошагово. Каждый шаг начинай с эмодзи и заголовка, затем факты и вывод.
Пример:
🌡️ Анализ температуры: Зафиксировано +36°C. Это критическая зона для пшеницы (оптимум +18→25°C). Добавляю высокий весовой коэффициент.

## Выходной формат

В конце рассуждения выведи JSON-вердикт на отдельной строке, СТРОГО в таком виде:
VERDICT: {"approved": true/false, "score": 0-100, "reasoning": "краткий итог для записи в блокчейн (≤200 символов)"}

Отвечай ТОЛЬКО на русском языке. Будь конкретным и точным.
"""


async def stream_ai_evaluation(
    farmer_data: Dict[str, Any],
    weather: Dict[str, Any],
    ndvi: Dict[str, Any],
    scores: Dict[str, Any],
) -> AsyncGenerator[AILogEntry, None]:
    """
    Генератор: стримит пошаговое рассуждение OpenAI через SSE.
    При ошибке автоматически переключается на fallback.
    """
    if not OPENAI_API_KEY:
        async for entry in evaluate_with_fallback(farmer_data, weather, ndvi, scores):
            yield entry
        return

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    user_message = f"""
Оцени заявку на агросубсидию:

**Данные фермера:**
- Координаты: lat={farmer_data.get('lat')}, lon={farmer_data.get('lon')}

**Погодные данные (реальные, OpenWeatherMap):**
- Температура: {weather.get('temperature', 'N/A')}°C
- Влажность: {weather.get('humidity', 'N/A')}%
- Описание: {weather.get('description', 'N/A')}
- Осадки (1ч): {weather.get('rain_1h', 0)} мм

**NDVI данные (спутниковые):**
- Текущий NDVI: {ndvi.get('current_ndvi', 'N/A')}
- Исторический норм NDVI: {ndvi.get('historical_avg', 'N/A')}
- Статус: {ndvi.get('alert', 'N/A')}

**Pre-computed Scores (алгоритм):**
- weather_score: {scores.get('weather_score')}/100
- ndvi_score: {scores.get('ndvi_score')}/100
- composite_score: {scores.get('composite_score')}/100
- Алгоритмическое решение: {"ОДОБРИТЬ" if scores.get('approved') else "ОТКЛОНИТЬ"}

Проведи детальный анализ и вынеси окончательный вердикт.
"""

    try:
        yield AILogEntry(
            step="🔌 Подключение",
            content="Подключаюсь к модели OpenAI. Загружаю агроданные..."
        )
        await asyncio.sleep(0.5)

        buffer = ""
        current_step = ""
        current_content = []

        stream = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            stream=True,
            max_tokens=1500,
            temperature=0.3,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            buffer += delta

            # Парсим строки по мере поступления
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()

                if not line:
                    # Пустая строка — завершаем текущий шаг и отправляем
                    if current_step and current_content:
                        yield AILogEntry(
                            step=current_step,
                            content=" ".join(current_content).strip()
                        )
                        current_step = ""
                        current_content = []
                    continue

                # Определяем это новый шаг или продолжение
                # Шаги начинаются с эмодзи + заголовок с двоеточием
                if line.startswith("VERDICT:"):
                    # Парсим финальный вердикт
                    if current_step and current_content:
                        yield AILogEntry(
                            step=current_step,
                            content=" ".join(current_content).strip()
                        )
                    json_str = line.replace("VERDICT:", "").strip()
                    try:
                        verdict = json.loads(json_str)
                        verdict_emoji = "✅" if verdict.get("approved") else "❌"
                        yield AILogEntry(
                            step=f"{verdict_emoji} Финальный вердикт",
                            content=f"SCORE: {verdict.get('score')}/100 | {verdict.get('reasoning', '')}",
                        )
                    except json.JSONDecodeError:
                        yield AILogEntry(step="⚠️ Вердикт", content=line)
                    current_step = ""
                    current_content = []

                elif any(line.startswith(emoji) for emoji in ["🌡️", "💧", "🌿", "📊", "⚠️", "🔍", "💡", "📈"]):
                    # Новый шаг
                    if current_step and current_content:
                        yield AILogEntry(
                            step=current_step,
                            content=" ".join(current_content).strip()
                        )
                    # Разделяем заголовок и начало текста
                    if ":" in line:
                        colon_idx = line.index(":")
                        current_step = line[:colon_idx]
                        rest = line[colon_idx + 1:].strip()
                        current_content = [rest] if rest else []
                    else:
                        current_step = line
                        current_content = []

                else:
                    current_content.append(line)

        # Выводим всё что осталось в буфере
        if buffer.strip() and current_step:
            current_content.append(buffer.strip())

        if current_step and current_content:
            yield AILogEntry(
                step=current_step,
                content=" ".join(current_content).strip()
            )

    except Exception as e:
        yield AILogEntry(
            step="⚠️ Ошибка OpenAI",
            content=f"OpenAI недоступен ({str(e)[:80]}). Переключаюсь на локальный агент..."
        )
        await asyncio.sleep(0.5)
        async for entry in evaluate_with_fallback(farmer_data, weather, ndvi, scores):
            yield entry


async def get_ai_verdict(
    farmer_data: Dict[str, Any],
    weather: Dict[str, Any],
    ndvi: Dict[str, Any],
    scores: Dict[str, Any],
    log_entries: list,
) -> EvaluationResult:
    """
    Извлекает вердикт из собранных лог-записей.
    Если OpenAI вернул VERDICT — парсим оттуда.
    Иначе используем алгоритмический скор.
    """
    # Ищем финальный вердикт в логах
    for entry in reversed(log_entries):
        if "SCORE:" in entry.content and ("✅" in entry.step or "❌" in entry.step):
            approved = "✅" in entry.step
            # Пытаемся извлечь числовой скор
            try:
                score_part = entry.content.split("SCORE:")[1].split("/")[0].strip()
                score = int(score_part)
            except (ValueError, IndexError):
                score = scores.get("composite_score", 50)

            reasoning = entry.content.split("|")[-1].strip() if "|" in entry.content else entry.content
            is_fallback = any("[FALLBACK MODE]" in e.content for e in log_entries)

            return EvaluationResult(
                approved=approved,
                score=score,
                reasoning=reasoning,
                is_fallback=is_fallback,
            )

    # Fallback: берём из scoring engine
    return get_fallback_result(scores)
