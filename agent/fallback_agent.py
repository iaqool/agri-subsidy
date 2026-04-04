import asyncio
import random
from typing import AsyncGenerator, Dict, Any

from models import EvaluationResult, AILogEntry


# Заготовленные сценарии для демо-режима без OpenAI
FALLBACK_SCENARIOS = [
    {
        "score": 92,
        "approved": True,
        "reasoning": (
            "Зафиксирована экстремальная засуха: температура +41°C, влажность 18%, "
            "осадки 0 мм за последние 14 дней. NDVI = 0.19 (критически низкий) при "
            "историческом среднем 0.62. Потеря посевов оценивается в 74%. "
            "Субсидия необходима для предотвращения банкротства хозяйства."
        ),
        "steps": [
            ("🌡️ Анализ температуры", "Зафиксировано +41°C — экстремальная жара. Добавляю +50 к weather_score."),
            ("💧 Анализ влажности", "Влажность 18% — критически низкая. Риск быстрого высыхания почвы. +35 к score."),
            ("🌿 Анализ NDVI", "NDVI 0.19 при норме 0.62. Отклонение -69%. Растительный покров почти уничтожен."),
            ("📊 Итоговый расчёт", "composite_score = 92. Порог одобрения: 55. Решение: ОДОБРИТЬ."),
        ],
    },
    {
        "score": 41,
        "approved": False,
        "reasoning": (
            "Погодные условия в пределах нормы: температура +22°C, влажность 58%, "
            "зафиксированы умеренные осадки. NDVI = 0.71 — состояние посевов хорошее. "
            "Оснований для экстренной субсидии нет. Рекомендовано стандартное плановое финансирование."
        ),
        "steps": [
            ("🌡️ Анализ температуры", "Температура +22°C — комфортный диапазон для большинства культур. +0 к score."),
            ("💧 Анализ влажности", "Влажность 58% — оптимальная. Отсутствует гидрологический стресс. +0."),
            ("🌿 Анализ NDVI", "NDVI 0.71 — высокий показатель. Посевы здоровы, активный вегетационный период."),
            ("📊 Итоговый расчёт", "composite_score = 41. Порог одобрения: 55. Решение: ОТКЛОНИТЬ."),
        ],
    },
    {
        "score": 67,
        "approved": True,
        "reasoning": (
            "Пограничный случай: температура +33°C — умеренный тепловой стресс. "
            "Влажность 31% — ниже нормы. NDVI = 0.48 при среднем 0.59 (падение 19%). "
            "Рисков не катастрофических, но накопление стресс-факторов приведёт к "
            "потере урожая без вмешательства. Субсидия одобрена с пониженным приоритетом."
        ),
        "steps": [
            ("🌡️ Анализ температуры", "Температура +33°C — умеренная жара. Добавляю +30 к weather_score."),
            ("💧 Анализ влажности", "Влажность 31% — тревожный уровень, признаки начинающейся засушливости. +20."),
            ("🌿 Анализ NDVI", "NDVI 0.48 при норме 0.59. Падение 19% за последний месяц. Умеренный стресс."),
            ("📊 Итоговый расчёт", "composite_score = 67. Порог одобрения: 55. Решение: ОДОБРИТЬ (пограничный)."),
        ],
    },
    {
        "score": 88,
        "approved": True,
        "reasoning": (
            "Заморозки: зафиксировано -4°C при норме +8°C. "
            "NDVI 0.28 — резкое падение из-за повреждения листового аппарата морозом. "
            "Потеря урожая критическая. Срочная субсидия необходима."
        ),
        "steps": [
            ("🌡️ Анализ температуры", "Температура -4°C — заморозки. Критическое повреждение для большинства культур. +40."),
            ("💧 Анализ влажности", "Влажность 72% — в норме, но на морозе она усиливает ледяное повреждение."),
            ("🌿 Анализ NDVI", "NDVI 0.28 — последствия заморозка явно видны. Значительная деградация листьев."),
            ("📊 Итоговый расчёт", "composite_score = 88. Порог одобрения: 55. Решение: ОДОБРИТЬ (срочно)."),
        ],
    },
    {
        "score": 29,
        "approved": False,
        "reasoning": (
            "Все показатели в норме или лучше: погода комфортная, NDVI = 0.79 — "
            "рекордный для региона за последние 3 года. "
            "Объективных оснований для субсидии не выявлено."
        ),
        "steps": [
            ("🌡️ Анализ температуры", "Температура +18°C — идеальный диапазон роста. Нет температурного стресса."),
            ("💧 Анализ влажности", "Влажность 65% после недавних дождей. Состояние почвы отличное."),
            ("🌿 Анализ NDVI", "NDVI 0.79 — рекордное значение для данного региона. Урожай ожидается выше среднего."),
            ("📊 Итоговый расчёт", "composite_score = 29. Порог одобрения: 55. Решение: ОТКЛОНИТЬ."),
        ],
    },
]


async def evaluate_with_fallback(
    farmer_data: Dict[str, Any],
    weather: Dict[str, Any],
    ndvi: Dict[str, Any],
    scores: Dict[str, Any],
) -> AsyncGenerator[AILogEntry, None]:
    """
    Генератор, имитирующий рассуждения ИИ-агента.
    Используется когда OpenAI API недоступен.
    Подбирает сценарий, близкий к реальным данным.
    """
    # Выбираем сценарий на основе итогового скора
    composite = scores.get("composite_score", 50)
    approved = scores.get("approved", False)

    # Находим сценарий с похожим решением и близким скором
    matching = [s for s in FALLBACK_SCENARIOS if s["approved"] == approved]
    if not matching:
        matching = FALLBACK_SCENARIOS
    scenario = min(matching, key=lambda s: abs(s["score"] - composite))

    yield AILogEntry(
        step="🔄 Инициализация",
        content="[FALLBACK MODE] OpenAI API недоступен. Использую локальный эвристический агент."
    )
    await asyncio.sleep(0.8)

    yield AILogEntry(
        step="📡 Загрузка данных",
        content=(
            f"Получены данные для фермера: "
            f"lat={farmer_data.get('lat', '?')}, lon={farmer_data.get('lon', '?')}. "
            f"Погода: {weather.get('description', 'неизвестно')}, T={weather.get('temperature', '?')}°C. "
            f"NDVI: {ndvi.get('current_ndvi', '?')} (норма: {ndvi.get('historical_avg', '?')})."
        )
    )
    await asyncio.sleep(1.2)

    # Прогоняем сценарные шаги
    for step_name, step_content in scenario["steps"]:
        yield AILogEntry(step=step_name, content=step_content)
        await asyncio.sleep(random.uniform(1.0, 2.5))

    # Финальный вердикт
    verdict_emoji = "✅" if scenario["approved"] else "❌"
    yield AILogEntry(
        step=f"{verdict_emoji} Вердикт",
        content=scenario["reasoning"]
    )


def get_fallback_result(scores: Dict[str, Any]) -> EvaluationResult:
    """Возвращает финальный объект результата для fallback-режима."""
    composite = scores.get("composite_score", 50)
    approved = scores.get("approved", False)

    matching = [s for s in FALLBACK_SCENARIOS if s["approved"] == approved]
    if not matching:
        matching = FALLBACK_SCENARIOS
    scenario = min(matching, key=lambda s: abs(s["score"] - composite))

    return EvaluationResult(
        approved=scenario["approved"],
        score=composite,  # Используем реальный скор из scoring engine
        reasoning=scenario["reasoning"],
        is_fallback=True,
    )
