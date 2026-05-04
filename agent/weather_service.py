import httpx
from config import OPENWEATHER_API_KEY
from typing import Dict, Any


async def fetch_weather_data(lat: float, lon: float) -> Dict[str, Any]:
    """Получает текущую погоду и возвращает упрощенный объект для ИИ"""
    if not OPENWEATHER_API_KEY:
        return {"error": "Missing OpenWeather API Key"}

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return {"error": "Coordinates out of range"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": OPENWEATHER_API_KEY,
                    "units": "metric",
                },
            )
            response.raise_for_status()
            data = response.json()

            return {
                "temperature": data["main"]["temp"],
                "humidity": data["main"]["humidity"],
                "description": data["weather"][0]["description"],
                "rain_1h": data.get("rain", {}).get("1h", 0),
            }
        except Exception:
            return {"error": "Weather API unavailable"}
