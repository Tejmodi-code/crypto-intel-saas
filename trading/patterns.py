import pandas as pd
import numpy as np
from typing import Dict, Any, List

class PatternRecognizer:
    def __init__(self):
        pass

    def _get_base_result(self, pattern: str) -> Dict[str, Any]:
        return {
            'detected': False,
            'pattern': pattern,
            'signal': 'neutral',
            'confidence': 0.0,
            'description': ''
        }

    # Candlestick Patterns
    def detect_doji(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('doji')
        if len(df) < 5: return res
        last = df.iloc[-1]
        body = abs(last['close'] - last['open'])
        total_range = last['high'] - last['low']
        if total_range > 0 and body / total_range < 0.1:
            res.update({'detected': True, 'confidence': 0.5, 'description': 'Doji detected (indecision)'})
        return res

    def detect_hammer(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('hammer')
        if len(df) < 5: return res
        last = df.iloc[-1]
        body = abs(last['close'] - last['open'])
        lower_shadow = min(last['open'], last['close']) - last['low']
        upper_shadow = last['high'] - max(last['open'], last['close'])
        if lower_shadow >= 2 * body and upper_shadow < body:
            res.update({'detected': True, 'signal': 'bullish', 'confidence': 0.7, 'description': 'Hammer detected'})
        return res

    def detect_inverted_hammer(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('inverted_hammer')
        if len(df) < 5: return res
        last = df.iloc[-1]
        body = abs(last['close'] - last['open'])
        lower_shadow = min(last['open'], last['close']) - last['low']
        upper_shadow = last['high'] - max(last['open'], last['close'])
        if upper_shadow >= 2 * body and lower_shadow < body:
            res.update({'detected': True, 'signal': 'bullish', 'confidence': 0.6, 'description': 'Inverted Hammer detected'})
        return res

    def detect_engulfing(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('engulfing')
        if len(df) < 2: return res
        curr, prev = df.iloc[-1], df.iloc[-2]
        curr_body = abs(curr['close'] - curr['open'])
        prev_body = abs(prev['close'] - prev['open'])
        
        is_curr_green = curr['close'] > curr['open']
        is_prev_red = prev['close'] < prev['open']
        is_curr_red = curr['close'] < curr['open']
        is_prev_green = prev['close'] > prev['open']

        if curr_body > prev_body:
            if is_curr_green and is_prev_red and curr['close'] >= prev['open'] and curr['open'] <= prev['close']:
                res.update({'detected': True, 'signal': 'bullish', 'confidence': 0.8, 'description': 'Bullish Engulfing'})
            elif is_curr_red and is_prev_green and curr['close'] <= prev['open'] and curr['open'] >= prev['close']:
                res.update({'detected': True, 'signal': 'bearish', 'confidence': 0.8, 'description': 'Bearish Engulfing'})
        return res

    def detect_morning_star(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('morning_star')
        if len(df) < 3: return res
        c3, c2, c1 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
        if c3['close'] < c3['open'] and abs(c3['close']-c3['open']) > (c3['high']-c3['low'])*0.5:
            if abs(c2['close']-c2['open']) < (c2['high']-c2['low'])*0.3 and c2['open'] < c3['close']:
                if c1['close'] > c1['open'] and c1['close'] > (c3['open']+c3['close'])/2:
                    res.update({'detected': True, 'signal': 'bullish', 'confidence': 0.85, 'description': 'Morning Star'})
        return res

    def detect_evening_star(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('evening_star')
        if len(df) < 3: return res
        c3, c2, c1 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
        if c3['close'] > c3['open'] and abs(c3['close']-c3['open']) > (c3['high']-c3['low'])*0.5:
            if abs(c2['close']-c2['open']) < (c2['high']-c2['low'])*0.3 and c2['open'] > c3['close']:
                if c1['close'] < c1['open'] and c1['close'] < (c3['open']+c3['close'])/2:
                    res.update({'detected': True, 'signal': 'bearish', 'confidence': 0.85, 'description': 'Evening Star'})
        return res

    def detect_three_white_soldiers(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('three_white_soldiers')
        if len(df) < 3: return res
        c3, c2, c1 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
        if all(c['close'] > c['open'] for c in [c3, c2, c1]):
            if c2['close'] > c3['close'] and c1['close'] > c2['close']:
                res.update({'detected': True, 'signal': 'bullish', 'confidence': 0.9, 'description': 'Three White Soldiers'})
        return res

    def detect_three_black_crows(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('three_black_crows')
        if len(df) < 3: return res
        c3, c2, c1 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
        if all(c['close'] < c['open'] for c in [c3, c2, c1]):
            if c2['close'] < c3['close'] and c1['close'] < c2['close']:
                res.update({'detected': True, 'signal': 'bearish', 'confidence': 0.9, 'description': 'Three Black Crows'})
        return res

    def detect_spinning_top(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('spinning_top')
        if len(df) < 1: return res
        last = df.iloc[-1]
        body = abs(last['close'] - last['open'])
        lower_shadow = min(last['open'], last['close']) - last['low']
        upper_shadow = last['high'] - max(last['open'], last['close'])
        if lower_shadow > body and upper_shadow > body:
            res.update({'detected': True, 'confidence': 0.4, 'description': 'Spinning Top'})
        return res

    def detect_marubozu(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('marubozu')
        if len(df) < 1: return res
        last = df.iloc[-1]
        body = abs(last['close'] - last['open'])
        total_range = last['high'] - last['low']
        if total_range > 0 and body / total_range > 0.95:
            sig = 'bullish' if last['close'] > last['open'] else 'bearish'
            res.update({'detected': True, 'signal': sig, 'confidence': 0.8, 'description': 'Marubozu'})
        return res

    def detect_harami(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('harami')
        if len(df) < 2: return res
        curr, prev = df.iloc[-1], df.iloc[-2]
        if max(curr['open'], curr['close']) < max(prev['open'], prev['close']) and \
           min(curr['open'], curr['close']) > min(prev['open'], prev['close']):
            sig = 'bullish' if prev['close'] < prev['open'] else 'bearish'
            res.update({'detected': True, 'signal': sig, 'confidence': 0.6, 'description': 'Harami'})
        return res

    def detect_piercing_line(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('piercing_line')
        if len(df) < 2: return res
        curr, prev = df.iloc[-1], df.iloc[-2]
        if prev['close'] < prev['open'] and curr['close'] > curr['open']:
            if curr['open'] < prev['low'] and curr['close'] > (prev['open'] + prev['close']) / 2 and curr['close'] < prev['open']:
                res.update({'detected': True, 'signal': 'bullish', 'confidence': 0.7, 'description': 'Piercing Line'})
        return res

    def detect_dark_cloud_cover(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('dark_cloud_cover')
        if len(df) < 2: return res
        curr, prev = df.iloc[-1], df.iloc[-2]
        if prev['close'] > prev['open'] and curr['close'] < curr['open']:
            if curr['open'] > prev['high'] and curr['close'] < (prev['open'] + prev['close']) / 2 and curr['close'] > prev['open']:
                res.update({'detected': True, 'signal': 'bearish', 'confidence': 0.7, 'description': 'Dark Cloud Cover'})
        return res

    def detect_tweezer_top(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('tweezer_top')
        if len(df) < 2: return res
        curr, prev = df.iloc[-1], df.iloc[-2]
        if abs(curr['high'] - prev['high']) / prev['high'] < 0.005:
            res.update({'detected': True, 'signal': 'bearish', 'confidence': 0.6, 'description': 'Tweezer Top'})
        return res

    def detect_tweezer_bottom(self, df: pd.DataFrame) -> Dict[str, Any]:
        res = self._get_base_result('tweezer_bottom')
        if len(df) < 2: return res
        curr, prev = df.iloc[-1], df.iloc[-2]
        if abs(curr['low'] - prev['low']) / prev['low'] < 0.005:
            res.update({'detected': True, 'signal': 'bullish', 'confidence': 0.6, 'description': 'Tweezer Bottom'})
        return res

    # Chart Patterns
    def detect_double_top(self, df: pd.DataFrame, lookback: int = 50) -> Dict[str, Any]:
        res = self._get_base_result('double_top')
        if len(df) < lookback: return res
        # Basic heuristic
        return res
        
    def detect_double_bottom(self, df: pd.DataFrame, lookback: int = 50) -> Dict[str, Any]:
        res = self._get_base_result('double_bottom')
        return res

    def detect_head_and_shoulders(self, df: pd.DataFrame, lookback: int = 60) -> Dict[str, Any]:
        res = self._get_base_result('head_and_shoulders')
        return res

    def detect_inverse_head_and_shoulders(self, df: pd.DataFrame, lookback: int = 60) -> Dict[str, Any]:
        res = self._get_base_result('inverse_head_and_shoulders')
        return res

    def detect_ascending_triangle(self, df: pd.DataFrame, lookback: int = 30) -> Dict[str, Any]:
        res = self._get_base_result('ascending_triangle')
        return res

    def detect_descending_triangle(self, df: pd.DataFrame, lookback: int = 30) -> Dict[str, Any]:
        res = self._get_base_result('descending_triangle')
        return res

    def detect_symmetrical_triangle(self, df: pd.DataFrame, lookback: int = 30) -> Dict[str, Any]:
        res = self._get_base_result('symmetrical_triangle')
        return res

    def detect_bull_flag(self, df: pd.DataFrame, lookback: int = 20) -> Dict[str, Any]:
        res = self._get_base_result('bull_flag')
        return res

    def detect_bear_flag(self, df: pd.DataFrame, lookback: int = 20) -> Dict[str, Any]:
        res = self._get_base_result('bear_flag')
        return res

    def detect_rising_wedge(self, df: pd.DataFrame, lookback: int = 30) -> Dict[str, Any]:
        res = self._get_base_result('rising_wedge')
        return res

    def detect_falling_wedge(self, df: pd.DataFrame, lookback: int = 30) -> Dict[str, Any]:
        res = self._get_base_result('falling_wedge')
        return res

    def detect_cup_and_handle(self, df: pd.DataFrame, lookback: int = 50) -> Dict[str, Any]:
        res = self._get_base_result('cup_and_handle')
        return res

    # Technical Indicators
    def calculate_ema(self, df: pd.DataFrame, period: int) -> pd.Series:
        return df['close'].ewm(span=period, adjust=False).mean()

    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        return true_range.rolling(period).mean()

    def calculate_macd(self, df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
        exp1 = df['close'].ewm(span=fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=slow, adjust=False).mean()
        macd = exp1 - exp2
        sig = macd.ewm(span=signal, adjust=False).mean()
        hist = macd - sig
        return pd.DataFrame({'macd': macd, 'signal': sig, 'histogram': hist})

    def calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20, std_dev: int = 2) -> pd.DataFrame:
        sma = df['close'].rolling(period).mean()
        std = df['close'].rolling(period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return pd.DataFrame({'upper': upper, 'middle': sma, 'lower': lower})

    def calculate_volume_sma(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        return df['volume'].rolling(period).mean()

    def calculate_stochastic(self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
        low_min = df['low'].rolling(k_period).min()
        high_max = df['high'].rolling(k_period).max()
        k = 100 * ((df['close'] - low_min) / (high_max - low_min))
        d = k.rolling(d_period).mean()
        return pd.DataFrame({'k': k, 'd': d})

    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        if len(df) < period + 1:
            return pd.Series(0.0, index=df.index)
        
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        
        plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(period).mean() / (atr + 1e-9))
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(period).mean() / (atr + 1e-9))
        
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
        adx = dx.rolling(period).mean().fillna(25.0)
        return adx

    # Master Scanner
    async def scan_all_patterns(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        patterns = [
            self.detect_doji(df), self.detect_hammer(df), self.detect_inverted_hammer(df),
            self.detect_engulfing(df), self.detect_morning_star(df), self.detect_evening_star(df),
            self.detect_three_white_soldiers(df), self.detect_three_black_crows(df),
            self.detect_spinning_top(df), self.detect_marubozu(df), self.detect_harami(df),
            self.detect_piercing_line(df), self.detect_dark_cloud_cover(df),
            self.detect_tweezer_top(df), self.detect_tweezer_bottom(df),
            self.detect_double_top(df), self.detect_double_bottom(df),
            self.detect_head_and_shoulders(df), self.detect_inverse_head_and_shoulders(df),
            self.detect_ascending_triangle(df), self.detect_descending_triangle(df),
            self.detect_symmetrical_triangle(df), self.detect_bull_flag(df),
            self.detect_bear_flag(df), self.detect_rising_wedge(df),
            self.detect_falling_wedge(df), self.detect_cup_and_handle(df)
        ]
        detected = [p for p in patterns if p['detected']]
        detected.sort(key=lambda x: x['confidence'], reverse=True)
        return detected

    async def get_pattern_consensus(self, df: pd.DataFrame) -> Dict[str, Any]:
        patterns = await self.scan_all_patterns(df)
        bullish = sum(1 for p in patterns if p['signal'] == 'bullish')
        bearish = sum(1 for p in patterns if p['signal'] == 'bearish')
        
        signal = 'neutral'
        strength = 0.0
        if bullish > bearish:
            signal = 'bullish'
            strength = min(1.0, (bullish - bearish) / 5.0)
        elif bearish > bullish:
            signal = 'bearish'
            strength = min(1.0, (bearish - bullish) / 5.0)

        return {
            'signal': signal,
            'strength': strength,
            'patterns_detected': patterns,
            'bullish_count': bullish,
            'bearish_count': bearish
        }
