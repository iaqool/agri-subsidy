# MEMORY.md

## Project
- Name: Dala Network — Drought Oracle Layer for Solana (`iaqool/agri-subsidy`).
- Goal: Drought-specific oracle on Solana that turns NDVI + weather + history into Anchor-enforced parametric payouts. Subscribers: parametric insurance protocols, reinsurers, public farmer-relief programs.
- Current stage: Late-MVP / hackathon submission build (Colosseum Frontier). Devnet-live, Vercel + Railway deployment, NDVI ingestion still simulated.

## Current Status
- What is already working:
  - Anchor M-of-N quorum build deployed to Devnet at `2tBU1bHZiydZGvcj3Dr5Sj3qQFDbQMrmCkYQt9SXgkfK` with parameterized policy, oracle registry, and idempotent attestation flow.
  - Subsidy pool PDA `AxnVgXUfeDk7nXXjhjvVuWPEvxh2SXBbDieUxfvJ64KL` initialized with `min_score=55`, `max_amount_per_payout=1.5 SOL`, `quorum=1` (demo).
  - FastAPI backend (`agent/`) with OpenAI streaming evaluation, rule-based fallback agent, NDVI simulator with arid-biome offset, OpenWeather integration, Solana bridge with live + MOCK modes.
  - React 19 + Vite dashboard (`dashboard/`) deployed on Vercel (https://agri-subsidy.vercel.app/), SSE streaming of AI reasoning, drought-scenario demo flag.
  - CORS allows Vercel prod + preview origins; `register_farmer` auto-init on first evaluation; AI verdict fallthrough fix.
  - Backend tests + CI: ruff, pytest (agent), npm lint + build (dashboard), `cargo +stable check`/`clippy` (contracts) via `.github/workflows/ci.yml`.
  - Local-dev SKILL at `.agents/skills/local-dev/SKILL.md` covers demo flow, silent-MOCK/Fallback detection, Devnet pool bootstrap procedure.
- What was recently finished:
  - PR #11 — deploy M-of-N quorum build to Devnet.
  - PR #10 — Local-dev SKILL update with Devnet pool bootstrap procedure.
  - PR #9 — prod on-chain `register_farmer` auto-init + AI verdict fallthrough.
  - PR #8 — prod-testing knowledge added to local-dev SKILL.
  - PR #7 — drought-scenario seed farmers + arid-biome aware NDVI sim + program-id doc fix.
- What is currently in progress:
  - None active in source. Roadmap next: first parametric-protocol integration (AMOCA-class) targeted Q2 2026.

## Decisions
- [2024-Q1] Drought-only oracle scope: composite score `weather × 0.4 + ndvi × 0.4 + history × 0.2`, approval threshold `composite ≥ 55`. Held as product invariant.
- [2024-Q1] Dual-validation architecture: off-chain AI recommends, on-chain Anchor enforces (score, amount, oracle authorization, pool state). AI cannot move funds.
- [2024-Q1] Solana over EVM for slot time, fee economics at $1–$50 policy scale, and public audit trail.
- [2024-Q1] M-of-N quorum + parameterized policy live on Devnet at `2tBU…gkfK`; single-oracle predecessor `971Z…ZjoF` is deprecated and must not be reintroduced.
- [2024-Q1] `ADMIN_PUBKEY` is intentionally set to the oracle pubkey for the hackathon deploy so the bridge can sign `initialize_subsidy_pool`; production deploys must move this to a separate admin/multisig.
- [2024-Q1] CI overrides `rust-toolchain.toml` (1.75.0) with `RUSTUP_TOOLCHAIN=stable` for `cargo check`/`clippy` only — BPF builds still use the pinned toolchain locally.

## Constraints
- NDVI data is simulated (deterministic per coordinates with arid-biome awareness). Real Sentinel/MODIS ingestion is roadmap (Q3 2026), not in source — do not present sim output as live satellite data.
- `farmers_db` and `evaluations_db` are in-memory in `agent/main.py`; every Railway redeploy or container restart wipes state. `POST /api/demo/seed` must be re-run after each redeploy.
- Both Solana MOCK mode and AI Fallback mode are silent successes in the UI. Verification must use the SSE log (`[LIVE] TX:` vs `[MOCK] TX:`) and `getSignatureStatuses` against Devnet RPC.
- Drought-scenario demo wallets (Aralkum `6zMppjRu…rY8LD8`, Karakum `7V9GTiEG…Ct76W`) must remain guaranteed-approve year-round via the arid-zone NDVI offset; they are the deterministic-payout pitch path.
- Composite scoring weights, approval threshold 55, and `max_amount_per_payout=1.5 SOL` are user-visible product copy — do not change without explicit approval.
- Do not weaken CORS, auth, oracle authorization, or pool/quorum guardrails for convenience. Do not expose `.env`, oracle keypair JSON, or Railway tokens in code, logs, or fixtures.

## Open Issues
- NDVI simulation gap vs roadmap claim of real Sentinel/MODIS — documented; ship blocker for mainnet beta.
- Silent MOCK/Fallback failure modes still depend on log inspection for detection — no UI surface yet.
- `rust-toolchain.toml` pin (1.75.0) is incompatible with transitive deps that require edition2024; CI works around it, but local BPF builds remain on the pinned toolchain.
- `MEMORY.md` did not exist before this session — historical decisions reconstructed from `README.md`, `.agents/skills/local-dev/SKILL.md`, and git log.
- No pre-commit hooks in repo (no `.pre-commit-config.yaml`, no `.husky/`, no `lefthook`); CI is the only gate.

## Next Steps
- 1. Replace simulated NDVI with real Sentinel/MODIS ingestion (Q3 2026 milestone) — design for at-least-once fetch and idempotency on the attestation side.
- 2. Surface Solana MOCK and AI Fallback modes in the dashboard verdict panel so silent-success failure modes are visible to operators and pitch viewers.
- 3. First parametric-protocol integration (AMOCA-class) targeted Q2 2026 — define the public oracle-read contract before integrating.

## Last Session
- Date: 2026-05-13
- Summary: Session Start Protocol run on a fresh clone. `MEMORY.md` was missing per GELOAGENT.md Memory Discipline; this file was created from repository evidence (`README.md`, `.agents/skills/local-dev/SKILL.md`, `.github/workflows/ci.yml`, git log). No code changes.
- Primary signal: `MEMORY.md` now present at repo root, aligned with README, SKILL, and Devnet deployment state.
- Secondary signals: ruff/pytest/npm/cargo CI workflows confirmed unchanged; no lint or build run was needed for a documentation-only change.
