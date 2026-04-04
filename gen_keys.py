from solders.keypair import Keypair

print("--- Данные для React (Frontend) и init_setup.py ---")
for i in range(1, 6):
    kp = Keypair()
    print(f"Farmer {i}: {kp.pubkey()}")
