"""
Institutional Risk & Position Sizing Engine.
Eliminates fixed percentage stop losses and fixed 1:3 ratios.
Sizes positions dynamically based on structural invalidation distance and pattern geometry.
"""
from typing import Dict, Any
from quant.config import quant_config


class RiskEngine:

    def __init__(self, config=None):
        self.config = config or quant_config
        self.peak_equity = self.config.INITIAL_CAPITAL_USDT
        self.circuit_breaker_active = False

    def calculate_pattern_based_sizing(self, total_equity: float, entry_price: float, 
                                       structural_sl: float, target_tp: float) -> Dict[str, Any]:
        """
        Sizes orders based on the exact structural invalidation level (pattern stop loss).
        Risk capital is strictly limited to 1.5% of portfolio equity.
        Position Units = Capital at Risk / |Entry Price - Structural Stop Loss|
        """
        if entry_price <= 0 or total_equity <= 0 or structural_sl <= 0:
            return {"units": 0.0, "stop_loss": 0.0, "take_profit": 0.0, "notional_usd": 0.0, "pattern_rr": "1:0"}

        risk_dist = abs(entry_price - structural_sl)
        reward_dist = abs(target_tp - entry_price) if target_tp > 0 else (risk_dist * 3.0)

        # Dynamic Pattern Risk-to-Reward Ratio
        rr_ratio = reward_dist / max(risk_dist, 1e-8)

        # Fixed Dollar Risk = 1.5% of total equity
        capital_at_risk = total_equity * self.config.BASE_RISK_PER_TRADE
        
        # Calculate exact unit size so that if structural SL is hit, only 1.5% is lost
        position_units = capital_at_risk / max(risk_dist, 1e-8)
        notional_usd = position_units * entry_price

        # Cap maximum position notional at 15% of equity for portfolio safety
        max_notional = total_equity * self.config.MAX_POSITION_PCT
        if notional_usd > max_notional:
            notional_usd = max_notional
            position_units = notional_usd / entry_price
            capital_at_risk = position_units * risk_dist

        return {
            "units": round(position_units, 6),
            "notional_usd": round(notional_usd, 2),
            "entry_price": round(entry_price, 2),
            "stop_loss": round(structural_sl, 2),
            "take_profit": round(target_tp, 2),
            "risk_amount_usd": round(capital_at_risk, 2),
            "target_reward_usd": round(position_units * reward_dist, 2),
            "pattern_rr": f"1:{rr_ratio:.1f}"
        }

    def validate_pre_trade_risk(self, total_equity: float, open_positions_count: int, spread_pct: float, pattern_rr: float = 2.0) -> Dict[str, Any]:
        """Pre-trade verification checks before order routing."""
        if self.circuit_breaker_active:
            return {"approved": False, "reason": "Circuit breaker active: Daily drawdown limit reached"}

        if open_positions_count >= self.config.MAX_OPEN_POSITIONS:
            return {"approved": False, "reason": f"Maximum open position limit ({self.config.MAX_OPEN_POSITIONS}) reached"}

        if spread_pct > self.config.MAX_SPREAD_LIMIT_PCT:
            return {"approved": False, "reason": f"Spread ({spread_pct*100:.3f}%) exceeds liquidity threshold"}

        if pattern_rr < 2.0:
            return {"approved": False, "reason": f"Pattern R:R (1:{pattern_rr:.1f}) is below minimum 1:2.0 hurdle"}

        return {"approved": True, "reason": "All structural risk checks passed"}

    def update_drawdown_monitor(self, current_equity: float) -> Dict[str, Any]:
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        drawdown_pct = (self.peak_equity - current_equity) / self.peak_equity if self.peak_equity > 0 else 0.0

        if drawdown_pct >= self.config.DAILY_DRAWDOWN_LIMIT_PCT:
            self.circuit_breaker_active = True
            return {"circuit_breaker": True, "drawdown_pct": round(drawdown_pct * 100, 2), "status": "HALTED"}

        return {"circuit_breaker": False, "drawdown_pct": round(drawdown_pct * 100, 2), "status": "NORMAL"}
