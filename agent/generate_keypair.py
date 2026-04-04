r"""
Этот скрипт запускается один раз для генерации Oracle keypair.
После запуска обновляет .env автоматически.

Запуск:
  C:\Users\USER\AppData\Local\Programs\Python\Python311\python.exe generate_keypair.py
"""
import json
import os
from pathlib import Path

from solders.keypair import Keypair

def main():
    # Генерируем новый Oracle keypair
    kp = Keypair()
    pubkey_str = str(kp.pubkey())

    print("=" * 55)
    print("🔑 Oracle Keypair Generated")
    print("=" * 55)
    print(f"  Public Key : {pubkey_str}")
    print(f"  Keypair saved to: oracle_keypair.json")
    print("=" * 55)

    # Сохраняем в oracle_keypair.json (формат совместим с solana-keygen)
    kp_bytes = list(bytes(kp))
    keypair_path = Path(__file__).parent / "oracle_keypair.json"
    with open(keypair_path, "w") as f:
        json.dump(kp_bytes, f)

    # Обновляем .env
    env_path = Path(__file__).parent / ".env"
    env_content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

    # Удаляем старые строки если есть
    lines = [l for l in env_content.splitlines()
             if not l.startswith("ORACLE_KEYPAIR_PATH=")
             and not l.startswith("ORACLE_PUBKEY=")]

    lines.append(f"ORACLE_KEYPAIR_PATH={keypair_path}")
    lines.append(f"ORACLE_PUBKEY={pubkey_str}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n✅ .env updated:")
    print(f"   ORACLE_KEYPAIR_PATH={keypair_path}")
    print(f"   ORACLE_PUBKEY={pubkey_str}")
    print()
    print("🪂 Next step — request Devnet airdrop:")
    print(f"   solana airdrop 2 {pubkey_str} --url devnet")
    print()
    print("Or request via browser:")
    print(f"   https://faucet.solana.com/?address={pubkey_str}")

if __name__ == "__main__":
    main()
