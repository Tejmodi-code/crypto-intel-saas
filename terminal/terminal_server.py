"""
Terminal Server - FastAPI High-Performance Backend for Bloomberg/TradingView Pro Terminal.
Delivers real-time funding rates, basis spreads, whale tracking, autonomous multi-strategy engine,
and live Server-Sent Events (SSE).
"""
import os
import time
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from arbitrage.funding_scanner import FundingScanner
from arbitrage.whale_radar import WhaleRadar
from arbitrage.basis_engine import BasisEngine
from arbitrage.delta_neutral_bot import delta_engine
from arbitrage.autonomous_trader import auto_trader


app = FastAPI(title="CryptoIntel Pro Institutional Terminal", version="4.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

scanner = FundingScanner()
whale_radar = WhaleRadar()

_ui_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "pro_terminal.html")


@app.on_event("startup")
async def startup_event():
    await delta_engine.initialize()
    await auto_trader.initialize()
    # Launch continuous background autonomous trading loop
    asyncio.create_task(auto_trader.run_autonomous_loop())
    print("[INIT] Institutional Terminal & Autonomous Multi-Strategy Engine Online!")


@app.get("/", response_class=HTMLResponse)
async def serve_terminal():
    try:
        with open(_ui_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Loading Institutional Terminal...</h1>")


@app.get("/api/health")
async def health():
    return {
        "status": "HEALTHY",
        "system": "CryptoIntel Pro Institutional Terminal",
        "engine": "Autonomous Multi-Strategy Execution Engine",
        "version": "4.5.0",
        "active_trades": len(auto_trader.active_trades),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/funding/matrix")
async def get_funding_matrix():
    rates = await scanner.fetch_funding_rates()
    return rates


@app.get("/api/whales/feed")
async def get_whale_feed():
    events = whale_radar.scan_new_whale_events()
    sentiment = whale_radar.get_market_sentiment()
    return {"events": events, "sentiment": sentiment}


@app.get("/api/basis/spreads")
async def get_basis_spreads():
    rates = await scanner.fetch_funding_rates()
    spreads = []
    for r in rates:
        b = BasisEngine.calculate_basis(r["index_price"], r["mark_price"])
        b["symbol"] = r["symbol"]
        spreads.append(b)
    return spreads


@app.get("/api/ledger/trades")
async def get_trade_ledger():
    """Returns active trades, closed history, and strategies deployed."""
    return auto_trader.get_ledger_summary()


class CloseTradeRequest(BaseModel):
    trade_id: str
    exit_price: Optional[float] = None


@app.post("/api/ledger/close")
async def close_ledger_trade(req: CloseTradeRequest):
    price = req.exit_price or 77650.0
    res = auto_trader.close_trade(req.trade_id, exit_price=price, reason="USER_MANUAL_EXIT")
    if not res:
        raise HTTPException(status_code=404, detail="Trade not found")
    return {"status": "SUCCESS", "closed_trade": res}


@app.get("/api/stream/live")
async def live_stream(request: Request):
    """Live SSE stream pushing real-time funding updates, whale alerts, and trade ledger."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                rates = await scanner.fetch_funding_rates()
                whales = whale_radar.scan_new_whale_events()
                sentiment = whale_radar.get_market_sentiment()
                ledger = auto_trader.get_ledger_summary()
                
                payload = {
                    "type": "TICK_UPDATE",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "funding_rates": rates,
                    "whale_radar": {"events": whales[:8], "sentiment": sentiment},
                    "ledger": ledger
                }
                yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(2.5)
            except Exception:
                await asyncio.sleep(2.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
