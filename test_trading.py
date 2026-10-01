"""
Integration Test for Crypto Trading Bot System
Tests all modules: DB, PaperTrader, Patterns, Strategies, RiskManager, Connector
"""
import sys
import os
import asyncio
import pandas as pd
import numpy as np

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trading.trading_config import TradingConfig
from trading.trade_db import (
    init_trading_db, log_trade, close_trade, get_open_trades,
    get_trade_history, log_equity_snapshot, get_equity_history,
    set_bot_state, get_bot_state, get_trade_stats
)
from trading.paper_trader import PaperTrader
from trading.patterns import PatternRecognizer
from trading.strategies import StrategyEngine
from trading.risk_manager import RiskManager
from trading.exchange_connector import ExchangeConnector
from backtesting.pattern_memory import PatternMemory
from backtesting.backtest_engine import BacktestEngine
from trading.pattern_memory_bridge import memory_bridge


def generate_mock_candles(n=100, base_price=65000.0):
    """Generate realistic OHLCV dataframe for testing."""
    np.random.seed(42)
    timestamps = [int(1700000000000 + i * 3600000) for i in range(n)]
    prices = [base_price]
    for _ in range(n - 1):
        prices.append(prices[-1] * (1 + np.random.normal(0.0005, 0.01)))
    
    opens = prices
    closes = [p * (1 + np.random.normal(0, 0.005)) for p in opens]
    highs = [max(o, c) * (1 + abs(np.random.normal(0, 0.003))) for o, c in zip(opens, closes)]
    lows = [min(o, c) * (1 - abs(np.random.normal(0, 0.003))) for o, c in zip(opens, closes)]
    volumes = [np.random.uniform(50, 500) for _ in range(n)]
    
    df = pd.DataFrame({
        'timestamp': timestamps,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df


async def test_pipeline():
    print("[TEST 1/7] Testing SQLite Trading Database...")
    init_trading_db()
    tid = log_trade("BTC/USDT", "buy", 65000.0, 0.1, 63700.0, 68900.0, "Test Strategy", "hammer", "test_ord_1")
    assert tid > 0, "log_trade failed"
    open_trades = get_open_trades()
    assert len(open_trades) > 0, "get_open_trades failed"
    close_trade(tid, 68900.0, 390.0, 6.0, 6.89)
    history = get_trade_history()
    assert len(history) > 0, "get_trade_history failed"
    log_equity_snapshot(10390.0, 10390.0, 0.0, 390.0, 3.9)
    snapshots = get_equity_history()
    assert len(snapshots) > 0, "get_equity_history failed"
    set_bot_state("test_key", "test_val")
    assert get_bot_state("test_key") == "test_val", "bot_state failed"
    stats = get_trade_stats()
    assert stats["total_trades"] >= 1, "get_trade_stats failed"
    print("  --> DB tests PASSED")

    print("[TEST 2/7] Testing PaperTrader Execution...")
    pt = PaperTrader(initial_balance=10000.0)
    buy_res = pt.execute_buy("BTC/USDT", 65000.0, 1000.0)
    assert buy_res.get("side") == "buy", "Paper buy failed"
    assert "BTC/USDT" in pt.positions, "Position not recorded in PaperTrader"
    pt.place_stop_loss("BTC/USDT", 63700.0)
    pt.place_take_profit("BTC/USDT", 68900.0)
    stops = pt.check_stops({"BTC/USDT": 69000.0})
    assert len(stops) > 0, "Take-profit auto trigger failed"
    assert "BTC/USDT" not in pt.positions, "Position not closed on TP"
    print("  --> PaperTrader tests PASSED")

    print("[TEST 3/7] Testing Pattern Recognizer (Candlesticks + Geometry)...")
    df = generate_mock_candles(100)
    pr = PatternRecognizer()
    patterns = await pr.scan_all_patterns(df)
    assert isinstance(patterns, list), "scan_all_patterns failed"
    consensus = await pr.get_pattern_consensus(df)
    assert "signal" in consensus and "strength" in consensus, "consensus failed"
    adx = pr.calculate_adx(df)
    assert len(adx) == len(df), "ADX calculation failed"
    rsi = pr.calculate_rsi(df)
    assert len(rsi) == len(df), "RSI calculation failed"
    print(f"  --> Patterns detected: {len(patterns)} | Consensus: {consensus['signal']} (Strength: {consensus['strength']:.2f})")
    print("  --> Pattern Recognizer tests PASSED")

    print("[TEST 4/7] Testing Risk Manager & 1:3 R:R Ratio Enforcer...")
    cfg = TradingConfig()
    rm = RiskManager(cfg)
    sizing = rm.calculate_position(equity=10000.0, entry_price=65000.0, symbol="BTC/USDT")
    assert sizing["stop_loss"] < 65000.0, "Stop loss not below entry"
    assert sizing["take_profit"] > 65000.0, "Take profit not above entry"
    # Verify 1:3 ratio
    risk = 65000.0 - sizing["stop_loss"]
    reward = sizing["take_profit"] - 65000.0
    ratio = reward / risk
    assert abs(ratio - 3.0) < 0.05, f"Risk:Reward ratio is {ratio:.2f}, expected 3.0!"
    print(f"  --> 1:3 R:R Enforced: Risk=${risk:.2f} vs Reward=${reward:.2f} (Ratio: {ratio:.1f}:1)")

    val = rm.validate_trade("BTC/USDT", "buy", sizing["amount"], 65000.0, 10000.0, 0.0005, 0)
    assert val["approved"] is True, f"Validation failed unexpectedly: {val['reason']}"
    
    # Test drawdown kill-switch
    dd_status = rm.update_equity(10000.0)
    assert dd_status["kill_switch_active"] is False
    dd_status = rm.update_equity(9400.0) # 6% drop > 5% limit
    assert dd_status["kill_switch_active"] is True, "Kill switch failed to trigger on 6% drawdown!"
    print("  --> Drawdown kill-switch (5% limit) trigger verified")
    rm.deactivate_emergency_stop()
    print("  --> Risk Manager tests PASSED")

    print("[TEST 5/7] Testing Strategy Engine Voting...")
    se = StrategyEngine(cfg)
    sig = await se.generate_signal(df, "BTC/USDT")
    assert "action" in sig and "confidence" in sig, "Strategy signal missing fields"
    assert sig["action"] in ["BUY", "SELL", "HOLD"], "Invalid signal action"
    print(f"  --> Signal generated for BTC/USDT: {sig['action']} (Confidence: {sig['confidence']:.2f})")
    print("  --> Strategy Engine tests PASSED")

    print("[TEST 6/7] Testing ExchangeConnector with CCXT...")
    connector = ExchangeConnector(cfg)
    await connector.connect()
    # Fetch live ticker for Binance BTC/USDT (public endpoint)
    ticker = await connector.get_ticker("BTC/USDT")
    assert ticker and "last" in ticker and ticker["last"] > 0, f"Live ticker fetch failed: {ticker}"
    print(f"  --> Live Binance BTC/USDT Price: ${ticker['last']:,.2f} (Spread: {ticker['spread_pct']*100:.4f}%)")
    bal = await connector.get_balance()
    assert "USDT" in bal["free"], "Balance fetch failed"
    await connector.close()
    print("  --> ExchangeConnector live feed tests PASSED")

    print("[TEST 7/8] Testing 3-Year Pattern Memory & Backtest Storage...")
    engine = BacktestEngine()
    summary = engine.get_overall_summary()
    assert summary["total_candles_analyzed"] >= 26280, "Missing 3-year candles"
    assert summary["total_trades"] > 0, "No backtest trades found"
    sessions = engine.get_session_analytics()
    assert len(sessions) >= 3, "Missing session breakdown"
    patterns = engine.get_pattern_leaderboard(limit=5)
    assert len(patterns) > 0, "Pattern leaderboard empty"
    
    # Test live pattern memory bridge
    eval_res = memory_bridge.evaluate_live_pattern("harami", "bullish")
    assert eval_res["has_memory"] is True, "Live memory bridge lookup failed"
    print(f"  --> Pattern Memory Loaded: {summary['total_candles_analyzed']:,} candles, {summary['total_trades']:,} trades tested across {len(sessions)} sessions")
    print(f"  --> Live Bridge Query ('harami'): {eval_res['description']}")
    print("  --> Pattern Memory tests PASSED")

    print("[TEST 8/8] All 8 System Components Tested Successfully!")


if __name__ == "__main__":
    asyncio.run(test_pipeline())
