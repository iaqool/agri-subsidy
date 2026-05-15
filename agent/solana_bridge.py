"""
Solana Bridge — Python → Solana Devnet

Отправляет транзакцию `release_funds_by_oracle` через solders.
Работает в двух режимах:
  - LIVE:  PROGRAM_ID задан → реальный on-chain вызов
  - MOCK:  PROGRAM_ID пуст → возвращает фейковый TX для демо
"""

import asyncio
import hashlib
import json
import random
from pathlib import Path

import httpx

from config import (
    SOLANA_RPC_URL,
    SOLANA_RPC_ENDPOINTS,
    PROGRAM_ID,
    ORACLE_KEYPAIR,
    ORACLE_KEYPAIR_JSON,
    ADMIN_PUBKEY,
)
from solders.system_program import ID as SYS_PROGRAM_ID


# ── RPC fallback helper ───────────────────────────────────────────────────────

# HTTP status codes that indicate the endpoint is unhealthy rather than the
# request being malformed. 408/425 are added belt+suspenders for proxies that
# stamp them on transient timeouts.
_RPC_FAILOVER_STATUS = {408, 425, 429, 500, 502, 503, 504}


def _rpc_endpoints() -> list[str]:
    """Return the live endpoint list at call time so tests can monkeypatch
    SOLANA_RPC_ENDPOINTS / SOLANA_RPC_URL on the bridge module.
    """
    if SOLANA_RPC_ENDPOINTS:
        return SOLANA_RPC_ENDPOINTS
    return [SOLANA_RPC_URL] if SOLANA_RPC_URL else []


async def _rpc_post(client, payload: dict, *, op: str) -> dict:
    """POST a JSON-RPC payload to the first healthy Solana RPC endpoint.

    Iterates SOLANA_RPC_ENDPOINTS in order, failing over to the next URL on
    network errors (httpx.HTTPError) or HTTP 408/425/429/5xx — the symptoms
    of an unhealthy provider, not a bad request. JSON-level RPC errors
    (`{"error": ...}` in a 200 response — e.g. "blockhash not found",
    "invalid params") are returned as-is so callers preserve the existing
    semantics: those are logic errors that retrying on another node will
    not heal, and propagating them lets release_subsidy fall back to
    degraded MOCK with an honest failure_reason (PR #9 contract).

    Solana dedupes signed transactions by signature, so retrying
    sendTransaction across endpoints with the same blockhash is idempotent.

    If every endpoint fails, raises RuntimeError with the per-endpoint
    causes joined together so the operator log line carries enough state
    to triage without a live debugger.

    Args:
        client: shared httpx.AsyncClient (reuses its timeout / limits).
        payload: JSON-RPC body, e.g. {"jsonrpc": "2.0", "method": ...}.
        op: short label (e.g. "getLatestBlockhash") used in fail-over
            log lines so operators can grep RPC_FALLOVER by call site.
    """
    endpoints = _rpc_endpoints()
    if not endpoints:
        raise RuntimeError(f"No RPC endpoint configured for {op}")

    errors: list[str] = []
    for idx, url in enumerate(endpoints):
        try:
            resp = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            reason = f"{type(exc).__name__}: {exc}"[:200]
            print(
                f"[bridge] RPC_FALLOVER op={op} endpoint=#{idx} reason={reason}"
            )
            errors.append(f"#{idx}: {reason}")
            continue

        if resp.status_code in _RPC_FAILOVER_STATUS:
            reason = f"HTTP {resp.status_code}"
            print(
                f"[bridge] RPC_FALLOVER op={op} endpoint=#{idx} reason={reason}"
            )
            errors.append(f"#{idx}: {reason}")
            continue

        return resp.json()

    raise RuntimeError(
        f"All {len(endpoints)} RPC endpoints failed for {op}: "
        + " | ".join(errors)
    )


# ── Mock TX Generator ─────────────────────────────────────────────────────────

_B58_CHARS = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _anchor_discriminator(instruction_name: str) -> bytes:
    return hashlib.sha256(f"global:{instruction_name}".encode("utf-8")).digest()[:8]


def _mock_signature() -> str:
    """Генерирует псевдо-Base58 подпись транзакции."""
    try:
        from solders.signature import Signature
        import os

        return str(Signature.from_bytes(os.urandom(64)))
    except ImportError:

        return "".join(random.choices(_B58_CHARS, k=87))


def _mock_tx_url(sig: str) -> str:
    return f"https://explorer.solana.com/tx/{sig}?cluster=devnet"


# ── Solders Live Bridge ───────────────────────────────────────────────────────


def _load_oracle_keypair():
    """Загружает Oracle keypair: сперва из ORACLE_KEYPAIR_JSON, иначе из файла."""
    from solders.keypair import Keypair

    if ORACLE_KEYPAIR_JSON:
        try:
            keypair_bytes = bytes(json.loads(ORACLE_KEYPAIR_JSON))
            return Keypair.from_bytes(keypair_bytes)
        except Exception as exc:
            raise ValueError(
                "Invalid ORACLE_KEYPAIR_JSON. Expected JSON array of 64 integers."
            ) from exc
    keypair_path = Path(ORACLE_KEYPAIR) if ORACLE_KEYPAIR else None
    if not keypair_path or not keypair_path.exists():
        raise FileNotFoundError(
            "Oracle keypair not found. Set ORACLE_KEYPAIR_JSON "
            "or valid ORACLE_KEYPAIR_PATH."
        )
    with open(keypair_path) as f:
        keypair_bytes = bytes(json.load(f))
    return Keypair.from_bytes(keypair_bytes)


async def _account_exists(client, pubkey_str: str) -> bool:
    """Проверяет через getAccountInfo, существует ли PDA на Devnet."""
    data = await _rpc_post(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [pubkey_str, {"encoding": "base64"}],
        },
        op="getAccountInfo",
    )
    return bool(data.get("result", {}).get("value"))


def _encode_string_borsh(s: str) -> bytes:
    """Borsh-style string: u32 little-endian length prefix + UTF-8 bytes."""
    import struct

    encoded = s.encode("utf-8")
    return struct.pack("<I", len(encoded)) + encoded


async def _send_register_farmer(
    client,
    oracle_kp,
    farmer_pk,
    farmer_pda,
    pool_pda,
    program_id,
    region_code: str,
) -> str:
    """Отправляет register_farmer(region_code) и ждёт подтверждения. Оракул платит ренту."""
    from solders.transaction import Transaction
    from solders.instruction import Instruction, AccountMeta
    from solders.hash import Hash
    from solders.message import Message
    import base64

    discriminator = _anchor_discriminator("register_farmer")
    data = discriminator + _encode_string_borsh(region_code[:32])

    accounts = [
        AccountMeta(pubkey=oracle_kp.pubkey(), is_signer=True, is_writable=True),  # payer
        AccountMeta(pubkey=farmer_pk, is_signer=False, is_writable=False),  # farmer_wallet
        AccountMeta(pubkey=farmer_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=pool_pda, is_signer=False, is_writable=True),
        AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
    ]
    instruction = Instruction(program_id=program_id, accounts=accounts, data=bytes(data))

    rpc_data = await _rpc_post(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getLatestBlockhash",
            "params": [{"commitment": "finalized"}],
        },
        op="getLatestBlockhash",
    )
    blockhash_str = rpc_data["result"]["value"]["blockhash"]
    recent_blockhash = Hash.from_string(blockhash_str)

    msg = Message([instruction], oracle_kp.pubkey())
    tx = Transaction([oracle_kp], msg, recent_blockhash)
    tx_b64 = base64.b64encode(bytes(tx)).decode()

    send_result = await _rpc_post(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [
                tx_b64,
                {"encoding": "base64", "preflightCommitment": "confirmed"},
            ],
        },
        op="sendTransaction",
    )
    if "error" in send_result:
        raise RuntimeError(f"register_farmer RPC error: {send_result['error']}")
    sig = send_result["result"]
    print(f"[bridge] register_farmer TX: {sig[:16]}...")

    # Ждём подтверждения, чтобы release_funds_by_oracle видела PDA.
    for _ in range(20):  # до ~10с
        await asyncio.sleep(0.5)
        status_data = await _rpc_post(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignatureStatuses",
                "params": [[sig], {"searchTransactionHistory": True}],
            },
            op="getSignatureStatuses",
        )
        st = status_data.get("result", {}).get("value", [None])[0]
        if st and st.get("confirmationStatus") in ("confirmed", "finalized"):
            return sig
        if st and st.get("err"):
            raise RuntimeError(f"register_farmer failed: {st['err']}")
    raise TimeoutError("register_farmer not confirmed within 10s")


async def _send_live_transaction(
    farmer_pubkey: str,
    amount_lamports: int,
    ai_score: int,
) -> str:
    """
    Реальный вызов контракта release_funds_by_oracle через solders.
    Требует:
      - PROGRAM_ID в .env
      - ORACLE_KEYPAIR_JSON (предпочтительно для cloud), либо
      - ORACLE_KEYPAIR_PATH — путь к keypair JSON (solana-keygen new)

    Если farmer PDA ещё не инициализирован на Devnet, сначала вызывает
    register_farmer (оракул платит rent), затем release_funds_by_oracle.
    """
    try:
        from solders.pubkey import Pubkey
        from solders.transaction import Transaction
        from solders.instruction import Instruction, AccountMeta
        from solders.hash import Hash
        from solders.message import Message
        import struct

        oracle_kp = _load_oracle_keypair()

        if not ADMIN_PUBKEY:
            raise ValueError("ADMIN_PUBKEY env var is required for LIVE TX (pool PDA seed).")

        program_id = Pubkey.from_string(PROGRAM_ID)
        farmer_pk = Pubkey.from_string(farmer_pubkey)
        admin_pk = Pubkey.from_string(ADMIN_PUBKEY)
        pool_pda, _ = Pubkey.find_program_address(
            [b"subsidy_pool", bytes(admin_pk)], program_id
        )
        farmer_pda, _ = Pubkey.find_program_address(
            [b"farmer", bytes(pool_pda), bytes(farmer_pk)], program_id
        )

        async with httpx.AsyncClient(timeout=15) as client:
            # Pre-flight: проверяем, зарегистрирован ли фермер на контракте.
            # На демо новые сид-фермеры живут только в in-memory базе бэкенда,
            # поэтому их PDA на Devnet пустые в первую эвалуацию.
            farmer_exists = await _account_exists(client, str(farmer_pda))
            if not farmer_exists:
                print("[bridge] Farmer PDA not found, registering on-chain...")
                await _send_register_farmer(
                    client, oracle_kp, farmer_pk, farmer_pda,
                    pool_pda, program_id, region_code="demo",
                )

            # Сериализация аргументов (borsh-like: little-endian)
            discriminator = _anchor_discriminator("release_funds_by_oracle")
            amount_bytes = struct.pack("<Q", amount_lamports)  # u64 LE
            score_bytes = struct.pack("<B", ai_score)  # u8

            data = discriminator + amount_bytes + score_bytes

            # Аккаунты для инструкции
            accounts = [
                AccountMeta(pubkey=oracle_kp.pubkey(), is_signer=True, is_writable=True),
                AccountMeta(pubkey=farmer_pk, is_signer=False, is_writable=True),
                AccountMeta(pubkey=farmer_pda, is_signer=False, is_writable=True),
                AccountMeta(pubkey=pool_pda, is_signer=False, is_writable=True),
                AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
            ]

            instruction = Instruction(
                program_id=program_id, accounts=accounts, data=bytes(data)
            )

            # Получаем свежий blockhash
            rpc_data = await _rpc_post(
                client,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getLatestBlockhash",
                    "params": [{"commitment": "finalized"}],
                },
                op="getLatestBlockhash",
            )
            blockhash_str = rpc_data["result"]["value"]["blockhash"]
            recent_blockhash = Hash.from_string(blockhash_str)

            # Строим транзакцию
            msg = Message([instruction], oracle_kp.pubkey())
            tx = Transaction([oracle_kp], msg, recent_blockhash)

            # Отправляем транзакцию
            import base64

            tx_bytes = bytes(tx)
            tx_b64 = base64.b64encode(tx_bytes).decode()

            send_result = await _rpc_post(
                client,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "sendTransaction",
                    "params": [
                        tx_b64,
                        {"encoding": "base64", "preflightCommitment": "confirmed"},
                    ],
                },
                op="sendTransaction",
            )
            if "error" in send_result:
                raise RuntimeError(f"RPC error: {send_result['error']}")

            return send_result["result"]  # TX signature

    except ImportError:
        raise RuntimeError("solders not installed correctly")


# ── Public Interface ──────────────────────────────────────────────────────────

SUBSIDY_AMOUNT_SOL = 1.5  # Размер субсидии в SOL
LAMPORTS_PER_SOL = 1_000_000_000


class SolanaBridgeResult:
    def __init__(
        self,
        signature: str,
        is_mock: bool,
        amount_sol: float,
        is_degraded: bool = False,
        failure_reason: str | None = None,
    ):
        self.signature = signature
        self.is_mock = is_mock
        self.amount_sol = amount_sol
        self.explorer_url = _mock_tx_url(signature)
        # is_degraded is True only when PROGRAM_ID was set (LIVE intended) but
        # the on-chain call failed and we silently fell back to a fake TX. This
        # is the failure mode that broke production in PR #9: the dashboard
        # showed an Explorer link, total_disbursed_sol grew, and nothing was
        # actually settled on Devnet. failure_reason carries the short error
        # string for operator/audit surfaces.
        self.is_degraded = is_degraded
        self.failure_reason = failure_reason

    def __repr__(self):
        if self.is_degraded:
            mode = "DEGRADED"
        elif self.is_mock:
            mode = "MOCK"
        else:
            mode = "LIVE"
        return (
            f"<SolanaBridgeResult [{mode}] sig={self.signature[:16]}... "
            f"amount={self.amount_sol} SOL>"
        )


async def release_subsidy(
    farmer_pubkey: str,
    ai_score: int,
    amount_sol: float = SUBSIDY_AMOUNT_SOL,
) -> SolanaBridgeResult:
    """
    Основная точка входа для отправки субсидии фермеру.

    Args:
        farmer_pubkey: Base58 публичный ключ кошелька фермера
        ai_score:      Скор ИИ 0–100 (записывается в контракт)
        amount_sol:    Размер субсидии в SOL

    Returns:
        SolanaBridgeResult с TX signature и ссылкой на Explorer
    """
    amount_lamports = int(amount_sol * LAMPORTS_PER_SOL)

    # LIVE mode — если контракт задеплоен
    degraded_reason: str | None = None
    if PROGRAM_ID:
        try:
            print(f"[bridge] Sending LIVE TX -> program={PROGRAM_ID[:8]}...")
            sig = await _send_live_transaction(farmer_pubkey, amount_lamports, ai_score)
            print(f"[bridge] TX confirmed: {sig[:16]}...")
            return SolanaBridgeResult(sig, is_mock=False, amount_sol=amount_sol)
        except Exception as e:
            degraded_reason = f"{type(e).__name__}: {e}"[:200]
            # Explicit prefix so operators can grep for production-degraded MOCK
            # vs the legitimate demo MOCK (PROGRAM_ID empty).
            print(f"[bridge] LIVE_TX_FAILED program={PROGRAM_ID[:8]}... reason={degraded_reason}")

    # MOCK mode — либо demo (PROGRAM_ID пуст), либо degraded fallback после ошибки LIVE
    await asyncio.sleep(random.uniform(0.8, 1.5))  # Имитация latency RPC
    sig = _mock_signature()
    if degraded_reason is not None:
        print(f"[bridge] DEGRADED_MOCK TX generated: {sig[:16]}... reason={degraded_reason}")
    else:
        print(f"[bridge] MOCK TX generated: {sig[:16]}...")
    return SolanaBridgeResult(
        sig,
        is_mock=True,
        amount_sol=amount_sol,
        is_degraded=degraded_reason is not None,
        failure_reason=degraded_reason,
    )


async def get_transaction_status(signature: str) -> dict:
    """
    Проверяет статус транзакции на Devnet.
    В mock-режиме всегда возвращает 'confirmed'.
    """
    if not PROGRAM_ID or len(signature) < 80:
        # Mock response
        return {
            "status": "confirmed",
            "slot": random.randint(200_000_000, 250_000_000),
            "confirmations": random.randint(10, 100),
            "is_mock": True,
        }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            data = await _rpc_post(
                client,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getSignatureStatuses",
                    "params": [[signature], {"searchTransactionHistory": True}],
                },
                op="getSignatureStatuses",
            )
            tx_status = data["result"]["value"][0]
            if tx_status is None:
                return {"status": "not_found", "is_mock": False}
            return {
                "status": tx_status.get("confirmationStatus", "unknown"),
                "slot": tx_status.get("slot"),
                "confirmations": tx_status.get("confirmations"),
                "err": tx_status.get("err"),
                "is_mock": False,
            }
    except Exception as e:
        return {"status": "error", "error": str(e), "is_mock": False}
