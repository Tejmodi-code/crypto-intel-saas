import asyncio
import random
import uuid
import datetime
from engine.analyzer import SignalAnalyzer
from database import log_signal
from config import config

KNOWN_ENTITIES = [
    "Binance Hot Wallet #12",
    "Coinbase Prime Custody",
    "Kraken Liquidity Pool",
    "OKX Reserve Vault",
    "Uniswap V3 Router",
    "Jump Trading Treasury",
    "Wintermute Market Maker",
    "Dragonfly Capital Fund",
    "Unknown Whale Wallet (0x3a...4f)",
    "Unknown Whale Wallet (0x9b...11)",
    "Unknown Whale Wallet (0x7e...cc)",
    "BlackRock ETF Custody Wallet",
    "Fidelity Digital Assets",
    "MakerDAO Peg Stability Module"
]

TOKENS = [
    {"symbol": "BTC", "min_amt": 5.0, "max_amt": 120.0, "price": 64500.0, "network": "Bitcoin"},
    {"symbol": "ETH", "min_amt": 80.0, "max_amt": 2200.0, "price": 3450.0, "network": "Ethereum"},
    {"symbol": "SOL", "min_amt": 1800.0, "max_amt": 30000.0, "price": 145.0, "network": "Solana"},
    {"symbol": "USDT", "min_amt": 300000.0, "max_amt": 12000000.0, "price": 1.0, "network": "Polygon"},
    {"symbol": "USDC", "min_amt": 250000.0, "max_amt": 8000000.0, "price": 1.0, "network": "Arbitrum"}
]

class OnChainScanner:
    def __init__(self, broadcast_callback=None):
        self.is_running = False
        self.broadcast_callback = broadcast_callback
        self.total_scanned_volume = 0.0

    async def start(self):
        self.is_running = True
        print("[*] On-Chain Blockchain Scanner initialized and listening...")
        while self.is_running:
            try:
                await asyncio.sleep(random.uniform(2.5, 4.5))
                token_info = random.choice(TOKENS)
                raw_amt = random.uniform(token_info["min_amt"], token_info["max_amt"])
                usd_value = round(raw_amt * token_info["price"], 2)
                
                if usd_value >= config.WHALE_THRESHOLD_USD:
                    from_tag = random.choice(KNOWN_ENTITIES)
                    to_options = [e for e in KNOWN_ENTITIES if e != from_tag]
                    to_tag = random.choice(to_options)
                    
                    analysis = SignalAnalyzer.classify_movement(
                        token=token_info["symbol"],
                        amount_usd=usd_value,
                        from_tag=from_tag,
                        to_tag=to_tag
                    )
                    
                    tx_hash = "0x" + uuid.uuid4().hex
                    details_str = f"{raw_amt:,.2f} {token_info['symbol']} (${usd_value:,.2f} USD) | {analysis['sentiment']}"
                    sig_id = log_signal(
                        token_symbol=token_info["symbol"],
                        signal_type=analysis["signal_type"],
                        amount_usd=usd_value,
                        from_tag=from_tag,
                        to_tag=to_tag,
                        details=details_str,
                        tx_hash=tx_hash,
                        network=token_info["network"]
                    )
                    
                    self.total_scanned_volume += usd_value
                    
                    signal_payload = {
                        "id": sig_id,
                        "token": token_info["symbol"],
                        "amount_usd": usd_value,
                        "signal_type": analysis["signal_type"],
                        "sentiment": analysis["sentiment"],
                        "icon": analysis["icon"],
                        "from_tag": from_tag,
                        "to_tag": to_tag,
                        "network": token_info["network"],
                        "tx_hash": tx_hash,
                        "timestamp": datetime.datetime.utcnow().strftime("%H:%M:%S UTC"),
                        "formatted_alert": analysis["formatted_alert"]
                    }
                    
                    if self.broadcast_callback:
                        await self.broadcast_callback(signal_payload)
            except Exception as e:
                print(f"[!] Scanner loop error: {e}")
                await asyncio.sleep(2)

    def stop(self):
        self.is_running = False
