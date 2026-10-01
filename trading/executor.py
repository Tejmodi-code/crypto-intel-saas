"""
Trading Executor - Main trading loop orchestrating strategies, risk, and execution.
Runs as an async background task polling prices and executing trades.
"""
import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from trading.trading_config import TradingConfig
from trading.exchange_connector import ExchangeConnector
from trading.strategies import StrategyEngine
from trading.risk_manager import RiskManager
from trading.trade_db import (
    init_trading_db, log_trade, close_trade, get_open_trades,
    log_equity_snapshot, set_bot_state, get_bot_state, get_trade_stats
)


class TradingExecutor:
    """
    Core trading engine that runs the continuous trading loop.
    Fetches prices, generates signals, validates risk, and executes trades.
    """

    def __init__(self, config: Optional[TradingConfig] = None):
        self.config = config or TradingConfig()
        self.connector: Optional[ExchangeConnector] = None
        self.strategy_engine = StrategyEngine(self.config)
        self.risk_manager = RiskManager(self.config)
        self.running = False
        self.paused = False
        self.cycle_count = 0
        self.last_prices: dict = {}
        self.last_signals: dict = {}
        self.start_time: Optional[datetime] = None
        self._errors_consecutive = 0
        self._max_consecutive_errors = 10

    async def initialize(self):
        """Initialize database, exchange connection, and load saved state."""
        print("[INIT] Initializing Trading Executor...")
        init_trading_db()

        self.connector = ExchangeConnector(self.config)
        await self.connector.connect()

        # Restore daily state if same day
        saved_date = get_bot_state("last_active_date")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if saved_date == today:
            peak = get_bot_state("daily_peak_equity")
            if peak:
                self.risk_manager.daily_peak_equity = float(peak)
                print(f"[INFO] Restored daily peak equity: {self.risk_manager.daily_peak_equity:.2f}")
            kill_state = get_bot_state("kill_switch_active")
            if kill_state == "true":
                self.risk_manager.kill_switch_active = True
                print("[WARN] Kill switch was active from previous session!")
        else:
            self.risk_manager.reset_daily_state()
            set_bot_state("last_active_date", today)
            print(f"[INFO] New trading day: {today} - daily state reset")

        mode = "PAPER" if self.config.PAPER_MODE else "LIVE"
        print(f"[OK] Trading Executor initialized in {mode} mode")
        print(f"[INFO] Trading pairs: {self.config.TRADING_PAIRS}")
        print(f"[INFO] Risk per trade: {self.config.RISK_PER_TRADE*100:.1f}%")
        print(f"[INFO] Risk:Reward ratio: 1:{self.config.RISK_REWARD_RATIO:.0f}")
        print(f"[INFO] Stop-loss: {self.config.STOP_LOSS_PCT*100:.1f}% | Take-profit: {self.config.TAKE_PROFIT_PCT*100:.1f}%")

    async def _fetch_all_prices(self) -> dict:
        """Fetch current ticker for all trading pairs."""
        prices = {}
        for symbol in self.config.TRADING_PAIRS:
            try:
                ticker = await self.connector.get_ticker(symbol)
                if ticker:
                    prices[symbol] = ticker
            except Exception as e:
                print(f"[ERROR] Failed to fetch price for {symbol}: {e}")
        return prices

    async def _check_and_close_stops(self, prices: dict):
        """Check stop-loss and take-profit levels for open trades."""
        open_trades = get_open_trades()
        if not open_trades:
            return

        for trade in open_trades:
            symbol = trade["symbol"]
            if symbol not in prices:
                continue

            current_price = prices[symbol]["last"]
            trade_id = trade["id"]

            # Check stop-loss hit
            if trade["side"] == "buy" and trade["stop_loss"]:
                if current_price <= trade["stop_loss"]:
                    pnl = (current_price - trade["entry_price"]) * trade["amount"]
                    pnl_pct = ((current_price / trade["entry_price"]) - 1) * 100
                    fees = current_price * trade["amount"] * self.config.SIMULATED_FEE_PCT

                    # Execute sell
                    try:
                        await self.connector.place_market_order(symbol, "sell", trade["amount"])
                    except Exception as e:
                        print(f"[ERROR] Failed to execute stop-loss sell for {symbol}: {e}")
                        continue

                    close_trade(trade_id, current_price, round(pnl - fees, 4), round(pnl_pct, 2), round(fees, 4))
                    self.risk_manager.register_loss()
                    print(f"[STOP-LOSS] {symbol} stopped out at {current_price:.2f} | PnL: {pnl-fees:.2f}")
                    continue

            # Check take-profit hit
            if trade["side"] == "buy" and trade["take_profit"]:
                if current_price >= trade["take_profit"]:
                    pnl = (current_price - trade["entry_price"]) * trade["amount"]
                    pnl_pct = ((current_price / trade["entry_price"]) - 1) * 100
                    fees = current_price * trade["amount"] * self.config.SIMULATED_FEE_PCT

                    try:
                        await self.connector.place_market_order(symbol, "sell", trade["amount"])
                    except Exception as e:
                        print(f"[ERROR] Failed to execute take-profit sell for {symbol}: {e}")
                        continue

                    close_trade(trade_id, current_price, round(pnl - fees, 4), round(pnl_pct, 2), round(fees, 4))
                    print(f"[TAKE-PROFIT] {symbol} hit TP at {current_price:.2f} | PnL: +{pnl-fees:.2f}")
                    continue

            # Trailing stop: move stop-loss up if price has risen significantly
            if trade["side"] == "buy" and trade["stop_loss"]:
                entry = trade["entry_price"]
                stop = trade["stop_loss"]
                # If price is more than 1.5x the stop distance above entry, trail the stop
                stop_distance = entry - stop
                price_gain = current_price - entry
                if price_gain > stop_distance * 1.5:
                    new_stop = round(current_price - stop_distance, 2)
                    if new_stop > stop:
                        # Update stop in DB
                        from trading.trade_db import _get_db_path
                        import sqlite3
                        conn = sqlite3.connect(_get_db_path())
                        conn.execute("UPDATE trades SET stop_loss = ? WHERE id = ?", (new_stop, trade_id))
                        conn.commit()
                        conn.close()
                        print(f"[TRAIL] {symbol} stop trailed up: {stop:.2f} -> {new_stop:.2f}")

    async def _process_symbol(self, symbol: str, prices: dict):
        """Run strategy and execute trade for a single symbol."""
        if symbol not in prices:
            return

        ticker = prices[symbol]
        current_price = ticker["last"]

        # Skip if we already have an open position in this symbol
        open_trades = get_open_trades()
        symbol_positions = [t for t in open_trades if t["symbol"] == symbol and t["status"] == "open"]
        if symbol_positions:
            return  # Already have a position, managed by stop/TP checks

        # Fetch OHLCV data for strategy analysis
        try:
            df = await self.connector.get_ohlcv(
                symbol, self.config.TIMEFRAME, self.config.CANDLE_LIMIT
            )
            if df is None or len(df) < 30:
                return
        except Exception as e:
            print(f"[ERROR] Failed to fetch OHLCV for {symbol}: {e}")
            return

        # Generate trading signal
        signal = await self.strategy_engine.generate_signal(df, symbol)
        self.last_signals[symbol] = signal

        if signal["action"] == "HOLD":
            return

        # Only process BUY signals (we exit via stops/TPs)
        if signal["action"] != "BUY":
            return

        if signal["confidence"] < 0.4:
            return  # Not confident enough

        # Calculate position size with 1:3 R:R
        try:
            balance = await self.connector.get_balance()
            free_usdt = balance.get("free", {}).get("USDT", 0)
            total_equity = balance.get("total", {}).get("USDT", 0)

            if total_equity <= 0 or free_usdt <= 0:
                return

            position = self.risk_manager.calculate_position(total_equity, current_price, symbol)
        except Exception as e:
            print(f"[ERROR] Position calculation failed for {symbol}: {e}")
            return

        # Validate trade through risk checks
        validation = self.risk_manager.validate_trade(
            symbol=symbol,
            side="buy",
            amount=position["amount"],
            entry_price=current_price,
            equity=total_equity,
            current_spread_pct=ticker.get("spread_pct", 0),
            open_positions_count=len(open_trades)
        )

        if not validation["approved"]:
            if validation["reason"] != "Kill switch is active":
                print(f"[RISK] {symbol} trade rejected: {validation['reason']}")
            return

        # Check we have enough free balance
        trade_cost = position["amount"] * current_price
        if trade_cost > free_usdt * 0.98:  # 2% buffer
            return

        # EXECUTE TRADE
        print(f"\n{'='*60}")
        print(f"[TRADE] Executing BUY {symbol}")
        print(f"  Price: {current_price:.2f}")
        print(f"  Amount: {position['amount']:.6f}")
        print(f"  Stop-Loss: {position['stop_loss']:.2f}")
        print(f"  Take-Profit: {position['take_profit']:.2f}")
        print(f"  Risk: ${position['risk_amount']:.2f} | Reward: ${position['potential_reward']:.2f}")
        print(f"  Strategy: {signal['reason']}")
        print(f"  Confidence: {signal['confidence']:.1%}")
        patterns = signal.get("patterns_detected", [])
        if patterns:
            print(f"  Patterns: {', '.join(p['pattern'] for p in patterns[:5])}")
        print(f"{'='*60}\n")

        try:
            order = await self.connector.place_market_order(symbol, "buy", position["amount"])
            order_id = order.get("id", f"paper_{int(time.time())}")

            # Place exchange-side stop-loss
            try:
                await self.connector.place_stop_loss_order(
                    symbol, "sell", position["amount"], position["stop_loss"]
                )
            except Exception as e:
                print(f"[WARN] Could not place exchange stop-loss (will use local): {e}")

            # Log trade to database
            pattern_str = ", ".join(p["pattern"] for p in patterns[:3]) if patterns else "none"
            log_trade(
                symbol=symbol,
                side="buy",
                entry_price=current_price,
                amount=position["amount"],
                stop_loss=position["stop_loss"],
                take_profit=position["take_profit"],
                strategy=signal.get("reason", "multi-strategy"),
                pattern=pattern_str,
                order_id=order_id
            )

            print(f"[OK] Trade executed successfully. Order ID: {order_id}")

        except Exception as e:
            print(f"[ERROR] Trade execution failed for {symbol}: {e}")

    async def _update_equity(self, prices: dict):
        """Take equity snapshot and check drawdown."""
        try:
            balance = await self.connector.get_balance()
            free_usdt = balance.get("free", {}).get("USDT", 0)
            total = balance.get("total", {}).get("USDT", 0)

            # Calculate positions value
            positions_value = 0
            for symbol in self.config.TRADING_PAIRS:
                currency = symbol.split("/")[0]
                held = balance.get("total", {}).get(currency, 0)
                if held > 0 and symbol in prices:
                    positions_value += held * prices[symbol]["last"]

            total_equity = free_usdt + positions_value

            # Get today's starting equity for daily P&L
            start_equity = get_bot_state("day_start_equity")
            if not start_equity:
                set_bot_state("day_start_equity", str(total_equity))
                start_equity = total_equity
            else:
                start_equity = float(start_equity)

            daily_pnl = total_equity - start_equity
            daily_pnl_pct = (daily_pnl / start_equity * 100) if start_equity > 0 else 0

            # Log snapshot (every 5th cycle to avoid DB bloat)
            if self.cycle_count % 5 == 0:
                log_equity_snapshot(
                    total_equity=round(total_equity, 2),
                    free_balance=round(free_usdt, 2),
                    positions_value=round(positions_value, 2),
                    daily_pnl=round(daily_pnl, 2),
                    daily_pnl_pct=round(daily_pnl_pct, 2)
                )

            # Check drawdown
            dd_result = self.risk_manager.update_equity(total_equity)
            if dd_result["kill_switch_active"]:
                set_bot_state("kill_switch_active", "true")
                print(f"[EMERGENCY] Daily drawdown limit hit! Drawdown: {dd_result['drawdown_pct']:.2%}")
                print("[EMERGENCY] All trading halted. Manual reset required.")

            set_bot_state("daily_peak_equity", str(dd_result["peak_equity"]))
            set_bot_state("current_equity", str(round(total_equity, 2)))
            set_bot_state("daily_pnl", str(round(daily_pnl, 2)))
            set_bot_state("daily_pnl_pct", str(round(daily_pnl_pct, 2)))

        except Exception as e:
            print(f"[ERROR] Equity update failed: {e}")

    async def run_cycle(self):
        """Execute one complete trading cycle."""
        self.cycle_count += 1

        # Fetch all prices
        prices = await self._fetch_all_prices()
        if not prices:
            return
        self.last_prices = prices

        # Check stops and take-profits first
        await self._check_and_close_stops(prices)

        # Also check paper trader stops if in paper mode
        if self.config.PAPER_MODE and self.connector and self.connector.paper_trader:
            price_map = {s: p["last"] for s, p in prices.items()}
            triggered = await self.connector.check_paper_stops(price_map)
            for trig in triggered:
                print(f"[PAPER-STOP] {trig.get('symbol', '?')} triggered at {trig.get('price', '?')}")

        # Process each symbol for potential new trades
        if not self.paused and not self.risk_manager.kill_switch_active:
            for symbol in self.config.TRADING_PAIRS:
                try:
                    await self._process_symbol(symbol, prices)
                except Exception as e:
                    print(f"[ERROR] Error processing {symbol}: {e}")

        # Update equity and check drawdown
        await self._update_equity(prices)

        # Reset day at midnight UTC
        now = datetime.now(timezone.utc)
        if now.hour == 0 and now.minute == 0:
            self.risk_manager.reset_daily_state()
            set_bot_state("last_active_date", now.strftime("%Y-%m-%d"))
            set_bot_state("day_start_equity", get_bot_state("current_equity"))

    async def run(self):
        """Main trading loop."""
        await self.initialize()
        self.running = True
        self.start_time = datetime.now(timezone.utc)
        set_bot_state("bot_status", "running")
        set_bot_state("bot_mode", "paper" if self.config.PAPER_MODE else "live")
        set_bot_state("start_time", self.start_time.isoformat())

        print("\n" + "="*60)
        mode = "PAPER TRADING" if self.config.PAPER_MODE else "LIVE TRADING"
        print(f"  [STARTED] {mode} Bot Active")
        print(f"  Polling every {self.config.POLL_INTERVAL_SECONDS}s")
        print("="*60 + "\n")

        while self.running:
            try:
                if not self.paused:
                    await self.run_cycle()
                    self._errors_consecutive = 0

                    # Status log every 30 cycles
                    if self.cycle_count % 30 == 0:
                        stats = get_trade_stats()
                        equity = get_bot_state("current_equity") or "?"
                        daily_pnl = get_bot_state("daily_pnl") or "0"
                        print(f"[STATUS] Cycle #{self.cycle_count} | Equity: ${equity} | Daily P&L: ${daily_pnl} | Trades: {stats.get('total_trades', 0)} | Win Rate: {stats.get('win_rate', 0):.0%}")

                await asyncio.sleep(self.config.POLL_INTERVAL_SECONDS)

            except KeyboardInterrupt:
                print("\n[INFO] Keyboard interrupt received. Shutting down...")
                break
            except Exception as e:
                self._errors_consecutive += 1
                print(f"[ERROR] Cycle error ({self._errors_consecutive}/{self._max_consecutive_errors}): {e}")
                if self._errors_consecutive >= self._max_consecutive_errors:
                    print("[EMERGENCY] Too many consecutive errors. Halting bot.")
                    self.risk_manager.activate_emergency_stop("Too many consecutive errors")
                    break
                await asyncio.sleep(self.config.POLL_INTERVAL_SECONDS * 2)

        await self.shutdown()

    async def shutdown(self):
        """Clean shutdown."""
        self.running = False
        set_bot_state("bot_status", "stopped")
        print("[INFO] Shutting down Trading Executor...")
        if self.connector:
            await self.connector.close()
        print("[OK] Trading Executor stopped.")

    def get_status(self) -> dict:
        """Get current bot status for dashboard."""
        stats = get_trade_stats()
        uptime = ""
        if self.start_time:
            delta = datetime.now(timezone.utc) - self.start_time
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime = f"{hours}h {minutes}m {seconds}s"

        return {
            "running": self.running,
            "paused": self.paused,
            "mode": "paper" if self.config.PAPER_MODE else "live",
            "cycle_count": self.cycle_count,
            "uptime": uptime,
            "kill_switch_active": self.risk_manager.kill_switch_active,
            "in_cooldown": self.risk_manager.is_in_cooldown(),
            "daily_drawdown_pct": get_bot_state("daily_pnl_pct") or "0",
            "current_equity": get_bot_state("current_equity") or "0",
            "daily_pnl": get_bot_state("daily_pnl") or "0",
            "pairs": self.config.TRADING_PAIRS,
            "last_prices": self.last_prices,
            "stats": stats
        }

    def pause(self):
        self.paused = True
        set_bot_state("bot_status", "paused")
        print("[INFO] Bot paused")

    def resume(self):
        self.paused = False
        set_bot_state("bot_status", "running")
        print("[INFO] Bot resumed")

    def emergency_stop(self):
        self.risk_manager.activate_emergency_stop("Manual emergency stop")
        set_bot_state("bot_status", "emergency_stopped")
        print("[EMERGENCY] Manual emergency stop activated")
