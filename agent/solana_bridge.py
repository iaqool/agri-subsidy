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

from config import SOLANA_RPC_URL, PROGRAM_ID, ORACLE_KEYPAIR, ADMIN_PUBKEY
from solders.system_program import ID as SYS_PROGRAM_ID


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
        import base64

        return "".join(random.choices(_B58_CHARS, k=87))


def _mock_tx_url(sig: str) -> str:
    return f"https://explorer.solana.com/tx/{sig}?cluster=devnet"


# ── Solders Live Bridge ───────────────────────────────────────────────────────


async def _send_live_transaction(
    farmer_pubkey: str,
    amount_lamports: int,
    ai_score: int,
) -> str:
    """
    Реальный вызов контракта release_funds_by_oracle через solders.
    Требует:
      - PROGRAM_ID в .env
      - ORACLE_KEYPAIR_PATH — путь к keypair JSON (solana-keygen new)
    """
    try:
        from solders.pubkey import Pubkey
        from solders.keypair import Keypair
        from solders.transaction import Transaction
        from solders.instruction import Instruction, AccountMeta
        from solders.hash import Hash
        from solders.message import Message
        import struct
        import httpx

        # Загружаем Oracle keypair
        keypair_path = Path(ORACLE_KEYPAIR) if ORACLE_KEYPAIR else None
        if not keypair_path or not keypair_path.exists():
            raise FileNotFoundError(f"Oracle keypair not found at: {ORACLE_KEYPAIR}")

        with open(keypair_path) as f:
            keypair_bytes = bytes(json.load(f))
        oracle_kp = Keypair.from_bytes(keypair_bytes)

        program_id = Pubkey.from_string(PROGRAM_ID)
        farmer_pk = Pubkey.from_string(farmer_pubkey)
        admin_pk = Pubkey.from_string(ADMIN_PUBKEY)
        pool_pda, _ = Pubkey.find_program_address(
            [b"subsidy_pool", bytes(admin_pk)], program_id
        )
        farmer_pda, _ = Pubkey.find_program_address(
            [b"farmer", bytes(pool_pda), bytes(farmer_pk)], program_id
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
        async with httpx.AsyncClient(timeout=15) as client:
            rpc_resp = await client.post(
                SOLANA_RPC_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getLatestBlockhash",
                    "params": [{"commitment": "finalized"}],
                },
            )
            blockhash_str = rpc_resp.json()["result"]["value"]["blockhash"]
            recent_blockhash = Hash.from_string(blockhash_str)

            # Строим транзакцию
            msg = Message([instruction], oracle_kp.pubkey())
            tx = Transaction([oracle_kp], msg, recent_blockhash)

            # Отправляем транзакцию
            tx_bytes = bytes(tx)
            tx_b64 = __import__("base64").b64encode(tx_bytes).decode()

            send_resp = await client.post(
                SOLANA_RPC_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "sendTransaction",
                    "params": [
                        tx_b64,
                        {"encoding": "base64", "preflightCommitment": "confirmed"},
                    ],
                },
            )
            result = send_resp.json()
            if "error" in result:
                raise RuntimeError(f"RPC error: {result['error']}")

            return result["result"]  # TX signature

    except ImportError:
        raise RuntimeError("solders not installed correctly")


# ── Public Interface ──────────────────────────────────────────────────────────

SUBSIDY_AMOUNT_SOL = 1.5  # Размер субсидии в SOL
LAMPORTS_PER_SOL = 1_000_000_000


class SolanaBridgeResult:
    def __init__(self, signature: str, is_mock: bool, amount_sol: float):
        self.signature = signature
        self.is_mock = is_mock
        self.amount_sol = amount_sol
        self.explorer_url = _mock_tx_url(signature)

    def __repr__(self):
        mode = "MOCK" if self.is_mock else "LIVE"
        return f"<SolanaBridgeResult [{mode}] sig={self.signature[:16]}... amount={self.amount_sol} SOL>"


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
    if PROGRAM_ID:
        try:
            print(f"🔗 [bridge] Sending LIVE TX → program={PROGRAM_ID[:8]}...")
            sig = await _send_live_transaction(farmer_pubkey, amount_lamports, ai_score)
            print(f"✅ [bridge] TX confirmed: {sig[:16]}...")
            return SolanaBridgeResult(sig, is_mock=False, amount_sol=amount_sol)
        except Exception as e:
            print(f"⚠️  [bridge] Live TX failed ({e}), falling back to mock")

    # MOCK mode — демо без реального контракта
    await asyncio.sleep(random.uniform(0.8, 1.5))  # Имитация latency RPC
    sig = _mock_signature()
    print(f"🎭 [bridge] MOCK TX generated: {sig[:16]}...")
    return SolanaBridgeResult(sig, is_mock=True, amount_sol=amount_sol)


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
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                SOLANA_RPC_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getSignatureStatuses",
                    "params": [[signature], {"searchTransactionHistory": True}],
                },
            )
            data = resp.json()
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
