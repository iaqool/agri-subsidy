# MEMORY.md

## Project
- Name: Dala Network — Drought Oracle Layer for Solana (`iaqool/agri-subsidy`).
- Goal: Drought-specific oracle on Solana that turns NDVI + weather + history into Anchor-enforced parametric payouts. Subscribers: parametric insurance protocols, reinsurers, public farmer-relief programs.
- Current stage: **Post-hackathon hardening.** Project advanced to Colosseum startup battle on the strength of the Devnet-live M-of-N build; user no longer needs the demo video. New goal is to push the project as close to "production-grade for serious investor / partner conversations" as possible.

## Strategic Shift (2026-05-14)
- Old north star: ship a credible hackathon demo (LIVE Devnet TX, honest MOCK chips, deployed M-of-N source). **Done.** PR #16 is live on chain, smoke-test payout `4P67WQ5g6Z…` finalized.
- New north star: production-grade engineering posture for investor / parametric-protocol due diligence. Target grade: **B+ → A−** on the post-merge-audit rubric.
- Roadmap tiers (see `/home/ubuntu/post-merge-audit.md` for the full rubric):
  - **Tier 1 — production basics:** durable storage, RPC fallback, real 2-of-2 quorum on chain, Railway-or-fly.io brought back up.
  - **Tier 2 — operations & trust:** Squads multisig under upgrade authority, Sentry + Discord error monitoring, anchor 0.30 + agave 2.x bump that finally puts mocha into CI.
  - **Tier 3 — differentiation:** real Sentinel/MODIS NDVI ingestion replacing the simulator; first parametric-protocol (AMOCA-class) integration with a public oracle-read contract.
- User declined the $5/mo fly.io spend and skipped the multisig keys question for now, so the work plan is biased toward zero-infra, code-only PRs first.
- **Tier 1.2 durable storage — done** (PR #19, merged 2026-05-15). SQLAlchemy 2.0 async, opt-in via `DATABASE_URL`; `sqlite+aiosqlite:///./agri.db` is the zero-infra default and a `postgresql+asyncpg://…` URL is the same code path for hosted Postgres. The disbursement ledger has `UNIQUE(signature)` so retries cannot inflate `total_disbursed_sol`. Production still has to actually **set** `DATABASE_URL` on whichever backend host comes back up.
- Current focus: **Tier 1.3 — RPC fallback** (next zero-infra Tier-1 item). Tier 1.1 (Railway-or-fly.io backend back up) and Tier 1.4 (real 2-of-2 quorum cutover) both depend on the user (Railway/fly.io action + a second oracle keypair on a separate machine) and stay parked until those inputs are available.

## Current Status
- What is already working:
  - Anchor M-of-N quorum build deployed to Devnet at `2tBU1bHZiydZGvcj3Dr5Sj3qQFDbQMrmCkYQt9SXgkfK` with parameterized policy, oracle registry, and idempotent attestation flow.
  - Subsidy pool PDA `AxnVgXUfeDk7nXXjhjvVuWPEvxh2SXBbDieUxfvJ64KL` initialized with `min_score=55`, `max_amount_per_payout=1.5 SOL`, `quorum=1` (demo).
  - FastAPI backend (`agent/`) with OpenAI streaming evaluation, rule-based fallback agent, NDVI simulator with arid-biome offset, OpenWeather integration, Solana bridge with live + MOCK modes.
  - React 19 + Vite dashboard (`dashboard/`) deployed on Vercel (https://agri-subsidy.vercel.app/), SSE streaming of AI reasoning, drought-scenario demo flag.
  - CORS allows Vercel prod + preview origins; `register_farmer` auto-init on first evaluation; AI verdict fallthrough fix.
  - Backend tests + CI: ruff, pytest (agent), npm lint + build (dashboard), `cargo +stable check`/`clippy` (contracts) via `.github/workflows/ci.yml`.
  - Local-dev SKILL at `.agents/skills/local-dev/SKILL.md` covers demo flow, silent-MOCK/Fallback detection, Devnet pool bootstrap procedure, and the `DATABASE_URL` switch.
  - Durable storage opt-in via `DATABASE_URL` (`agent/db.py`): SQLAlchemy 2.0 async, three tables (`farmers`, `evaluations`, `disbursements`), startup hydrates `farmers_db` from the persisted snapshot, `/api/stats` reads counters from SQL when enabled. `DATABASE_URL` unset stays a complete no-op so the legacy in-memory path keeps working for tests and quick local runs.
- What was recently finished:
  - PR #19 — durable storage for farmers / evaluations / disbursement ledger (SQLAlchemy 2.0 async, `DATABASE_URL`-gated, append-only ledger with `UNIQUE(signature)`). 73/73 tests green; behaviour unchanged unless `DATABASE_URL` is set.
  - PR #18 — MEMORY.md refresh recording the live PR #16 Devnet deploy, BPF toolchain triangle (agave 2.1.21 + Cargo.lock v3 downgrade), Railway-down status, and the hackathon → post-hackathon-hardening Strategic Shift.
  - PR #17 — fly.io fallback deploy artifacts (dormant `fly.toml` + `agent/FLY_MIGRATION.md`) wired up after Railway's free-plan policy started rejecting builds.
  - PR #16 — rent-exempt guard on pool drain + `.ok_or` on every checked counter. `debit_pool_credit_wallet` helper added in `programs/agri_subsidy/src/lib.rs`. Adversarial mocha tests live but local-only (toolchain triangle). **Deployed to Devnet at slot 462313048 with this session's upgrade.**
  - PR #15 — anchor mocha harness wired up (`contracts/package.json`, `Anchor.toml [scripts]/[test]`). Full mocha suite stays local until anchor 0.30+/agave 2.x bump removes the toolchain triangle. Documented in `contracts/README.md`.
  - PR #14 — README headline-honesty patch: clarified `quorum=1` demo state vs M-of-N source build so judges don't read it as already-running M-of-N.
  - PR #13 — surface MOCK / DEGRADED-MOCK / Fallback in API + UI; `total_disbursed_sol` only credits on LIVE TX, MOCK/DEGRADED expose `is_mock`/`is_degraded`/`failure_reason` fields and matching chips.
  - PR #12 — first `MEMORY.md`.
  - PR #11 — deploy M-of-N quorum build to Devnet (original deploy, predates rent-guard).
  - PR #10 / #9 / #8 / #7 — see earlier memory entries for context.
- What is currently in progress:
  - None active in source. Tier 1.3 (RPC fallback) is the next planned zero-infra PR; Tier 1.1 / 1.4 are user-blocked (see Strategic Shift).

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
- `farmers_db` and `evaluations_db` are in-memory by default in `agent/main.py`. They become durable when `DATABASE_URL` is set (PR #19); until the deployment host actually exports that env var, every Railway / fly.io / container restart still wipes state and `POST /api/demo/seed` has to be re-run.
- The MOCK/Fallback honesty contract from PR #13 is load-bearing: `total_disbursed_sol` only credits LIVE TX, and the dashboard's amber / red Simulated-TX chips distinguish demo MOCK from degraded MOCK from LIVE. Do not regress these without explicit approval. Verification on prod still checks the SSE log (`[LIVE] TX:` vs `[MOCK] TX:`) and `getSignatureStatuses` against Devnet RPC.
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
- 1. **Bring backend back up and set `DATABASE_URL`**: either manual Railway Redeploy with serverless mode confirmed, or activate fly.io fallback per `agent/FLY_MIGRATION.md`. Whichever host wins, point `DATABASE_URL` at a persistent volume / managed Postgres so PR #19's durable storage is actually load-bearing in prod; until then the audit ledger still resets on redeploy.
- 2. **Tier 1.3 — RPC fallback**: protect against single-RPC Devnet outages (next zero-infra, code-only PR; does not depend on user inputs).
- 3. **Answer the 6 open audit questions** so quorum cutover (`update_quorum` from 1 → 2) can be scheduled with a second oracle keypair on a separate machine.
- 4. **Move program upgrade authority to Squads multisig** (P2 from solana.new audit). Right now `GPu53YV…wHdxN` is a single-key SPOF.
- 5. Replace simulated NDVI with real Sentinel/MODIS ingestion (Q3 2026 roadmap) — design for at-least-once fetch and idempotency on the attestation side.
- 6. First parametric-protocol integration (AMOCA-class) targeted Q2 2026 — define the public oracle-read contract before integrating.

## Last Session
- Date: 2026-05-15
- Summary: Session Start Protocol on a fresh clone surfaced PR #18 (MEMORY refresh) and PR #19 (durable storage) as still-open at session start. User directed take-over and merge of PR #18 as-is (CI 6/6 green, no review changes). PR #19 was merged immediately after, retiring Tier 1.2 from the strategic-shift roadmap. This second refresh folds both into MEMORY: durable storage moves from “current focus” to “done”, the in-memory-DB constraint is rewritten as `DATABASE_URL`-opt-in, recent-PRs / next-steps lists are reordered, and Tier 1.3 (RPC fallback) is promoted to the new current focus since Tier 1.1 (host) and Tier 1.4 (quorum cutover) remain user-blocked.
- Primary signal: MEMORY.md now matches `main` post PR #19, no stale durable-storage references remain.
- Secondary signals: docs-only diff; CI sanity (ruff / pytest / npm lint+build / cargo check on the rest of the tree) expected green as nothing in `agent/`, `dashboard/`, `contracts/` changes.
- Audit deliverables (off-repo, on `~`): `/home/ubuntu/council-synthesis.md`, `/home/ubuntu/post-merge-audit.md`, `/home/ubuntu/demo-video-script.md`.
