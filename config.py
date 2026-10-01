import os

class Config:
    PROJECT_NAME = 'CryptoIntel Pro SaaS'
    VERSION = '1.0.0'
    MERCHANT_WALLET_EVM = os.getenv('MERCHANT_WALLET_EVM', '0x71C83648611f77d346b761765c9E45758063aC4F')
    MERCHANT_WALLET_SOL = os.getenv('MERCHANT_WALLET_SOL', '7Nxq5Wz6j8V1QW2bM4T9mF5C1Z7xK9pL3yN6vB8sR4dE')
    TIERS = {
        'STARTER': {'name': 'Starter Signal Tier', 'price_usd': 29.0, 'duration_days': 30},
        'PRO': {'name': 'Pro Quantitative Tier', 'price_usd': 79.0, 'duration_days': 30},
        'ENTERPRISE': {'name': 'Institutional Tier', 'price_usd': 199.0, 'duration_days': 30}
    }
    WHALE_THRESHOLD_USD = 250000.0
    MEGA_WHALE_THRESHOLD_USD = 1000000.0
    DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crypto_intel.db')
    HOST = os.getenv('HOST', '127.0.0.1')
    PORT = int(os.getenv('PORT', '8000'))
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_VIP_CHANNEL_ID = os.getenv('TELEGRAM_VIP_CHANNEL_ID', '')

config = Config()
