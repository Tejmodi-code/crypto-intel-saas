"""
TrendRider Bot - Session-aware momentum trading bot.
Trades EMA crossovers + ADX strength + session intelligence.
Most active during London and London/NY Overlap sessions.
Fully autonomous - no permission gates.
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from trading.trading_config import TradingConfig
from trading.exchange_connector import ExchangeConnector
from trading.risk_manager import RiskManager
from trading.trade_db import (
    init_trading_db, log_trade, close_trade, get_open_trades, log_equity_snapshot, get_trade_stats
)
from trading.notification_bus import bus
from trading.bots.supervisor import supervisor

BOT_NAME = "TrendRider"
BOT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
POLL_INTERVAL = 45  # seconds between checks
BASE_RISK_PCT = 0.01   # 1% base risk per trade
MEMORY_BOOST_RISK_PCT = 0.015  # 1.5% when pattern memory confirms edge
CONFIDENCE_THRESHOLD = 0.50
ACTIVE_SESSIONS = {"London", "London/NY Overlap"}  # primary sessions


class TrendRiderBot:
    def __init__(self, config: Optional[TradingConfig] = None):
        self.config = config or TradingConfig()
        self.config.RISK_PER_TRADE = BASE_RISK_PCT
        self.connector: Optional[ExchangeConnector] = None
        self.risk_manager = RiskManager(self.config)
        self.paused = False
        self.running = False
        self.cycle = 0
        self.consecutive_losses = 0
        self.cooldown_until: Optional[float] = None

    async def initialize(self) -> None:
        init_trading_db()
        self.connector = ExchangeConnector(self.config)
        await self.connector.connect()
        print(f"[{BOT_NAME}] Initialized in {'PAPER' if self.config.PAPER_MODE else 'LIVE'} mode")

    async def run(self) -> None:
        await self.initialize()
        self.running = True
        print(f"[{BOT_NAME}] Starting trading loop on {BOT_SYMBOLS}")
        while self.running:
            supervisor.heartbeat(BOT_NAME)
            try:
                if not self.paused:
                    await self._cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[{BOT_NAME}] Cycle error: {e}")
                bus.error_alert(BOT_NAME, str(e))
            await asyncio.sleep(POLL_INTERVAL)

    async def _cycle(self) -> None:
        self.cycle += 1
        if self.cooldown_until and time_now() < self.cooldown_until:
            return

        if supervisor.is_emergency_stopped():
            return

        current_session = _get_session()
        if current_session not in ACTIVE_SESSIONS:
            if self.cycle % 20 == 0:
                print(f"[{BOT_NAME}] Resting in {current_session} session")
            return

        for symbol in BOT_SYMBOLS:
            await self._process_symbol(symbol, current_session)

    async def _process_symbol(self, symbol: str, session: str) -> None:
        try:
            candles = await self.connector.get_ohlcv(symbol, "1h", limit=120)
            if not candles or len(candles) < 60:
                return

            ticker = await self.connector.get_ticker(symbol)
            current_price = ticker.get("last", 0)
            if current_price <= 0:
                return

            signal = _ema_adx_signal(candles)

            if signal["action"] == "BUY" and signal["confidence"] >= CONFIDENCE_THRESHOLD:
                await self._try_buy(symbol, current_price, signal, ticker, session)

            await self._manage_open_positions(symbol, current_price)
        except Exception as e:
            print(f"[{BOT_NAME}] Error on {symbol}: {e}")

    async def _try_buy(self, symbol: str, price: float, signal: Dict, ticker: Dict, session: str) -> None:
        open_trades = get_open_trades()
        sym_open = [t for t in open_trades if t["symbol"] == symbol and t["strategy"] == BOT_NAME]
        if sym_open:
            return  # Already have a position

        if len(open_trades) >= self.config.MAX_OPEN_POSITIONS:
            return

        balance = await self.connector.get_balance()
        total_equity = balance.get("total", {}).get("USDT", 0)
        if total_equity <= 0:
            return

        # Apply memory boost risk if available
        risk_pct = _check_memory_boost(signal.get("patterns", []), session)
        self.config.RISK_PER_TRADE = risk_pct
        position = self.risk_manager.calculate_position(total_equity, price, symbol)

        validation = self.risk_manager.validate_trade(
            symbol=symbol, side="buy", amount=position["amount"],
            entry_price=price, equity=total_equity,
            current_spread_pct=ticker.get("spread_pct", 0),
            open_positions_count=len(open_trades)
        )
        if not validation["approved"]:
            return

        order = await self.connector.place_market_order(symbol, "buy", position["amount"], price)
        if order:
            trade_id = log_trade(
                symbol=symbol, side="buy", entry_price=price,
                amount=position["amount"], stop_loss=position["stop_loss"],
                take_profit=position["take_profit"], strategy=BOT_NAME,
                pattern=",".join(signal.get("patterns", [])) or "ema_crossover",
                order_id=str(order.get("id", ""))
            )
            bus.trade_opened(BOT_NAME, symbol, "buy", price, position["amount"],
                             position["stop_loss"], position["take_profit"], BOT_NAME)
            print(f"[{BOT_NAME}] BUY {symbol} @ {price:.4f} | SL={position['stop_loss']:.4f} | TP={position['take_profit']:.4f}")

    async def _manage_open_positions(self, symbol: str, current_price: float) -> None:
        open_trades = get_open_trades()
        for trade in open_trades:
            if trade["symbol"] != symbol or trade["strategy"] != BOT_NAME:
                continue
            entry = trade["entry_price"]
            stop = trade["stop_loss"]
            tp = trade["take_profit"]
            trade_id = trade["id"]

            # Trailing stop: once 3% up, trail at 1.5%
            unrealized_pct = (current_price - entry) / entry
            if unrealized_pct >= 0.03:
                trail_stop = current_price * (1 - 0.015)
                if trail_stop > stop:
                    stop = trail_stop

            if current_price <= stop:
                pnl = (current_price - entry) * trade["amount"]
                pnl_pct = (current_price - entry) / entry
                close_trade(trade_id, current_price, pnl, pnl_pct, 0)
                bus.stop_loss_hit(BOT_NAME, symbol, current_price, abs(pnl_pct))
                self.consecutive_losses += 1
                self.cooldown_until = time_now() + self.config.COOLDOWN_SECONDS
                self.risk_manager.register_loss(abs(pnl_pct))
                print(f"[{BOT_NAME}] SL HIT {symbol} @ {current_price:.4f} PnL={pnl:.2f}")

            elif current_price >= tp:
                pnl = (current_price - entry) * trade["amount"]
                pnl_pct = (current_price - entry) / entry
                close_trade(trade_id, current_price, pnl, pnl_pct, 0)
                bus.take_profit_hit(BOT_NAME, symbol, current_price, pnl_pct)
                self.consecutive_losses = 0
                print(f"[{BOT_NAME}] TP HIT {symbol} @ {current_price:.4f} PnL={pnl:.2f}")


def _ema(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return values
    k = 2.0 / (period + 1)
    ema = [sum(values[:period]) / period]
    for v in values[period:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def _ema_adx_signal(candles: list) -> Dict[str, Any]:
    closes = [c[4] for c in candles]
    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]

    ema9 = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    ema55 = _ema(closes, 55)

    if len(ema9) < 2 or len(ema21) < 2 or len(ema55) < 2:
        return {"action": "HOLD", "confidence": 0.0, "patterns": [], "reasons": []}

    # EMA stack bullish: price > EMA9 > EMA21 > EMA55
    bullish_stack = closes[-1] > ema9[-1] > ema21[-1] > ema55[-1]
    # Recent crossover (EMA9 crossed above EMA21 in last 3 bars)
    cross_up = ema9[-1] > ema21[-1] and ema9[-2] <= ema21[-2]
    cross_up_recent = any(
        ema9[-(i+1)] > ema21[-(i+1)] and ema9[-(i+2)] <= ema21[-(i+2)]
        for i in range(min(3, len(ema9)-2))
    ) if len(ema9) > 4 else cross_up

    # Simple ADX proxy: directional strength
    recent_range = sum(highs[-14:]) / 14 - sum(lows[-14:]) / 14
    avg_close = sum(closes[-14:]) / 14
    adx_proxy = (recent_range / avg_close) * 100 if avg_close > 0 else 0
    strong_trend = adx_proxy > 1.5

    confidence = 0.0
    reasons = []
    patterns = []

    if bullish_stack:
        confidence += 0.30
        reasons.append("Bullish EMA stack (9>21>55)")

    if cross_up_recent:
        confidence += 0.30
        reasons.append("EMA9 crossed above EMA21")
        patterns.append("ema_crossover")

    if strong_trend:
        confidence += 0.20
        reasons.append(f"Strong trend ADX proxy={adx_proxy:.1f}")

    # Momentum check
    if len(closes) >= 5:
        recent_momentum = (closes[-1] - closes[-5]) / closes[-5]
        if recent_momentum > 0.005:
            confidence += 0.15
            reasons.append(f"Positive momentum {recent_momentum*100:.2f}%")

    action = "BUY" if confidence >= 0.50 else "HOLD"
    return {"action": action, "confidence": round(confidence, 3), "patterns": patterns, "reasons": reasons}


def _get_session() -> str:
    try:
        from trading.pattern_memory_bridge import get_current_session
        return get_current_session()
    except Exception:
        hour = datetime.now(timezone.utc).hour
        if 7 <= hour < 12:
            return "London"
        elif 12 <= hour < 17:
            return "London/NY Overlap"
        elif 0 <= hour < 7:
            return "Asian"
        else:
            return "New York"


def _check_memory_boost(patterns: List[str], session: str) -> float:
    """Check if pattern memory warrants boosted risk."""
    try:
        from trading.pattern_memory_bridge import evaluate_live_pattern
        for p in patterns:
            mem = evaluate_live_pattern(p, session)
            if mem and mem.get("recommendation") == "AUTO_APPLY":
                return MEMORY_BOOST_RISK_PCT
    except Exception:
        pass
    return BASE_RISK_PCT


def time_now() -> float:
    import time
    return time.time()
