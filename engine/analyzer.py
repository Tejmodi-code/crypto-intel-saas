from config import config

class SignalAnalyzer:
    @staticmethod
    def classify_movement(token: str, amount_usd: float, from_tag: str, to_tag: str) -> dict:
        is_mega = amount_usd >= config.MEGA_WHALE_THRESHOLD_USD
        
        if any(x in to_tag for x in ["Binance", "Coinbase", "Kraken", "OKX"]):
            signal_type = "EXCHANGE_INFLOW (Potential Sell Pressure)"
            sentiment = "BEARISH_ALERT"
            icon = "🚨"
        elif any(x in from_tag for x in ["Binance", "Coinbase", "Kraken", "OKX"]):
            signal_type = "EXCHANGE_OUTFLOW (Cold Storage Accumulation)"
            sentiment = "BULLISH_ACCUMULATION"
            icon = "🟢"
        elif any(x in to_tag for x in ["Uniswap", "Curve", "Raydium"]):
            signal_type = "DEX_LIQUIDITY_INJECTION"
            sentiment = "VOLATILITY_SURGE"
            icon = "⚡"
        else:
            signal_type = "WHALE_WALLET_TRANSFER"
            sentiment = "WATCHLIST"
            icon = "🐋"
            
        tier_label = "Institutional Mega Whale" if is_mega else "Whale Movement"
        formatted_alert = (
            f"{icon} [{signal_type}]\n"
            f"Value: ${amount_usd:,.2f} USD ({token})\n"
            f"From: {from_tag}\n"
            f"To: {to_tag}\n"
            f"Sentiment: {sentiment}\n"
            f"Tier: {tier_label}"
        )
        
        return {
            "token": token,
            "amount_usd": amount_usd,
            "signal_type": signal_type,
            "sentiment": sentiment,
            "icon": icon,
            "is_mega": is_mega,
            "formatted_alert": formatted_alert
        }
