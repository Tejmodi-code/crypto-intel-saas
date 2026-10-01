import ccxt
import asyncio
import pandas as pd
from typing import Dict, List, Any, Optional
from trading.trading_config import config
from trading.paper_trader import PaperTrader

class ExchangeConnector:
    def __init__(self, config_obj):
        self.config = config_obj
        self.exchange = None
        self.paper_trader: Optional[PaperTrader] = None
        
    async def connect(self) -> None:
        try:
            exchange_class = getattr(ccxt, self.config.EXCHANGE_NAME)
            self.exchange = exchange_class({
                'apiKey': self.config.API_KEY,
                'secret': self.config.API_SECRET,
                'password': self.config.API_PASSPHRASE,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                }
            })
            
            if self.config.SANDBOX_MODE:
                self.exchange.set_sandbox_mode(True)
                print(f"[INFO] Enabled sandbox mode for {self.config.EXCHANGE_NAME}")
                
            if self.config.PAPER_MODE:
                self.paper_trader = PaperTrader()
                print("[INFO] Paper trading mode enabled.")
                
            await asyncio.to_thread(self.exchange.load_markets)
            print(f"[INFO] Connected to {self.config.EXCHANGE_NAME} successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to connect to exchange: {e}")
            raise

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        try:
            ticker = await asyncio.to_thread(self.exchange.fetch_ticker, symbol)
            bid = ticker.get('bid', 0.0)
            ask = ticker.get('ask', 0.0)
            last = ticker.get('last', 0.0)
            spread = ask - bid if ask and bid else 0.0
            spread_pct = (spread / bid) if bid else 0.0
            
            return {
                'bid': bid,
                'ask': ask,
                'last': last,
                'spread': spread,
                'spread_pct': spread_pct,
                'timestamp': ticker.get('timestamp')
            }
        except Exception as e:
            print(f"[ERROR] get_ticker error for {symbol}: {e}")
            return {}

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        try:
            ohlcv = await asyncio.to_thread(self.exchange.fetch_ohlcv, symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"[ERROR] get_ohlcv error for {symbol}: {e}")
            return pd.DataFrame()

    async def get_balance(self) -> Dict[str, Any]:
        if self.config.PAPER_MODE and self.paper_trader:
            return self.paper_trader.get_balance()
            
        try:
            balance = await asyncio.to_thread(self.exchange.fetch_balance)
            return {
                'free': balance.get('free', {}),
                'total': balance.get('total', {}),
                'used': balance.get('used', {})
            }
        except Exception as e:
            print(f"[ERROR] get_balance error: {e}")
            return {'free': {}, 'total': {}, 'used': {}}

    async def place_market_order(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        if self.config.PAPER_MODE and self.paper_trader:
            ticker = await self.get_ticker(symbol)
            price = ticker.get('last', 0.0)
            if side.lower() == 'buy':
                # PaperTrader.execute_buy expects amount in USDT value
                amount_usdt = amount * price
                return self.paper_trader.execute_buy(symbol, price, amount_usdt)
            else:
                return self.paper_trader.execute_sell(symbol, price, amount)
                
        try:
            precision_amount = self.exchange.amount_to_precision(symbol, amount)
            order = await asyncio.to_thread(
                self.exchange.create_market_order,
                symbol, side, precision_amount
            )
            print(f"[INFO] Placed market {side} for {amount} {symbol}")
            return order
        except Exception as e:
            print(f"[ERROR] place_market_order error: {e}")
            return {}

    async def place_stop_loss_order(self, symbol: str, side: str, amount: float, stop_price: float) -> Dict[str, Any]:
        if self.config.PAPER_MODE and self.paper_trader:
            self.paper_trader.place_stop_loss(symbol, stop_price)
            return {'status': 'paper_stop_set'}
            
        try:
            precision_amount = self.exchange.amount_to_precision(symbol, amount)
            precision_price = self.exchange.price_to_precision(symbol, stop_price)
            params = {'stopPrice': float(precision_price)}
            
            order = await asyncio.to_thread(
                self.exchange.create_order,
                symbol, 'stop_market', side, precision_amount, None, params
            )
            print(f"[INFO] Placed SL {side} for {symbol} at {stop_price}")
            return order
        except Exception as e:
            print(f"[ERROR] place_stop_loss_order error: {e}")
            return {}

    async def place_take_profit_order(self, symbol: str, side: str, amount: float, tp_price: float) -> Dict[str, Any]:
        if self.config.PAPER_MODE and self.paper_trader:
            self.paper_trader.place_take_profit(symbol, tp_price)
            return {'status': 'paper_tp_set'}
            
        try:
            precision_amount = self.exchange.amount_to_precision(symbol, amount)
            precision_price = self.exchange.price_to_precision(symbol, tp_price)
            params = {'stopPrice': float(precision_price)}
            
            order = await asyncio.to_thread(
                self.exchange.create_order,
                symbol, 'take_profit_market', side, precision_amount, None, params
            )
            print(f"[INFO] Placed TP {side} for {symbol} at {tp_price}")
            return order
        except Exception as e:
            print(f"[ERROR] place_take_profit_order error: {e}")
            return {}

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        if self.config.PAPER_MODE:
            return True
            
        try:
            await asyncio.to_thread(self.exchange.cancel_order, order_id, symbol)
            print(f"[INFO] Cancelled order {order_id} for {symbol}")
            return True
        except Exception as e:
            print(f"[ERROR] cancel_order error: {e}")
            return False

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.config.PAPER_MODE:
            return []
            
        try:
            orders = await asyncio.to_thread(self.exchange.fetch_open_orders, symbol)
            return orders
        except Exception as e:
            print(f"[ERROR] get_open_orders error: {e}")
            return []

    async def check_paper_stops(self, prices: Dict[str, float]) -> List[Dict[str, Any]]:
        if self.config.PAPER_MODE and self.paper_trader:
            return self.paper_trader.check_stops(prices)
        return []

    async def close(self) -> None:
        if self.exchange:
            await asyncio.to_thread(self.exchange.close)
            print("[INFO] Exchange connection closed.")
