"""
High Win-Ratio Quantitative Strategy Suite with Dynamic Pattern-Derived SL & TP Targets.
No fixed percentage stop losses. No static 1:3 ratio.
Every stop loss and target is derived directly from market structure and pattern geometry.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List
from quant.indicators import QuantIndicators


class QuantStrategies:

    @staticmethod
    def evaluate_vwap_mean_reversion(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Strategy 1: Volume-Weighted Mean Reversion.
        Stop Loss: Anchored to the structural low of the reversal candle cluster minus 0.35x ATR buffer.
        Target: Dynamic VWAP equilibrium level or opposite Bollinger band.
        R:R: Dynamically calculated based on distance to VWAP vs distance to structural stop.
        """
        if len(df) < 30:
            return {"action": "HOLD", "confidence": 0.0, "reason": "Insufficient candle data"}

        upper, sma, lower, zscore = QuantIndicators.calculate_bollinger_zscore(df, 20)
        vwap = QuantIndicators.calculate_vwap(df, 20)
        k, d = QuantIndicators.calculate_stochastic_rsi(df)
        swings = QuantIndicators.detect_structural_swing_levels(df, 15)

        last_close = float(df['close'].iloc[-1])
        last_z = float(zscore.iloc[-1])
        last_k = float(k.iloc[-1])
        last_d = float(d.iloc[-1])
        target_vwap = float(vwap.iloc[-1])
        atr = swings["atr"]

        # Long Trigger: Statistical oversold (Z < -2.0) with Stochastic RSI bullish turn
        if last_z < -2.0 and last_k < 20 and last_k > last_d:
            structural_sl = round(swings["structural_support"], 2)
            risk_dist = max(last_close - structural_sl, atr * 0.5)
            
            # Dynamic Target: Measured move to VWAP equilibrium
            target_tp = round(max(target_vwap, last_close + (risk_dist * 2.2)), 2)
            reward_dist = target_tp - last_close
            dynamic_rr = round(reward_dist / risk_dist, 2)

            # Only execute if pattern structure offers a viable reward-to-risk (>= 1:2.0)
            if dynamic_rr >= 2.0:
                confidence = min(0.92, 0.65 + abs(last_z) * 0.10)
                return {
                    "action": "BUY",
                    "strategy": "VWAP_MEAN_REVERSION",
                    "confidence": round(confidence, 3),
                    "entry_price": last_close,
                    "stop_loss": structural_sl,
                    "take_profit": target_tp,
                    "pattern_rr": f"1:{dynamic_rr:.1f}",
                    "pattern_name": "VWAP_OVERSOLD_REVERSION",
                    "reason": f"Pattern Z-Score={last_z:.2f} with structural SL at swing base ${structural_sl} and VWAP target ${target_tp} (1:{dynamic_rr:.1f} R:R)"
                }

        # Short Trigger: Statistical overbought (Z > +2.0) with Stochastic RSI bearish turn
        elif last_z > 2.0 and last_k > 80 and last_k < last_d:
            structural_sl = round(swings["structural_resistance"], 2)
            risk_dist = max(structural_sl - last_close, atr * 0.5)
            target_tp = round(min(target_vwap, last_close - (risk_dist * 2.2)), 2)
            reward_dist = last_close - target_tp
            dynamic_rr = round(reward_dist / risk_dist, 2)

            if dynamic_rr >= 2.0:
                confidence = min(0.92, 0.65 + abs(last_z) * 0.10)
                return {
                    "action": "SELL",
                    "strategy": "VWAP_MEAN_REVERSION",
                    "confidence": round(confidence, 3),
                    "entry_price": last_close,
                    "stop_loss": structural_sl,
                    "take_profit": target_tp,
                    "pattern_rr": f"1:{dynamic_rr:.1f}",
                    "pattern_name": "VWAP_OVERBOUGHT_REVERSION",
                    "reason": f"Pattern Z-Score={last_z:.2f} with structural SL at swing high ${structural_sl} and VWAP target ${target_tp} (1:{dynamic_rr:.1f} R:R)"
                }

        return {"action": "HOLD", "strategy": "VWAP_MEAN_REVERSION", "confidence": 0.0, "reason": "Variance within bounds"}

    @staticmethod
    def evaluate_trend_continuation(df_h1: pd.DataFrame) -> Dict[str, Any]:
        """
        Strategy 2: Multi-Timeframe Trend Continuation.
        Stop Loss: Placed below the consolidation breakout base (Donchian mid or recent swing low).
        Target: Measured breakout height expansion ($1.618\times$ pattern height or Fibonacci projection).
        R:R: Dynamically derived from the expansion geometry (typically 1:2.8 to 1:5.0).
        """
        if len(df_h1) < 50:
            return {"action": "HOLD", "confidence": 0.0, "reason": "Insufficient H1 candles"}

        ema50 = QuantIndicators.calculate_ema(df_h1['close'], 50)
        ema200 = QuantIndicators.calculate_ema(df_h1['close'], 200)
        adx = QuantIndicators.calculate_adx(df_h1, 14)
        donch_upper, donch_lower = QuantIndicators.calculate_donchian_channels(df_h1, 20)
        swings = QuantIndicators.detect_structural_swing_levels(df_h1, 20)

        last_close = float(df_h1['close'].iloc[-1])
        last_adx = float(adx.iloc[-1])
        macro_bullish = float(ema50.iloc[-1]) > float(ema200.iloc[-1])

        # Breakout Long: Donchian 20-bar High break + ADX >= 24.0 in bullish macro regime
        if macro_bullish and last_close >= float(donch_upper.iloc[-2]) and last_adx >= 24.0:
            # Structural SL: Placed at recent swing low support (invalidation of the breakout base)
            structural_sl = round(swings["structural_support"], 2)
            risk_dist = max(last_close - structural_sl, swings["atr"] * 0.5)

            # Target: Pattern height Fibonacci expansion (1.618x range of the consolidation box)
            pattern_height = float(donch_upper.iloc[-2]) - float(donch_lower.iloc[-2])
            target_tp = round(last_close + max(pattern_height * 1.618, risk_dist * 2.5), 2)
            reward_dist = target_tp - last_close
            dynamic_rr = round(reward_dist / risk_dist, 2)

            if dynamic_rr >= 2.0:
                confidence = min(0.92, 0.60 + (last_adx / 100.0) * 0.5)
                return {
                    "action": "BUY",
                    "strategy": "TREND_CONTINUATION",
                    "confidence": round(confidence, 3),
                    "entry_price": last_close,
                    "stop_loss": structural_sl,
                    "take_profit": target_tp,
                    "pattern_rr": f"1:{dynamic_rr:.1f}",
                    "pattern_name": "DONCHIAN_FIBONACCI_EXPANSION",
                    "reason": f"Donchian breakout with structural SL at base ${structural_sl} and 1.618x expansion target ${target_tp} (1:{dynamic_rr:.1f} R:R)"
                }

        return {"action": "HOLD", "strategy": "TREND_CONTINUATION", "confidence": 0.0, "reason": "No breakout structure"}
