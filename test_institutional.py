"""
Comprehensive Test Suite for Institutional Engine & Delta-Neutral Arbitrage.
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arbitrage.funding_scanner import FundingScanner
from arbitrage.basis_engine import BasisEngine
from arbitrage.whale_radar import WhaleRadar
from arbitrage.margin_guard import MarginGuard
from arbitrage.delta_neutral_bot import DeltaNeutralEngine
from arbitrage.autonomous_trader import auto_trader
from terminal.terminal_server import app
from fastapi.testclient import TestClient


async def run_tests():
    print("[TEST 1/6] Testing Funding Scanner & Annualized APY Calculator...")
    scanner = FundingScanner()
    rates = await scanner.fetch_funding_rates()
    assert len(rates) > 0, "No funding rates returned"
    top = scanner.get_top_opportunity()
    assert top is not None, "Failed to identify top opportunity"
    print(f"  --> Top Yield: {top['symbol']} at {top['annualized_apy']:.1f}% APY (8h Rate: {top['funding_rate_pct']:.4f}%)")
    print("  --> Funding Scanner: PASSED")

    print("[TEST 2/6] Testing Spot-Futures Basis Engine...")
    basis_res = BasisEngine.calculate_basis(spot_price=77600.0, futures_price=77650.0)
    assert basis_res["basis"] == 50.0, f"Basis calculation error: {basis_res}"
    assert basis_res["regime"] == "CONTANGO", "Basis regime should be CONTANGO"
    print(f"  --> Basis: ${basis_res['basis']:.2f} ({basis_res['basis_pct']:.3f}%) | Regime: {basis_res['regime']}")
    print("  --> Basis Engine: PASSED")

    print("[TEST 3/6] Testing Whale Smart-Money Radar...")
    radar = WhaleRadar()
    events = radar.scan_new_whale_events()
    assert len(events) > 0, "Whale events empty"
    sent = radar.get_market_sentiment()
    print(f"  --> Whale Events Tracked: {len(events)} | Bias: {sent['net_flow_bias']}")
    print("  --> Whale Radar: PASSED")

    print("[TEST 4/6] Testing Margin Guard Liquidation Protection...")
    margin = MarginGuard.evaluate_futures_leg(
        entry_price=77650.0,
        current_price=77650.0,
        collateral_usdt=5000.0,
        position_size=0.064
    )
    assert margin["liquidation_price"] > 77650.0, "Short liquidation price must be above entry"
    assert margin["liquidation_distance_pct"] > 30.0, "Buffer should be safe"
    print(f"  --> Short Liq Price: ${margin['liquidation_price']:,.2f} | Distance: +{margin['liquidation_distance_pct']:.1f}%")
    print("  --> Margin Guard: PASSED")

    print("[TEST 5/6] Testing Autonomous Multi-Strategy Trader & Trade Ledger...")
    await auto_trader.initialize()
    ledger = auto_trader.get_ledger_summary()
    assert ledger["active_trades_count"] >= 3, "All 3 initial strategies must be deployed"
    assert len(ledger["strategies_deployed"]) == 3, "3 Strategy profiles must be registered"
    print(f"  --> Active Autonomous Trades: {ledger['active_trades_count']} | Portfolio Equity: ${ledger['total_portfolio_equity']:,.2f}")
    print("  --> Autonomous Strategy Engine: PASSED")

    print("[TEST 6/6] Testing Terminal Server Endpoints & Pro UI...")
    client = TestClient(app)
    
    res_ui = client.get("/")
    assert res_ui.status_code == 200 and "CRYPTOINTEL" in res_ui.text, "Pro terminal UI failed to serve"
    
    res_funding = client.get("/api/funding/matrix")
    assert res_funding.status_code == 200 and len(res_funding.json()) > 0, "Funding API failed"
    
    res_ledger = client.get("/api/ledger/trades")
    assert res_ledger.status_code == 200 and len(res_ledger.json()["active_trades"]) >= 3, "Ledger API failed"
    
    print("  --> Terminal Server & Pro UI: PASSED")
    print("\n[ALL 6/6 INSTITUTIONAL ENGINE TESTS COMPLETED WITH 100% SUCCESS]")


if __name__ == "__main__":
    asyncio.run(run_tests())
