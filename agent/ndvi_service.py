"""NDVI data source for the AI oracle.

The MVP uses a deterministic simulator so demos are reproducible without
external dependencies. The simulator combines:

- Latitude band (tropics / temperate / polar) — sets a base vegetation level
- Coordinate-derived noise — keeps the same farmer plot stable across runs
- Calendar month — adds seasonal variation in the northern hemisphere

Real Sentinel-2 / MODIS ingestion is the next milestone (see README roadmap).
The function signature is stable — only the internals change when we wire up
the real Copernicus / NASA endpoints.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from datetime import datetime
from typing import Any, Dict, Optional


def _coord_seed(lat: float, lon: float) -> int:
    """Stable seed from rounded coordinates so the same farmer plot is reproducible."""
    payload = f"{round(lat, 4)}|{round(lon, 4)}".encode()
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:4], "big")


def _band_base_ndvi(lat: float) -> float:
    """Pick a baseline NDVI from the latitude band.

    Tropics (|lat| <= 23.5) — dense vegetation
    Temperate (23.5 < |lat| <= 50) — mixed
    Boreal (50 < |lat| <= 66) — patchy, shorter growing season
    Polar (|lat| > 66) — very low
    """
    abs_lat = abs(lat)
    if abs_lat <= 23.5:
        return 0.72
    if abs_lat <= 50:
        return 0.55
    if abs_lat <= 66:
        return 0.45
    return 0.18


# Major arid biomes that the latitude-band heuristic alone cannot detect.
# Bounding boxes are coarse on purpose — the simulator is a stand-in for
# real Sentinel-2 ingestion, so over-specifying would be misleading false
# precision. Offsets are subtracted from the band base to push baseline
# vegetation toward the empirical reality of these biomes.
_ARID_ZONES: tuple[dict, ...] = (
    {"name": "Sahara/Sahel", "lat": (12.0, 30.0), "lon": (-17.0, 40.0), "offset": -0.45},
    {"name": "Arabian Peninsula", "lat": (15.0, 30.0), "lon": (35.0, 55.0), "offset": -0.45},
    {"name": "Atacama / Coastal Andes", "lat": (-30.0, -15.0), "lon": (-75.0, -68.0), "offset": -0.45},
    {"name": "Iranian Plateau", "lat": (25.0, 36.0), "lon": (52.0, 75.0), "offset": -0.40},
    {"name": "Aralkum / Karakum / Kyzylkum", "lat": (38.0, 48.0), "lon": (53.0, 70.0), "offset": -0.40},
    {"name": "Gobi", "lat": (40.0, 48.0), "lon": (95.0, 115.0), "offset": -0.35},
    {"name": "Australian Outback", "lat": (-33.0, -18.0), "lon": (115.0, 145.0), "offset": -0.35},
    {"name": "Kalahari / Namib", "lat": (-28.0, -18.0), "lon": (15.0, 28.0), "offset": -0.35},
    {"name": "Great Basin (US)", "lat": (35.0, 45.0), "lon": (-120.0, -110.0), "offset": -0.30},
    {"name": "Patagonia (steppe)", "lat": (-50.0, -38.0), "lon": (-72.0, -64.0), "offset": -0.30},
)


def _arid_zone_offset(lat: float, lon: float) -> float:
    """Return a negative NDVI offset if (lat, lon) falls inside a known arid biome."""
    for zone in _ARID_ZONES:
        lat_min, lat_max = zone["lat"]
        lon_min, lon_max = zone["lon"]
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return zone["offset"]
    return 0.0


def _seasonal_adjustment(lat: float, month: int) -> float:
    """Northern-hemisphere growing season peaks in July; mirror for southern."""
    # Map month to a -1..1 sine wave with peak at June/July
    angle = (month - 6.5) / 12.0 * 2 * math.pi
    seasonal = math.cos(angle)  # 1 in June/July, -1 in December/January
    if lat < 0:
        seasonal = -seasonal
    # Effect is small at the equator and larger near the poles
    weight = min(abs(lat) / 60.0, 1.0)
    return seasonal * 0.18 * weight


def _coord_noise(seed: int) -> float:
    """Stable per-coordinate noise in -0.08..+0.08."""
    return ((seed % 16001) / 16000.0 - 0.5) * 0.16


def _historical_avg(lat: float, lon: float, seed: int) -> float:
    """Long-term mean ignores seasonality but keeps coordinate-specific bias.

    Arid-zone offset is also baked in so the historical baseline reflects
    the biome — otherwise low current NDVI in a desert would always trip
    `anomalous_drop` against a misleadingly green historical average.
    """
    base = _band_base_ndvi(lat) + _arid_zone_offset(lat, lon)
    return max(0.05, min(0.95, base + _coord_noise(seed) * 0.5))


def _alert_label(current: float, historical_avg: float) -> str:
    if current < 0.25:
        return "severe_drought"
    if current < 0.4:
        return "low_vegetation"
    if historical_avg - current > 0.2:
        return "anomalous_drop"
    return "normal"


async def fetch_historical_ndvi(
    lat: float,
    lon: float,
    *,
    now: Optional[datetime] = None,
    sleep_s: float = 0.5,
) -> Dict[str, Any]:
    """Return a deterministic NDVI snapshot for the given coordinate.

    The output shape matches what the scoring engine expects:
        {"current_ndvi", "historical_avg", "alert", "source"}

    Args:
        lat: latitude in -90..90
        lon: longitude in -180..180
        now: timestamp used for seasonal adjustment (defaults to UTC now)
        sleep_s: simulated network delay; tests override to 0
    """
    if not -90 <= lat <= 90:
        raise ValueError("latitude must be in -90..90")
    if not -180 <= lon <= 180:
        raise ValueError("longitude must be in -180..180")

    if sleep_s > 0:
        await asyncio.sleep(sleep_s)

    when = now or datetime.utcnow()
    seed = _coord_seed(lat, lon)
    base = _band_base_ndvi(lat) + _arid_zone_offset(lat, lon) + _coord_noise(seed)
    seasonal = _seasonal_adjustment(lat, when.month)
    current = max(0.05, min(0.95, base + seasonal))

    historical = _historical_avg(lat, lon, seed)
    alert = _alert_label(current, historical)

    return {
        "current_ndvi": round(current, 3),
        "historical_avg": round(historical, 3),
        "alert": alert,
        "source": "simulated",
    }
