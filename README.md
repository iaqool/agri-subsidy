# Dala Network — Public-Benefit Payout Rail for Climate Relief

Dala Network is an AI oracle for drought-triggered public-benefit payouts on Solana.
It combines off-chain climate intelligence with on-chain policy enforcement, so aid can be fast, auditable, and resistant to manipulation.

## Track

**Decentrathon / AI + Blockchain**

## What It Does

Government climate aid is manual, delayed, and opaque. Dala Network automates drought relief:

1. Collects satellite NDVI + weather data for a farmer's region
2. AI evaluates drought severity and produces an explainable composite score
3. If the score passes the threshold — the smart contract releases funds to the farmer's Solana wallet
4. Everything is on-chain: auditable, transparent, tamper-proof

## Dual-Validation Architecture

The system is split into two trust layers by design:

| Layer | Role | Trust model |
|-------|------|-------------|
| **Off-chain AI oracle** (Python + OpenAI) | Evaluates drought severity using NDVI, weather, historical context | Can recommend, **cannot move funds** |
| **On-chain policy guardrails** (Anchor on Solana) | Enforces payout rules: score ≥ 55, amount ≤ 5 SOL, authorized oracle, active pool | Final authority on all disbursements |

AI recommends — blockchain decides. This protects against rogue or incorrect AI behavior.

## Scoring Algorithm

The composite score determines subsidy eligibility:

```
composite = weather_score × 0.4 + ndvi_score × 0.4 + history_score × 0.2
```

- **weather_score** (0–100): temperature stress, humidity deficit, precipitation absence
- **ndvi_score** (0–100): inverse of vegetation health index (low NDVI = high stress score)
- **history_score** (0–100): penalty for past abuse (always 100 in MVP — no history yet)
- **Approval threshold**: composite ≥ 55

## Tech Stack

- **Solana Devnet** — blockchain layer
- **Anchor 0.29** — smart contract framework
- **OpenAI GPT-4o** — AI reasoning (with rule-based fallback)
- **Sentinel NDVI** — satellite vegetation index
- **OpenWeatherMap** — real-time weather data
- **FastAPI + Python** — backend API
- **React 19 + Vite** — frontend dashboard

## Repository Structure

```
agri-subsidy/
├── agent/              # FastAPI backend (AI oracle + Solana bridge)
│   ├── main.py         # API endpoints and evaluation pipeline
│   ├── ai_agent.py     # OpenAI streaming evaluation
│   ├── fallback_agent.py   # Rule-based fallback when OpenAI is unavailable
│   ├── scoring_engine.py   # Composite score calculation
│   ├── weather_service.py  # OpenWeatherMap integration
│   ├── ndvi_service.py     # NDVI satellite data (simulated in MVP)
│   ├── solana_bridge.py    # Solana transaction builder (live + mock modes)
│   └── Dockerfile
├── contracts/          # Anchor smart contract
│   └── programs/agri_subsidy/src/lib.rs
└── dashboard/          # React frontend (landing + dashboard)
    └── src/
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/demo/seed` | Seed 5 demo farmers (Kazakh regions) |
| `GET` | `/api/farmers` | List all registered farmers with statuses |
| `POST` | `/api/farmers/register` | Register a new farmer (`wallet_address`, `region_lat`, `region_lon`) |
| `POST` | `/api/evaluate` | Start AI evaluation (`wallet_address`, `lat`, `lon`) → returns `evaluation_id` |
| `GET` | `/api/stream/{evaluation_id}` | SSE stream of real-time AI reasoning |
| `GET` | `/api/evaluation/{evaluation_id}` | Full evaluation result |
| `GET` | `/api/stats` | Aggregated stats (total, approved, rejected, SOL disbursed) |
| `GET` | `/api/tx/{signature}` | Solana transaction status |
| `GET` | `/health` | Health check |

## Environment Variables

### Backend (`agent/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | For AI mode | OpenAI API key. Without it, fallback mode activates |
| `OPENWEATHER_API_KEY` | For weather | OpenWeatherMap API key. Without it, neutral weather data used |
| `PROGRAM_ID` | For live TX | Deployed Anchor program ID. Without it, mock transactions used |
| `ORACLE_KEYPAIR_PATH` | For live TX | Path to oracle keypair JSON file |
| `ORACLE_KEYPAIR_JSON` | For live TX | Alternative: keypair as JSON array (for cloud deploy) |
| `ORACLE_PUBKEY` | For init | Oracle public key |
| `ADMIN_PUBKEY` | For live TX | Deployer wallet public key |
| `ADMIN_KEYPAIR_PATH` | For init | Path to deployer keypair |
| `SOLANA_RPC_URL` | No | Defaults to `https://api.devnet.solana.com` |

### Frontend (`dashboard/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_BASE_URL` | No | Backend URL. Defaults to `http://127.0.0.1:8080` |

## How To Run Locally

### 1. Backend

```bash
cd agent
pip install -r requirements.txt
cp .env.example .env
# Fill in OPENAI_API_KEY and OPENWEATHER_API_KEY at minimum
```

Start:

```bash
python -m uvicorn main:app --reload --port 8080
```

Health check: `curl http://127.0.0.1:8080/health`

### 2. Frontend

```bash
cd dashboard
npm install
npm run dev
```

Open: `http://localhost:5173`

### 3. Demo Flow

1. Click **Load Demo** → seeds 5 demo farmers (Kazakh regions)
2. Pick a farmer → click **Evaluate**
3. Watch real-time AI reasoning stream via SSE
4. If approved → Solana transaction link appears (Explorer)

### 4. Smart Contract (optional)

```bash
cd contracts
anchor build
anchor deploy   # → copy Program ID to agent/.env
python agent/init_setup.py   # initializes pool + registers farmers on-chain
```

## Fallback Mode

The system is resilient to external service failures:

| Service down | Behavior |
|-------------|----------|
| OpenAI unavailable | Switches to rule-based fallback agent with pre-computed scenarios |
| OpenWeatherMap unavailable | Uses neutral weather data (25°C, 45% humidity) |
| Solana contract not deployed | Generates mock transactions with fake signatures |

## Deployment (Docker)

```bash
cd agent
docker build -t dala-agent .
docker run -p 8080:8080 --env-file .env dala-agent
```

Frontend: `cd dashboard && npm run build` → serve `dist/` with any static hosting.

## Why Solana

- Low fees suitable for micro-disbursements
- High throughput and fast confirmation
- Public, verifiable transaction history for accountability

## Submission Notes

- Designed for live demo under hackathon constraints
- NDVI data is simulated in MVP (deterministic based on coordinates)
- Demo includes a stress-case farmer profile (Aktobe Region) to show drought-triggered payout
