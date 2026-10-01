import asyncio
import uuid
from database import init_db, create_subscription, get_active_subscribers_count, get_total_revenue_mrr, verify_access_key, log_signal, get_recent_signals
from engine.analyzer import SignalAnalyzer
from payments.gateway import CryptoPaymentGateway
from config import config

def test_full_pipeline():
    print("=== RUNNING CRYPTO INTEL SAAS AUTOMATED TEST SUITE ===")
    init_db()
    print("[PASS] Database initialized successfully.")
    
    analysis = SignalAnalyzer.classify_movement(
        token="ETH",
        amount_usd=1500000.0,
        from_tag="Binance Hot Wallet #12",
        to_tag="Whale Cold Storage"
    )
    assert "OUTFLOW" in analysis["signal_type"]
    assert analysis["sentiment"] == "BULLISH_ACCUMULATION"
    print("[PASS] Signal Analyzer classified whale movement accurately.")
    
    sig_id = log_signal("ETH", analysis["signal_type"], 1500000.0, "Binance", "Cold Storage", "Accumulation", "0x" + uuid.uuid4().hex, "Ethereum")
    signals = get_recent_signals(limit=5)
    assert any(s["id"] == sig_id for s in signals)
    print("[PASS] Signal logging and retrieval passed.")
    
    unique_tx = "0x" + uuid.uuid4().hex
    payment_res = CryptoPaymentGateway.process_onchain_payment(
        email="test_user@familyfund.com",
        tier="PRO",
        tx_hash=unique_tx,
        from_wallet="0x999988887777"
    )
    assert payment_res["success"] is True
    key = payment_res["access_key"]
    print(f"[PASS] Subscription provisioned with key: {key}")
    
    verification = verify_access_key(key)
    assert verification is not None
    assert verification["tier"] == "PRO"
    assert verification["email"] == "test_user@familyfund.com"
    print("[PASS] Access Key verification succeeded.")
    
    count = get_active_subscribers_count()
    mrr = get_total_revenue_mrr()
    assert count >= 1
    assert mrr >= 79.0
    print(f"[PASS] MRR Calculation verified: ${mrr:,.2f} USD across {count} active subscribers.")
    
    print("=====================================================")
    print("[SUCCESS] ALL SYSTEM UNIT & INTEGRATION TESTS PASSED 100%!")
    print("=====================================================")

if __name__ == "__main__":
    test_full_pipeline()
