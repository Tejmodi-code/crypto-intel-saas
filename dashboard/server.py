from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import os
from config import config
from database import (
    init_db,
    get_active_subscribers_count,
    get_total_revenue_mrr,
    get_recent_signals,
    get_all_subscribers,
    verify_access_key
)
from payments.gateway import CryptoPaymentGateway

app = FastAPI(title=config.PROJECT_NAME, version=config.VERSION)
index_html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "index.html")

class SubscribeRequest(BaseModel):
    email: str
    tier: str
    wallet_address: str = None
    tx_hash: str = None

@app.on_event("startup")
async def startup_event():
    init_db()

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    with open(index_html_path, "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content=content)

@app.get("/api/metrics")
async def get_metrics():
    active_subs = get_active_subscribers_count()
    mrr = get_total_revenue_mrr()
    recent = get_recent_signals(limit=100)
    total_volume = sum(s["amount_usd"] for s in recent)
    return {
        "active_subscribers": active_subs,
        "mrr": mrr,
        "total_signals": len(recent),
        "tracked_volume": total_volume
    }

@app.get("/api/signals")
async def list_signals(limit: int = 25):
    return get_recent_signals(limit=limit)

@app.get("/api/subscribers")
async def list_subscribers():
    return get_all_subscribers()

@app.post("/api/subscribe")
async def subscribe_user(req: SubscribeRequest):
    res = CryptoPaymentGateway.process_onchain_payment(
        email=req.email,
        tier=req.tier,
        tx_hash=req.tx_hash,
        from_wallet=req.wallet_address
    )
    return res

@app.get("/api/verify-license/{access_key}")
async def verify_key(access_key: str):
    sub = verify_access_key(access_key)
    if sub:
        return {"valid": True, "tier": sub["tier"], "expires_at": sub["expires_at"]}
    return JSONResponse(status_code=404, content={"valid": False, "message": "Invalid or expired access key"})
