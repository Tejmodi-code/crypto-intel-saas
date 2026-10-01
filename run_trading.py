"""
CryptoIntel Pro - Multi-Bot Trading System Entry Point.
Launches 3 autonomous trading bots + bulletproof dashboard simultaneously.
All bots run 24/7 in parallel without manual approval.
"""
import asyncio
import threading
from datetime import datetime, timezone

from trading.trading_config import TradingConfig
from trading.bots.supervisor import supervisor
from trading.notification_bus import bus


def make_trend_rider(config):
    from trading.bots.trend_rider import TrendRiderBot
    return TrendRiderBot(config)


def make_reversal_hunter(config):
    from trading.bots.reversal_hunter import ReversalHunterBot
    return ReversalHunterBot(config)


def make_breakout_sniper(config):
    from trading.bots.breakout_sniper import BreakoutSniperBot
    return BreakoutSniperBot(config)


def start_dashboard(config):
    import uvicorn
    from trading.trading_dashboard import create_app
    app = create_app(config)
    uvicorn.run(
        app,
        host=config.DASHBOARD_HOST,
        port=config.DASHBOARD_PORT,
        log_level="warning",
        access_log=False,
    )


async def main():
    config = TradingConfig()

    print("=" * 60)
    print("  CryptoIntel Pro - Autonomous Trading System v3.0")
    print("=" * 60)
    print(f"  Mode: {'PAPER TRADING' if config.PAPER_MODE else 'LIVE TRADING'}")
    print(f"  Pairs: {', '.join(config.TRADING_PAIRS)}")
    print(f"  Risk:Reward: 1:{config.RISK_REWARD_RATIO:.0f}")
    print(f"  Stop-Loss: {config.STOP_LOSS_PCT*100:.0f}% | Take-Profit: {config.TAKE_PROFIT_PCT*100:.0f}%")
    print(f"  Daily drawdown kill switch: 5%")
    print(f"  Dashboard: http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}")
    print("=" * 60)
    print("  [Bot 1] TrendRider      - EMA Momentum - London/NY sessions")
    print("  [Bot 2] ReversalHunter  - RSI Reversal - Asian session")
    print("  [Bot 3] BreakoutSniper  - ATR Breakout - London/NY sessions")
    print("=" * 60)

    # Register all 3 bots
    supervisor.register(
        "TrendRider", lambda: make_trend_rider(config),
        symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        poll_interval=45, restart_delay=5
    )
    supervisor.register(
        "ReversalHunter", lambda: make_reversal_hunter(config),
        symbols=["BTC/USDT", "ETH/USDT"],
        poll_interval=60, restart_delay=5
    )
    supervisor.register(
        "BreakoutSniper", lambda: make_breakout_sniper(config),
        symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        poll_interval=30, restart_delay=5
    )

    # Start dashboard in background thread
    dash_thread = threading.Thread(target=start_dashboard, args=(config,), daemon=True)
    dash_thread.start()
    print(f"[OK] Dashboard started at http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}")

    # Publish system start event
    bus.publish("SYSTEM_START", {
        "message": "CryptoIntel Pro started. 3 autonomous bots activating.",
        "mode": "PAPER" if config.PAPER_MODE else "LIVE",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # Launch all bots under supervision
    await supervisor.start_all()

    # Keep the event loop alive
    try:
        while True:
            await asyncio.sleep(60)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await supervisor.shutdown()
        print("[OK] CryptoIntel Pro shut down cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[INFO] Stopped by user.")
