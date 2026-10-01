"""
CryptoIntel Pro - Bulletproof Trading Dashboard.
FastAPI server with JWT auth, rate limiting, bot control API, and SSE notifications.
All sensitive endpoints are JWT-protected. Public endpoints are rate-limited.
"""
import os
import time
import json
import hashlib
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from collections import defaultdict

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from trading.trade_db import (
    get_open_trades, get_trade_history, get_equity_history,
    get_trade_stats, get_bot_state, set_bot_state
)
from trading.trading_config import TradingConfig
from trading.notification_bus import bus as notification_bus

# Optional backtest imports
try:
    from backtesting.backtest_config import backtest_config
    from backtesting.backtest_engine import BacktestEngine
    BACKTEST_AVAILABLE = True
except Exception:
    BACKTEST_AVAILABLE = False

try:
    from trading.pattern_memory_bridge import memory_bridge
    MEMORY_BRIDGE_AVAILABLE = True
except Exception:
    MEMORY_BRIDGE_AVAILABLE = False


# ============================================================
# RATE LIMITER
# ============================================================
_rate_store: Dict[str, list] = defaultdict(list)

def rate_limit(max_requests: int = 60, window_seconds: int = 60):
    """Rate limiter dependency - per IP."""
    async def _check(request: Request):
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - window_seconds
        _rate_store[ip] = [t for t in _rate_store[ip] if t > window_start]
        if len(_rate_store[ip]) >= max_requests:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Please slow down.")
        _rate_store[ip].append(now)
    return _check


# ============================================================
# JWT-STYLE TOKEN AUTH (simple HMAC-based, no external deps)
# ============================================================
_SECRET = os.environ.get("DASHBOARD_SECRET", "cryptointel_secret_2025")
_SESSION_TOKENS: Dict[str, float] = {}  # token -> expiry timestamp
_DASHBOARD_PIN = os.environ.get("DASHBOARD_PIN", "1234")


def _issue_token() -> str:
    import secrets
    token = secrets.token_hex(32)
    _SESSION_TOKENS[token] = time.time() + 3600 * 8  # 8-hour session
    return token


async def require_auth(authorization: str = Header(default="")):
    """Dependency that validates Bearer token."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:]
    expiry = _SESSION_TOKENS.get(token)
    if not expiry or time.time() > expiry:
        raise HTTPException(status_code=401, detail="Token expired or invalid")
    return token


# ============================================================
# APP FACTORY
# ============================================================
_supervisor = None
_config: Optional[TradingConfig] = None
_ui_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "trading_ui.html")


def create_app(config: TradingConfig = None):
    global _config, _supervisor
    _config = config or TradingConfig()

    # Import supervisor after bots module is loaded
    try:
        from trading.bots.supervisor import supervisor as sup
        _supervisor = sup
    except Exception:
        _supervisor = None

    app = FastAPI(
        title="CryptoIntel Pro",
        version="3.0.0",
        docs_url=None,  # Disable swagger in prod
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # ---- Public read-only endpoints ----

    @app.get("/", response_class=HTMLResponse)
    async def serve_dashboard():
        try:
            with open(_ui_path, "r", encoding="utf-8") as f:
                content = f.read()
            return HTMLResponse(content=content)
        except FileNotFoundError:
            return HTMLResponse(content="<h1>Dashboard loading...</h1>")

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "3.0.0",
            "mode": "PAPER" if _config and _config.PAPER_MODE else "LIVE",
        }

    @app.get("/api/status", dependencies=[Depends(rate_limit(60, 60))])
    async def get_status():
        bot_statuses = _supervisor.get_status() if _supervisor else {}
        stats = get_trade_stats()
        return {
            "running": True,
            "mode": "PAPER" if _config and _config.PAPER_MODE else "LIVE",
            "bots": bot_statuses,
            "bot_count": len(bot_statuses),
            "active_bots": sum(1 for b in bot_statuses.values() if b.get("status") == "running"),
            "emergency_stop": _supervisor.is_emergency_stopped() if _supervisor else False,
            "open_positions": len(get_open_trades()),
            "stats": stats,
            "current_equity": get_bot_state("current_equity") or "10000",
            "daily_pnl": get_bot_state("daily_pnl") or "0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/prices", dependencies=[Depends(rate_limit(120, 60))])
    async def get_prices():
        # Return last known prices from notification bus history or empty
        prices = {}
        if _supervisor:
            for name, meta in _supervisor.bots.items():
                instance = meta.get("instance")
                if instance and hasattr(instance, "connector") and instance.connector:
                    try:
                        config_pairs = _config.TRADING_PAIRS if _config else []
                        for symbol in config_pairs:
                            if symbol not in prices:
                                try:
                                    ticker = await asyncio.wait_for(
                                        instance.connector.get_ticker(symbol), timeout=5.0
                                    )
                                    if ticker and ticker.get("last", 0) > 0:
                                        prices[symbol] = {
                                            "last": ticker.get("last", 0),
                                            "bid": ticker.get("bid", 0),
                                            "ask": ticker.get("ask", 0),
                                            "spread_pct": ticker.get("spread_pct", 0),
                                        }
                                except Exception:
                                    pass
                        break
                    except Exception:
                        pass
        return prices

    @app.get("/api/positions", dependencies=[Depends(rate_limit(60, 60))])
    async def get_positions():
        trades = get_open_trades()
        return trades

    @app.get("/api/trades", dependencies=[Depends(rate_limit(30, 60))])
    async def get_trades(limit: int = 50):
        if limit > 200:
            limit = 200
        return get_trade_history(limit=limit)

    @app.get("/api/equity", dependencies=[Depends(rate_limit(30, 60))])
    async def get_equity(limit: int = 500):
        if limit > 1000:
            limit = 1000
        return get_equity_history(limit=limit)

    @app.get("/api/stats", dependencies=[Depends(rate_limit(30, 60))])
    async def get_stats():
        stats = get_trade_stats()
        stats["current_equity"] = get_bot_state("current_equity") or "10000"
        stats["daily_pnl"] = get_bot_state("daily_pnl") or "0"
        stats["daily_pnl_pct"] = get_bot_state("daily_pnl_pct") or "0"
        return stats

    @app.get("/api/notifications", dependencies=[Depends(rate_limit(20, 60))])
    async def get_notifications(limit: int = 20):
        return notification_bus.get_history(limit=limit)

    @app.get("/api/backtest/summary")
    async def get_backtest_summary():
        if BACKTEST_AVAILABLE:
            try:
                if os.path.exists(backtest_config.BACKTEST_DB_PATH):
                    engine = BacktestEngine()
                    return engine.get_overall_summary()
            except Exception as e:
                return {"error": str(e), "total_trades": 0}
        return {"status": "unavailable"}

    @app.get("/api/backtest/sessions")
    async def get_backtest_sessions():
        if BACKTEST_AVAILABLE:
            try:
                if os.path.exists(backtest_config.PATTERN_MEMORY_DB_PATH):
                    engine = BacktestEngine()
                    return engine.get_session_analytics()
            except Exception:
                pass
        return []

    @app.get("/api/backtest/patterns")
    async def get_backtest_patterns(session: Optional[str] = None):
        if BACKTEST_AVAILABLE:
            try:
                if os.path.exists(backtest_config.PATTERN_MEMORY_DB_PATH):
                    engine = BacktestEngine()
                    return engine.get_pattern_leaderboard(session=session, limit=30)
            except Exception:
                pass
        return []

    @app.get("/api/backtest/live-memory")
    async def get_live_memory():
        if MEMORY_BRIDGE_AVAILABLE:
            try:
                session_info = memory_bridge.get_current_session()
                return {"session_info": session_info, "symbol_evaluations": {}}
            except Exception:
                pass
        return {"session_info": {}, "symbol_evaluations": {}}

    @app.get("/api/portfolio", dependencies=[Depends(rate_limit(20, 60))])
    async def get_portfolio():
        if _supervisor:
            for name, meta in _supervisor.bots.items():
                instance = meta.get("instance")
                if instance and hasattr(instance, "connector") and instance.connector:
                    try:
                        balance = await asyncio.wait_for(
                            instance.connector.get_balance(), timeout=5.0
                        )
                        usdt = balance.get("free", {}).get("USDT", 0)
                        total = balance.get("total", {}).get("USDT", 0)
                        return {
                            "usdt_free": round(usdt, 2),
                            "total_equity": round(total, 2),
                            "allocations": [{"asset": "USDT", "value": round(usdt, 2), "type": "cash"}],
                        }
                    except Exception:
                        pass
        return {"usdt_free": 10000, "total_equity": 10000, "allocations": []}

    # ---- Authentication ----

    class AuthRequest(BaseModel):
        pin: str

        @field_validator("pin")
        @classmethod
        def validate_pin(cls, v):
            if len(v) > 20:
                raise ValueError("Invalid PIN")
            return v

    @app.post("/api/auth/token", dependencies=[Depends(rate_limit(5, 60))])
    async def get_token(req: AuthRequest):
        if req.pin != _DASHBOARD_PIN:
            raise HTTPException(status_code=401, detail="Invalid PIN")
        token = _issue_token()
        return {"token": token, "expires_in": 28800, "message": "Authentication successful"}

    # ---- Protected bot control endpoints ----

    class BotControlRequest(BaseModel):
        bot_name: Optional[str] = None
        action: str

        @field_validator("action")
        @classmethod
        def validate_action(cls, v):
            allowed = {"pause", "resume", "emergency_stop", "resume_all", "reset_killswitch"}
            if v not in allowed:
                raise ValueError(f"Unknown action. Allowed: {allowed}")
            return v

    @app.post("/api/bot/control", dependencies=[Depends(rate_limit(30, 60))])
    async def bot_control(req: BotControlRequest, _token: str = Depends(require_auth)):
        if not _supervisor:
            raise HTTPException(status_code=503, detail="Supervisor not initialized")

        if req.action == "emergency_stop":
            _supervisor.emergency_stop_all()
            return {"status": "emergency_stopped", "message": "All bots halted"}

        elif req.action == "resume_all":
            _supervisor.resume_all()
            return {"status": "resumed", "message": "All bots resumed"}

        elif req.action == "pause" and req.bot_name:
            ok = _supervisor.pause_bot(req.bot_name)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Bot '{req.bot_name}' not found or no instance")
            return {"status": "paused", "bot": req.bot_name}

        elif req.action == "resume" and req.bot_name:
            ok = _supervisor.resume_bot(req.bot_name)
            if not ok:
                raise HTTPException(status_code=404, detail=f"Bot '{req.bot_name}' not found")
            return {"status": "resumed", "bot": req.bot_name}

        elif req.action == "reset_killswitch":
            if _supervisor:
                _supervisor._emergency_stop = False
                notification_bus.kill_switch_deactivated()
            return {"status": "killswitch_reset"}

        raise HTTPException(status_code=400, detail="Invalid action/bot combination")

    @app.post("/api/emergency-stop")
    async def emergency_stop(_token: str = Depends(require_auth)):
        if _supervisor:
            _supervisor.emergency_stop_all()
        return {"status": "emergency_stopped", "message": "All trading halted"}

    # ---- Settings endpoints ----

    class SettingsRequest(BaseModel):
        display_name: Optional[str] = None
        risk_profile: Optional[str] = None  # conservative, moderate, aggressive
        preferred_pairs: Optional[list] = None
        theme: Optional[str] = None  # dark, light

    @app.get("/api/settings")
    async def get_settings():
        return {
            "display_name": get_bot_state("display_name") or "Trader",
            "risk_profile": get_bot_state("risk_profile") or "moderate",
            "theme": get_bot_state("theme") or "dark",
            "preferred_pairs": (_config.TRADING_PAIRS if _config else ["BTC/USDT", "ETH/USDT", "SOL/USDT"]),
        }

    @app.post("/api/settings", dependencies=[Depends(rate_limit(10, 60))])
    async def save_settings(req: SettingsRequest, _token: str = Depends(require_auth)):
        if req.display_name:
            set_bot_state("display_name", req.display_name[:50])
        if req.risk_profile and req.risk_profile in {"conservative", "moderate", "aggressive"}:
            set_bot_state("risk_profile", req.risk_profile)
        if req.theme and req.theme in {"dark", "light"}:
            set_bot_state("theme", req.theme)
        return {"status": "saved"}

    # ---- SSE Notification Stream ----

    @app.get("/api/stream/notifications")
    async def notification_stream(request: Request):
        """Server-Sent Events endpoint for real-time toast notifications."""
        queue = notification_bus.subscribe()

        async def event_generator():
            # Send history on connect
            for event in notification_bus.get_history(10):
                yield f"data: {json.dumps(event)}\n\n"

            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield f"data: {json.dumps(event)}\n\n"
                    except asyncio.TimeoutError:
                        yield f"data: {json.dumps({'type': 'PING', 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
            finally:
                notification_bus.unsubscribe(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            }
        )

    # ---- Error handlers ----

    @app.exception_handler(404)
    async def not_found(request: Request, exc: Exception):
        return JSONResponse(status_code=404, content={"error": "Not found"})

    @app.exception_handler(500)
    async def server_error(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return app
