"""
Pattern Memory Bridge - Modular Connector
Connects the live bot & strategies to 3-year pattern memory storage without tight coupling.
"""
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import os

from backtesting.backtest_config import backtest_config
from backtesting.sessions import SessionClassifier
from backtesting.pattern_memory import PatternMemory


class PatternMemoryBridge:
    """Provides real-time pattern intelligence and historical validation for live trading."""

    def __init__(self, memory_db_path: Optional[str] = None):
        self.memory_db_path = memory_db_path or backtest_config.PATTERN_MEMORY_DB_PATH
        self._memory = None
        if os.path.exists(self.memory_db_path):
            try:
                self._memory = PatternMemory(self.memory_db_path)
            except Exception as e:
                print(f"[WARN] Could not initialize PatternMemory: {e}")

    def get_current_session(self) -> Dict[str, Any]:
        """Returns the current active market session in UTC."""
        now = datetime.now(timezone.utc)
        return SessionClassifier.get_session(now)

    def evaluate_live_pattern(self, pattern_name: str, signal_type: str = 'bullish',
                              trend_regime: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluates a newly detected pattern against 3 years of historical memory
        in the currently active session.
        """
        curr_session_info = self.get_current_session()
        session_name = curr_session_info['session']

        if not self._memory or not os.path.exists(self.memory_db_path):
            return {
                'has_memory': False,
                'session': session_name,
                'primary_session': curr_session_info['primary_session'],
                'recommendation': 'CONFIRMATION_REQUIRED',
                'confidence_boost': 0.0,
                'reason': "Pattern memory database not yet populated. Using standard multi-strategy consensus."
            }

        try:
            lookup = self._memory.lookup_pattern(
                pattern_name=pattern_name,
                session=session_name,
                signal_type=signal_type,
                trend_regime=trend_regime
            )
            lookup['has_memory'] = lookup.get('has_history', False)
            lookup['current_session'] = session_name
            lookup['session_tier'] = curr_session_info['liquidity_tier']
            return lookup
        except Exception as e:
            return {
                'has_memory': False,
                'session': session_name,
                'recommendation': 'CONFIRMATION_REQUIRED',
                'confidence_boost': 0.0,
                'reason': f"Memory lookup error: {e}"
            }

# Global bridge instance
memory_bridge = PatternMemoryBridge()
