# Dala Network — Drought Oracle Layer for Solana

Dala Network is a drought-specific oracle layer on Solana. Parametric insurance protocols, reinsurers, and public farmer-relief programs subscribe to a single feed and a single Anchor-enforced payout rail — the same way DeFi protocols subscribe to Pyth, but for drought events.

Live on Devnet · [agri-subsidy.vercel.app](https://agri-subsidy.vercel.app/) · Program: [`2tBU1bHZiydZGvcj3Dr5Sj3qQFDbQMrmCkYQt9SXgkfK`](https://explorer.solana.com/address/2tBU1bHZiydZGvcj3Dr5Sj3qQFDbQMrmCkYQt9SXgkfK?cluster=devnet) (M-of-N source, initialized as 1-of-1 for the live demo)

## Track

**Colosseum Frontier Hackathon** — targeting DePIN, Climate Award, and Public Goods nominations.

## The Problem

- Drought caused over **$40B** in agricultural losses in 2024
- **70%** of smallholder farmers globally have no access to crop insurance
- Manual claims pipelines take **30–90 days**, often longer
- Public subsidy programs leak **15–40%** to corruption and fraud
- Existing parametric products on EVM (Etherisc, Arbol) rely on simple rainfall thresholds — single-signal, low accuracy in mixed-drought conditions

## The Solution

A drought oracle layer that turns satellite NDVI and climate signals into verifiable on-chain payout triggers on Solana.

1. Sentinel and MODIS NDVI plus OpenWeatherMap data normalized by region
2. AI produces an explainable composite drought score (NDVI + weather + history, weighted 0.4 / 0.4 / 0.2)
3. Anchor program enforces final policy — score ≥ 55, amount ≤ 5 SOL, authorized oracle, active pool
4. Approved payout commits in seconds, with a full on-chain audit trail

## Who It Is For

| ICP | What we provide | Status |
|-----|-----------------|--------|
| **Parametric insurance protocols** (AMOCA, SeedFlow, NOVA and the like) | Drought trigger feed, $0.50 per evaluation, no infra to maintain | Primary focus |
| **Reinsurers** (Munich Re / Swiss Re sandbox programs) | White-label drought oracle for emerging-market portfolios with on-chain audit trail | B2B traditional |
| **Public relief programs** (ministries of agriculture, donor agencies) | Replacement for manual disbursement, automated and auditable | Q3 2026 pilot, Central Asia |

## Status

- Anchor program deployed on Devnet at [`2tBU1bHZiydZGvcj3Dr5Sj3qQFDbQMrmCkYQt9SXgkfK`](https://explorer.solana.com/address/2tBU1bHZiydZGvcj3Dr5Sj3qQFDbQMrmCkYQt9SXgkfK?cluster=devnet) — the **M-of-N quorum** binary (parameterized policy, oracle registry, idempotent attestation) is on-chain ([source](contracts/programs/agri_subsidy/src/lib.rs)), but the live pool is initialized with `quorum=1` so a single AI oracle keypair can drive the demo end-to-end. Cutting over to a real 2-of-3 quorum requires provisioning the additional oracle keypairs and a `update_quorum` call — the contract path already exists.
- Subsidy pool PDA: [`AxnVgXUfeDk7nXXjhjvVuWPEvxh2SXBbDieUxfvJ64KL`](https://explorer.solana.com/address/AxnVgXUfeDk7nXXjhjvVuWPEvxh2SXBbDieUxfvJ64KL?cluster=devnet) (initialized with `min_score=55`, `max_amount_per_payout=1.5 SOL`, `quorum=1` — single-signer for demo, see note above)
- Predecessor single-oracle build at `971ZxLBhqc9p7rqCX5UkpknEo4AJNBdN8PTXmWHxzJoF` is deprecated
- Backend live with OpenAI streaming + rule-based fallback. `/api/stats` exposes `live_tx_count`, `mock_tx_count`, `degraded_tx_count`, and `fallback_eval_count` so a degraded MOCK does not silently inflate `total_disbursed_sol`
- Dashboard deployed on Vercel; verdict card distinguishes LIVE TX from demo MOCK and from degraded MOCK (LIVE failed, returned a simulated signature)
- NDVI ingestion currently simulated (deterministic per coordinates with arid-biome awareness); real Sentinel/MODIS integration is on the roadmap
- Farmer state and evaluation history are durable when `DATABASE_URL` is set (SQLAlchemy 2.0 async; defaults to `sqlite+aiosqlite:///./agri.db`, the same code path drives hosted Postgres via `postgresql+asyncpg://...`); the disbursement ledger is append-only with `UNIQUE` on the TX signature so retries cannot inflate `total_disbursed_sol`. When `DATABASE_URL` is unset the agent falls back to the legacy in-memory dicts (useful for tests and quick local smoke runs).

## Roadmap

| When | What |
|------|------|
| Q4 2025 · done | Anchor program on Devnet, dual-validation architecture |
| Q4 2025 · done | AI oracle MVP with fallback agent and SSE streaming |
| Q1 2026 · done | Colosseum Frontier submission |
| Q1 2026 · done | M-of-N quorum + parameterized policy + idempotent attestation in source ([`contracts/programs/agri_subsidy`](contracts/programs/agri_subsidy/src/lib.rs)) |
| ✅ Done | M-of-N quorum binary deployed to Devnet at `2tBU…gkfK`; live pool initialized as 1-of-1 for the demo (quorum cutover pending additional oracle keypairs) |
| Q2 2026 | First parametric-protocol integration (AMOCA-class) |
| Q3 2026 | Real Sentinel / MODIS NDVI ingestion, mainnet beta |
| Q3 2026 | Public-benefit pilot with one Central-Asian Ministry of Agriculture |
| Q4 2026 | Production launch, $1M+ TVL in subsidy pools |

## Honest Note on Competition

Three projects on Solana touch the parametric-insurance space (AMOCA, SeedFlow, NOVA — all Breakout / Cypherpunk hackathon prototypes). None target drought specifically, none combine NDVI + weather + history into a composite explainable score, none ship a separate oracle layer. We are not their competitor — we are the data layer they can use. On EVM, Etherisc and Arbol use rainfall thresholds; we use a multi-signal score plus dual-validation.

## What It Does (one-liner)

For parametric protocols and public programs, Dala Network turns drought into a smart-contract event. NDVI in, payout out, audit trail forever.

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
| `SOLANA_RPC_URL` | No | Primary Solana JSON-RPC endpoint. Defaults to `https://api.devnet.solana.com` |
| `SOLANA_RPC_URLS` | No | Comma-separated extra RPC endpoints used as fallbacks when the primary is unhealthy (network errors, HTTP 5xx, 429). Empty → single-RPC behaviour. Example: `https://devnet.helius-rpc.com/?api-key=XYZ,https://api.devnet.solana.com` |

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

Production targets:
- **Primary**: Railway (`https://agri-subsidy-production.up.railway.app`).
- **Fallback**: fly.io. The agent ships with `agent/fly.toml`; see `agent/FLY_MIGRATION.md` for the one-time setup when Railway is unavailable.

## Why Solana

- Sub-second slot times and ~13s finalization make oracle updates economic at micro-policy scale
- Low fees keep $1–$50 per-policy economics viable; on EVM the gas alone would eat the premium
- Public, verifiable transaction history is exactly what reinsurers and donors need for audit
- Anchor's account model fits multi-pool, multi-oracle policy enforcement cleanly

## Submission Notes

- Live demo on [agri-subsidy.vercel.app](https://agri-subsidy.vercel.app/) under hackathon constraints
- NDVI data is simulated in MVP (deterministic based on coordinates); real Sentinel/MODIS ingestion ships in Q3 2026
- Demo includes a stress-case farmer profile (Aktobe Region) to show a drought-triggered payout end-to-end
