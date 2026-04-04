import httpx
from config import OPENWEATHER_API_KEY
from typing import Dict, Any

async def fetch_weather_data(lat: float, lon: float) -> Dict[str, Any]:
    """Получает текущую погоду и возвращает упрощенный объект для ИИ"""
    if not OPENWEATHER_API_KEY:
        return {"error": "Missing OpenWeather API Key"}

    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            return {
                "temperature": data["main"]["temp"],
                "humidity": data["main"]["humidity"],
                "description": data["weather"][0]["description"],
                "rain_1h": data.get("rain", {}).get("1h", 0)
            }
        except Exception as e:
            return {"error": str(e)}
