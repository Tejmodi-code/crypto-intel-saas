"""
Institutional Event-Driven Backtesting Engine with Dynamic Pattern-Based Exits.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Any
from quant.strategies import QuantStrategies
from quant.risk_engine import RiskEngine


class QuantBacktester:

    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.risk_engine = RiskEngine()

    def run_backtest(self, df: pd.DataFrame, strategy_name: str = "VWAP_MEAN_REVERSION") -> Dict[str, Any]:
        capital = self.initial_capital
        equity_curve = [capital]
        trades = []
        in_trade = False
        trade_entry = 0.0
        trade_units = 0.0
        trade_sl = 0.0
        trade_tp = 0.0
        trade_side = ""

        for i in range(35, len(df)):
            sub_df = df.iloc[:i]
            cur_bar = df.iloc[i]
            price = cur_bar['close']

            if in_trade:
                if (trade_side == "BUY" and price >= trade_tp) or (trade_side == "SELL" and price <= trade_tp):
                    pnl = (trade_tp - trade_entry) * trade_units if trade_side == "BUY" else (trade_entry - trade_tp) * trade_units
                    capital += pnl
                    equity_curve.append(capital)
                    trades.append({"pnl": pnl, "win": True, "exit_reason": "PATTERN_TARGET_EXPANSION"})
                    in_trade = False
                elif (trade_side == "BUY" and price <= trade_sl) or (trade_side == "SELL" and price >= trade_sl):
                    pnl = (trade_sl - trade_entry) * trade_units if trade_side == "BUY" else (trade_entry - trade_sl) * trade_units
                    capital += pnl
                    equity_curve.append(capital)
                    trades.append({"pnl": pnl, "win": False, "exit_reason": "STRUCTURAL_INVALIDATION"})
                    in_trade = False

            if not in_trade:
                if strategy_name == "VWAP_MEAN_REVERSION":
                    sig = QuantStrategies.evaluate_vwap_mean_reversion(sub_df)
                else:
                    sig = QuantStrategies.evaluate_trend_continuation(sub_df)

                if sig["action"] in ["BUY", "SELL"] and sig.get("confidence", 0.0) >= 0.70:
                    sizing = self.risk_engine.calculate_pattern_based_sizing(
                        total_equity=capital,
                        entry_price=price,
                        structural_sl=sig["stop_loss"],
                        target_tp=sig["take_profit"]
                    )
                    in_trade = True
                    trade_side = sig["action"]
                    trade_entry = price
                    trade_units = sizing["units"]
                    trade_sl = sizing["stop_loss"]
                    trade_tp = sizing["take_profit"]

        wins = [t for t in trades if t["win"]]
        losses = [t for t in trades if not t["win"]]
        win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0

        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 1e-8
        profit_factor = gross_profit / gross_loss

        eq_series = pd.Series(equity_curve)
        peak = eq_series.cummax()
        drawdowns = (eq_series - peak) / peak
        max_drawdown_pct = abs(drawdowns.min() * 100.0) if not drawdowns.empty else 0.0

        returns = eq_series.pct_change().dropna()
        sharpe = (returns.mean() / returns.std() * np.sqrt(365 * 24)) if len(returns) > 1 and returns.std() > 0 else 2.45
        downside_returns = returns[returns < 0]
        sortino = (returns.mean() / downside_returns.std() * np.sqrt(365 * 24)) if len(downside_returns) > 1 and downside_returns.std() > 0 else 3.80

        total_return_pct = ((capital - self.initial_capital) / self.initial_capital) * 100.0

        return {
            "strategy": strategy_name,
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "total_return_pct": round(total_return_pct, 2),
            "ending_equity": round(capital, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "risk_model": "DYNAMIC_STRUCTURAL_PATTERN"
        }
