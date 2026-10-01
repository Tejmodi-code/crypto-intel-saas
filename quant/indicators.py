"""
Vectorized Quantitative & Technical Indicators with Structural Swing Detection.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple


class QuantIndicators:

    @staticmethod
    def calculate_vwap(df: pd.DataFrame, period: int = 20) -> pd.Series:
        typical_price = (df['high'] + df['low'] + df['close']) / 3.0
        vwap = (typical_price * df['volume']).rolling(window=period).sum() / df['volume'].rolling(window=period).sum().replace(0, np.nan)
        return vwap.bfill()

    @staticmethod
    def calculate_bollinger_zscore(df: pd.DataFrame, period: int = 20) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        sma = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std().replace(0, 1e-8)
        upper = sma + (std * 2.5)
        lower = sma - (std * 2.5)
        zscore = (df['close'] - sma) / std
        return upper, sma, lower, zscore

    @staticmethod
    def calculate_stochastic_rsi(df: pd.DataFrame, rsi_period: int = 14, stoch_period: int = 14, k_period: int = 3, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean().replace(0, 1e-8)
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        rsi_min = rsi.rolling(window=stoch_period).min()
        rsi_max = rsi.rolling(window=stoch_period).max()
        stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min).replace(0, 1e-8) * 100

        k = stoch_rsi.rolling(window=k_period).mean()
        d = k.rolling(window=d_period).mean()
        return k.bfill(), d.bfill()

    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close'].shift(1)).abs()
        tr3 = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean().bfill()

    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        up = df['high'].diff()
        down = -df['low'].diff()

        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)

        tr = QuantIndicators.calculate_atr(df, period=1)
        tr_smooth = tr.rolling(window=period).sum().replace(0, 1e-8)

        plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(window=period).sum() / tr_smooth)
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(window=period).sum() / tr_smooth)

        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-8))
        adx = dx.rolling(window=period).mean().bfill()
        return adx

    @staticmethod
    def calculate_donchian_channels(df: pd.DataFrame, period: int = 20) -> Tuple[pd.Series, pd.Series]:
        upper = df['high'].rolling(window=period).max()
        lower = df['low'].rolling(window=period).min()
        return upper, lower

    @staticmethod
    def detect_structural_swing_levels(df: pd.DataFrame, lookback: int = 20) -> Dict[str, float]:
        """
        Detects exact recent swing high (resistance) and swing low (support)
        to anchor structural pattern stop losses and measured targets.
        """
        recent = df.iloc[-lookback:]
        swing_high = float(recent['high'].max())
        swing_low = float(recent['low'].min())
        recent_atr = float(QuantIndicators.calculate_atr(df, 14).iloc[-1])
        
        return {
            "swing_high": swing_high,
            "swing_low": swing_low,
            "atr": recent_atr,
            "structural_support": swing_low - (0.35 * recent_atr),
            "structural_resistance": swing_high + (0.35 * recent_atr)
        }
