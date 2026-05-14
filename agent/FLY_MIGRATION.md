# fly.io migration playbook (fallback for Railway free-plan changes)

This file is a **fallback** runbook. Primary backend deploy target is Railway
(`https://agri-subsidy-production.up.railway.app`). If Railway's free-plan
serverless mode keeps failing the build or otherwise blocks us, follow these
steps to bring the agent up on fly.io instead. No code changes are required —
the existing `Dockerfile` is portable.

## When to migrate

Migrate when one of the following is true:

- Railway builds fail repeatedly with policy errors (e.g. "Free plan
  deployments must be serverless") that can't be resolved with a single
  toggle/redeploy.
- Cold-start latency on Railway exceeds 10s and the demo SSE stream stalls.
- We need durable state (Postgres volume) and don't want to pay Railway's
  hobby tier.

## Prerequisites

- A fly.io account (free tier supports two `shared-cpu-1x` machines).
- `flyctl` installed locally: `curl -L https://fly.io/install.sh | sh`.
- The current Railway env values exported (we'll copy them as fly secrets).

## One-time setup

```bash
# Authenticate (opens browser)
fly auth login

# From repo root, switch into the agent folder
cd agent

# Create the fly app from the existing fly.toml.
# --no-deploy lets us wire secrets before the first build.
# --copy-config reuses fly.toml verbatim.
# Pick a unique app name (the default in fly.toml is "dala-agri-subsidy-agent").
fly launch --no-deploy --copy-config --name dala-agri-subsidy-agent

# Wire secrets (replace the right-hand sides with the real values).
# Use single quotes around ORACLE_KEYPAIR_JSON so the shell doesn't expand the
# JSON array.
fly secrets set \
  OPENAI_API_KEY='sk-...' \
  OPENWEATHER_API_KEY='...' \
  ORACLE_KEYPAIR_JSON='[1,2,3,...,64]' \
  ADMIN_PUBKEY='GPu53YVseFDgzVEWbTQqiRKFaY8RnciHEJQMn66wHdxN' \
  SOLANA_RPC_URL='https://api.devnet.solana.com' \
  CORS_ORIGINS='https://agri-subsidy.vercel.app,http://localhost:5173'

# First deploy
fly deploy
```

After `fly deploy` finishes, the URL will be printed
(typically `https://dala-agri-subsidy-agent.fly.dev`).

## Wire the frontend

Vercel deploy reads `VITE_API_BASE_URL` at build time, so a code-less env flip
is all that's needed:

1. Vercel dashboard → project `agri-subsidy` → Settings → Environment Variables.
2. Update `VITE_API_BASE_URL` to `https://<your-fly-app>.fly.dev`
   for the `Production` and `Preview` environments.
3. Deployments → click the latest production deploy → `…` → **Redeploy**
   (uncheck "Use existing Build Cache" so the new env var is baked in).

The dashboard will start hitting fly.io within ~60s after the new build
finishes. No code change required because the dashboard reads
`import.meta.env.VITE_API_BASE_URL` at build time.

## Smoke test

```bash
# 1. Health check
curl -s https://<your-fly-app>.fly.dev/health
# expected: {"status":"ok","farmers_count":0}

# 2. Seed demo farmers (in-memory; reset on every cold start)
curl -s -X POST https://<your-fly-app>.fly.dev/api/demo/seed

# 3. Load the frontend, click an arid-biome farmer, watch the SSE log for the
#    "LIVE TX" chip (not "MOCK" or "Fallback"). Click through to the explorer
#    URL and confirm From: pool PDA, To: farmer wallet, ~1.5 SOL, confirmed.
```

If any of these fail, check `fly logs --app <your-fly-app>` for the equivalent
of the Railway logs documented in `.agents/skills/local-dev/SKILL.md`. The
same MOCK / DEGRADED / Fallback signals from PR #13 surface in fly logs
unchanged.

## Rolling back to Railway

If we ever want to go back, flip `VITE_API_BASE_URL` in Vercel to the Railway
URL and redeploy the frontend. The fly.io app can stay parked at zero
machines (cost: $0 because `min_machines_running = 0`).

## Cost expectations

| Item | Free tier | Paid (if exceeded) |
|------|-----------|--------------------|
| 2× `shared-cpu-1x` machines, 256MB each | included | $1.94/mo each |
| 3GB persistent volume | included | $0.15/GB/mo |
| 160GB egress | included | $0.02/GB |

For the demo / hackathon workload (a handful of evaluations / day), we stay
inside the free tier.

## Open follow-ups

- Switch `farmers_db` / `evaluations_db` to a durable store (Postgres on the
  same fly.io account, or Supabase) so cold starts don't wipe seeded farmers.
  Tracked in the post-merge audit roadmap, P3.
- Add a fly.io GitHub Action for auto-deploys on push to `main`. Currently
  `fly deploy` is manual on purpose so we don't redeploy on unrelated changes.
