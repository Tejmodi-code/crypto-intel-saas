"""
3-Year Backtested Data Generator & Comprehensive Pattern Evaluation Pipeline
Builds 3-year hourly crypto datasets tagged with sessions and evaluates all 37 patterns.
"""
import sqlite3
import os
import asyncio
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
from typing import Dict, Any, List

from backtesting.backtest_config import backtest_config
from backtesting.sessions import SessionClassifier
from backtesting.pattern_memory import PatternMemory
from trading.patterns import PatternRecognizer


def generate_3year_ohlcv(symbol: str, base_price: float, volatility: float = 0.008) -> pd.DataFrame:
    """
    Generates realistic 3-year hourly crypto price history covering 26,280 bars
    with realistic cyclical bull/bear markets, volatility spikes, and session variations.
    """
    np.random.seed(abs(hash(symbol)) % (2**31))
    total_bars = backtest_config.TOTAL_BARS_PER_PAIR
    
    start_time = datetime.now(timezone.utc) - timedelta(hours=total_bars)
    timestamps = [int((start_time + timedelta(hours=i)).timestamp() * 1000) for i in range(total_bars)]
    datetimes = [(start_time + timedelta(hours=i)).isoformat() for i in range(total_bars)]
    
    # Generate multi-regime drift (bull runs, deep pullbacks, consolidations)
    t = np.linspace(0, 6 * np.pi, total_bars)
    macro_cycle = np.sin(t) * 0.4 + np.sin(t * 2.5) * 0.15
    returns = np.random.normal(0.0001, volatility, total_bars) + (np.gradient(macro_cycle) * 0.1)
    
    # Intraday session volatility amplification
    hours = np.array([(start_time + timedelta(hours=i)).hour for i in range(total_bars)])
    vol_multiplier = np.ones(total_bars)
    # London/NY overlap (12-16 UTC) has 1.8x volatility
    vol_multiplier[(hours >= 12) & (hours < 16)] = 1.8
    # London morning (8-12 UTC) has 1.4x volatility
    vol_multiplier[(hours >= 8) & (hours < 12)] = 1.4
    # Asian session (0-8 UTC) has 0.7x volatility (quieter)
    vol_multiplier[hours < 8] = 0.7
    
    adjusted_returns = returns * vol_multiplier
    price_series = base_price * np.exp(np.cumsum(adjusted_returns))
    
    opens = price_series
    closes = opens * (1 + np.random.normal(0, volatility * 0.6, total_bars))
    highs = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, volatility * 0.5, total_bars)))
    lows = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, volatility * 0.5, total_bars)))
    volumes = np.random.uniform(100, 2000, total_bars) * vol_multiplier
    
    df = pd.DataFrame({
        'timestamp': timestamps,
        'datetime': datetimes,
        'symbol': symbol,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })
    
    # Tag with sessions
    df = SessionClassifier.tag_dataframe(df)
    return df


def init_backtest_db(db_path: str) -> None:
    """Initializes SQLite tables for 3-year backtested data."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historical_candles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            timestamp INTEGER,
            datetime TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            session TEXT,
            is_overlap INTEGER,
            liquidity_tier TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backtest_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            timestamp TEXT,
            pattern_name TEXT,
            session TEXT,
            signal_type TEXT,
            trend_regime TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            exit_price REAL,
            outcome TEXT,
            pnl_pct REAL,
            bars_held INTEGER
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_candles_sym_time ON historical_candles(symbol, timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_patt_sess ON backtest_trades(pattern_name, session)')
    conn.commit()
    conn.close()


async def evaluate_patterns_on_dataset(df: pd.DataFrame, memory: PatternMemory, db_path: str,
                                      sample_step: int = 4) -> int:
    """
    Evaluates patterns across the 3-year historical dataset with 1:3 R:R forward simulation.
    sample_step=4 tests every 4th bar to ensure realistic trade spacing (~6,500 test points).
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    recognizer = PatternRecognizer()
    symbol = df['symbol'].iloc[0]
    total_bars = len(df)
    lookahead = backtest_config.FORWARD_LOOKAHEAD_BARS
    
    # Pre-calculate 50-bar EMA for trend regime
    ema50 = recognizer.calculate_ema(df, 50)
    
    trade_count = 0
    trades_batch = []
    
    # Sliding window evaluation
    for i in range(60, total_bars - lookahead, sample_step):
        window = df.iloc[i-50 : i+1]
        current_bar = df.iloc[i]
        curr_close = current_bar['close']
        session = str(current_bar['session'])
        timestamp = str(current_bar['datetime'])
        
        # Trend regime
        curr_ema = ema50.iloc[i]
        if curr_close > curr_ema * 1.01:
            trend_regime = 'bullish_trend'
        elif curr_close < curr_ema * 0.99:
            trend_regime = 'bearish_trend'
        else:
            trend_regime = 'range_bound'
            
        # Detect patterns on this window
        patterns = await recognizer.scan_all_patterns(window)
        if not patterns:
            continue
            
        # Test the highest-confidence detected pattern
        best_pattern = patterns[0]
        patt_name = best_pattern['pattern']
        sig_type = best_pattern['signal']
        
        if sig_type not in ['bullish', 'bearish']:
            continue
            
        # 1:3 Risk-to-Reward calculation
        if sig_type == 'bullish':
            entry = curr_close
            sl = entry * (1 - backtest_config.STOP_LOSS_PCT)  # -2%
            tp = entry * (1 + backtest_config.TAKE_PROFIT_PCT)  # +6%
            
            # Forward simulation over lookahead bars
            forward_window = df.iloc[i+1 : i+1+lookahead]
            outcome = 'EXPIRED'
            exit_price = forward_window.iloc[-1]['close']
            bars_held = lookahead
            pnl_pct = ((exit_price / entry) - 1) * 100
            
            for bar_idx, (_, f_bar) in enumerate(forward_window.iterrows(), 1):
                if f_bar['high'] >= tp:
                    outcome = 'WIN'
                    exit_price = tp
                    bars_held = bar_idx
                    pnl_pct = backtest_config.TAKE_PROFIT_PCT * 100  # +6%
                    break
                elif f_bar['low'] <= sl:
                    outcome = 'LOSS'
                    exit_price = sl
                    bars_held = bar_idx
                    pnl_pct = -backtest_config.STOP_LOSS_PCT * 100  # -2%
                    break
        else:
            # Bearish short trade with 1:3 R:R
            entry = curr_close
            sl = entry * (1 + backtest_config.STOP_LOSS_PCT)  # +2%
            tp = entry * (1 - backtest_config.TAKE_PROFIT_PCT)  # -6%
            
            forward_window = df.iloc[i+1 : i+1+lookahead]
            outcome = 'EXPIRED'
            exit_price = forward_window.iloc[-1]['close']
            bars_held = lookahead
            pnl_pct = ((entry / exit_price) - 1) * 100
            
            for bar_idx, (_, f_bar) in enumerate(forward_window.iterrows(), 1):
                if f_bar['low'] <= tp:
                    outcome = 'WIN'
                    exit_price = tp
                    bars_held = bar_idx
                    pnl_pct = backtest_config.TAKE_PROFIT_PCT * 100  # +6%
                    break
                elif f_bar['high'] >= sl:
                    outcome = 'LOSS'
                    exit_price = sl
                    bars_held = bar_idx
                    pnl_pct = -backtest_config.STOP_LOSS_PCT * 100  # -2%
                    break

        trades_batch.append((
            symbol, timestamp, patt_name, session, sig_type, trend_regime,
            round(entry, 2), round(sl, 2), round(tp, 2), round(exit_price, 2),
            outcome, round(pnl_pct, 2), bars_held
        ))
        
        # Feed into Pattern Memory storage
        memory.record_instance(
            timestamp=timestamp, symbol=symbol, pattern_name=patt_name,
            session=session, signal_type=sig_type, trend_regime=trend_regime,
            entry_price=entry, stop_loss=sl, take_profit=tp,
            outcome=outcome, pnl_pct=pnl_pct, bars_held=bars_held
        )
        trade_count += 1
        
        # Batch insert every 500 records
        if len(trades_batch) >= 500:
            cursor.executemany('''
                INSERT INTO backtest_trades (
                    symbol, timestamp, pattern_name, session, signal_type,
                    trend_regime, entry_price, stop_loss, take_profit,
                    exit_price, outcome, pnl_pct, bars_held
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', trades_batch)
            conn.commit()
            trades_batch.clear()

    if trades_batch:
        cursor.executemany('''
            INSERT INTO backtest_trades (
                symbol, timestamp, pattern_name, session, signal_type,
                trend_regime, entry_price, stop_loss, take_profit,
                exit_price, outcome, pnl_pct, bars_held
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', trades_batch)
        conn.commit()
        
    conn.close()
    return trade_count


async def run_full_3year_generation() -> Dict[str, Any]:
    """Orchestrates 3-year data generation, session tagging, and pattern evaluation."""
    print("="*65)
    print("  [INIT] Starting 3-Year Historical Data & Pattern Pipeline")
    print(f"  Target: {backtest_config.TOTAL_BARS_PER_PAIR} hourly bars per coin (3 Years)")
    print(f"  Pairs: {', '.join(backtest_config.TRADING_PAIRS)}")
    print(f"  Risk:Reward = 1:{backtest_config.RISK_REWARD_RATIO:.0f} (SL: 2%, TP: 6%)")
    print("="*65)
    
    if os.path.exists(backtest_config.BACKTEST_DB_PATH):
        try: os.remove(backtest_config.BACKTEST_DB_PATH)
        except Exception: pass
    if os.path.exists(backtest_config.PATTERN_MEMORY_DB_PATH):
        try: os.remove(backtest_config.PATTERN_MEMORY_DB_PATH)
        except Exception: pass

    init_backtest_db(backtest_config.BACKTEST_DB_PATH)
    memory = PatternMemory(backtest_config.PATTERN_MEMORY_DB_PATH)
    
    base_prices = {'BTC/USDT': 65000.0, 'ETH/USDT': 2600.0, 'SOL/USDT': 110.0}
    total_trades_tested = 0
    
    for symbol in backtest_config.TRADING_PAIRS:
        print(f"\n[*] Generating 3-year historical candles for {symbol}...")
        df = generate_3year_ohlcv(symbol, base_prices.get(symbol, 50000.0))
        
        # Save raw candles to backtested_data.db
        print(f"[+] Saving {len(df)} candles with session tags to backtested_data.db...")
        conn = sqlite3.connect(backtest_config.BACKTEST_DB_PATH)
        df_to_save = df[['symbol', 'timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'session', 'is_overlap', 'liquidity_tier']].copy()
        df_to_save['is_overlap'] = df_to_save['is_overlap'].astype(int)
        df_to_save.to_sql('historical_candles', conn, if_exists='append', index=False)
        conn.close()
        
        print(f"[+] Scanning & testing all 37 patterns across {symbol} (1:3 R:R forward simulations)...")
        trades = await evaluate_patterns_on_dataset(df, memory, backtest_config.BACKTEST_DB_PATH, sample_step=4)
        total_trades_tested += trades
        print(f"[OK] Completed {symbol}: {trades} pattern instances evaluated.")

    print("\n[*] Compiling aggregated pattern memory statistics & auto-apply rules...")
    memory.compile_memory()
    print("[OK] Pattern memory compiled successfully!")
    
    summary = {
        'total_bars_generated': len(backtest_config.TRADING_PAIRS) * backtest_config.TOTAL_BARS_PER_PAIR,
        'total_trades_tested': total_trades_tested,
        'pairs': backtest_config.TRADING_PAIRS,
        'backtest_db': backtest_config.BACKTEST_DB_PATH,
        'pattern_memory_db': backtest_config.PATTERN_MEMORY_DB_PATH
    }
    return summary


if __name__ == '__main__':
    asyncio.run(run_full_3year_generation())
