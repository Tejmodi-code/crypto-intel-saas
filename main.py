import asyncio
import uvicorn
from database import init_db, create_subscription
from engine.scanner import OnChainScanner
from config import config
from dashboard.server import app

scanner = OnChainScanner()

def seed_demo_data():
    init_db()
    try:
        create_subscription("alpha_fund@hedge.io", "ENTERPRISE", "0x88c1a...e20", amount_usd=199.0)
        create_subscription("quant_trader@propdesk.crypto", "PRO", "0x3a4fb...991", amount_usd=79.0)
        create_subscription("retail_vip@gmail.com", "STARTER", "0x12a9c...3c4", amount_usd=29.0)
        print("[+] Initialized bootstrap subscribers & recurring cash flow.")
    except Exception as e:
        print(f"[!] Seed note: {e}")

async def main():
    seed_demo_data()
    print("="*65)
    print(f"[*] Launching {config.PROJECT_NAME} v{config.VERSION}")
    print(f"[*] Web Dashboard & API: http://{config.HOST}:{config.PORT}")
    print(f"[*] Merchant Wallet: {config.MERCHANT_WALLET_EVM}")
    print("="*65)
    
    asyncio.create_task(scanner.start())
    server_config = uvicorn.Config(app, host=config.HOST, port=config.PORT, log_level="info")
    server = uvicorn.Server(server_config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
