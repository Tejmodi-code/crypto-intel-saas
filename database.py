import sqlite3
import datetime
import uuid
import os
from config import config

def get_db():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS subscribers (
        id TEXT PRIMARY KEY,
        email TEXT,
        wallet_address TEXT,
        tier TEXT NOT NULL,
        access_key TEXT UNIQUE NOT NULL,
        is_active INTEGER DEFAULT 1,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY,
        subscriber_id TEXT,
        tx_hash TEXT UNIQUE NOT NULL,
        from_address TEXT,
        to_address TEXT,
        amount_usd REAL NOT NULL,
        token_symbol TEXT NOT NULL,
        network TEXT NOT NULL,
        status TEXT DEFAULT 'CONFIRMED',
        confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS signals (
        id TEXT PRIMARY KEY,
        token_symbol TEXT NOT NULL,
        signal_type TEXT NOT NULL,
        amount_usd REAL NOT NULL,
        from_tag TEXT,
        to_tag TEXT,
        details TEXT,
        tx_hash TEXT,
        network TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

def create_subscription(email, tier, wallet_address=None, tx_hash=None, amount_usd=0.0, network="Polygon", token_symbol="USDT"):
    conn = get_db()
    c = conn.cursor()
    tier_info = config.TIERS.get(tier.upper(), config.TIERS["STARTER"])
    now = datetime.datetime.utcnow()
    expires_at = now + datetime.timedelta(days=tier_info["duration_days"])
    sub_id = str(uuid.uuid4())
    access_key = f"VIP-{tier[:3].upper()}-{uuid.uuid4().hex[:8].upper()}"
    
    c.execute("""
    INSERT INTO subscribers (id, email, wallet_address, tier, access_key, is_active, started_at, expires_at)
    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
    """, (sub_id, email, wallet_address, tier.upper(), access_key, now.isoformat(), expires_at.isoformat()))
    
    pay_id = str(uuid.uuid4())
    actual_tx = tx_hash or ("0x" + uuid.uuid4().hex)
    c.execute("""
    INSERT INTO payments (id, subscriber_id, tx_hash, from_address, to_address, amount_usd, token_symbol, network, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CONFIRMED')
    """, (pay_id, sub_id, actual_tx, wallet_address or "0xAnonymous", config.MERCHANT_WALLET_EVM, amount_usd or tier_info["price_usd"], token_symbol, network))
    
    conn.commit()
    conn.close()
    return {
        "subscriber_id": sub_id,
        "access_key": access_key,
        "tier": tier.upper(),
        "expires_at": expires_at.isoformat(),
        "status": "ACTIVE",
        "tx_hash": actual_tx
    }

def get_active_subscribers_count():
    conn = get_db()
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    c.execute("SELECT COUNT(*) as count FROM subscribers WHERE is_active = 1 AND expires_at > ?", (now,))
    count = c.fetchone()["count"]
    conn.close()
    return count

def get_total_revenue_mrr():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT SUM(amount_usd) as total FROM payments WHERE status = 'CONFIRMED'")
    total = c.fetchone()["total"] or 0.0
    conn.close()
    return round(total, 2)

def log_signal(token_symbol, signal_type, amount_usd, from_tag, to_tag, details, tx_hash=None, network="Ethereum"):
    conn = get_db()
    c = conn.cursor()
    sig_id = str(uuid.uuid4())
    c.execute("""
    INSERT INTO signals (id, token_symbol, signal_type, amount_usd, from_tag, to_tag, details, tx_hash, network)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (sig_id, token_symbol, signal_type, amount_usd, from_tag, to_tag, details, tx_hash or ("0x" + uuid.uuid4().hex), network))
    conn.commit()
    conn.close()
    return sig_id

def get_recent_signals(limit=25):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    signals = [dict(r) for r in rows]
    conn.close()
    return signals

def get_all_subscribers():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM subscribers ORDER BY created_at DESC")
    rows = c.fetchall()
    subs = [dict(r) for r in rows]
    conn.close()
    return subs

def verify_access_key(access_key):
    conn = get_db()
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    c.execute("SELECT * FROM subscribers WHERE access_key = ? AND is_active = 1 AND expires_at > ?", (access_key, now))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None
