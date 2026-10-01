import datetime
from typing import Dict, Any
from .patterns import PatternRecognizer
from .trading_config import TradingConfig

class StrategyEngine:
    def __init__(self, config: Any):
        self.config = config
        self.recognizer = PatternRecognizer()

    async def ema_crossover_strategy(self, df) -> Dict[str, Any]:
        if len(df) < 21:
            return {'action': 'HOLD', 'confidence': 0.0, 'reason': 'Insufficient data', 'strategy': 'ema_crossover'}
        
        ema9 = self.recognizer.calculate_ema(df, 9)
        ema21 = self.recognizer.calculate_ema(df, 21)
        adx = self.recognizer.calculate_adx(df, 14)
        macd = self.recognizer.calculate_macd(df)

        curr_ema9, prev_ema9 = ema9.iloc[-1], ema9.iloc[-2]
        curr_ema21, prev_ema21 = ema21.iloc[-1], ema21.iloc[-2]
        curr_adx = adx.iloc[-1]
        
        action = 'HOLD'
        confidence = 0.0
        reason = 'No clear crossover'

        if prev_ema9 <= prev_ema21 and curr_ema9 > curr_ema21 and curr_adx > 25:
            action = 'BUY'
            confidence = min(1.0, 0.5 + (curr_adx - 25) / 100)
            reason = 'Bullish EMA crossover with strong ADX'
        elif prev_ema9 >= prev_ema21 and curr_ema9 < curr_ema21:
            action = 'SELL'
            confidence = 0.7
            reason = 'Bearish EMA crossover'
            
        return {'action': action, 'confidence': confidence, 'reason': reason, 'strategy': 'ema_crossover'}

    async def rsi_mean_reversion_strategy(self, df) -> Dict[str, Any]:
        if len(df) < 20:
            return {'action': 'HOLD', 'confidence': 0.0, 'reason': 'Insufficient data', 'strategy': 'rsi_mean_reversion'}

        rsi = self.recognizer.calculate_rsi(df, 14)
        bb = self.recognizer.calculate_bollinger_bands(df, 20, 2)
        vol_sma = self.recognizer.calculate_volume_sma(df, 20)

        curr_rsi = rsi.iloc[-1]
        curr_price = df.iloc[-1]['close']
        curr_vol = df.iloc[-1]['volume']
        avg_vol = vol_sma.iloc[-1]
        lower_bb = bb.iloc[-1]['lower']
        upper_bb = bb.iloc[-1]['upper']

        action = 'HOLD'
        confidence = 0.0
        reason = 'RSI in neutral zone'

        if curr_rsi < 30 and curr_price <= lower_bb * 1.01 and curr_vol > 1.2 * avg_vol:
            action = 'BUY'
            confidence = min(1.0, 1.0 - (curr_rsi / 30))
            reason = 'Oversold RSI near lower BB with high volume'
        elif curr_rsi > 70 and curr_price >= upper_bb * 0.99:
            action = 'SELL'
            confidence = min(1.0, (curr_rsi - 70) / 30)
            reason = 'Overbought RSI near upper BB'

        return {'action': action, 'confidence': confidence, 'reason': reason, 'strategy': 'rsi_mean_reversion'}

    async def momentum_breakout_strategy(self, df) -> Dict[str, Any]:
        if len(df) < 20:
            return {'action': 'HOLD', 'confidence': 0.0, 'reason': 'Insufficient data', 'strategy': 'momentum_breakout'}

        period_high = df['high'].rolling(20).max().iloc[-2]
        period_low = df['low'].rolling(20).min().iloc[-2]
        vol_sma = self.recognizer.calculate_volume_sma(df, 20)

        curr_price = df.iloc[-1]['close']
        curr_vol = df.iloc[-1]['volume']
        avg_vol = vol_sma.iloc[-1]

        action = 'HOLD'
        confidence = 0.0
        reason = 'Price within recent range'

        if curr_price > period_high and curr_vol > 1.5 * avg_vol:
            action = 'BUY'
            confidence = 0.7
            reason = 'Bullish momentum breakout'
        elif curr_price < period_low:
            action = 'SELL'
            confidence = 0.7
            reason = 'Bearish momentum breakdown'

        # Optional: Adjust confidence based on patterns
        consensus = await self.recognizer.get_pattern_consensus(df)
        if action == 'BUY' and consensus['signal'] == 'bullish':
            confidence = min(1.0, confidence + 0.2)
        elif action == 'SELL' and consensus['signal'] == 'bearish':
            confidence = min(1.0, confidence + 0.2)
        elif action != 'HOLD' and consensus['signal'] != 'neutral':
            confidence = max(0.0, confidence - 0.2)

        return {'action': action, 'confidence': confidence, 'reason': reason, 'strategy': 'momentum_breakout'}

    async def generate_signal(self, df, symbol: str) -> Dict[str, Any]:
        print(f"[INFO] Generating signal for {symbol}")
        
        s1 = await self.ema_crossover_strategy(df)
        s2 = await self.rsi_mean_reversion_strategy(df)
        s3 = await self.momentum_breakout_strategy(df)
        
        consensus = await self.recognizer.get_pattern_consensus(df)

        score = 0.0
        score += (s1['confidence'] if s1['action'] == 'BUY' else -s1['confidence'] if s1['action'] == 'SELL' else 0) * 0.30
        score += (s2['confidence'] if s2['action'] == 'BUY' else -s2['confidence'] if s2['action'] == 'SELL' else 0) * 0.30
        score += (s3['confidence'] if s3['action'] == 'BUY' else -s3['confidence'] if s3['action'] == 'SELL' else 0) * 0.25
        score += (consensus['strength'] if consensus['signal'] == 'bullish' else -consensus['strength'] if consensus['signal'] == 'bearish' else 0) * 0.15

        action = 'HOLD'
        if score > 0.5:
            action = 'BUY'
        elif score < -0.5:
            action = 'SELL'

        return {
            'symbol': symbol,
            'action': action,
            'confidence': abs(score),
            'strategies': [s1, s2, s3],
            'patterns_detected': consensus['patterns_detected'],
            'pattern_consensus': consensus['signal'],
            'reason': f"Weighted score: {score:.2f}",
            'timestamp': datetime.datetime.utcnow().isoformat()
        }
