import os
import hashlib
import struct
from dotenv import load_dotenv
from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.system_program import ID as SYS_PROGRAM_ID
from solders.transaction import Transaction

load_dotenv()

DEFAULT_ADMIN_KEYPAIR_PATH = os.path.expanduser("~/.config/solana/id.json")
ADMIN_KEYPAIR_PATH = os.getenv("ADMIN_KEYPAIR_PATH", DEFAULT_ADMIN_KEYPAIR_PATH)

# Инициализация клиента (Devnet)
client = Client("https://api.devnet.solana.com")

# Подтягиваем ключ админа (тот, с которого деплоили контракт)
if not os.path.exists(ADMIN_KEYPAIR_PATH):
    raise FileNotFoundError(
        f"Admin keypair not found: {ADMIN_KEYPAIR_PATH}. "
        "Set ADMIN_KEYPAIR_PATH in agent/.env to the deployer keypair JSON."
    )

with open(ADMIN_KEYPAIR_PATH, "r") as f:
    admin_keypair = Keypair.from_json(f.read())

PROGRAM_ID = Pubkey.from_string(os.getenv("PROGRAM_ID"))
ORACLE_PUBKEY = Pubkey.from_string(os.getenv("ORACLE_PUBKEY"))

FARMERS = [
    Pubkey.from_string("4pMnsypmRtd94bK94LXjFPWghpXN5WfCcLvnJhoUdX5z"),
    Pubkey.from_string("EeqwDr7kNxp4y9vj4MaQijv4BmgAm3WXArzZM5WikD6U"),
    Pubkey.from_string("CHaGvsfMx5YKE3mYq7huQM6keRN2UUsfhwAZMypWw7KC"),
    Pubkey.from_string("FZA62o7rNFBmx5g1hFyCmpRYWhpxAHTiqnYUaRd7EGfL"),
    Pubkey.from_string("8jm7bVG8CiqxDmohHUuMk5R3WZkucTrXPUDsDhzvLQ3p"),
]

REGIONS = [
    "Kostanay Region",
    "North Kazakhstan Region",
    "Akmola Region",
    "Aktobe Region",
    "Almaty Region",
]


# Утилита для вычисления дискриминатора Anchor
def get_discriminator(instruction_name: str) -> bytes:
    preimage = f"global:{instruction_name}".encode("utf-8")
    return hashlib.sha256(preimage).digest()[:8]


def serialize_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<I", len(encoded)) + encoded


def setup():
    print(f"Admin: {admin_keypair.pubkey()}")

    # 1. Вычисляем PDA для пула и дергаем initialize_subsidy_pool
    print("Инициализируем пул субсидий...")
    pool_pda, pool_bump = Pubkey.find_program_address(
        [b"subsidy_pool", bytes(admin_keypair.pubkey())], PROGRAM_ID
    )

    init_data = get_discriminator("initialize_subsidy_pool") + struct.pack(
        "<B", pool_bump
    )
    init_ix = Instruction(
        program_id=PROGRAM_ID,
        data=init_data,
        accounts=[
            AccountMeta(
                pubkey=admin_keypair.pubkey(), is_signer=True, is_writable=True
            ),
            AccountMeta(pubkey=ORACLE_PUBKEY, is_signer=False, is_writable=False),
            AccountMeta(pubkey=pool_pda, is_signer=False, is_writable=True),
            AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
        ],
    )

    init_blockhash = client.get_latest_blockhash().value.blockhash
    tx_init = Transaction.new_signed_with_payer(
        [init_ix], admin_keypair.pubkey(), [admin_keypair], init_blockhash
    )

    try:
        resp = client.send_transaction(tx_init)
        print(f"Pool initialized successfully. Tx: {resp.value}")
    except Exception as e:
        print(f"Pool may already exist or initialization failed: {e}")

    # 2. Регистрируем 5 фермеров
    for farmer, region in zip(FARMERS, REGIONS):
        print(f"Регистрируем фермера: {farmer} ({region})")
        farmer_pda, _ = Pubkey.find_program_address(
            [b"farmer", bytes(pool_pda), bytes(farmer)], PROGRAM_ID
        )

        reg_data = get_discriminator("register_farmer") + serialize_string(region)
        reg_ix = Instruction(
            program_id=PROGRAM_ID,
            data=reg_data,
            accounts=[
                AccountMeta(
                    pubkey=admin_keypair.pubkey(), is_signer=True, is_writable=True
                ),
                AccountMeta(pubkey=farmer, is_signer=False, is_writable=False),
                AccountMeta(pubkey=farmer_pda, is_signer=False, is_writable=True),
                AccountMeta(pubkey=pool_pda, is_signer=False, is_writable=True),
                AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
            ],
        )

        reg_blockhash = client.get_latest_blockhash().value.blockhash
        tx_reg = Transaction.new_signed_with_payer(
            [reg_ix], admin_keypair.pubkey(), [admin_keypair], reg_blockhash
        )

        try:
            resp = client.send_transaction(tx_reg)
            print(f"Farmer registered successfully. Tx: {resp.value}")
        except Exception as e:
            print(f"Failed to register {region}: {e}")


if __name__ == "__main__":
    setup()
