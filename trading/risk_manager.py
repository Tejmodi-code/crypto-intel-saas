"""
Risk Manager - Capital protection engine enforcing 1:3 risk-reward ratio.
Multiple safety layers: position sizing, drawdown kill switch, cooldown, spread filter.
"""
import datetime
from typing import Dict, Any
from trading.trading_config import TradingConfig


class RiskManager:
    """Multi-layered capital protection engine."""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.daily_peak_equity = 0.0
        self.kill_switch_active = False
        self.last_loss_time = None

    def calculate_position(self, equity: float, entry_price: float, symbol: str) -> Dict[str, Any]:
        """
        Calculate position size enforcing 1:3 risk-reward ratio.
        Stop-loss = 2% below entry, Take-profit = 6% above entry (3x stop).
        """
        stop_loss_price = round(entry_price * (1 - self.config.STOP_LOSS_PCT), 4)
        take_profit_price = round(entry_price * (1 + self.config.STOP_LOSS_PCT * self.config.RISK_REWARD_RATIO), 4)

        risk_per_unit = round(entry_price - stop_loss_price, 4)
        if risk_per_unit <= 0:
            risk_per_unit = 0.0001

        # 1% of equity risked per trade
        risk_amount = round(equity * self.config.RISK_PER_TRADE, 4)
        position_size_units = round(risk_amount / risk_per_unit, 6)
        position_value = round(position_size_units * entry_price, 4)

        # Cap at 20% of equity
        max_position_value = equity * self.config.MAX_POSITION_PCT
        if position_value > max_position_value:
            position_value = max_position_value
            position_size_units = round(position_value / entry_price, 6)
            risk_amount = round(position_size_units * risk_per_unit, 4)

        return {
            'amount': position_size_units,
            'stop_loss': stop_loss_price,
            'take_profit': take_profit_price,
            'risk_amount': risk_amount,
            'potential_reward': round(risk_amount * self.config.RISK_REWARD_RATIO, 4),
            'position_value': position_value,
            'position_pct': round(position_value / equity, 4) if equity > 0 else 0
        }

    def validate_trade(self, symbol: str, side: str, amount: float, entry_price: float,
                       equity: float, current_spread_pct: float, open_positions_count: int) -> Dict[str, Any]:
        """Validate trade against all risk checks. All must pass."""
        checks = {}

        # 1. Kill switch check
        checks['kill_switch'] = not self.kill_switch_active

        # 2. Cooldown check
        checks['cooldown'] = not self.is_in_cooldown()

        # 3. Spread filter
        checks['spread'] = current_spread_pct <= self.config.SPREAD_FILTER_PCT

        # 4. Max positions
        checks['max_positions'] = open_positions_count < self.config.MAX_OPEN_POSITIONS

        # 5. Max position size
        position_value = amount * entry_price
        checks['max_position_size'] = position_value <= (equity * self.config.MAX_POSITION_PCT * 1.01)

        # 6. Sufficient balance
        checks['free_balance'] = position_value <= equity

        approved = all(checks.values())

        # Generate specific reason for rejection
        reason = "Trade approved"
        if not approved:
            for check_name, passed in checks.items():
                if not passed:
                    reasons = {
                        'kill_switch': 'Kill switch is active',
                        'cooldown': f'In cooldown period ({self.config.COOLDOWN_SECONDS}s after loss)',
                        'spread': f'Spread too wide ({current_spread_pct:.4f} > {self.config.SPREAD_FILTER_PCT})',
                        'max_positions': f'Max positions reached ({open_positions_count}/{self.config.MAX_OPEN_POSITIONS})',
                        'max_position_size': f'Position too large ({position_value:.2f} > {equity * self.config.MAX_POSITION_PCT:.2f})',
                        'free_balance': f'Insufficient balance'
                    }
                    reason = reasons.get(check_name, f'{check_name} check failed')
                    break

        return {
            'approved': approved,
            'reason': reason,
            'checks': checks
        }

    def update_equity(self, current_equity: float) -> Dict[str, Any]:
        """Track equity and check daily drawdown limit."""
        if current_equity > self.daily_peak_equity:
            self.daily_peak_equity = current_equity

        drawdown_pct = 0.0
        if self.daily_peak_equity > 0:
            drawdown_pct = (self.daily_peak_equity - current_equity) / self.daily_peak_equity

        if drawdown_pct >= self.config.DAILY_DRAWDOWN_LIMIT:
            print("[RISK] Daily drawdown limit exceeded! Activating kill switch.")
            self.activate_emergency_stop(reason='Daily drawdown limit reached')

        return {
            'drawdown_pct': round(drawdown_pct, 4),
            'peak_equity': self.daily_peak_equity,
            'kill_switch_active': self.kill_switch_active
        }

    def register_loss(self):
        """Record a losing trade for cooldown tracking."""
        print("[INFO] Loss registered. Entering cooldown.")
        self.last_loss_time = datetime.datetime.utcnow()

    def is_in_cooldown(self) -> bool:
        """Check if bot is in post-loss cooldown period."""
        if not self.last_loss_time:
            return False
        elapsed = (datetime.datetime.utcnow() - self.last_loss_time).total_seconds()
        return elapsed < self.config.COOLDOWN_SECONDS

    def activate_emergency_stop(self, reason: str = 'Manual'):
        """Halt all trading immediately."""
        print(f"[EMERGENCY] Kill switch activated: {reason}")
        self.kill_switch_active = True

    def deactivate_emergency_stop(self):
        """Reset kill switch to allow trading."""
        print("[OK] Kill switch deactivated.")
        self.kill_switch_active = False

    def reset_daily_state(self):
        """Reset daily tracking at midnight UTC."""
        print("[INFO] Daily state reset.")
        self.daily_peak_equity = 0.0
        self.kill_switch_active = False
        self.last_loss_time = None
