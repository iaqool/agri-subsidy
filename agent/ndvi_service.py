import asyncio
import random

async def fetch_historical_ndvi(lat: float, lon: float) -> dict:
    """Генерация реалистичных NDVI данных для демо"""
    
    # Используем координаты как зерно генератора. 
    # Это позволяет получать консистентные результаты для одних и тех же фермеров
    seed_val = int((lat + lon) * 1000)
    random.seed(seed_val)
    
    # Симуляция. Для примера - пустыня(Lat: 30) -> низкий NDVI, степь/поля (50) -> высокий
    base_ndvi = min(max((abs(lat) / 90.0) + (random.random() * 0.4), 0.1), 0.9)
    
    # Имитируем небольшую задержку обращения к 'спутнику' (неблокирующая)
    await asyncio.sleep(0.5)
    
    return {
        "current_ndvi": round(base_ndvi * 0.9, 2), # Якобы небольшое падение 
        "historical_avg": round(base_ndvi, 2),
        "alert": "low_vegetation" if base_ndvi < 0.4 else "normal"
    }
