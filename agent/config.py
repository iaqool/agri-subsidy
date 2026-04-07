import os
from pathlib import Path
from dotenv import load_dotenv

# Явно указываем путь к .env относительно этого файла
_env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_path, override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

# Solana Devnet settings
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")
PROGRAM_ID = os.getenv("PROGRAM_ID", "")  # Заполнить после деплоя контракта
ORACLE_KEYPAIR = os.getenv(
    "ORACLE_KEYPAIR_PATH", ""
)  # Путь к keypair JSON (для bridge)
ADMIN_PUBKEY = os.getenv("ADMIN_PUBKEY", "")

# Debug: проверяем загрузку при старте
if not OPENAI_API_KEY:
    print("[config] OPENAI_API_KEY not found - fallback mode will be used")
else:
    print(f"[config] OPENAI_API_KEY loaded ({OPENAI_API_KEY[:12]}...)")

if not OPENWEATHER_API_KEY:
    print("[config] OPENWEATHER_API_KEY not found")
else:
    print("[config] OPENWEATHER_API_KEY loaded")
