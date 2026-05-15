"""Tests for the operational monitoring module.

The module wraps Sentry SDK init + Discord webhook dispatch. All entry
points must be safe to call with the env vars unset (no-op) and must
swallow network errors so monitoring failures never leak into the user-
facing payout path. The PR #9 honesty contract (LIVE / MOCK / degraded
MOCK surfaced on the verdict) is independent of whether Discord / Sentry
land — these tests assert exactly that.
"""

import httpx
import pytest

import monitoring


# ─── Sentry init ─────────────────────────────────────────────────────────────


def test_init_sentry_noop_when_dsn_unset(monkeypatch):
    """Without SENTRY_DSN, init_sentry returns False and does not call
    sentry_sdk.init. This is the default on every CI run and every local
    smoke run — the boot path must not require a Sentry account.
    """
    monkeypatch.setattr(monitoring, "SENTRY_DSN", "")
    called = {"init": False}

    class _StubSdk:
        @staticmethod
        def init(**kwargs):
            called["init"] = True

    monkeypatch.setitem(__import__("sys").modules, "sentry_sdk", _StubSdk)
    assert monitoring.init_sentry() is False
    assert called["init"] is False


def test_init_sentry_initialises_with_expected_kwargs(monkeypatch):
    """With SENTRY_DSN set, init_sentry forwards the DSN + environment to
    sentry_sdk.init with traces_sample_rate=0 (error-only, no perf spans)
    and send_default_pii=False (no request bodies → no wallet leakage).
    """
    monkeypatch.setattr(monitoring, "SENTRY_DSN", "https://pub@sentry.example/1")
    monkeypatch.setattr(monitoring, "SENTRY_ENVIRONMENT", "staging")

    captured = {}

    class _StubSdk:
        @staticmethod
        def init(**kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(__import__("sys").modules, "sentry_sdk", _StubSdk)
    assert monitoring.init_sentry() is True
    assert captured["dsn"] == "https://pub@sentry.example/1"
    assert captured["environment"] == "staging"
    assert captured["traces_sample_rate"] == 0.0
    assert captured["send_default_pii"] is False


def test_init_sentry_survives_missing_sdk(monkeypatch):
    """If sentry-sdk is not installed (slim deploy), init_sentry must
    return False instead of crashing the agent at boot.
    """
    monkeypatch.setattr(monitoring, "SENTRY_DSN", "https://pub@sentry.example/1")

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            raise ImportError("sentry_sdk not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert monitoring.init_sentry() is False


# ─── Discord notify — degraded MOCK ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_degraded_mock_noop_when_webhook_unset(monkeypatch):
    """Without DISCORD_WEBHOOK_URL, notify_degraded_mock is a fast no-op
    that returns False — and crucially does not perform any HTTP request.
    """
    monkeypatch.setattr(monitoring, "DISCORD_WEBHOOK_URL", "")
    called = {"post": False}

    class _ShouldNotPost:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, *a, **kw):
            called["post"] = True
            raise AssertionError("should not POST when webhook unset")

    monkeypatch.setattr(httpx, "AsyncClient", _ShouldNotPost)
    result = await monitoring.notify_degraded_mock(
        wallet="A" * 44,
        signature="sig" * 10,
        failure_reason="all RPCs down",
        amount_sol=0.1,
    )
    assert result is False
    assert called["post"] is False


@pytest.mark.asyncio
async def test_notify_degraded_mock_posts_payload(monkeypatch):
    """With DISCORD_WEBHOOK_URL set, the webhook receives a payload with the
    expected structure (single embed, fields contain wallet / signature /
    failure_reason / amount). We assert the shape, not the cosmetics — the
    operator-facing copy can drift without breaking the test.
    """
    monkeypatch.setattr(
        monitoring, "DISCORD_WEBHOOK_URL", "https://discord.example/webhook"
    )
    captured = {}

    class _ScriptedClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            req = httpx.Request("POST", url)
            return httpx.Response(204, request=req)

    monkeypatch.setattr(httpx, "AsyncClient", _ScriptedClient)
    result = await monitoring.notify_degraded_mock(
        wallet="WALLET" + "X" * 38,
        signature="MOCK_SIG_ABCDEFG",
        failure_reason="All 2 RPC endpoints failed",
        amount_sol=0.25,
        evaluation_id="eval_42",
    )
    assert result is True
    assert captured["url"] == "https://discord.example/webhook"
    body = captured["json"]
    # Username is configurable but defaults to "Dala Alert".
    assert body["username"] == monitoring.DISCORD_ALERT_USERNAME
    assert len(body["embeds"]) == 1
    embed = body["embeds"][0]
    assert "Degraded MOCK" in embed["title"]
    # Flatten field values to one string for substring assertions.
    flat = " | ".join(f["value"] for f in embed["fields"])
    assert "WALLETXX" in flat
    assert "MOCK_SIG_ABCDEFG" in flat
    assert "All 2 RPC endpoints failed" in flat
    assert "0.25 SOL" in flat
    assert "eval_42" in flat


@pytest.mark.asyncio
async def test_notify_degraded_mock_swallows_network_errors(monkeypatch):
    """If Discord is down / throttling / DNS-broken, the notifier must NOT
    raise. The fire-and-forget caller would only log a warning anyway, but
    we still guarantee the boundary so a hot path can't be poisoned.
    """
    monkeypatch.setattr(
        monitoring, "DISCORD_WEBHOOK_URL", "https://discord.example/webhook"
    )

    class _FailingClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, *a, **kw):
            raise httpx.ConnectError("discord down")

    monkeypatch.setattr(httpx, "AsyncClient", _FailingClient)
    result = await monitoring.notify_degraded_mock(
        wallet="A" * 44,
        signature="MOCK",
        failure_reason="rpc fail",
        amount_sol=0.5,
    )
    assert result is False


@pytest.mark.asyncio
async def test_notify_degraded_mock_swallows_5xx(monkeypatch):
    """A 500/429 from Discord (rate limit / outage) returns False without
    raising. The hot path keeps moving.
    """
    monkeypatch.setattr(
        monitoring, "DISCORD_WEBHOOK_URL", "https://discord.example/webhook"
    )

    class _ServerErrorClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json):
            req = httpx.Request("POST", url)
            return httpx.Response(503, request=req)

    monkeypatch.setattr(httpx, "AsyncClient", _ServerErrorClient)
    result = await monitoring.notify_degraded_mock(
        wallet="A" * 44,
        signature="MOCK",
        failure_reason="rpc fail",
        amount_sol=0.5,
    )
    assert result is False


# ─── Discord notify — critical exception ────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_critical_noop_when_webhook_unset(monkeypatch):
    monkeypatch.setattr(monitoring, "DISCORD_WEBHOOK_URL", "")
    result = await monitoring.notify_critical(
        where="eval_1", error=RuntimeError("boom")
    )
    assert result is False


@pytest.mark.asyncio
async def test_notify_critical_posts_with_error_class_and_message(monkeypatch):
    """The critical payload must surface both the exception class name AND
    its message so an operator can triage from the Discord channel alone
    (Sentry has the full stack — Discord is the at-a-glance alert).
    """
    monkeypatch.setattr(
        monitoring, "DISCORD_WEBHOOK_URL", "https://discord.example/webhook"
    )
    captured = {}

    class _ScriptedClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json):
            captured["json"] = json
            req = httpx.Request("POST", url)
            return httpx.Response(204, request=req)

    monkeypatch.setattr(httpx, "AsyncClient", _ScriptedClient)
    result = await monitoring.notify_critical(
        where="eval_99", error=ValueError("schema mismatch on row 17")
    )
    assert result is True
    flat = " | ".join(
        f["value"] for f in captured["json"]["embeds"][0]["fields"]
    )
    assert "ValueError" in flat
    assert "schema mismatch on row 17" in flat
    assert "eval_99" in flat


# ─── Truncation / safety ─────────────────────────────────────────────────────


def test_truncate_short_string_unchanged():
    assert monitoring._truncate("hello") == "hello"


def test_truncate_long_string_appends_ellipsis():
    long = "x" * 2000
    out = monitoring._truncate(long, limit=10)
    assert len(out) == 10
    assert out.endswith("\u2026")


def test_truncate_at_exact_limit_unchanged():
    """Boundary check: a value of exactly `limit` characters must pass
    through verbatim. The original Discord cap is 1024 chars per field —
    we use 900 with headroom for JSON quoting.
    """
    s = "y" * 900
    assert monitoring._truncate(s) == s


# ─── fire_and_forget ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fire_and_forget_schedules_task():
    """fire_and_forget must hand the coroutine to the running event loop and
    return a Task so the caller can opt to await in tests.
    """
    ran = {"yes": False}

    async def _work():
        ran["yes"] = True

    task = monitoring.fire_and_forget(_work())
    assert task is not None
    await task
    assert ran["yes"] is True


def test_fire_and_forget_no_loop_returns_none():
    """Outside an event loop, fire_and_forget returns None instead of
    raising — defensive in case it's ever called from a sync context.
    """

    async def _work():
        return None

    coro = _work()
    try:
        result = monitoring.fire_and_forget(coro)
        assert result is None
    finally:
        # Close the coroutine we never awaited so pytest doesn't warn.
        coro.close()


# ─── Sanity check on payload builders (no network, no monkeypatch) ───────────


def test_degraded_payload_includes_pr9_disclaimer():
    """The embed description must explicitly say `total_disbursed_sol` was
    NOT credited. This is the PR #9 honesty contract — if an operator sees
    a "Degraded MOCK fired" alert, the channel must not let them assume
    the payout still went through.
    """
    payload = monitoring._build_degraded_mock_payload(
        wallet="W" * 44,
        signature="MOCK",
        failure_reason="rpc down",
        amount_sol=0.1,
    )
    desc = payload["embeds"][0]["description"]
    assert "total_disbursed_sol" in desc
    assert "NOT credited" in desc


def test_degraded_payload_omits_evaluation_id_when_missing():
    """evaluation_id is optional (older callers may not pass it). When
    omitted, the field is not present in the embed — no empty placeholder.
    """
    payload = monitoring._build_degraded_mock_payload(
        wallet="W" * 44,
        signature="MOCK",
        failure_reason="rpc down",
        amount_sol=0.1,
    )
    names = [f["name"] for f in payload["embeds"][0]["fields"]]
    assert "evaluation_id" not in names
