"""
Signal Engine - Unified multi-timeframe + pattern memory signal generator.
Combines strategy engine outputs with 3-year pattern memory intelligence
to produce high-confidence trading signals without any manual gates.
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from trading.trading_config import TradingConfig
from trading.strategies import StrategyEngine
from trading.patterns import PatternRecognizer

# Try to import pattern memory bridge (3-year backtest data)
try:
    from trading.pattern_memory_bridge import evaluate_live_pattern, get_current_session
    MEMORY_AVAILABLE = True
except Exception:
    MEMORY_AVAILABLE = False


class SignalEngine:
    """
    Produces final BUY/SELL/HOLD signals by fusing:
      1. Strategy consensus (EMA, RSI, Momentum) - weighted vote
      2. Pattern recognition (37 candlestick/chart patterns)
      3. Pattern memory intelligence (3-year backtest win rates per session)
      4. Multi-timeframe alignment (1h primary, 4h confirmation)
    """

    def __init__(self, config: Optional[TradingConfig] = None):
        self.config = config or TradingConfig()
        self.strategy_engine = StrategyEngine(self.config)
        self.pattern_recognizer = PatternRecognizer()

    async def generate(self, symbol: str, connector, timeframe_1h: str = "1h",
                        timeframe_4h: str = "4h") -> Dict[str, Any]:
        """
        Generate a fused trading signal for a symbol.
        Returns dict with action, confidence, reasons, session, patterns.
        """
        result = {
            "symbol": symbol,
            "action": "HOLD",
            "confidence": 0.0,
            "reasons": [],
            "patterns": [],
            "session": "unknown",
            "memory_boost": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Fetch 1h candles (primary)
            candles_1h = await connector.get_ohlcv(symbol, timeframe_1h, limit=150)
            if not candles_1h or len(candles_1h) < 50:
                result["reasons"].append("Insufficient 1h candle data")
                return result

            # Fetch 4h candles (confirmation timeframe)
            candles_4h = await connector.get_ohlcv(symbol, timeframe_4h, limit=60)

            # --- Strategy Engine Signal ---
            strategy_signal = await self.strategy_engine.generate_signal(symbol, candles_1h)
            strat_action = strategy_signal.get("action", "HOLD")
            strat_confidence = strategy_signal.get("confidence", 0.0)
            result["reasons"].extend(strategy_signal.get("reasons", []))

            # --- 4h Trend Confirmation ---
            trend_4h = "neutral"
            if candles_4h and len(candles_4h) >= 20:
                closes_4h = [c[4] for c in candles_4h]
                ema20_4h = _ema(closes_4h, 20)[-1]
                ema50_4h = _ema(closes_4h, 50)[-1] if len(closes_4h) >= 50 else ema20_4h
                if closes_4h[-1] > ema20_4h > ema50_4h:
                    trend_4h = "bullish"
                elif closes_4h[-1] < ema20_4h < ema50_4h:
                    trend_4h = "bearish"

            # 4h confirmation boost / penalty
            trend_multiplier = 1.0
            if strat_action == "BUY" and trend_4h == "bullish":
                trend_multiplier = 1.25
                result["reasons"].append("4h trend confirms BUY")
            elif strat_action == "BUY" and trend_4h == "bearish":
                trend_multiplier = 0.70
                result["reasons"].append("4h trend opposes BUY - confidence reduced")
            elif strat_action == "SELL" and trend_4h == "bearish":
                trend_multiplier = 1.25
                result["reasons"].append("4h trend confirms SELL")
            elif strat_action == "SELL" and trend_4h == "bullish":
                trend_multiplier = 0.70
                result["reasons"].append("4h trend opposes SELL - confidence reduced")

            adjusted_confidence = strat_confidence * trend_multiplier

            # --- Pattern Recognition ---
            closes_1h = [c[4] for c in candles_1h]
            opens_1h = [c[1] for c in candles_1h]
            highs_1h = [c[2] for c in candles_1h]
            lows_1h = [c[3] for c in candles_1h]
            volumes_1h = [c[5] for c in candles_1h]

            detected_patterns = self.pattern_recognizer.detect_all(
                closes_1h, opens_1h, highs_1h, lows_1h, volumes_1h
            )
            result["patterns"] = detected_patterns

            # --- Pattern Memory Intelligence ---
            memory_confidence_boost = 0.0
            current_session = "unknown"
            if MEMORY_AVAILABLE and detected_patterns:
                try:
                    current_session = get_current_session()
                    result["session"] = current_session
                    for pattern_name in detected_patterns[:3]:  # top 3 patterns
                        mem = evaluate_live_pattern(pattern_name, current_session)
                        if mem:
                            win_rate = mem.get("win_rate", 0)
                            recommendation = mem.get("recommendation", "NEUTRAL")
                            if recommendation == "AUTO_APPLY" and win_rate >= 0.55:
                                memory_confidence_boost += 0.12
                                result["reasons"].append(
                                    f"Memory: {pattern_name} has {win_rate*100:.0f}% win rate in {current_session}"
                                )
                                result["memory_boost"] = True
                            elif recommendation == "FILTER_OUT":
                                memory_confidence_boost -= 0.15
                                result["reasons"].append(
                                    f"Memory: {pattern_name} filtered (low win rate in {current_session})"
                                )
                except Exception:
                    pass

            # --- Final Fused Signal ---
            final_confidence = min(1.0, adjusted_confidence + memory_confidence_boost)
            result["confidence"] = round(final_confidence, 3)

            if strat_action != "HOLD" and final_confidence >= 0.45:
                result["action"] = strat_action
            else:
                result["action"] = "HOLD"

        except Exception as e:
            result["reasons"].append(f"SignalEngine error: {str(e)}")

        return result


def _ema(values: List[float], period: int) -> List[float]:
    """Calculate Exponential Moving Average."""
    if len(values) < period:
        return values
    k = 2.0 / (period + 1)
    ema = [sum(values[:period]) / period]
    for v in values[period:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema
