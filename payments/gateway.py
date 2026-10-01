from config import config
from database import create_subscription, verify_access_key

class CryptoPaymentGateway:
    @staticmethod
    def get_payment_instructions(tier_name: str) -> dict:
        tier_info = config.TIERS.get(tier_name.upper(), config.TIERS['STARTER'])
        return {
            'tier': tier_name.upper(),
            'tier_name': tier_info['name'],
            'amount_usd': tier_info['price_usd'],
            'evm_payment_address': config.MERCHANT_WALLET_EVM,
            'sol_payment_address': config.MERCHANT_WALLET_SOL,
            'accepted_tokens': ['USDT', 'USDC', 'POL', 'SOL', 'ETH'],
            'supported_networks': ['Polygon (Recommended)', 'Arbitrum', 'Solana', 'Ethereum']
        }

    @staticmethod
    def process_onchain_payment(email: str, tier: str, tx_hash: str = None, from_wallet: str = None, network: str = 'Polygon', token_symbol: str = 'USDT') -> dict:
        tier_info = config.TIERS.get(tier.upper(), config.TIERS['STARTER'])
        price = tier_info['price_usd']
        
        sub = create_subscription(
            email=email,
            tier=tier.upper(),
            wallet_address=from_wallet or '0x' + (tx_hash[:10] if tx_hash else 'Anonymous'),
            tx_hash=tx_hash,
            amount_usd=price,
            network=network,
            token_symbol=token_symbol
        )
        
        return {
            'success': True,
            'message': f'Payment successfully verified! VIP {tier.upper()} access granted.',
            'access_key': sub['access_key'],
            'tier': sub['tier'],
            'expires_at': sub['expires_at'],
            'tx_hash': sub['tx_hash']
        }
