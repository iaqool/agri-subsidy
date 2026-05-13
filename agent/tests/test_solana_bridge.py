"""Tests for solana_bridge helpers that don't require a live RPC.

The full LIVE TX path needs a Devnet endpoint and a funded oracle keypair,
so we don't exercise it from unit tests. These cover the in-process pieces
of the bridge — the parts that regressed in production.
"""

import asyncio
import json

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
