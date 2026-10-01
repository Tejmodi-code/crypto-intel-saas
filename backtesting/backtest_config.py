"""
Backtest & Pattern Memory Configuration
Defines 3-year date ranges, session hours, R:R parameters, and database paths.
"""
import os

class BacktestConfig:
    # 3-year historical configuration
    YEARS_OF_DATA = 3
    TIMEFRAME = '1h'
    HOURS_PER_YEAR = 365 * 24
    TOTAL_BARS_PER_PAIR = YEARS_OF_DATA * HOURS_PER_YEAR  # 26,280 bars
    
    TRADING_PAIRS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    
    # 1:3 Risk-to-Reward parameters
    STOP_LOSS_PCT = 0.02       # 2.0% Stop Loss
    RISK_REWARD_RATIO = 3.0    # 1:3 R:R
    TAKE_PROFIT_PCT = STOP_LOSS_PCT * RISK_REWARD_RATIO  # 6.0% Take Profit
    FORWARD_LOOKAHEAD_BARS = 48  # Up to 48 hours to evaluate trade outcome
    
    # Market Session Time Ranges (UTC hours)
    # Asian Session: Tokyo, Sydney, Hong Kong, Singapore
    ASIAN_START_HOUR = 0
    ASIAN_END_HOUR = 8
    
    # London Session: European main liquidity
    LONDON_START_HOUR = 7
    LONDON_END_HOUR = 16
    
    # New York Session: US core liquidity
    NY_START_HOUR = 12
    NY_END_HOUR = 21
    
    # Overlap sessions
    ASIA_LONDON_OVERLAP = (7, 8)
    LONDON_NY_OVERLAP = (12, 16)
    
    # Pattern Memory Thresholds
    AUTO_APPLY_MIN_WIN_RATE = 0.55  # 55% win rate at 1:3 R:R has massive positive expectancy!
    AUTO_APPLY_MIN_SAMPLES = 5      # At least 5 historical instances required
    FILTER_MAX_WIN_RATE = 0.35      # Under 35% win rate in this session gets filtered
    
    # Database Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BACKTEST_DB_PATH = os.path.join(BASE_DIR, 'backtested_data.db')
    PATTERN_MEMORY_DB_PATH = os.path.join(BASE_DIR, 'pattern_memory.db')

backtest_config = BacktestConfig()
