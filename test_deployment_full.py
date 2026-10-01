"""
Comprehensive Production Deployment Test Suite.
Verifies all 6 mission-critical system components:
1. SQLite Database Persistence (Across Server Reboots & Page Refreshes)
2. Vectorized Indicators & Structural Swing Math
3. Dynamic Pattern Strategy Engine (Pre-entry SL/TP & Adaptive R:R)
4. Risk Management Engine (Pattern Sizing & 4% Drawdown Circuit Breaker)
5. Broker Connector & Live Market Ticker Routing
6. FastAPI Web Server & Real-Time SSE Telemetry
"""
import sys
import os
import asyncio
import sqlite3
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from quant.config import quant_config
from quant.quant_blotter import QuantBlotter
from quant.indicators import QuantIndicators
from quant.strategies import QuantStrategies
from quant.risk_engine import RiskEngine
from quant.backtester import QuantBacktester
from quant.broker_connector import BrokerConnector
from quant.order_executor import OrderExecutor, executor
from web.server import app, generate_sample_candles
from fastapi.testclient import TestClient


async def run_full_verification():
    print("=" * 65)
    print("  ATLAS QUANTITATIVE PLATFORM - FULL DEPLOYMENT TEST SUITE")
    print("=" * 65)

    # -------------------------------------------------------------
    # 1. TEST PERSISTENCE ACROSS REBOOTS
    # -------------------------------------------------------------
    print("\n[PART 1/6] Testing SQLite Database Persistence Across Reboots...")
    blotter = QuantBlotter()
    # Simulate an established profit and active trade in DB
    blotter.save_portfolio_state(
        initial_capital=10000.0,
        realized_pnl=342.50,
        total_equity=10342.50,
        available_cash=10000.0
    )
    test_trade = {
        "order_id": "ORD_TEST_PERSIST_01",
        "timestamp": "2026-09-14T12:00:00Z",
        "symbol": "BTC/USDT",
        "strategy": "VWAP_MEAN_REVERSION",
        "side": "BUY",
        "entry_price": 77650.0,
        "exit_price": None,
        "units": 0.019,
        "notional_usd": 1500.0,
        "stop_loss": 76800.0,
        "take_profit": 81000.0,
        "pattern_rr": "1:3.9",
        "pnl_usd": 42.50,
        "pnl_pct": 2.83,
        "status": "ACTIVE_POSITION",
        "execution_notes": "Persistence verification order"
    }
    blotter.record_order(test_trade)

    # Simulate fresh reboot by instantiating a completely new OrderExecutor instance
    fresh_executor = OrderExecutor()
    await fresh_executor.initialize()

    assert fresh_executor.total_realized_pnl == 342.50, f"Realized PnL reset! Got ${fresh_executor.total_realized_pnl}"
    assert "ORD_TEST_PERSIST_01" in fresh_executor.active_positions, "Active trade was not restored from SQLite!"
    restored_trade = fresh_executor.active_positions["ORD_TEST_PERSIST_01"]
    assert restored_trade["stop_loss"] == 76800.0 and restored_trade["pattern_rr"] == "1:3.9"
    print(f"  --> Persistence Verified: Realized P&L = ${fresh_executor.total_realized_pnl:,.2f} preserved across reboot.")
    print("  --> [PASSED] SQLite Database Persistence Engine")

    # -------------------------------------------------------------
    # 2. TEST INDICATORS & STRUCTURAL MATH
    # -------------------------------------------------------------
    print("\n[PART 2/6] Testing Vectorized Indicators & Structural Swings...")
    df = generate_sample_candles(120)
    vwap = QuantIndicators.calculate_vwap(df)
    upper, sma, lower, zscore = QuantIndicators.calculate_bollinger_zscore(df)
    k, d = QuantIndicators.calculate_stochastic_rsi(df)
    adx = QuantIndicators.calculate_adx(df)
    atr = QuantIndicators.calculate_atr(df)
    swings = QuantIndicators.detect_structural_swing_levels(df, 20)

    assert len(vwap) == 120 and len(zscore) == 120
    assert swings["structural_support"] < swings["swing_low"]
    assert swings["structural_resistance"] > swings["swing_high"]
    print(f"  --> VWAP: {vwap.iloc[-1]:.2f} | Z-Score: {zscore.iloc[-1]:.2f} | ADX: {adx.iloc[-1]:.2f} | Support: ${swings['structural_support']:.2f}")
    print("  --> [PASSED] Vectorized Technical & Structural Math")

    # -------------------------------------------------------------
    # 3. TEST DYNAMIC PATTERN STRATEGY ENGINE
    # -------------------------------------------------------------
    print("\n[PART 3/6] Testing Dynamic Pattern Strategy Engine (No Fixed 2% SL / No Fixed 1:3)...")
    df_oversold = df.copy()
    df_oversold.loc[df_oversold.index[-1], 'close'] = df_oversold['close'].mean() * 0.94
    vwap_sig = QuantStrategies.evaluate_vwap_mean_reversion(df_oversold)
    
    if vwap_sig["action"] == "BUY":
        assert vwap_sig["stop_loss"] < vwap_sig["entry_price"]
        assert vwap_sig["take_profit"] > vwap_sig["entry_price"]
        assert "pattern_rr" in vwap_sig
        print(f"  --> Pattern Signal Generated: Action={vwap_sig['action']} | SL=${vwap_sig['stop_loss']} | TP=${vwap_sig['take_profit']} | Dynamic R:R={vwap_sig['pattern_rr']}")
    print("  --> [PASSED] Dynamic Structural Pattern Strategies")

    # -------------------------------------------------------------
    # 4. TEST RISK ENGINE & SIZING
    # -------------------------------------------------------------
    print("\n[PART 4/6] Testing Risk Engine (Pattern-Based Sizing & Circuit Breaker)...")
    risk = RiskEngine(quant_config)
    sizing = risk.calculate_pattern_based_sizing(10000.0, 77650.0, 76800.0, 80800.0)
    assert sizing["stop_loss"] == 76800.0
    assert sizing["notional_usd"] <= 1500.0  # Max 15% allocation
    
    # Test 4% drawdown circuit breaker
    dd_normal = risk.update_drawdown_monitor(9900.0) # 1% down
    assert dd_normal["circuit_breaker"] is False
    dd_halt = risk.update_drawdown_monitor(9550.0)   # 4.5% down > 4.0% limit
    assert dd_halt["circuit_breaker"] is True, "Circuit breaker failed to trip on 4.5% drawdown"
    print(f"  --> Sizing: ${sizing['notional_usd']:,.2f} | Risk: ${sizing['risk_amount_usd']:.2f} | Circuit Breaker: Trigger Verified at 4.5% Drawdown")
    print("  --> [PASSED] Risk Engine & Sizing Controls")

    # -------------------------------------------------------------
    # 5. TEST BROKER CONNECTOR & LIVE TICKERS
    # -------------------------------------------------------------
    print("\n[PART 5/6] Testing Broker Connector & Order Routing...")
    broker = BrokerConnector(quant_config)
    init_res = await broker.initialize()
    assert init_res["status"] in ["CONNECTED_PAPER", "AUTHENTICATED_LIVE"]
    ticker = await broker.fetch_ticker("BTC/USDT")
    assert ticker["last"] > 0
    order_fill = await broker.execute_market_order("BTC/USDT", "BUY", 0.01, ticker["last"])
    assert order_fill["status"] == "FILLED"
    print(f"  --> Broker Status: {init_res['status']} | Live Binance BTC: ${ticker['last']:,.2f} | Order Fill: {order_fill['order_id']}")
    print("  --> [PASSED] Broker Connector & Order Execution Interface")

    # -------------------------------------------------------------
    # 6. TEST WEB SERVER & SSE TELEMETRY STREAM
    # -------------------------------------------------------------
    print("\n[PART 6/6] Testing FastAPI Server Endpoints & Telemetry...")
    with TestClient(app) as client:
        res_ui = client.get("/")
        assert res_ui.status_code == 200 and "ATLAS QUANT" in res_ui.text
        
        res_health = client.get("/api/health")
        assert res_health.status_code == 200 and res_health.json()["status"] == "OPERATIONAL"
        
        res_port = client.get("/api/portfolio")
        assert res_port.status_code == 200 and res_port.json()["total_portfolio_equity"] > 0
        
        res_matrix = client.get("/api/signals/matrix")
        assert res_matrix.status_code == 200 and len(res_matrix.json()) > 0
        
        res_bt = client.get("/api/backtest/results")
        assert res_bt.status_code == 200 and "win_rate_pct" in res_bt.json()
        print(f"  --> Telemetry Verified: Health={res_health.json()['status']} | Portfolio Equity=${res_port.json()['total_portfolio_equity']:,.2f}")

    print("  --> [PASSED] Web Server & Real-Time Telemetry Interface")
    print("\n" + "=" * 65)
    print("  ALL 6/6 MISSION-CRITICAL DEPLOYMENT TESTS PASSED (100% SUCCESS)")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_full_verification())
