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

# Optional comma-separated extra RPC endpoints used as fallbacks when
# SOLANA_RPC_URL is unhealthy (timeouts, HTTP 5xx, 429). Empty by default →
# the bridge keeps its single-RPC behaviour. Set e.g.
# SOLANA_RPC_URLS="https://devnet.helius-rpc.com/?api-key=XYZ,https://api.devnet.solana.com"
# on the host to activate fail-over without code changes.
_RPC_URLS_RAW = os.getenv("SOLANA_RPC_URLS", "")


def _parse_rpc_endpoints() -> list[str]:
    """Ordered, de-duplicated list of RPC endpoints. Primary first, then
    any extras from SOLANA_RPC_URLS (in order). Empty strings are dropped.
    """
    extras = [u.strip() for u in _RPC_URLS_RAW.split(",") if u.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for url in [SOLANA_RPC_URL, *extras]:
        if url and url not in seen:
            out.append(url)
            seen.add(url)
    return out


SOLANA_RPC_ENDPOINTS: list[str] = _parse_rpc_endpoints()

PROGRAM_ID = os.getenv("PROGRAM_ID", "")  # Заполнить после деплоя контракта
ORACLE_KEYPAIR = os.getenv(
    "ORACLE_KEYPAIR_PATH", ""
)  # Путь к keypair JSON (для bridge)
ORACLE_KEYPAIR_JSON = os.getenv(
    "ORACLE_KEYPAIR_JSON", ""
)  # JSON-массив байт keypair (для cloud deploy без файла)
ADMIN_PUBKEY = os.getenv("ADMIN_PUBKEY", "")

# ── Monitoring (opt-in, off by default) ──────────────────────────────────────
# All four variables follow the same pattern as DATABASE_URL / SOLANA_RPC_URLS:
# empty = monitoring disabled, set on the host to activate. Keep the values out
# of logs — DSN and webhook URL both carry credentials in their query string.
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "local")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_ALERT_USERNAME = os.getenv("DISCORD_ALERT_USERNAME", "Dala Alert")

if not OPENAI_API_KEY:
    print("[config] OPENAI_API_KEY not found - fallback mode will be used")
else:
    print("[config] OPENAI_API_KEY loaded (***)")

if not OPENWEATHER_API_KEY:
    print("[config] OPENWEATHER_API_KEY not found")
else:
    print("[config] OPENWEATHER_API_KEY loaded (***)")
