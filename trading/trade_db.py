import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from trading.trading_config import config

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.TRADING_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _get_db_path() -> str:
    return config.TRADING_DB_PATH

def init_trading_db() -> None:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    symbol TEXT,
                    side TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    amount REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    status TEXT,
                    pnl REAL,
                    pnl_pct REAL,
                    strategy TEXT,
                    pattern TEXT,
                    order_id TEXT,
                    fees REAL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS equity_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    total_equity REAL,
                    free_balance REAL,
                    positions_value REAL,
                    daily_pnl REAL,
                    daily_pnl_pct REAL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                )
            ''')
            conn.commit()
            print("[INFO] Initialized trading database.")
    except Exception as e:
        print(f"[ERROR] Failed to init trading database: {e}")

def log_trade(symbol: str, side: str, entry_price: float, amount: float, stop_loss: float, take_profit: float, strategy: str, pattern: str, order_id: str) -> int:
    timestamp = datetime.utcnow().isoformat() + "Z"
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trades (timestamp, symbol, side, entry_price, amount, stop_loss, take_profit, status, strategy, pattern, order_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, symbol, side, entry_price, amount, stop_loss, take_profit, 'open', strategy, pattern, order_id))
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        print(f"[ERROR] log_trade error: {e}")
        return -1

def close_trade(trade_id: int, exit_price: float, pnl: float, pnl_pct: float, fees: float) -> None:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE trades
                SET exit_price = ?, status = ?, pnl = ?, pnl_pct = ?, fees = ?
                WHERE id = ?
            ''', (exit_price, 'closed', pnl, pnl_pct, fees, trade_id))
            conn.commit()
    except Exception as e:
        print(f"[ERROR] close_trade error: {e}")

def get_open_trades() -> List[Dict[str, Any]]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE status = 'open'")
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[ERROR] get_open_trades error: {e}")
        return []

def get_trade_history(limit: int = 50) -> List[Dict[str, Any]]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE status = 'closed' ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[ERROR] get_trade_history error: {e}")
        return []

def get_todays_trades() -> List[Dict[str, Any]]:
    today = datetime.utcnow().date().isoformat()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE timestamp LIKE ?", (f"{today}%",))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[ERROR] get_todays_trades error: {e}")
        return []

def log_equity_snapshot(total_equity: float, free_balance: float, positions_value: float, daily_pnl: float, daily_pnl_pct: float) -> None:
    timestamp = datetime.utcnow().isoformat() + "Z"
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO equity_snapshots (timestamp, total_equity, free_balance, positions_value, daily_pnl, daily_pnl_pct)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (timestamp, total_equity, free_balance, positions_value, daily_pnl, daily_pnl_pct))
            conn.commit()
    except Exception as e:
        print(f"[ERROR] log_equity_snapshot error: {e}")

def get_equity_history(limit: int = 500) -> List[Dict[str, Any]]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM equity_snapshots ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[ERROR] get_equity_history error: {e}")
        return []

def set_bot_state(key: str, value: str) -> None:
    timestamp = datetime.utcnow().isoformat() + "Z"
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO bot_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            ''', (key, value, timestamp))
            conn.commit()
    except Exception as e:
        print(f"[ERROR] set_bot_state error: {e}")

def get_bot_state(key: str) -> Optional[str]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_state WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row['value'] if row else None
    except Exception as e:
        print(f"[ERROR] get_bot_state error: {e}")
        return None

def get_trade_stats() -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT pnl FROM trades WHERE status = 'closed'")
            rows = cursor.fetchall()
            pnls = [r['pnl'] for r in rows if r['pnl'] is not None]
            
            total_trades = len(pnls)
            winning_trades = len([p for p in pnls if p > 0])
            losing_trades = len([p for p in pnls if p <= 0])
            win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0
            total_pnl = sum(pnls)
            avg_pnl = (total_pnl / total_trades) if total_trades > 0 else 0.0
            best_trade = max(pnls) if pnls else 0.0
            worst_trade = min(pnls) if pnls else 0.0
            
            return {
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "avg_pnl": avg_pnl,
                "best_trade": best_trade,
                "worst_trade": worst_trade
            }
    except Exception as e:
        print(f"[ERROR] get_trade_stats error: {e}")
        return {}
