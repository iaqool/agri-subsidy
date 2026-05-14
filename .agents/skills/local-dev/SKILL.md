---
name: local-dev
description: Run, develop, and test the Dala Network agri-subsidy app — locally and against the Vercel + Railway production deployment. Covers the demo seed flow, how to detect silent MOCK / Fallback modes, how to verify a Devnet transaction, and how to bootstrap a fresh Devnet pool.
---

# Local Development & Testing

## Start Services Locally

```bash
# Backend (FastAPI)
cd agent && python -m uvicorn main:app --host 0.0.0.0 --port 8080

# Frontend (Vite + React)
cd dashboard && npm install && npx vite --host 0.0.0.0 --port 5173
```

## Fallback Mode (local dev)

The backend runs without `OPENAI_API_KEY` and `OPENWEATHER_API_KEY`. It uses:
- `fallback_agent.py` for AI reasoning (pre-scripted scenarios)
- Neutral weather data when OpenWeather is unavailable
- NDVI data still fetched from Copernicus (public API)

## Key Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `CORS_ORIGINS` | Allowed frontend origins (note: plural; singular `CORS_ORIGIN` is a no-op) | `http://localhost:5173,http://127.0.0.1:5173` plus the Vercel prod + preview regex |
| `CORS_ORIGIN_REGEX` | Regex for additional dynamic origins (preview deployments) | matches `agri-subsidy-git-*.vercel.app` |
| `ENABLE_DOCS` | Show FastAPI /docs | disabled |
| `DISABLE_DEMO` | Block /api/demo/seed | disabled |
| `MAX_FARMERS` | Registration cap | 10000 |
| `MAX_EVALUATIONS` | Evaluation DB cap | 50000 |
| `MAX_CONCURRENT_SSE` | SSE connection limit | 200 |
| `DATABASE_URL` | Durable storage backend (SQLAlchemy async). Unset → in-memory dicts (legacy, OK for tests). `sqlite+aiosqlite:///./agri.db` → file-based SQLite (zero infra). `postgresql+asyncpg://user:pw@host/db` → hosted Postgres. Plain `sqlite:///…` / `postgresql://…` URLs are auto-normalised. Tables (`farmers`, `evaluations`, `disbursements`) are created on first boot. The disbursement ledger has `UNIQUE(signature)` so retries cannot double-credit `total_disbursed_sol`. | unset |
| `OPENAI_API_KEY` | If unset / invalid → AI agent enters Fallback mode silently | unset |
| `ORACLE_KEYPAIR_JSON` | Solana payer keypair (JSON array). If unset / unparseable → bridge enters MOCK mode silently | unset |
| `SOLANA_RPC_URL` | Devnet/mainnet RPC | `https://api.devnet.solana.com` |
| `PROGRAM_ID` | Anchor program on Devnet | `971ZxLBhqc9p7rqCX5UkpknEo4AJNBdN8PTXmWHxzJoF` (live, single-oracle build) |
| `ADMIN_PUBKEY` | Authority used to derive pool PDA: `[b"subsidy_pool", ADMIN_PUBKEY]`. The bridge re-reads this on every request. For the hackathon-demo deploy this is set to the **oracle** pubkey so we can sign `initialize_subsidy_pool` ourselves; in a production pool this would be a separate admin/multisig. | unset |

## Demo Flow (UI)

1. Open http://localhost:5173 (local) or `https://agri-subsidy.vercel.app/` (prod)
2. Click "Открыть дашборд" / "Launch App" on landing page
3. Click "Load Demo" button → seeds **7** demo farmers (5 KZ + 2 drought-scenario in arid biomes)
4. Click a farmer card → click "Evaluate" → SSE stream shows AI reasoning
5. Verdict card appears with composite score, threshold 55/100, plus a Devnet TX link if approved

### Demo seed farmers and expected outcome

| Wallet | Coords | Region | Behavior |
|---|---|---|---|
| `4pMnsypm…UdX5z` | 53.2°N 63.6°E | Kostanay (KZ) | weather-dependent |
| `EeqwDr7k…4MaQ` | 54.9°N 69.1°E | North Kazakhstan (KZ) | weather-dependent |
| `CHaGvsfM…7hu` | 51.1°N 71.4°E | Akmola (KZ) | weather-dependent |
| `FZA62o7r…1hFyC` | 50.3°N 57.2°E | Aktobe (KZ) | typically rejects in cool/wet months, may approve in summer |
| `8jm7bVG8…MUM` | 43.8°N 77.1°E | Almaty (KZ) | weather-dependent |
| `6zMppjRu…rY8LD8` | 45.5°N 59.0°E | Aralkum / former Aral Sea | **always approves** (severe_drought year-round via arid-zone NDVI offset) |
| `7V9GTiEG…Ct76W` | 39.5°N 60.0°E | Karakum desert (TM) | **always approves** (severe_drought year-round) |

The last two are tagged in the dashboard with a 🏜️ flag and a yellow `DEMO` chip. Use them for any pitch demo where a guaranteed-approve walkthrough is required.

## Testing on Prod

- Frontend: `https://agri-subsidy.vercel.app/`
- Backend:  `https://agri-subsidy-production.up.railway.app/` (primary). If Railway is down or the free plan keeps refusing the build, a fly.io fallback is wired up — see `agent/FLY_MIGRATION.md` for the activation runbook.
- `POST /api/demo/seed` is idempotent and **must be re-run after every backend redeploy** — `farmers_db` is in-memory and resets on container restart.
- `GET /api/farmers` should return 7 entries; the two drought-scenario ones include a non-null `label` field — pre-PR-#7 backends will only return 5.

### Detecting silent MOCK / Fallback modes

Both modes look like success in the UI. Always verify before claiming a real Devnet payout:

- **Solana MOCK mode.** Triggered when `ORACLE_KEYPAIR_JSON` is missing/unparseable, when the pool PDA does not exist on-chain, or when any other on-chain step fails inside the bridge's broad `except`. The success log line in the AI Reasoning Log will read `✅ TX Confirmed — [MOCK] TX: <signature>...` instead of `[LIVE] TX:`. The signature is well-formed but is **not** on chain. Verify with:

  ```bash
  curl -sS -X POST https://api.devnet.solana.com \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"getSignatureStatuses","params":[["<signature>"]]}'
  # value:[null]   →  not on chain (MOCK)
  # value:[{ok}]   →  real Devnet TX
  ```

  For PR #9+ the most common cause is a **missing pool PDA** on Devnet — see the bootstrap section below. Railway logs will show `AnchorError caused by account: farmer_account. Error Code: AccountNotInitialized. Error Number: 3012` followed by `[bridge] MOCK TX generated:`.

- **AI Fallback mode.** Triggered when OpenAI is unreachable / quota / 401, or when GPT-4o never produces the final `VERDICT:` line. Visible as a small `⚡ Fallback mode` chip on the verdict panel. Critically, the verdict-panel "AI Reasoning" paragraph in this mode comes from a hard-coded scenario template and may cite **completely different numbers** (temperature, humidity, NDVI) than the SSE log for the same evaluation — do not trust it as evidence. The SSE log (left side) contains the canonical pipeline truth.

If either mode is detected on prod, the fix is on Railway env (key validity, JSON shape, network) or a missing on-chain pool, not in the repo code.

## Bootstrap a fresh Devnet pool

If the prod backend is going to MOCK on every eval and Railway logs show `AnchorError ... AccountNotInitialized` for the **pool** account (or `getAccountInfo` on the derived pool PDA returns `null`), the pool was never initialized on-chain. `solana program deploy` and `initialize_subsidy_pool` are separate steps and the second is easy to forget.

Minimum-friction recovery (no admin private key needed):

1. Set `ADMIN_PUBKEY` on Railway to the **oracle** pubkey (`Pubkey.from_bytes(ORACLE_KEYPAIR_JSON).pubkey()`). The bridge re-derives pool PDA from `ADMIN_PUBKEY` on every request, so this just changes the seed.
2. Sign `initialize_subsidy_pool(pool_bump)` with the oracle keypair, passing oracle as both authority and oracle account. Anchor seed: `[b"subsidy_pool", oracle_pubkey]`. Discriminator: `sha256("global:initialize_subsidy_pool")[:8]`. Args: `pool_bump: u8`.
3. Fund the pool with SOL (each `release_funds_by_oracle` payout is `SUBSIDY_AMOUNT_SOL` = 1.5 SOL by default — fund with 3-5 SOL for a typical demo).
4. Trigger Railway redeploy (env change does this) and re-run `POST /api/demo/seed`.

After step 2 the pool PDA exists; PR #9's `register_farmer` auto-init will then work for any farmer evaluated for the first time. Pool funding is a hard prerequisite — without it, payouts will fail with insufficient lamports even when the pool account exists.

## Architecture Notes

- **Dual-Validation**: Off-chain AI oracle recommends, on-chain Anchor contract enforces (single-oracle authority on Devnet today; M-of-N quorum is in source and reserved for redeploy at `971Z…XpB`).
- **Scoring**: `composite = weather_score × 0.4 + ndvi_score × 0.4 + history_score × 0.2`; approve if ≥ 55. With `severe_drought` NDVI status, `ndvi_score=95` → composite floor ≈ 58 regardless of weather, which is why the two arid-zone demo farmers are deterministic-approve.
- **In-memory state**: `farmers_db` and `evaluations_db` are volatile (restart / Railway redeploy clears data — re-run `POST /api/demo/seed`).
- **Smart contract**: Anchor program at `contracts/`, live `PROGRAM_ID` differs from `declare_id!()` until the M-of-N redeploy.
- **Frontend API base**: Configured via `VITE_API_BASE_URL`, defaults to `http://127.0.0.1:8080`.

## Devin Secrets Needed

- `RAILWAY_API_TOKEN` — temporary token (user creates at https://railway.com/account/tokens) to read/edit Railway env vars and logs during prod debugging. Not needed for plain UI testing.
- `OPENAI_API_KEY` — only needed for local end-to-end with live AI; unset = fallback mode.
- `OPENWEATHER_API_KEY` — same.
