"""Operational monitoring — Sentry error capture + Discord webhook alerts.

Both backends are opt-in via environment variables (`SENTRY_DSN` and
`DISCORD_WEBHOOK_URL`) and stay completely no-op when unset. Same activation
pattern as `DATABASE_URL` (PR #19) and `SOLANA_RPC_URLS` (PR #21): the code
lands once, the host turns it on per deploy.

All Discord-bound calls are fire-and-forget (`asyncio.create_task`) with a
short timeout and a defensive try/except around the actual HTTP POST — a
flaky Discord webhook MUST NOT slow down or break a payout. The PR #9
honesty contract is unaffected: the `SolanaBridgeResult` returned to the API
caller still carries `is_degraded` / `failure_reason`; monitoring is a pure
side-effect.

Credentials (DSN, webhook URL) never appear in log lines — only the
boolean success state of each emission, so operator log volume can grow
without leaking the secret to Sentry / GitHub / Vercel build output.
"""

import asyncio
import logging
from typing import Optional

import httpx

from config import (
    SENTRY_DSN,
    SENTRY_ENVIRONMENT,
    DISCORD_WEBHOOK_URL,
    DISCORD_ALERT_USERNAME,
)

logger = logging.getLogger(__name__)

# Discord embed colours (decimal). Matches the dashboard's amber/red chip
# semantics from PR #13 so an operator scanning the channel can correlate
# directly to what the UI is showing.
_COLOR_DEGRADED = 0xE0A800  # amber — degraded MOCK fallback fired
_COLOR_CRITICAL = 0xDC3545  # red — unhandled exception in eval pipeline

# Discord caps embed field values at 1024 chars; keep some headroom for
# JSON quoting overhead.
_FIELD_VALUE_MAX = 900

_DISCORD_TIMEOUT_SECONDS = 3.0


def init_sentry() -> bool:
    """Initialise Sentry SDK if SENTRY_DSN is set.

    Returns True if Sentry was initialised, False if skipped (no DSN or the
    SDK isn't importable). `traces_sample_rate=0` keeps us on error-only
    tracking — no performance instrumentation, no spans, lowest overhead.
    The FastAPI / ASGI integration is auto-enabled when sentry_sdk is
    init'd before the app starts handling requests, which is what the
    `@app.on_event("startup")` hook ensures.
    """
    if not SENTRY_DSN:
        logger.info("[monitoring] Sentry disabled (SENTRY_DSN unset)")
        return False
    try:
        import sentry_sdk
    except ImportError:
        # sentry-sdk is in requirements.txt; this branch is for environments
        # that installed the agent without the optional extra (e.g. a slimmed
        # container). We log and continue so the API still serves traffic.
        logger.warning("[monitoring] sentry-sdk not importable; Sentry skipped")
        return False

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        # Error-only tracking. Performance / spans are explicitly off to keep
        # the per-request overhead at "tag + capture exception" only.
        traces_sample_rate=0.0,
        # Don't ship request bodies to Sentry — they can contain wallet
        # addresses and (theoretically) farmer PII; the stack trace is
        # enough for triage.
        send_default_pii=False,
    )
    logger.info(
        "[monitoring] Sentry initialised environment=%s", SENTRY_ENVIRONMENT
    )
    return True


def _truncate(value: str, limit: int = _FIELD_VALUE_MAX) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "\u2026"


async def _post_to_discord(payload: dict) -> bool:
    """POST a Discord webhook payload. Returns True on 2xx, False otherwise.

    Never raises — the caller (fire-and-forget task) only logs the result.
    """
    if not DISCORD_WEBHOOK_URL:
        return False
    try:
        async with httpx.AsyncClient(timeout=_DISCORD_TIMEOUT_SECONDS) as client:
            resp = await client.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as exc:
        # Defensive: any network / serialisation / timeout error is swallowed
        # so monitoring failures cannot bubble into the payout pipeline.
        # Log the exception class only — never the webhook URL or DSN.
        logger.warning(
            "[monitoring] discord_post error=%s",
            type(exc).__name__,
        )
        return False
    ok = 200 <= resp.status_code < 300
    if not ok:
        logger.warning(
            "[monitoring] discord_post non_2xx status=%s", resp.status_code
        )
    return ok


def _build_degraded_mock_payload(
    *,
    wallet: str,
    signature: str,
    failure_reason: Optional[str],
    amount_sol: float,
    evaluation_id: Optional[str] = None,
) -> dict:
    """Build the Discord webhook JSON for a degraded-MOCK event.

    The PR #13 honesty contract names "degraded MOCK" specifically — a
    response where `PROGRAM_ID` was set (LIVE intended) but the on-chain
    call failed and the bridge fell back to a fake signature. The dashboard
    paints this with a red chip; the Discord alert mirrors that semantic.
    """
    fields = [
        {
            "name": "wallet",
            "value": f"`{_truncate(wallet)}`",
            "inline": True,
        },
        {
            "name": "amount",
            "value": f"{amount_sol} SOL (NOT settled on-chain)",
            "inline": True,
        },
        {
            "name": "signature (MOCK)",
            "value": f"`{_truncate(signature)}`",
            "inline": False,
        },
    ]
    if failure_reason:
        fields.append(
            {
                "name": "failure_reason",
                "value": _truncate(failure_reason),
                "inline": False,
            }
        )
    if evaluation_id:
        fields.append(
            {
                "name": "evaluation_id",
                "value": f"`{_truncate(evaluation_id)}`",
                "inline": True,
            }
        )
    return {
        "username": DISCORD_ALERT_USERNAME,
        "embeds": [
            {
                "title": "Degraded MOCK fired",
                "description": (
                    "`release_subsidy` intended LIVE TX but fell back to a "
                    "simulated signature. `total_disbursed_sol` was NOT "
                    "credited (PR #9 contract). Investigate before the next "
                    "payout."
                ),
                "color": _COLOR_DEGRADED,
                "fields": fields,
            }
        ],
    }


def _build_critical_payload(*, where: str, error: BaseException) -> dict:
    """Build the Discord webhook JSON for an unhandled-error event.

    Sentry captures the stack trace via its FastAPI integration; Discord
    gets a short, operator-readable note so a human can react in the
    channel without opening Sentry.
    """
    reason = f"{type(error).__name__}: {error}"
    return {
        "username": DISCORD_ALERT_USERNAME,
        "embeds": [
            {
                "title": "Eval pipeline exception",
                "description": (
                    "Unhandled exception inside `_run_evaluation`. "
                    "Sentry will carry the full stack; this is the at-a-glance "
                    "alert. Farmer status was reset to `pending`."
                ),
                "color": _COLOR_CRITICAL,
                "fields": [
                    {"name": "where", "value": _truncate(where), "inline": True},
                    {
                        "name": "error",
                        "value": _truncate(reason),
                        "inline": False,
                    },
                ],
            }
        ],
    }


async def notify_degraded_mock(
    *,
    wallet: str,
    signature: str,
    failure_reason: Optional[str],
    amount_sol: float,
    evaluation_id: Optional[str] = None,
) -> bool:
    """Send a Discord alert for a degraded-MOCK event.

    Safe to call from a fire-and-forget task — never raises, no-op when the
    webhook URL is unset. Returns True on a 2xx Discord response, False
    otherwise (including the disabled / unconfigured case).
    """
    if not DISCORD_WEBHOOK_URL:
        return False
    payload = _build_degraded_mock_payload(
        wallet=wallet,
        signature=signature,
        failure_reason=failure_reason,
        amount_sol=amount_sol,
        evaluation_id=evaluation_id,
    )
    ok = await _post_to_discord(payload)
    logger.info("[monitoring] discord_alert kind=degraded_mock sent=%s", ok)
    return ok


async def notify_critical(*, where: str, error: BaseException) -> bool:
    """Send a Discord alert for an unhandled exception in the eval pipeline.

    Mirrors `notify_degraded_mock` — never raises, no-op without webhook.
    """
    if not DISCORD_WEBHOOK_URL:
        return False
    payload = _build_critical_payload(where=where, error=error)
    ok = await _post_to_discord(payload)
    logger.info("[monitoring] discord_alert kind=critical sent=%s", ok)
    return ok


def fire_and_forget(coro) -> Optional[asyncio.Task]:
    """Schedule a monitoring coroutine without awaiting it.

    Returns the Task so callers may attach a callback in tests, but the
    common case is fire-and-forget: the event loop runs the task in the
    background while the payout response is sent back to the dashboard.
    Returns None if there is no running event loop (defensive).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    return loop.create_task(coro)
