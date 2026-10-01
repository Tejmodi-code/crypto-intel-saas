"""
Pattern Memory Storage & Self-Learning Engine
Stores pattern fingerprints, historical win rates by session, and auto-applies recurring patterns.
"""
import sqlite3
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from backtesting.backtest_config import backtest_config


class PatternMemory:
    """
    Long-term memory repository for technical chart and candlestick patterns.
    Indexes patterns by market session and market regime, calculating empirical win rates.
    When a pattern repeats, this engine auto-evaluates its statistical edge.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or backtest_config.PATTERN_MEMORY_DB_PATH
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Initializes pattern memory and instance tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Pattern statistical memory
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pattern_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_name TEXT,
                    session TEXT,
                    signal_type TEXT,
                    trend_regime TEXT,
                    total_occurrences INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    win_rate REAL DEFAULT 0.0,
                    avg_pnl_pct REAL DEFAULT 0.0,
                    profit_factor REAL DEFAULT 0.0,
                    expectancy REAL DEFAULT 0.0,
                    recommendation TEXT DEFAULT 'CONFIRMATION_REQUIRED',
                    updated_at TEXT,
                    UNIQUE(pattern_name, session, signal_type, trend_regime)
                )
            ''')
            
            # Granular historical instances
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pattern_instances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    symbol TEXT,
                    pattern_name TEXT,
                    session TEXT,
                    signal_type TEXT,
                    trend_regime TEXT,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    outcome TEXT,
                    pnl_pct REAL,
                    bars_held INTEGER,
                    created_at TEXT
                )
            ''')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mem_lookup ON pattern_memory(pattern_name, session, signal_type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_inst_patt ON pattern_instances(pattern_name, session)')
            conn.commit()

    def record_instance(self, timestamp: str, symbol: str, pattern_name: str, session: str,
                        signal_type: str, trend_regime: str, entry_price: float,
                        stop_loss: float, take_profit: float, outcome: str,
                        pnl_pct: float, bars_held: int) -> None:
        """Records a single resolved pattern outcome into historical instance memory."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO pattern_instances (
                    timestamp, symbol, pattern_name, session, signal_type,
                    trend_regime, entry_price, stop_loss, take_profit,
                    outcome, pnl_pct, bars_held, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, symbol, pattern_name, session, signal_type,
                  trend_regime, entry_price, stop_loss, take_profit,
                  outcome, pnl_pct, bars_held, now))
            conn.commit()

    def compile_memory(self) -> None:
        """
        Compiles all raw instances into aggregated pattern memory records with
        win rates, profit factors, and automated recommendations.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    pattern_name, session, signal_type, trend_regime,
                    COUNT(*) as total_occurrences,
                    SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
                    AVG(pnl_pct) as avg_pnl_pct,
                    SUM(CASE WHEN pnl_pct > 0 THEN pnl_pct ELSE 0 END) as gross_profit,
                    SUM(CASE WHEN pnl_pct < 0 THEN ABS(pnl_pct) ELSE 0 END) as gross_loss
                FROM pattern_instances
                GROUP BY pattern_name, session, signal_type, trend_regime
            ''')
            
            rows = cursor.fetchall()
            for r in rows:
                total = r['total_occurrences']
                wins = r['wins'] or 0
                losses = r['losses'] or 0
                win_rate = (wins / total) if total > 0 else 0.0
                avg_pnl = r['avg_pnl_pct'] or 0.0
                gross_profit = r['gross_profit'] or 0.0
                gross_loss = r['gross_loss'] or 0.001
                profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 3.0
                
                # Expectancy = (WinRate * 3.0) - (LossRate * 1.0) for 1:3 R:R
                loss_rate = 1.0 - win_rate
                expectancy = (win_rate * backtest_config.RISK_REWARD_RATIO) - (loss_rate * 1.0)
                
                # Automated Recommendation logic
                if total >= backtest_config.AUTO_APPLY_MIN_SAMPLES and win_rate >= backtest_config.AUTO_APPLY_MIN_WIN_RATE:
                    rec = 'AUTO_APPLY'
                elif total >= backtest_config.AUTO_APPLY_MIN_SAMPLES and win_rate <= backtest_config.FILTER_MAX_WIN_RATE:
                    rec = 'FILTER_OUT'
                else:
                    rec = 'CONFIRMATION_REQUIRED'
                    
                cursor.execute('''
                    INSERT INTO pattern_memory (
                        pattern_name, session, signal_type, trend_regime,
                        total_occurrences, winning_trades, losing_trades,
                        win_rate, avg_pnl_pct, profit_factor, expectancy,
                        recommendation, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(pattern_name, session, signal_type, trend_regime) DO UPDATE SET
                        total_occurrences = excluded.total_occurrences,
                        winning_trades = excluded.winning_trades,
                        losing_trades = excluded.losing_trades,
                        win_rate = excluded.win_rate,
                        avg_pnl_pct = excluded.avg_pnl_pct,
                        profit_factor = excluded.profit_factor,
                        expectancy = excluded.expectancy,
                        recommendation = excluded.recommendation,
                        updated_at = excluded.updated_at
                ''', (
                    r['pattern_name'], r['session'], r['signal_type'], r['trend_regime'],
                    total, wins, losses, round(win_rate, 4), round(avg_pnl, 4),
                    round(profit_factor, 2), round(expectancy, 2), rec, now
                ))
            conn.commit()

    def lookup_pattern(self, pattern_name: str, session: str, signal_type: str = 'bullish',
                       trend_regime: Optional[str] = None) -> Dict[str, Any]:
        """
        Live query: when a pattern is detected by the bot, looks up its historical
        behavior in this exact session to auto-apply or filter.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if trend_regime:
                cursor.execute('''
                    SELECT * FROM pattern_memory
                    WHERE pattern_name = ? AND session = ? AND signal_type = ? AND trend_regime = ?
                ''', (pattern_name, session, signal_type, trend_regime))
                row = cursor.fetchone()
                if row:
                    return self._format_lookup(dict(row))
                    
            # Fallback to session aggregate without trend regime
            cursor.execute('''
                SELECT 
                    pattern_name, session, signal_type,
                    SUM(total_occurrences) as total_occurrences,
                    SUM(winning_trades) as winning_trades,
                    SUM(losing_trades) as losing_trades,
                    AVG(win_rate) as win_rate,
                    AVG(profit_factor) as profit_factor,
                    AVG(expectancy) as expectancy
                FROM pattern_memory
                WHERE pattern_name = ? AND session = ? AND signal_type = ?
                GROUP BY pattern_name, session, signal_type
            ''', (pattern_name, session, signal_type))
            row = cursor.fetchone()
            if row and row['total_occurrences']:
                d = dict(row)
                total = d['total_occurrences']
                wr = d['win_rate'] or 0.0
                if total >= backtest_config.AUTO_APPLY_MIN_SAMPLES and wr >= backtest_config.AUTO_APPLY_MIN_WIN_RATE:
                    d['recommendation'] = 'AUTO_APPLY'
                elif total >= backtest_config.AUTO_APPLY_MIN_SAMPLES and wr <= backtest_config.FILTER_MAX_WIN_RATE:
                    d['recommendation'] = 'FILTER_OUT'
                else:
                    d['recommendation'] = 'CONFIRMATION_REQUIRED'
                return self._format_lookup(d)

        # No direct match
        return {
            'has_history': False,
            'pattern_name': pattern_name,
            'session': session,
            'sample_count': 0,
            'win_rate': 0.5,
            'expectancy': 0.0,
            'recommendation': 'CONFIRMATION_REQUIRED',
            'confidence_boost': 0.0,
            'description': f"No prior memory for {pattern_name} in {session} session."
        }

    def _format_lookup(self, row: Dict[str, Any]) -> Dict[str, Any]:
        rec = row.get('recommendation', 'CONFIRMATION_REQUIRED')
        wr = row.get('win_rate', 0.5)
        
        if rec == 'AUTO_APPLY':
            confidence_boost = min(0.35, (wr - 0.5) * 0.8)
            desc = f"HIGH STATISTICAL EDGE: {wr*100:.1f}% win rate across {row['total_occurrences']} {row['session']} occurrences (1:3 R:R). Auto-applying."
        elif rec == 'FILTER_OUT':
            confidence_boost = -0.40
            desc = f"STATISTICAL TRAP: {wr*100:.1f}% low win rate in {row['session']} session. Filtering to protect capital."
        else:
            confidence_boost = 0.0
            desc = f"Moderate edge ({wr*100:.1f}% win rate, {row['total_occurrences']} samples). Standard multi-strategy confirmation required."

        return {
            'has_history': True,
            'pattern_name': row.get('pattern_name'),
            'session': row.get('session'),
            'sample_count': row.get('total_occurrences', 0),
            'win_rate': row.get('win_rate', 0.0),
            'profit_factor': row.get('profit_factor', 1.0),
            'expectancy': row.get('expectancy', 0.0),
            'recommendation': rec,
            'confidence_boost': confidence_boost,
            'description': desc
        }

    def get_top_patterns(self, session: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
        """Returns the top performing patterns sorted by win rate and sample count."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if session and session != 'ALL':
                cursor.execute('''
                    SELECT * FROM pattern_memory
                    WHERE session = ? AND total_occurrences >= ?
                    ORDER BY win_rate DESC, total_occurrences DESC
                    LIMIT ?
                ''', (session, backtest_config.AUTO_APPLY_MIN_SAMPLES, limit))
            else:
                cursor.execute('''
                    SELECT 
                        pattern_name, signal_type,
                        SUM(total_occurrences) as total_occurrences,
                        SUM(winning_trades) as winning_trades,
                        SUM(losing_trades) as losing_trades,
                        AVG(win_rate) as win_rate,
                        AVG(profit_factor) as profit_factor,
                        AVG(expectancy) as expectancy,
                        session
                    FROM pattern_memory
                    WHERE total_occurrences >= ?
                    GROUP BY pattern_name, signal_type, session
                    ORDER BY win_rate DESC, total_occurrences DESC
                    LIMIT ?
                ''', (backtest_config.AUTO_APPLY_MIN_SAMPLES, limit))
            return [dict(r) for r in cursor.fetchall()]

    def get_session_stats(self) -> List[Dict[str, Any]]:
        """Aggregates historical trading performance by session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    session,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
                    AVG(pnl_pct) as avg_pnl_pct,
                    SUM(pnl_pct) as total_pnl_pct
                FROM pattern_instances
                GROUP BY session
                ORDER BY wins * 1.0 / COUNT(*) DESC
            ''')
            rows = cursor.fetchall()
            results = []
            for r in rows:
                total = r['total_trades']
                wins = r['wins'] or 0
                losses = r['losses'] or 0
                wr = (wins / total) if total > 0 else 0.0
                results.append({
                    'session': r['session'],
                    'total_trades': total,
                    'winning_trades': wins,
                    'losing_trades': losses,
                    'win_rate': round(wr, 4),
                    'avg_pnl_pct': round(r['avg_pnl_pct'] or 0.0, 2),
                    'total_pnl_pct': round(r['total_pnl_pct'] or 0.0, 2)
                })
            return results
