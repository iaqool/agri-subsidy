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
  - PR #17 — fly.io fallback deploy artifacts (dormant `fly.toml` + `agent/FLY_MIGRATION.md`) wired up after Railway's free-plan policy started rejecting builds.
  - PR #16 — rent-exempt guard on pool drain + `.ok_or` on every checked counter. `debit_pool_credit_wallet` helper added in `programs/agri_subsidy/src/lib.rs`. Adversarial mocha tests live but local-only (toolchain triangle). **Deployed to Devnet at slot 462313048 with this session's upgrade.**
  - PR #15 — anchor mocha harness wired up (`contracts/package.json`, `Anchor.toml [scripts]/[test]`). Full mocha suite stays local until anchor 0.30+/agave 2.x bump removes the toolchain triangle. Documented in `contracts/README.md`.
  - PR #14 — README headline-honesty patch: clarified `quorum=1` demo state vs M-of-N source build so judges don't read it as already-running M-of-N.
  - PR #13 — surface MOCK / DEGRADED-MOCK / Fallback in API + UI; `total_disbursed_sol` only credits on LIVE TX, MOCK/DEGRADED expose `is_mock`/`is_degraded`/`failure_reason` fields and matching chips.
  - PR #12 — first `MEMORY.md`.
  - PR #11 — deploy M-of-N quorum build to Devnet (original deploy, predates rent-guard).
  - PR #10 / #9 / #8 / #7 — see earlier memory entries for context.
- What is currently in progress:
  - None active in source. Roadmap next: first parametric-protocol integration (AMOCA-class) targeted Q2 2026.

## Decisions
- [2024-Q1] Drought-only oracle scope: composite score `weather × 0.4 + ndvi × 0.4 + history × 0.2`, approval threshold `composite ≥ 55`. Held as product invariant.
- [2024-Q1] Dual-validation architecture: off-chain AI recommends, on-chain Anchor enforces (score, amount, oracle authorization, pool state). AI cannot move funds.
- [2024-Q1] Solana over EVM for slot time, fee economics at $1–$50 policy scale, and public audit trail.
- [2024-Q1] M-of-N quorum + parameterized policy live on Devnet at `2tBU…gkfK`; single-oracle predecessor `971Z…ZjoF` is deprecated and must not be reintroduced.
- [2024-Q1] `ADMIN_PUBKEY` is intentionally set to the oracle pubkey for the hackathon deploy so the bridge can sign `initialize_subsidy_pool`; production deploys must move this to a separate admin/multisig.
- [2024-Q1] CI overrides `rust-toolchain.toml` (1.75.0) with `RUSTUP_TOOLCHAIN=stable` for `cargo check`/`clippy` only — BPF builds still use the pinned toolchain locally.
- [2026-05-14] BPF build toolchain: agave 2.1.21 (platform-tools v1.43, rustc 1.79 internally) is the floor for compiling anchor 0.29 program code on Devin VMs. Solana 1.18.x + 2.0.x bundle rustc 1.75-dev, which cannot compile borsh 1.6+. Host cargo `Cargo.lock` v4 must be manually downgraded to v3 (sed) before invoking `cargo-build-sbf`. Documented in `contracts/README.md` toolchain-triangle section; the file regenerates after build, so commit nothing.
- [2026-05-14] PR #16 rent-guard verified live on Devnet: smoke-test payout `4P67WQ5g6Z6wz6woSCSuT5ya5s6su4BU2WMQ8EgVJDGXKYhhycshL3F7Uy1dqiKa3DoP5ksDXVdRKcMC9Ea261nX` (finalized slot 462314276) drained pool from 4.00248 SOL to 2.50248 SOL with 1.5 SOL payout and stayed above rent-exempt minimum, exactly as `debit_pool_credit_wallet` enforces.

## Constraints
- NDVI data is simulated (deterministic per coordinates with arid-biome awareness). Real Sentinel/MODIS ingestion is roadmap (Q3 2026), not in source — do not present sim output as live satellite data.
- `farmers_db` and `evaluations_db` are in-memory in `agent/main.py`; every Railway redeploy or container restart wipes state. `POST /api/demo/seed` must be re-run after each redeploy.
- Both Solana MOCK mode and AI Fallback mode are silent successes in the UI. Verification must use the SSE log (`[LIVE] TX:` vs `[MOCK] TX:`) and `getSignatureStatuses` against Devnet RPC.
- Drought-scenario demo wallets (Aralkum `6zMppjRu…rY8LD8`, Karakum `7V9GTiEG…Ct76W`) must remain guaranteed-approve year-round via the arid-zone NDVI offset; they are the deterministic-payout pitch path.
- Composite scoring weights, approval threshold 55, and `max_amount_per_payout=1.5 SOL` are user-visible product copy — do not change without explicit approval.
- Do not weaken CORS, auth, oracle authorization, or pool/quorum guardrails for convenience. Do not expose `.env`, oracle keypair JSON, or Railway tokens in code, logs, or fixtures.

## Open Issues
- **Railway down**: as of 2026-05-14 the primary backend `https://agri-subsidy-production.up.railway.app/` returns 404 ("Free plan deployments must be serverless"). Service has `Enable Serverless` toggled on but builds 022e7140 and prior keep failing. Fix: manual Redeploy on Railway, OR activate the dormant fly.io fallback per `agent/FLY_MIGRATION.md`.
- NDVI simulation gap vs roadmap claim of real Sentinel/MODIS — documented; ship blocker for mainnet beta.
- Silent MOCK/Fallback failure modes are now surfaced in the UI/API after PR #13 (`is_mock`, `is_degraded`, `failure_reason`).
- `rust-toolchain.toml` pin (1.75.0) is incompatible with transitive deps that require edition2024; CI works around it for `cargo check`/`clippy`, BPF builds need agave 2.1.21 + manual Cargo.lock v3 downgrade.
- Open questions from the council audit (blocking quorum cutover): (1) who holds `pool.authority`, (2) AMOCA/SeedFlow/NOVA outreach status, (3) `total_disbursed_sol` semantics, (4) oracle keypair sharing/M-of-N machine plan, (5) disbursement ledger retention, (6) demo wallet retirement plan post real-NDVI. See `/home/ubuntu/post-merge-audit.md` for full list. Owner: user.
- No pre-commit hooks in repo (no `.pre-commit-config.yaml`, no `.husky/`, no `lefthook`); CI is the only gate.

## Next Steps
- 1. **Bring backend back up**: either manual Railway Redeploy with serverless mode confirmed, or activate fly.io fallback per `agent/FLY_MIGRATION.md`. Until then, `agri-subsidy.vercel.app` shows a broken UI even though the Devnet program + pool are fully operational.
- 2. **Record 2-min demo video** using `/home/ubuntu/demo-video-script.md`. Live Devnet TX evidence already available (signature `4P67WQ5g6Z…`).
- 3. **Answer the 6 open audit questions** so quorum cutover (`update_quorum` from 1 → 2) can be scheduled with a second oracle keypair on a separate machine.
- 4. **Move program upgrade authority to Squads multisig** (P2 from solana.new audit). Right now `GPu53YV…wHdxN` is a single-key SPOF.
- 5. **Durable storage**: Postgres (Supabase or fly.io managed) for `farmers_db` + `evaluations_db` + an audit-ledger of disbursements (currently process-memory; redeploy wipes everything).
- 6. **RPC fallback in `solana_bridge.py`**: Helius primary + QuickNode secondary, with health-check failover. Today a Devnet RPC blip silently degrades the bridge to MOCK.
- 7. Replace simulated NDVI with real Sentinel/MODIS ingestion (Q3 2026 roadmap) — design for at-least-once fetch and idempotency on the attestation side.
- 8. First parametric-protocol integration (AMOCA-class) targeted Q2 2026 — define the public oracle-read contract before integrating.

## Last Session
- Date: 2026-05-14
- Summary: Three sessions chained. Session 1: council 3-lens synthesis (Product / Production-Readiness / Engineering) shipped PRs #13, #14, #15. Session 2: solana.new toolkit audit found two extra findings (rent-exempt guard + checked arithmetic), shipped PR #16; CI 6/6 green. Session 3: Railway broke under free-plan serverless policy; opened PR #17 with dormant fly.io fallback as insurance, then received the Devnet upgrade-authority keypair and rolled out PR #16 to Devnet end-to-end. `cargo-build-sbf` failed on agave 1.18.17 / 2.0.21 due to platform-tools rustc 1.75-dev; agave 2.1.21 (platform-tools v1.43) cleared the build. Program upgraded at slot 462313048 (TX `29SNAYSLGUeqp4Qc62vyaaSji1BsnPKPYbc5wcTcF53YvcyPb3Bhup456o5or3yJTGAq7adzVe5JtYqWPuP5XW26`), pool funded with 4 SOL (TX `D3JWAiWFZVzcuZscop1AFG8VeLgwdqKkHkvAeNGWYXvtQx7spKnqQbeU6SWyBt6JP46isvvstoZdFFb3jUtegUH`), and a fresh-wallet payout (`Fs5veBwKriHTE6eJ3APxm1e4nFspT7HjK8qKzmQ6AoKw`) confirmed the rent-guard live on chain (TX `4P67WQ5g6Z6wz6woSCSuT5ya5s6su4BU2WMQ8EgVJDGXKYhhycshL3F7Uy1dqiKa3DoP5ksDXVdRKcMC9Ea261nX`, finalized slot 462314276, pool drained 4.00248 → 2.50248 SOL above rent floor).
- Primary signal: PR #16 code path exercised on Devnet without errors; finalized 1.5 SOL payout received; pool stayed above rent-exempt minimum exactly as `debit_pool_credit_wallet` enforces.
- Secondary signals: CI green on PR #16 (6/6) + PR #17 (6/6); two demo wallets (Aralkum, Karakum) returned `AlreadyProcessed` (0x1779) from earlier on-chain evaluations and now require a fresh wallet for new payouts — expected, not a bug. AI agent ran in fallback mode (no OpenAI key on this VM); on prod with `OPENAI_API_KEY` set, the same flow produces `is_fallback: false`.
- Audit deliverables on `~`: `/home/ubuntu/council-synthesis.md`, `/home/ubuntu/post-merge-audit.md`, `/home/ubuntu/demo-video-script.md`.
