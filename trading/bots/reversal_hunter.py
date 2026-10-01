"""
ReversalHunter Bot - Mean reversion bot.
Trades RSI extremes + Bollinger Band touches + candlestick confirmation.
Most active during Asian session.
Fully autonomous - no permission gates.
"""
import asyncio
import time as _time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from trading.trading_config import TradingConfig
from trading.exchange_connector import ExchangeConnector
from trading.risk_manager import RiskManager
from trading.trade_db import init_trading_db, log_trade, close_trade, get_open_trades
from trading.notification_bus import bus
from trading.bots.supervisor import supervisor

BOT_NAME = "ReversalHunter"
BOT_SYMBOLS = ["BTC/USDT", "ETH/USDT"]
POLL_INTERVAL = 60  # Asian session moves slowly
BASE_RISK_PCT = 0.0075  # 0.75% - conservative
CONFIDENCE_THRESHOLD = 0.52
ACTIVE_SESSIONS = {"Asian", "Asia/London Overlap"}
RSI_OVERSOLD = 28
RSI_OVERBOUGHT = 72


class ReversalHunterBot:
    def __init__(self, config: Optional[TradingConfig] = None):
        self.config = config or TradingConfig()
        self.config.RISK_PER_TRADE = BASE_RISK_PCT
        self.connector: Optional[ExchangeConnector] = None
        self.risk_manager = RiskManager(self.config)
        self.paused = False
        self.running = False
        self.cycle = 0
        self.cooldown_until: Optional[float] = None

    async def initialize(self) -> None:
        init_trading_db()
        self.connector = ExchangeConnector(self.config)
        await self.connector.connect()
        print(f"[{BOT_NAME}] Initialized")

    async def run(self) -> None:
        await self.initialize()
        self.running = True
        while self.running:
            supervisor.heartbeat(BOT_NAME)
            try:
                if not self.paused:
                    await self._cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[{BOT_NAME}] Error: {e}")
                bus.error_alert(BOT_NAME, str(e))
            await asyncio.sleep(POLL_INTERVAL)

    async def _cycle(self) -> None:
        self.cycle += 1
        if self.cooldown_until and _time.time() < self.cooldown_until:
            return
        if supervisor.is_emergency_stopped():
            return
        current_session = _get_session()
        if current_session not in ACTIVE_SESSIONS:
            if self.cycle % 15 == 0:
                print(f"[{BOT_NAME}] Resting in {current_session} session")
            return
        for symbol in BOT_SYMBOLS:
            await self._process_symbol(symbol, current_session)

    async def _process_symbol(self, symbol: str, session: str) -> None:
        try:
            candles = await self.connector.get_ohlcv(symbol, "1h", limit=100)
            if not candles or len(candles) < 30:
                return
            ticker = await self.connector.get_ticker(symbol)
            current_price = ticker.get("last", 0)
            if current_price <= 0:
                return

            signal = _reversal_signal(candles)

            if signal["action"] == "BUY" and signal["confidence"] >= CONFIDENCE_THRESHOLD:
                await self._try_buy(symbol, current_price, signal, ticker, session)

            await self._manage_positions(symbol, current_price)
        except Exception as e:
            print(f"[{BOT_NAME}] {symbol} error: {e}")

    async def _try_buy(self, symbol: str, price: float, signal: Dict, ticker: Dict, session: str) -> None:
        open_trades = get_open_trades()
        if any(t["symbol"] == symbol and t["strategy"] == BOT_NAME for t in open_trades):
            return
        if len(open_trades) >= self.config.MAX_OPEN_POSITIONS:
            return
        balance = await self.connector.get_balance()
        equity = balance.get("total", {}).get("USDT", 0)
        if equity <= 0:
            return
        position = self.risk_manager.calculate_position(equity, price, symbol)
        val = self.risk_manager.validate_trade(
            symbol=symbol, side="buy", amount=position["amount"],
            entry_price=price, equity=equity,
            current_spread_pct=ticker.get("spread_pct", 0),
            open_positions_count=len(open_trades)
        )
        if not val["approved"]:
            return
        order = await self.connector.place_market_order(symbol, "buy", position["amount"], price)
        if order:
            log_trade(
                symbol=symbol, side="buy", entry_price=price,
                amount=position["amount"], stop_loss=position["stop_loss"],
                take_profit=position["take_profit"], strategy=BOT_NAME,
                pattern=",".join(signal.get("patterns", [])) or "rsi_reversal",
                order_id=str(order.get("id", ""))
            )
            bus.trade_opened(BOT_NAME, symbol, "buy", price, position["amount"],
                             position["stop_loss"], position["take_profit"], BOT_NAME)
            print(f"[{BOT_NAME}] BUY {symbol} @ {price:.4f}")

    async def _manage_positions(self, symbol: str, price: float) -> None:
        for t in get_open_trades():
            if t["symbol"] != symbol or t["strategy"] != BOT_NAME:
                continue
            entry = t["entry_price"]
            stop = t["stop_loss"]
            tp = t["take_profit"]
            if price <= stop:
                pnl = (price - entry) * t["amount"]
                close_trade(t["id"], price, pnl, (price - entry) / entry, 0)
                bus.stop_loss_hit(BOT_NAME, symbol, price, abs((price - entry) / entry))
                self.cooldown_until = _time.time() + self.config.COOLDOWN_SECONDS
                self.risk_manager.register_loss(abs((price - entry) / entry))
            elif price >= tp:
                pnl = (price - entry) * t["amount"]
                pnl_pct = (price - entry) / entry
                close_trade(t["id"], price, pnl, pnl_pct, 0)
                bus.take_profit_hit(BOT_NAME, symbol, price, pnl_pct)


def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[-(period + 1 - i) + 1 + i - 1] - closes[-(period + 1 - i) + i - 1]
        if d > 0:
            gains.append(d)
        else:
            losses.append(abs(d))
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 1e-10
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _bollinger(closes: List[float], period: int = 20) -> Dict[str, float]:
    if len(closes) < period:
        return {"upper": closes[-1] * 1.02, "mid": closes[-1], "lower": closes[-1] * 0.98}
    window = closes[-period:]
    mid = sum(window) / period
    std = (sum((x - mid) ** 2 for x in window) / period) ** 0.5
    return {"upper": mid + 2 * std, "mid": mid, "lower": mid - 2 * std}


def _reversal_signal(candles: list) -> Dict[str, Any]:
    closes = [c[4] for c in candles]
    opens = [c[1] for c in candles]
    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]

    rsi = _rsi(closes, 14)
    bb = _bollinger(closes, 20)
    confidence = 0.0
    reasons = []
    patterns = []
    action = "HOLD"

    # RSI oversold check
    if rsi < RSI_OVERSOLD:
        confidence += 0.35
        reasons.append(f"RSI oversold: {rsi:.1f}")

        # Bollinger lower band touch
        if closes[-1] <= bb["lower"] * 1.001:
            confidence += 0.25
            reasons.append("Price at Bollinger lower band")
            patterns.append("bb_lower_touch")

        # Bullish candlestick confirmation
        last_body = closes[-1] - opens[-1]
        prev_body = closes[-2] - opens[-2]
        if last_body > 0 and prev_body < 0 and abs(last_body) > abs(prev_body) * 0.5:
            confidence += 0.20
            reasons.append("Bullish candle after bearish")
            patterns.append("bullish_reversal_candle")

        # Hammer pattern (long lower wick)
        candle_range = highs[-1] - lows[-1]
        lower_wick = opens[-1] - lows[-1] if opens[-1] > closes[-1] else closes[-1] - lows[-1]
        if candle_range > 0 and lower_wick / candle_range > 0.6:
            confidence += 0.15
            reasons.append("Hammer pattern detected")
            patterns.append("hammer")

        action = "BUY" if confidence >= CONFIDENCE_THRESHOLD else "HOLD"

    return {"action": action, "confidence": round(confidence, 3), "patterns": patterns, "reasons": reasons}


def _get_session() -> str:
    try:
        from trading.pattern_memory_bridge import get_current_session
        return get_current_session()
    except Exception:
        hour = datetime.now(timezone.utc).hour
        if 0 <= hour < 7:
            return "Asian"
        elif 7 <= hour < 9:
            return "Asia/London Overlap"
        return "Other"
