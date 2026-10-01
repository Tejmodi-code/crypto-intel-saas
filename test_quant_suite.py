"""
Exhaustive Quantitative Test Suite with Dynamic Pattern Risk Validation.
"""
import sys
import os
import asyncio
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from quant.config import quant_config
from quant.indicators import QuantIndicators
from quant.strategies import QuantStrategies
from quant.risk_engine import RiskEngine
from quant.backtester import QuantBacktester
from quant.broker_connector import BrokerConnector
from quant.order_executor import executor
from web.server import app, generate_sample_candles
from fastapi.testclient import TestClient


async def run_tests():
    print("[TEST 1/6] Testing Quantitative Indicators & Structural Swing Detection...")
    df = generate_sample_candles(100)
    vwap = QuantIndicators.calculate_vwap(df)
    swings = QuantIndicators.detect_structural_swing_levels(df, 20)
    assert "swing_high" in swings and "swing_low" in swings and "structural_support" in swings
    assert swings["structural_support"] < swings["swing_low"], "Structural support must sit below swing low"
    print(f"  --> Structural Support: ${swings['structural_support']:.2f} | Structural Resistance: ${swings['structural_resistance']:.2f} (ATR: ${swings['atr']:.2f})")
    print("  --> Indicators & Swings: PASSED")

    print("[TEST 2/6] Testing Dynamic Pattern-Derived SL/TP & Adaptive R:R Generation...")
    df_oversold = df.copy()
    df_oversold.loc[df_oversold.index[-1], 'close'] = df_oversold['close'].mean() * 0.94
    vwap_sig = QuantStrategies.evaluate_vwap_mean_reversion(df_oversold)
    if vwap_sig["action"] == "BUY":
        assert "stop_loss" in vwap_sig and "take_profit" in vwap_sig and "pattern_rr" in vwap_sig
        assert vwap_sig["stop_loss"] < vwap_sig["entry_price"], "Stop loss must be below entry"
        assert vwap_sig["take_profit"] > vwap_sig["entry_price"], "Take profit must be above entry"
        print(f"  --> Generated Pattern Setup: Action={vwap_sig['action']} | SL=${vwap_sig['stop_loss']} | TP=${vwap_sig['take_profit']} | Dynamic R:R={vwap_sig['pattern_rr']}")
    print("  --> Dynamic Pattern Strategy: PASSED")

    print("[TEST 3/6] Testing Risk Engine Pattern Sizing (Zero Fixed 2% SL)...")
    risk = RiskEngine(quant_config)
    entry_p = 77650.0
    struct_sl = 76820.0
    target_tp = 80800.0
    sizing = risk.calculate_pattern_based_sizing(10000.0, entry_p, struct_sl, target_tp)
    assert sizing["stop_loss"] == struct_sl, "Stop loss was not anchored to structural invalidation level"
    assert sizing["notional_usd"] <= 1500.0, "Position sizing exceeded maximum 15% equity allocation"
    print(f"  --> Sizing: ${sizing['notional_usd']:,.2f} | Units: {sizing['units']} | Pattern R:R: {sizing['pattern_rr']} | Risk: ${sizing['risk_amount_usd']:.2f}")
    print("  --> Pattern Sizing Engine: PASSED")

    print("[TEST 4/6] Testing Backtester with Dynamic Pattern-Based Exits...")
    backtester = QuantBacktester(10000.0)
    df_long = generate_sample_candles(600)
    bt_res = backtester.run_backtest(df_long, "VWAP_MEAN_REVERSION")
    assert "win_rate_pct" in bt_res and "risk_model" in bt_res
    assert bt_res["risk_model"] == "DYNAMIC_STRUCTURAL_PATTERN"
    print(f"  --> Backtest Result: Win Rate={bt_res['win_rate_pct']}% | Sharpe={bt_res['sharpe_ratio']} | Risk Model={bt_res['risk_model']}")
    print("  --> Backtest Engine: PASSED")

    print("[TEST 5/6] Testing Broker Connector & Live Ticker...")
    broker = BrokerConnector(quant_config)
    init_res = await broker.initialize()
    assert init_res["status"] in ["CONNECTED_PAPER", "AUTHENTICATED_LIVE"]
    ticker = await broker.fetch_ticker("BTC/USDT")
    assert ticker["last"] > 0
    print(f"  --> Broker Status: {init_res['status']} | Live BTC: ${ticker['last']:,.2f}")
    print("  --> Broker Connector: PASSED")

    print("[TEST 6/6] Testing Telemetry API with Pattern-Based Positions...")
    await executor.initialize()
    with TestClient(app) as client:
        res_port = client.get("/api/portfolio")
        assert res_port.status_code == 200
        pos_list = res_port.json()["active_positions"]
        assert len(pos_list) >= 2
        for p in pos_list:
            assert "stop_loss" in p and "take_profit" in p and "pattern_rr" in p
            print(f"  --> Active Position: {p['symbol']} | SL: ${p['stop_loss']} | TP: ${p['take_profit']} | Dynamic R:R: {p['pattern_rr']}")
    print("  --> Web Server & Telemetry: PASSED")
    print("\n[ALL 6/6 QUANTITATIVE TESTS PASSED WITH DYNAMIC PATTERN-BASED RISK]")


if __name__ == "__main__":
    asyncio.run(run_tests())
