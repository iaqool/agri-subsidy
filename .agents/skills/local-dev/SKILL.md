# Local Development & Testing

## Start Services

```bash
# Backend (FastAPI)
cd agent && python -m uvicorn main:app --host 0.0.0.0 --port 8080

# Frontend (Vite + React)
cd dashboard && npm install && npx vite --host 0.0.0.0 --port 5173
```

## Fallback Mode

The backend runs without `OPENAI_API_KEY` and `OPENWEATHER_API_KEY`. It uses:
- `fallback_agent.py` for AI reasoning (pre-scripted scenarios)
- Neutral weather data when OpenWeather is unavailable
- NDVI data still fetched from Copernicus (public API)

## Key Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `CORS_ORIGINS` | Allowed frontend origins | `http://localhost:5173,http://127.0.0.1:5173` |
| `ENABLE_DOCS` | Show FastAPI /docs | disabled |
| `DISABLE_DEMO` | Block /api/demo/seed | disabled |
| `MAX_FARMERS` | Registration cap | 10000 |
| `MAX_EVALUATIONS` | Evaluation DB cap | 50000 |
| `MAX_CONCURRENT_SSE` | SSE connection limit | 200 |

## Demo Flow (Testing)

1. Open http://localhost:5173
2. Click "Открыть дашборд" (Launch App) on landing page
3. Click "Load Demo" button → seeds 5 Kazakhstan demo farmers
4. Click a farmer card → click "Evaluate" → SSE stream shows AI reasoning
5. Verdict card appears with composite score, threshold 55/100

## Architecture Notes

- **Dual-Validation**: Off-chain AI oracle recommends, on-chain Anchor contract enforces
- **Scoring**: `composite = weather_score × 0.4 + ndvi_score × 0.4 + history_score × 0.2`; approve if ≥ 55
- **In-memory state**: `farmers_db` and `evaluations_db` are volatile (restart clears data)
- **Smart contract**: Anchor program at `contracts/`, program ID in `Anchor.toml`
- **Frontend API base**: Configured via `VITE_API_BASE_URL`, defaults to `http://127.0.0.1:8080`
