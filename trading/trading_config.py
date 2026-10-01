import os
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

class TradingConfig:
    EXCHANGE_NAME = os.getenv('EXCHANGE_NAME', 'binance')
    API_KEY = os.getenv('EXCHANGE_API_KEY', '')
    API_SECRET = os.getenv('EXCHANGE_API_SECRET', '')
    API_PASSPHRASE = os.getenv('EXCHANGE_PASSPHRASE', '')
    
    PAPER_MODE = os.getenv('PAPER_MODE', 'true').lower() == 'true'
    SANDBOX_MODE = False
    
    TRADING_PAIRS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    TIMEFRAME = '1h'
    CANDLE_LIMIT = 100
    POLL_INTERVAL_SECONDS = 10
    
    RISK_PER_TRADE = 0.01
    RISK_REWARD_RATIO = 3.0
    MAX_POSITION_PCT = 0.20
    MAX_OPEN_POSITIONS = 3
    DAILY_DRAWDOWN_LIMIT = 0.05
    
    SPREAD_FILTER_PCT = 0.0015
    STOP_LOSS_PCT = 0.02
    TAKE_PROFIT_PCT = STOP_LOSS_PCT * RISK_REWARD_RATIO
    COOLDOWN_SECONDS = 300
    
    SIMULATED_SLIPPAGE_BPS = 5
    SIMULATED_FEE_PCT = 0.001
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    TRADING_DB_PATH = os.path.join(base_dir, 'trading.db')
    
    DASHBOARD_HOST = '127.0.0.1'
    DASHBOARD_PORT = 8080

config = TradingConfig()
