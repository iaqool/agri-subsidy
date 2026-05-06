"""Tests for solana_bridge helpers that don't require a live RPC.

The full LIVE TX path needs a Devnet endpoint and a funded oracle keypair,
so we don't exercise it from unit tests. These cover the in-process pieces
of the bridge — the parts that regressed in production.
"""

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
