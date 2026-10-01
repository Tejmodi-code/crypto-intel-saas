"""
BreakoutSniper Bot - Volatility expansion breakout trader.
Trades ATR breakouts + volume surges + structural patterns.
Most active during London/NY Overlap.
Fully autonomous.
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

BOT_NAME = "BreakoutSniper"
BOT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
POLL_INTERVAL = 30
BASE_RISK_PCT = 0.005
CONFIDENCE_THRESHOLD = 0.55
ACTIVE_SESSIONS = {"London/NY Overlap", "London"}


class BreakoutSniperBot:
    def __init__(self, config: Optional[TradingConfig] = None):
        self.config = config or TradingConfig()
        self.config.RISK_PER_TRADE = BASE_RISK_PCT
        self.connector: Optional[ExchangeConnector] = None
        self.risk_manager = RiskManager(self.config)
        self.paused = False
        self.running = False
        self.cycle = 0
        self.cooldown_until: Optional[float] = None
        self._recent_breakouts: Dict[str, float] = {}

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
            return
        for symbol in BOT_SYMBOLS:
            await self._process_symbol(symbol, current_session)

    async def _process_symbol(self, symbol: str, session: str) -> None:
        try:
            last_breakout = self._recent_breakouts.get(symbol, 0)
            if _time.time() - last_breakout < 7200:
                return
            candles = await self.connector.get_ohlcv(symbol, "1h", limit=100)
            if not candles or len(candles) < 30:
                return
            ticker = await self.connector.get_ticker(symbol)
            current_price = ticker.get("last", 0)
            if current_price <= 0:
                return
            signal = _breakout_signal(candles, current_price)
            if signal["action"] == "BUY" and signal["confidence"] >= CONFIDENCE_THRESHOLD:
                await self._try_buy(symbol, current_price, signal, ticker, session)
            await self._manage_positions(symbol, current_price)
        except Exception as e:
            print(f"[{BOT_NAME}] {symbol}: {e}")

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
            self._recent_breakouts[symbol] = _time.time()
            log_trade(
                symbol=symbol, side="buy", entry_price=price,
                amount=position["amount"], stop_loss=position["stop_loss"],
                take_profit=position["take_profit"], strategy=BOT_NAME,
                pattern=",".join(signal.get("patterns", [])) or "atr_breakout",
                order_id=str(order.get("id", ""))
            )
            bus.trade_opened(BOT_NAME, symbol, "buy", price, position["amount"],
                             position["stop_loss"], position["take_profit"], BOT_NAME)
            print(f"[{BOT_NAME}] BREAKOUT BUY {symbol} @ {price:.4f}")

    async def _manage_positions(self, symbol: str, price: float) -> None:
        for t in get_open_trades():
            if t["symbol"] != symbol or t["strategy"] != BOT_NAME:
                continue
            entry = t["entry_price"]
            stop = t["stop_loss"]
            unrealized_pct = (price - entry) / entry
            if unrealized_pct >= 0.02:
                trail_stop = price * (1 - 0.01)
                if trail_stop > stop:
                    stop = trail_stop
            if price <= stop:
                pnl = (price - entry) * t["amount"]
                close_trade(t["id"], price, pnl, (price - entry) / entry, 0)
                bus.stop_loss_hit(BOT_NAME, symbol, price, abs((price - entry) / entry))
                self.cooldown_until = _time.time() + self.config.COOLDOWN_SECONDS
                self.risk_manager.register_loss(abs((price - entry) / entry))
            elif price >= t["take_profit"]:
                pnl = (price - entry) * t["amount"]
                close_trade(t["id"], price, pnl, (price - entry) / entry, 0)
                bus.take_profit_hit(BOT_NAME, symbol, price, (price - entry) / entry)


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    return sum(trs[-period:]) / period


def _breakout_signal(candles: list, current_price: float) -> Dict[str, Any]:
    closes = [c[4] for c in candles]
    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]
    volumes = [c[5] for c in candles]

    confidence = 0.0
    reasons = []
    patterns = []

    resistance = max(highs[-20:-1]) if len(highs) >= 20 else highs[-1]
    atr = _atr(highs, lows, closes, 14)

    if current_price > resistance:
        breakout_strength = (current_price - resistance) / atr if atr > 0 else 0
        if breakout_strength >= 0.5:
            confidence += 0.40
            reasons.append(f"ATR breakout above {resistance:.4f} strength={breakout_strength:.2f}x")
            patterns.append("atr_breakout")

    avg_vol = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else 0
    if avg_vol > 0 and volumes[-1] > avg_vol * 1.5:
        confidence += 0.30
        reasons.append(f"Volume surge {volumes[-1]/avg_vol:.1f}x average")
        patterns.append("volume_surge")

    if len(closes) >= 4 and closes[-1] > closes[-2] > closes[-3]:
        confidence += 0.20
        reasons.append("3 consecutive higher closes")
        patterns.append("momentum_continuation")

    upper_wick = highs[-1] - closes[-1]
    if atr > 0 and upper_wick > atr * 0.5:
        confidence -= 0.15
        reasons.append("Large upper wick - possible false breakout")

    action = "BUY" if confidence >= CONFIDENCE_THRESHOLD else "HOLD"
    return {"action": action, "confidence": round(max(0, confidence), 3), "patterns": patterns, "reasons": reasons}


def _get_session() -> str:
    try:
        from trading.pattern_memory_bridge import get_current_session
        return get_current_session()
    except Exception:
        hour = datetime.now(timezone.utc).hour
        if 12 <= hour < 17:
            return "London/NY Overlap"
        elif 7 <= hour < 12:
            return "London"
        return "Other"
