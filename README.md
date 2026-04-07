# Dala Network - Public-Benefit Payout Rail for Climate Relief

Dala Network is an AI oracle for drought-triggered public-benefit payouts on Solana.  
It combines off-chain climate intelligence with on-chain policy enforcement, so aid can be fast, auditable, and resistant to manipulation.

## Track

**Decentrathon / AI + Blockchain**

## What We Built

Government climate aid is often manual, delayed, and opaque.  
Dala Network automates drought relief decisions using satellite + weather signals, then executes payouts through Solana smart contracts with full auditability.

## Dual-Validation Architecture (Core Innovation)

Dala Network is intentionally split into two trust layers:

1. **Off-chain AI oracle (OpenAI + climate features)**  
   The backend evaluates drought severity using NDVI, weather data, and historical context, then returns a structured verdict and score.

2. **On-chain policy guardrails (Anchor on Solana)**  
   The smart contract enforces strict payout rules and blocks disbursement if conditions are not met.

This means AI can recommend, but **cannot unilaterally move funds**.  
Blockchain logic is the final authority, protecting against rogue or incorrect AI behavior.

## Tech Stack

- **Solana Devnet**
- **Anchor** (smart contracts)
- **OpenAI API** (AI reasoning)
- **Sentinel NDVI signals** (via NDVI service)
- **Helius / Solana RPC tooling**
- **FastAPI + Python** backend
- **React + Vite** frontend dashboard

## Repository Structure

```text
agri-subsidy/
├── agent/         # FastAPI AI oracle backend
├── contracts/     # Anchor smart contract
└── dashboard/     # React frontend (landing + demo dashboard)
```

## How To Run Locally

### 1. Backend

```bash
cd agent
pip install -r requirements.txt
cp .env.example .env
```

Fill `agent/.env`:

- `OPENAI_API_KEY`
- `OPENWEATHER_API_KEY`
- `PROGRAM_ID` (if live contract is deployed)
- keypair paths/public keys as needed for live transfer flow

Start backend on the port expected by frontend:

```bash
py -3 -m uvicorn main:app --reload --port 8080
```

Health check:

```bash
http://127.0.0.1:8080/health
```

### 2. Frontend

```bash
cd ../dashboard
npm install
npm run dev
```

Open:

```bash
http://localhost:5173
```

### 3. Demo Flow

1. Click **Load Demo** (seeds demo farmers).
2. Pick a farmer and click **Evaluate**.
3. Watch real-time AI reasoning stream.
4. Open the generated Solana Explorer transaction link.

You can also seed from terminal:

```bash
curl -X POST http://127.0.0.1:8080/api/demo/seed
```

## Why Solana

- Low fees suitable for micro-disbursements
- High throughput and fast confirmation
- Public, verifiable transaction history for accountability

## Submission Notes

- The project is designed for live demo under hackathon constraints.
- Fallback behavior exists for resilience when external AI/RPC services are degraded.
- Demo includes a stress-case farmer profile to clearly show drought-triggered payout logic.
