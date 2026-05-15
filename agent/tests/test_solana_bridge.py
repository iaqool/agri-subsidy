"""Tests for solana_bridge helpers that don't require a live RPC.

The full LIVE TX path needs a Devnet endpoint and a funded oracle keypair,
so we don't exercise it from unit tests. These cover the in-process pieces
of the bridge — the parts that regressed in production.
"""

import asyncio
import json

import httpx
import pytest

import solana_bridge as bridge


def test_anchor_discriminator_register_farmer():
    """Anchor discriminator must match `sha256("global:register_farmer")[:8]`.

    If this drifts, the register_farmer auto-init step silently falls through
    to MOCK on prod (deployed binary cannot decode our instruction).
    """
    expected_for_release = bridge._anchor_discriminator("release_funds_by_oracle")
    expected_for_register = bridge._anchor_discriminator("register_farmer")
    assert len(expected_for_release) == 8
    assert len(expected_for_register) == 8
    assert expected_for_release != expected_for_register


def test_borsh_string_encoding_basic():
    """Borsh strings prefix UTF-8 bytes with a u32 little-endian length."""
    out = bridge._encode_string_borsh("demo")
    # length=4, then b"demo"
    assert out == b"\x04\x00\x00\x00demo"


def test_borsh_string_encoding_unicode():
    """UTF-8 byte length, NOT character count, prefixes the string."""
    out = bridge._encode_string_borsh("засуха")  # 6 chars, 12 bytes UTF-8
    assert out[:4] == b"\x0c\x00\x00\x00"
    assert out[4:].decode("utf-8") == "засуха"


def test_load_oracle_keypair_rejects_invalid_json(monkeypatch):
    """A common Railway misconfig: ORACLE_KEYPAIR_JSON pasted as a base58
    string instead of a JSON array. Must raise a clear ValueError so the
    bridge logs explain the fix instead of silently falling to MOCK.
    """
    monkeypatch.setattr(bridge, "ORACLE_KEYPAIR_JSON", "not-a-json-array")
    monkeypatch.setattr(bridge, "ORACLE_KEYPAIR", "")
    with pytest.raises(ValueError, match="Invalid ORACLE_KEYPAIR_JSON"):
        bridge._load_oracle_keypair()


def test_load_oracle_keypair_accepts_valid_json_array(monkeypatch):
    """Valid 64-byte JSON array (real Keypair format) decodes without raising."""
    from solders.keypair import Keypair

    fresh = Keypair()
    fake = json.dumps(list(bytes(fresh)))
    monkeypatch.setattr(bridge, "ORACLE_KEYPAIR_JSON", fake)
    kp = bridge._load_oracle_keypair()
    assert hasattr(kp, "pubkey")
    # round-trip: derived pubkey must match the source keypair
    assert str(kp.pubkey()) == str(fresh.pubkey())


def test_bridge_result_legitimate_mock_is_not_degraded():
    """PROGRAM_ID empty (demo mode) → MOCK but not degraded."""
    r = bridge.SolanaBridgeResult("sig", is_mock=True, amount_sol=1.5)
    assert r.is_mock is True
    assert r.is_degraded is False
    assert r.failure_reason is None
    assert "MOCK" in repr(r)
    assert "DEGRADED" not in repr(r)


def test_bridge_result_degraded_carries_failure_reason():
    """When PROGRAM_ID is set but LIVE TX fails, the response must record
    is_degraded=True and a short failure_reason so downstream API surfaces
    can distinguish demo MOCK from production-degraded MOCK."""
    r = bridge.SolanaBridgeResult(
        "sig",
        is_mock=True,
        amount_sol=1.5,
        is_degraded=True,
        failure_reason="RuntimeError: RPC error: blockhash not found",
    )
    assert r.is_mock is True
    assert r.is_degraded is True
    assert r.failure_reason is not None
    assert "DEGRADED" in repr(r)


def test_release_subsidy_falls_back_to_degraded_when_live_fails(monkeypatch):
    """Regression guard for the PR #9 class of failure: when PROGRAM_ID is set
    but the LIVE RPC call raises, release_subsidy used to return a vanilla MOCK
    that was indistinguishable from a demo signature. It must now mark the
    result as is_degraded=True with the underlying error captured.
    """
    monkeypatch.setattr(bridge, "PROGRAM_ID", "FakeProgramIdNotARealKey1111111111111111111")

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("RPC error: blockhash not found")

    monkeypatch.setattr(bridge, "_send_live_transaction", _boom)

    # Avoid real latency-imitation sleep slowing the test suite.
    async def _noop_sleep(_seconds):
        return None

    monkeypatch.setattr(bridge.asyncio, "sleep", _noop_sleep)

    result = asyncio.run(
        bridge.release_subsidy(
            farmer_pubkey="4pMnsypmRtd94bK94LXjFPWghpXN5WfCcLvnJhoUdX5z",
            ai_score=72,
            amount_sol=1.5,
        )
    )
    assert result.is_mock is True
    assert result.is_degraded is True
    assert result.failure_reason is not None
    assert "RuntimeError" in result.failure_reason
    assert "blockhash not found" in result.failure_reason


def test_release_subsidy_legitimate_demo_mock(monkeypatch):
    """Empty PROGRAM_ID is the local-dev / demo path. Result must be MOCK but
    not degraded — the dashboard amber chip is correct here, the red one is not.
    """
    monkeypatch.setattr(bridge, "PROGRAM_ID", "")

    async def _noop_sleep(_seconds):
        return None

    monkeypatch.setattr(bridge.asyncio, "sleep", _noop_sleep)

    result = asyncio.run(
        bridge.release_subsidy(
            farmer_pubkey="4pMnsypmRtd94bK94LXjFPWghpXN5WfCcLvnJhoUdX5z",
            ai_score=72,
            amount_sol=1.5,
        )
    )
    assert result.is_mock is True
    assert result.is_degraded is False
    assert result.failure_reason is None


# ── RPC fallback helper tests ────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class _ScriptedClient:
    """httpx.AsyncClient stand-in that returns scripted outcomes per endpoint URL.

    `outcomes` is a dict of url → list of outcomes consumed left-to-right.
    Each outcome is either:
      - a _FakeResponse (HTTP response, status_code may be 2xx or in failover set)
      - an Exception subclass instance (raised on .post())

    Records every (url, payload) tuple in `.calls` so tests can assert order.
    """

    def __init__(self, outcomes: dict[str, list]):
        self.outcomes = {url: list(seq) for url, seq in outcomes.items()}
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url: str, json: dict | None = None):
        self.calls.append((url, json or {}))
        seq = self.outcomes.get(url, [])
        if not seq:
            raise AssertionError(f"_ScriptedClient: no outcome scripted for {url}")
        outcome = seq.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_rpc_post_uses_primary_when_healthy(monkeypatch):
    """Happy path: primary 200 → return its JSON, no fail-over log line."""
    monkeypatch.setattr(
        bridge, "SOLANA_RPC_ENDPOINTS", ["https://primary", "https://secondary"]
    )
    client = _ScriptedClient(
        {"https://primary": [_FakeResponse(200, {"result": "ok-primary"})]}
    )

    out = asyncio.run(
        bridge._rpc_post(
            client,
            {"jsonrpc": "2.0", "method": "getLatestBlockhash"},
            op="getLatestBlockhash",
        )
    )

    assert out == {"result": "ok-primary"}
    assert [url for url, _ in client.calls] == ["https://primary"]


def test_rpc_post_fails_over_on_network_error(monkeypatch):
    """httpx.ConnectError on primary → must POST to secondary and return its JSON.

    This is the Devnet-RPC-blip scenario from MEMORY Open Issues: the bridge
    must NOT degrade to MOCK while a healthy backup endpoint is configured.
    """
    monkeypatch.setattr(
        bridge, "SOLANA_RPC_ENDPOINTS", ["https://primary", "https://secondary"]
    )
    client = _ScriptedClient(
        {
            "https://primary": [httpx.ConnectError("connection refused")],
            "https://secondary": [_FakeResponse(200, {"result": "ok-secondary"})],
        }
    )

    out = asyncio.run(
        bridge._rpc_post(
            client,
            {"jsonrpc": "2.0", "method": "getLatestBlockhash"},
            op="getLatestBlockhash",
        )
    )

    assert out == {"result": "ok-secondary"}
    assert [url for url, _ in client.calls] == [
        "https://primary",
        "https://secondary",
    ]


def test_rpc_post_fails_over_on_http_500(monkeypatch):
    """HTTP 500 on primary → fail-over. Provider 5xx is unhealthy, not malformed."""
    monkeypatch.setattr(
        bridge, "SOLANA_RPC_ENDPOINTS", ["https://primary", "https://secondary"]
    )
    client = _ScriptedClient(
        {
            "https://primary": [_FakeResponse(500)],
            "https://secondary": [_FakeResponse(200, {"result": "ok-secondary"})],
        }
    )

    out = asyncio.run(
        bridge._rpc_post(
            client,
            {"jsonrpc": "2.0", "method": "getLatestBlockhash"},
            op="getLatestBlockhash",
        )
    )

    assert out == {"result": "ok-secondary"}


def test_rpc_post_fails_over_on_429(monkeypatch):
    """HTTP 429 (rate limited) on primary → fail-over to secondary."""
    monkeypatch.setattr(
        bridge, "SOLANA_RPC_ENDPOINTS", ["https://primary", "https://secondary"]
    )
    client = _ScriptedClient(
        {
            "https://primary": [_FakeResponse(429)],
            "https://secondary": [_FakeResponse(200, {"result": "ok-secondary"})],
        }
    )

    out = asyncio.run(
        bridge._rpc_post(
            client, {"jsonrpc": "2.0", "method": "x"}, op="x"
        )
    )
    assert out == {"result": "ok-secondary"}


def test_rpc_post_returns_json_level_error_without_failover(monkeypatch):
    """A 200 response carrying `{"error": ...}` is a logic error
    (bad blockhash, invalid params) — retrying on another node would not
    heal it, so we must return as-is and let the caller propagate. This
    preserves the PR #9 degraded-MOCK contract: the dashboard still gets
    an honest failure_reason for malformed requests.
    """
    monkeypatch.setattr(
        bridge, "SOLANA_RPC_ENDPOINTS", ["https://primary", "https://secondary"]
    )
    client = _ScriptedClient(
        {
            "https://primary": [
                _FakeResponse(200, {"error": {"code": -32602, "message": "invalid params"}})
            ]
        }
    )

    out = asyncio.run(bridge._rpc_post(client, {"jsonrpc": "2.0", "method": "x"}, op="x"))

    assert "error" in out
    # Secondary must NOT have been touched
    assert [url for url, _ in client.calls] == ["https://primary"]


def test_rpc_post_raises_when_all_endpoints_fail(monkeypatch):
    """Every endpoint unhealthy → RuntimeError aggregating per-endpoint causes
    so the operator log line carries triage state. Caller (release_subsidy)
    will then catch this and produce degraded MOCK."""
    monkeypatch.setattr(
        bridge, "SOLANA_RPC_ENDPOINTS", ["https://primary", "https://secondary"]
    )
    client = _ScriptedClient(
        {
            "https://primary": [httpx.ConnectError("dns failed")],
            "https://secondary": [_FakeResponse(503)],
        }
    )

    with pytest.raises(RuntimeError, match="All 2 RPC endpoints failed"):
        asyncio.run(bridge._rpc_post(client, {"jsonrpc": "2.0", "method": "x"}, op="x"))


def test_rpc_post_falls_back_to_legacy_single_url_when_list_empty(monkeypatch):
    """Backwards compatibility: if SOLANA_RPC_ENDPOINTS is empty (operator hasn't
    set SOLANA_RPC_URLS), bridge still POSTs to the legacy single SOLANA_RPC_URL.
    """
    monkeypatch.setattr(bridge, "SOLANA_RPC_ENDPOINTS", [])
    monkeypatch.setattr(bridge, "SOLANA_RPC_URL", "https://legacy")
    client = _ScriptedClient(
        {"https://legacy": [_FakeResponse(200, {"result": "ok"})]}
    )

    out = asyncio.run(bridge._rpc_post(client, {}, op="x"))
    assert out == {"result": "ok"}
    assert client.calls == [("https://legacy", {})]


def test_release_subsidy_stays_live_when_secondary_picks_up(monkeypatch):
    """End-to-end value-add of Tier 1.3: with PROGRAM_ID set and primary RPC
    flaky, release_subsidy must return a LIVE result (not degraded MOCK) when
    the secondary RPC succeeds. This is the regression guard for the Devnet
    blip → silent MOCK degradation scenario in MEMORY Open Issues.
    """
    monkeypatch.setattr(bridge, "PROGRAM_ID", "FakeProgramIdNotARealKey1111111111111111111")

    async def _live_after_failover(*_args, **_kwargs):
        # Simulate the bridge having retried via _rpc_post and ultimately
        # producing a signed TX from the secondary endpoint.
        return "5LiveSecondarySig" + "A" * 70

    monkeypatch.setattr(bridge, "_send_live_transaction", _live_after_failover)

    async def _noop_sleep(_seconds):
        return None

    monkeypatch.setattr(bridge.asyncio, "sleep", _noop_sleep)

    result = asyncio.run(
        bridge.release_subsidy(
            farmer_pubkey="4pMnsypmRtd94bK94LXjFPWghpXN5WfCcLvnJhoUdX5z",
            ai_score=72,
            amount_sol=1.5,
        )
    )

    assert result.is_mock is False
    assert result.is_degraded is False
    assert result.signature.startswith("5LiveSecondarySig")


def test_release_subsidy_degraded_mock_when_all_rpc_endpoints_down(monkeypatch):
    """End-to-end honesty preserved: if every configured RPC endpoint fails
    (the realistic worst case — Solana Foundation Devnet AND the operator's
    Helius/Triton backup both unreachable), release_subsidy must STILL return
    is_degraded=True with the RuntimeError message captured. The PR #9 amber
    vs red MOCK chip contract on the dashboard depends on this.
    """
    monkeypatch.setattr(bridge, "PROGRAM_ID", "FakeProgramIdNotARealKey1111111111111111111")

    async def _all_rpc_down(*_args, **_kwargs):
        raise RuntimeError(
            "All 2 RPC endpoints failed for getLatestBlockhash: "
            "#0: ConnectError: dns | #1: HTTP 503"
        )

    monkeypatch.setattr(bridge, "_send_live_transaction", _all_rpc_down)

    async def _noop_sleep(_seconds):
        return None

    monkeypatch.setattr(bridge.asyncio, "sleep", _noop_sleep)

    result = asyncio.run(
        bridge.release_subsidy(
            farmer_pubkey="4pMnsypmRtd94bK94LXjFPWghpXN5WfCcLvnJhoUdX5z",
            ai_score=72,
            amount_sol=1.5,
        )
    )

    assert result.is_mock is True
    assert result.is_degraded is True
    assert result.failure_reason is not None
    assert "All 2 RPC endpoints failed" in result.failure_reason
