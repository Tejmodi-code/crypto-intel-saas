"""
CryptoIntel Pro - Institutional Terminal & Delta-Neutral Cashflow Engine.
Launches the Bloomberg/TradingView-grade pro terminal on port 8080 with real-time
funding rate arbitrage, whale radar, and delta-neutral cashflow engine.
"""
import sys
import uvicorn
from terminal.terminal_server import app


def main():
    print("=" * 65)
    print("  CRYPTOINTEL PRO - INSTITUTIONAL ALPHA & FUNDING ARBITRAGE")
    print("=" * 65)
    print("  Engine: Delta-Neutral Cashflow (Zero Directional Price Risk)")
    print("  Whale Radar: Real-Time On-Chain Monitor (> $500k Transfers)")
    print("  Strategy: Spot-Long + Futures-Short 8h Funding Rate Harvest")
    print("  Terminal URL: http://127.0.0.1:8080")
    print("=" * 65)

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8080,
        log_level="warning",
        access_log=False
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Terminal stopped cleanly.")
