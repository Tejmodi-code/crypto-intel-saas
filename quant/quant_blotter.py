"""
Institutional Order Execution Blotter & SQLite Persistent Database Engine.
Persists all portfolio equity, active positions, realized profits, and historical trade records
so that refreshing the browser or restarting the application preserves 100% of data.
"""
import sqlite3
import os
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from quant.config import quant_config


class QuantBlotter:

    def __init__(self, db_path: str = None):
        self.db_path = db_path or quant_config.DATABASE_PATH
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS execution_blotter (
                order_id TEXT PRIMARY KEY,
                timestamp TEXT,
                symbol TEXT,
                strategy TEXT,
                side TEXT,
                entry_price REAL,
                exit_price REAL,
                units REAL,
                notional_usd REAL,
                stop_loss REAL,
                take_profit REAL,
                pattern_rr TEXT,
                pnl_usd REAL,
                pnl_pct REAL,
                status TEXT,
                execution_notes TEXT
            )
        ''')
        cur.execute("PRAGMA table_info(execution_blotter)")
        columns = [col[1] for col in cur.fetchall()]
        if "pattern_rr" not in columns:
            cur.execute("ALTER TABLE execution_blotter ADD COLUMN pattern_rr TEXT")
        cur.execute('''
            CREATE TABLE IF NOT EXISTS portfolio_state (
                key TEXT PRIMARY KEY,
                initial_capital REAL,
                realized_pnl_usd REAL,
                total_equity_usd REAL,
                available_cash_usd REAL,
                last_updated TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def save_portfolio_state(self, initial_capital: float, realized_pnl: float, total_equity: float, available_cash: float):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute('''
            INSERT OR REPLACE INTO portfolio_state
            (key, initial_capital, realized_pnl_usd, total_equity_usd, available_cash_usd, last_updated)
            VALUES ('PRIMARY_PORTFOLIO', ?, ?, ?, ?, ?)
        ''', (
            initial_capital,
            realized_pnl,
            total_equity,
            available_cash,
            datetime.now(timezone.utc).isoformat()
        ))
        conn.commit()
        conn.close()

    def load_portfolio_state(self) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM portfolio_state WHERE key = 'PRIMARY_PORTFOLIO'")
        row = cur.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    def record_order(self, trade: Dict[str, Any]):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute('''
            INSERT OR REPLACE INTO execution_blotter
            (order_id, timestamp, symbol, strategy, side, entry_price, exit_price, units, notional_usd, stop_loss, take_profit, pattern_rr, pnl_usd, pnl_pct, status, execution_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade["order_id"], trade["timestamp"], trade["symbol"], trade["strategy"],
            trade["side"], trade["entry_price"], trade.get("exit_price"), trade["units"],
            trade["notional_usd"], trade["stop_loss"], trade["take_profit"], trade.get("pattern_rr", "1:3"),
            trade["pnl_usd"], trade["pnl_pct"], trade["status"], trade["execution_notes"]
        ))
        conn.commit()
        conn.close()

    def load_active_positions(self) -> Dict[str, Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM execution_blotter WHERE status = 'ACTIVE_POSITION'")
        rows = cur.fetchall()
        conn.close()
        return {r["order_id"]: dict(r) for r in rows}

    def get_blotter_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM execution_blotter ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
