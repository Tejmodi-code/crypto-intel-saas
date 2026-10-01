"""
Session Classifier & Market Timing Intelligence
Tags timestamps with market sessions (Asian, London, New York, Overlaps) and liquidity context.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List
import pandas as pd


class SessionClassifier:
    """Classifies UTC timestamps into market trading sessions and liquidity regimes."""

    @staticmethod
    def get_session(dt: datetime) -> Dict[str, Any]:
        """
        Determines the session, overlaps, and liquidity status for a given datetime.
        All calculations are strictly based on UTC hours.
        """
        hour = dt.hour
        day_name = dt.strftime('%A')
        is_weekend = dt.weekday() >= 5

        # Check Overlaps first
        if 12 <= hour < 16:
            session_name = "London_NY_Overlap"
            primary_session = "New York / London"
            liquidity_tier = "High Volatility / Peak Liquidity"
            is_overlap = True
        elif 7 <= hour < 8:
            session_name = "Asia_London_Overlap"
            primary_session = "Asia / London"
            liquidity_tier = "Medium-High Liquidity"
            is_overlap = True
        elif 0 <= hour < 8:
            session_name = "Asian"
            primary_session = "Asian (Tokyo/Sydney)"
            liquidity_tier = "Medium-Low / Mean Reverting"
            is_overlap = False
        elif 8 <= hour < 12:
            session_name = "London"
            primary_session = "London (Europe)"
            liquidity_tier = "High Liquidity / Trend Continuation"
            is_overlap = False
        elif 16 <= hour < 21:
            session_name = "New York"
            primary_session = "New York (US Afternoon)"
            liquidity_tier = "High Liquidity / Institutional Trend"
            is_overlap = False
        else:
            session_name = "Off_Hours"
            primary_session = "Late NY / Sydney Pre-open"
            liquidity_tier = "Low Liquidity / Chop"
            is_overlap = False

        if is_weekend:
            liquidity_tier = "Weekend / Retail Driven"

        return {
            'session': session_name,
            'primary_session': primary_session,
            'hour_utc': hour,
            'day_name': day_name,
            'is_weekend': is_weekend,
            'is_overlap': is_overlap,
            'liquidity_tier': liquidity_tier
        }

    @classmethod
    def tag_dataframe(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Adds session metadata columns to a pandas DataFrame with datetime index or column."""
        df = df.copy()
        
        # Ensure datetime column exists
        if 'datetime' not in df.columns:
            if 'timestamp' in df.columns:
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
            else:
                df['datetime'] = pd.to_datetime(df.index, utc=True)
        else:
            df['datetime'] = pd.to_datetime(df['datetime'], utc=True)

        sessions = []
        is_overlaps = []
        liquidity_tiers = []
        hours = []

        for dt in df['datetime']:
            info = cls.get_session(dt)
            sessions.append(info['session'])
            is_overlaps.append(info['is_overlap'])
            liquidity_tiers.append(info['liquidity_tier'])
            hours.append(info['hour_utc'])

        df['session'] = sessions
        df['is_overlap'] = is_overlaps
        df['liquidity_tier'] = liquidity_tiers
        df['hour_utc'] = hours
        return df
