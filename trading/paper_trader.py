import threading
from typing import Dict, Any, List, Optional
from trading.trading_config import config
from trading.trade_db import log_trade, close_trade, get_open_trades

class PaperTrader:
    def __init__(self, initial_balance: float = 10000.0):
        self.lock = threading.RLock()
        self.initial_balance = initial_balance
        self.usdt_balance = initial_balance
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.trade_history: List[Dict[str, Any]] = []
        self._load_state_from_db()

    def _load_state_from_db(self) -> None:
        try:
            open_trades = get_open_trades()
            for trade in open_trades:
                self.positions[trade['symbol']] = {
                    'amount': trade['amount'],
                    'entry_price': trade['entry_price'],
                    'side': trade['side'],
                    'trade_id': trade['id'],
                    'stop_loss': trade['stop_loss'],
                    'take_profit': trade['take_profit']
                }
            print(f"[INFO] Loaded {len(self.positions)} open positions from DB.")
        except Exception as e:
            print(f"[ERROR] Failed to load open trades: {e}")

    def execute_buy(self, symbol: str, current_price: float, amount_usdt: float) -> Dict[str, Any]:
        with self.lock:
            if self.usdt_balance < amount_usdt:
                print(f"[WARN] Insufficient balance to buy {amount_usdt} of {symbol}")
                return {}

            slippage = current_price * (config.SIMULATED_SLIPPAGE_BPS / 10000.0)
            executed_price = current_price + slippage
            fee_usdt = amount_usdt * config.SIMULATED_FEE_PCT
            
            net_usdt = amount_usdt - fee_usdt
            amount_coin = net_usdt / executed_price
            
            self.usdt_balance -= amount_usdt
            
            trade_id = log_trade(
                symbol=symbol,
                side='buy',
                entry_price=executed_price,
                amount=amount_coin,
                stop_loss=0.0,
                take_profit=0.0,
                strategy='paper',
                pattern='',
                order_id='paper_order'
            )
            
            self.positions[symbol] = {
                'amount': amount_coin,
                'entry_price': executed_price,
                'side': 'buy',
                'trade_id': trade_id,
                'stop_loss': 0.0,
                'take_profit': 0.0
            }
            
            print(f"[INFO] Paper buy {symbol}: {amount_coin} @ {executed_price}")
            return {
                'symbol': symbol,
                'side': 'buy',
                'amount': amount_coin,
                'price': executed_price,
                'fee': fee_usdt
            }

    def execute_sell(self, symbol: str, current_price: float, amount: Optional[float] = None) -> Dict[str, Any]:
        with self.lock:
            if symbol not in self.positions:
                print(f"[WARN] No open position for {symbol}")
                return {}

            pos = self.positions[symbol]
            sell_amount = amount if amount is not None else pos['amount']
            
            if sell_amount > pos['amount']:
                print(f"[WARN] Selling more than owned for {symbol}")
                return {}

            slippage = current_price * (config.SIMULATED_SLIPPAGE_BPS / 10000.0)
            executed_price = current_price - slippage
            
            gross_usdt = sell_amount * executed_price
            fee_usdt = gross_usdt * config.SIMULATED_FEE_PCT
            net_usdt = gross_usdt - fee_usdt
            
            pnl = net_usdt - (sell_amount * pos['entry_price'])
            pnl_pct = pnl / (sell_amount * pos['entry_price']) if pos['entry_price'] > 0 else 0.0
            
            self.usdt_balance += net_usdt
            
            if sell_amount == pos['amount']:
                close_trade(
                    trade_id=pos['trade_id'],
                    exit_price=executed_price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    fees=fee_usdt
                )
                del self.positions[symbol]
            else:
                pos['amount'] -= sell_amount

            print(f"[INFO] Paper sell {symbol}: {sell_amount} @ {executed_price} (PnL: {pnl})")
            return {
                'symbol': symbol,
                'side': 'sell',
                'amount': sell_amount,
                'price': executed_price,
                'fee': fee_usdt,
                'pnl': pnl,
                'pnl_pct': pnl_pct
            }

    def place_stop_loss(self, symbol: str, stop_price: float) -> None:
        with self.lock:
            if symbol in self.positions:
                self.positions[symbol]['stop_loss'] = stop_price
                print(f"[INFO] Set stop-loss for {symbol} at {stop_price}")

    def place_take_profit(self, symbol: str, tp_price: float) -> None:
        with self.lock:
            if symbol in self.positions:
                self.positions[symbol]['take_profit'] = tp_price
                print(f"[INFO] Set take-profit for {symbol} at {tp_price}")

    def check_stops(self, current_prices: Dict[str, float]) -> List[Dict[str, Any]]:
        triggered = []
        with self.lock:
            for symbol, pos in list(self.positions.items()):
                if symbol not in current_prices:
                    continue
                
                price = current_prices[symbol]
                
                if pos['stop_loss'] > 0 and price <= pos['stop_loss']:
                    print(f"[INFO] Stop-loss triggered for {symbol} at {price}")
                    res = self.execute_sell(symbol, price)
                    if res:
                        triggered.append(res)
                elif pos['take_profit'] > 0 and price >= pos['take_profit']:
                    print(f"[INFO] Take-profit triggered for {symbol} at {price}")
                    res = self.execute_sell(symbol, price)
                    if res:
                        triggered.append(res)
        return triggered

    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        with self.lock:
            value = self.usdt_balance
            for symbol, pos in self.positions.items():
                if symbol in current_prices:
                    value += pos['amount'] * current_prices[symbol]
                else:
                    value += pos['amount'] * pos['entry_price']
            return value

    def get_balance(self) -> Dict[str, Any]:
        with self.lock:
            free_dict = {'USDT': self.usdt_balance}
            total_dict = {'USDT': self.usdt_balance}
            for symbol, pos in self.positions.items():
                base_asset = symbol.split('/')[0]
                total_dict[base_asset] = total_dict.get(base_asset, 0) + pos['amount']
                free_dict[base_asset] = 0.0
            return {
                'free': free_dict,
                'total': total_dict,
                'used': {}
            }

    def get_positions(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [{'symbol': k, **v} for k, v in self.positions.items()]

    def reset(self) -> None:
        with self.lock:
            self.usdt_balance = self.initial_balance
            self.positions.clear()
            self.trade_history.clear()
            print("[INFO] Paper trader reset.")
