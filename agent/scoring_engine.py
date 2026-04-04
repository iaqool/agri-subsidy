from typing import Dict, Any


def calculate_weather_score(weather: Dict[str, Any]) -> int:
    """
    Оценивает погодные условия по шкале 0–100.
    Высокий скор = стресс для урожая = больше оснований для субсидии.
    """
    if "error" in weather:
        return 50  # Нейтральный скор при ошибке

    score = 0
    temperature = weather.get("temperature", 20)
    humidity = weather.get("humidity", 50)
    rain_1h = weather.get("rain_1h", 0)

    # Температурный стресс: экстремальная жара или холод
    if temperature > 38:
        score += 50  # Сильная жара
    elif temperature > 32:
        score += 30  # Умеренная жара
    elif temperature < 0:
        score += 40  # Заморозки
    elif temperature < 5:
        score += 20  # Холодный стресс

    # Влажность: очень низкая = засуха
    if humidity < 20:
        score += 35
    elif humidity < 35:
        score += 20
    elif humidity > 90:
        score += 10  # Избыточная влажность тоже вредна (грибки)

    # Осадки: нет дождя = плохо, но это только за 1 час
    if rain_1h == 0:
        score += 15  # Нет дождя → +15
    elif rain_1h > 50:
        score += 10  # Ливень → тоже стресс

    return min(score, 100)


def calculate_ndvi_score(ndvi: Dict[str, Any]) -> int:
    """
    NDVI-скор: низкий индекс растительности = больше оснований для помощи.
    Инвертируем: низкий NDVI → высокий скор стресса.
    """
    current = ndvi.get("current_ndvi", 0.5)
    historical_avg = ndvi.get("historical_avg", 0.5)

    # Базовый стресс-скор по текущему NDVI
    if current < 0.2:
        base = 95
    elif current < 0.35:
        base = 80
    elif current < 0.5:
        base = 60
    elif current < 0.65:
        base = 35
    else:
        base = 15

    # Корректируем по отклонению от исторического среднего
    deviation = historical_avg - current
    if deviation > 0.15:
        base = min(base + 10, 100)  # Сильное падение относительно нормы
    elif deviation > 0.05:
        base = min(base + 5, 100)

    return int(base)


def calculate_composite_score(
    weather: Dict[str, Any],
    ndvi: Dict[str, Any],
    history_penalty: int = 0,
) -> Dict[str, Any]:
    """
    Итоговый скор = weather * 0.4 + ndvi * 0.4 + history * 0.2
    
    history_penalty: штраф за прошлые злоупотребления субсидиями (0–100).
    В MVP всегда 0 (нет истории).
    """
    weather_score = calculate_weather_score(weather)
    ndvi_score = calculate_ndvi_score(ndvi)
    
    # История (обратная — 100 означает ХОРОШУЮ историю, т.е. нет штрафа)
    history_score = 100 - history_penalty

    composite = int(
        weather_score * 0.4
        + ndvi_score * 0.4
        + history_score * 0.2
    )

    APPROVAL_THRESHOLD = 55  # Порог одобрения субсидии

    return {
        "composite_score": composite,
        "weather_score": weather_score,
        "ndvi_score": ndvi_score,
        "history_score": history_score,
        "approved": composite >= APPROVAL_THRESHOLD,
        "threshold": APPROVAL_THRESHOLD,
    }
