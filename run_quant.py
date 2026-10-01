"""
Atlas Quantitative Platform - Primary Application Entry Point.
Launches the institutional execution server on port 8080 with autonomous
strategy loops, real-time market feeds, and broker connectivity.
"""
import sys
import uvicorn
from web.server import app
from quant.config import quant_config


def main():
    print("=" * 65)
    print("  ATLAS QUANTITATIVE TRADING & BROKER EXECUTION PLATFORM")
    print("=" * 65)
    print(f"  Execution Mode: {quant_config.EXECUTION_MODE}")
    print(f"  Broker API: {quant_config.EXCHANGE_ID.upper()}")
    print(f"  Universe: {', '.join(quant_config.TRADING_PAIRS)}")
    print(f"  Risk Profile: Strict 1:3 Risk-to-Reward | 4.0% Daily Drawdown Circuit Breaker")
    print(f"  Institutional Terminal: http://{quant_config.SERVER_HOST}:{quant_config.SERVER_PORT}")
    print("=" * 65)

    uvicorn.run(
        app,
        host=quant_config.SERVER_HOST,
        port=quant_config.SERVER_PORT,
        log_level="warning",
        access_log=False
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] System terminated by operator.")
