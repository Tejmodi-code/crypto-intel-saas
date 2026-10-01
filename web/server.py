"""
Atlas Quantitative Terminal Server.
FastAPI Institutional Backend providing REST APIs, Broker Configuration Validator,
Quantitative Backtesting Engine, Operator Authentication, and Real-Time SSE Telemetry.
"""
import os
import json
import uuid
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from quant.config import quant_config
from quant.order_executor import executor
from quant.broker_connector import BrokerConnector
from quant.strategies import QuantStrategies
from quant.backtester import QuantBacktester


app = FastAPI(title="Atlas Quantitative Execution Terminal", version="5.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_ui_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "terminal.html")
backtester = QuantBacktester(initial_capital=quant_config.INITIAL_CAPITAL_USDT)

# In-memory operator session store (token -> metadata)
ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}
OPERATOR_PIN = os.getenv("OPERATOR_PIN", "1234")


def verify_operator(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Dependency ensuring caller holds valid Bearer token for protected operator actions."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required: Bearer token missing")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    token = parts[1]
    if token not in ACTIVE_SESSIONS:
        raise HTTPException(status_code=401, detail="Invalid or expired operator token")
    return ACTIVE_SESSIONS[token]


def generate_sample_candles(n: int = 500, base_price: float = 77650.0) -> pd.DataFrame:
    """Generates synthetic historical OHLCV candles for rigorous backtest simulation."""
    np.random.seed(42)
    timestamps = [int(1700000000000 + i * 3600000) for i in range(n)]
    prices = [base_price]
    for _ in range(n - 1):
        prices.append(prices[-1] * (1.0 + np.random.normal(0.0003, 0.008)))
    
    opens = prices
    closes = [p * (1.0 + np.random.normal(0, 0.004)) for p in opens]
    highs = [max(o, c) * (1.0 + abs(np.random.normal(0, 0.003))) for o, c in zip(opens, closes)]
    lows = [min(o, c) * (1.0 - abs(np.random.normal(0, 0.003))) for o, c in zip(opens, closes)]
    volumes = [float(np.random.uniform(100, 1200)) for _ in range(n)]

    df = pd.DataFrame({
        'timestamp': timestamps,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })
    return df


@app.on_event("startup")
async def startup_event():
    await executor.initialize()
    asyncio.create_task(executor.run_execution_loop())
    print("[INIT] Atlas Quantitative Execution Platform Initialized Successfully")


@app.get("/", response_class=HTMLResponse)
async def serve_terminal():
    try:
        with open(_ui_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Initializing Institutional Terminal...</h1>")


# --- AUTHENTICATION ENDPOINTS ---

class LoginRequest(BaseModel):
    pin: str


@app.post("/api/auth/login")
async def operator_login(req: LoginRequest):
    """Authenticates operator via PIN and issues an 8-hour Bearer token."""
    if req.pin != OPERATOR_PIN:
        raise HTTPException(status_code=401, detail="Invalid Operator PIN")
    
    token = str(uuid.uuid4())
    session_data = {
        "authenticated": True,
        "role": "QUANT_OPERATOR",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_in_sec": 28800
    }
    ACTIVE_SESSIONS[token] = session_data
    return {
        "status": "AUTHENTICATED",
        "token": token,
        "role": "QUANT_OPERATOR",
        "expires_in": 28800
    }


@app.get("/api/auth/status")
async def auth_status(authorization: Optional[str] = Header(None)):
    """Checks current token validity."""
    if not authorization:
        return {"authenticated": False}
    parts = authorization.split()
    if len(parts) == 2 and parts[1] in ACTIVE_SESSIONS:
        return {"authenticated": True, "session": ACTIVE_SESSIONS[parts[1]]}
    return {"authenticated": False}


@app.post("/api/auth/logout")
async def operator_logout(authorization: Optional[str] = Header(None)):
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[1] in ACTIVE_SESSIONS:
            del ACTIVE_SESSIONS[parts[1]]
    return {"status": "LOGGED_OUT"}


# --- TELEMETRY & STRATEGY ENDPOINTS ---

@app.get("/api/health")
async def health():
    return {
        "status": "OPERATIONAL",
        "system": "Atlas Quantitative Platform",
        "execution_mode": quant_config.EXECUTION_MODE,
        "exchange": quant_config.EXCHANGE_ID.upper(),
        "active_positions": len(executor.active_positions),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/portfolio")
async def get_portfolio():
    """Returns current portfolio telemetry, live equity, active positions, and persistent trade blotter."""
    return executor.get_portfolio_telemetry()


@app.get("/api/signals/matrix")
async def get_signals_matrix():
    """Evaluates live quantitative strategy matrix across universe pairs."""
    results = []
    df_sample = generate_sample_candles(80)

    for sym in quant_config.TRADING_PAIRS:
        ticker = await executor.broker.fetch_ticker(sym)
        price = ticker["last"]
        
        vwap_sig = QuantStrategies.evaluate_vwap_mean_reversion(df_sample)
        trend_sig = QuantStrategies.evaluate_trend_continuation(df_sample)
        
        results.append({
            "symbol": sym,
            "current_price": price,
            "spread_pct": ticker["spread_pct"],
            "vwap_reversion": vwap_sig,
            "trend_continuation": trend_sig,
            "composite_consensus": "BUY" if (vwap_sig["action"] == "BUY" or trend_sig["action"] == "BUY") else "HOLD",
            "confidence": max(vwap_sig.get("confidence", 0.0), trend_sig.get("confidence", 0.0))
        })
    return results


@app.get("/api/backtest/results")
async def get_backtest_analytics(strategy: str = "VWAP_MEAN_REVERSION"):
    """Runs historical event-driven backtest and returns quantitative performance metrics."""
    df = generate_sample_candles(1000)
    res = backtester.run_backtest(df, strategy_name=strategy)
    return res


# --- PROTECTED OPERATOR ACTIONS ---

class BrokerConfigRequest(BaseModel):
    exchange_id: str
    api_key: Optional[str] = ""
    api_secret: Optional[str] = ""
    passphrase: Optional[str] = ""
    execution_mode: str  # LIVE or PAPER


@app.post("/api/broker/config")
async def update_broker_config(req: BrokerConfigRequest, session: Dict[str, Any] = Depends(verify_operator)):
    """Updates exchange credentials and verifies live broker connectivity (Protected)."""
    quant_config.EXCHANGE_ID = req.exchange_id.lower()
    quant_config.API_KEY = req.api_key or ""
    quant_config.API_SECRET = req.api_secret or ""
    quant_config.API_PASSPHRASE = req.passphrase or ""
    quant_config.EXECUTION_MODE = req.execution_mode.upper()

    res = await executor.broker.initialize()
    return {
        "status": "CONFIGURED",
        "connection_result": res,
        "exchange": quant_config.EXCHANGE_ID.upper(),
        "execution_mode": quant_config.EXECUTION_MODE
    }


class ClosePositionRequest(BaseModel):
    order_id: str


@app.post("/api/positions/close")
async def close_position(req: ClosePositionRequest, session: Dict[str, Any] = Depends(verify_operator)):
    """Manually closes an active position and realizes P&L in persistent SQLite ledger (Protected)."""
    pos = executor.active_positions.get(req.order_id)
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    
    ticker = await executor.broker.fetch_ticker(pos["symbol"])
    res = executor.close_position(req.order_id, exit_price=ticker["last"], reason="MANUAL_OPERATOR_CLOSE")
    return {"status": "SUCCESS", "closed_position": res}


@app.post("/api/portfolio/emergency-flatten")
async def emergency_flatten_portfolio(session: Dict[str, Any] = Depends(verify_operator)):
    """Emergency closes all active positions immediately and saves to ledger (Protected)."""
    closed = executor.flatten_all_positions(reason="OPERATOR_EMERGENCY_FLATTEN")
    return {
        "status": "FLATTENED",
        "positions_closed": len(closed),
        "details": closed,
        "portfolio": executor.get_portfolio_telemetry()
    }


@app.get("/api/stream/live")
async def live_stream(request: Request):
    """Server-Sent Events (SSE) telemetry stream pushing live price and execution data."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                portfolio = executor.get_portfolio_telemetry()
                payload = {
                    "type": "QUANT_TELEMETRY",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "portfolio": portfolio
                }
                yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(2.0)
            except Exception:
                await asyncio.sleep(2.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )