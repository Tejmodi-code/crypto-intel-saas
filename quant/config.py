"""
Atlas Quantitative Platform - Configuration & Broker Credentials.
Supports dynamic environment loading, broker API parameterization, and institutional risk limits.
"""
import os
from typing import List


class QuantConfig:
    # Broker & Exchange Parameters
    EXCHANGE_ID: str = os.getenv("EXCHANGE_ID", "binance").lower()
    API_KEY: str = os.getenv("EXCHANGE_API_KEY", "")
    API_SECRET: str = os.getenv("EXCHANGE_API_SECRET", "")
    API_PASSPHRASE: str = os.getenv("EXCHANGE_PASSPHRASE", "")  # Required for OKX / KuCoin
    
    # Execution Mode: LIVE or PAPER
    EXECUTION_MODE: str = os.getenv("EXECUTION_MODE", "PAPER").upper()
    USE_TESTNET: bool = os.getenv("USE_TESTNET", "false").lower() == "true"
    
    # Portfolio & Universe
    TRADING_PAIRS: List[str] = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    PRIMARY_TIMEFRAME: str = "1h"
    MACRO_TIMEFRAME: str = "4h"
    
    # Capital Allocation & Sizing
    INITIAL_CAPITAL_USDT: float = float(os.getenv("INITIAL_CAPITAL", "10000.0"))
    MAX_POSITION_PCT: float = 0.15          # Max 15% equity per individual allocation
    MAX_OPEN_POSITIONS: int = 4            # Max 4 concurrent positions
    BASE_RISK_PER_TRADE: float = 0.015     # 1.5% capital risked per trade
    RISK_REWARD_RATIO: float = 3.0         # Strict 1:3 minimum R:R enforced
    
    # Risk Guardrails
    DAILY_DRAWDOWN_LIMIT_PCT: float = 0.04 # 4.0% daily circuit breaker
    MAX_SPREAD_LIMIT_PCT: float = 0.0010   # 0.10% max allowed spread
    STOP_LOSS_PCT: float = 0.015           # 1.5% standard stop loss
    TAKE_PROFIT_PCT: float = 0.045         # 4.5% standard take profit (3x stop)
    
    # System & Server
    SERVER_HOST: str = "127.0.0.1"
    SERVER_PORT: int = 8080
    DATABASE_PATH: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quant_ledger.db")


quant_config = QuantConfig()
