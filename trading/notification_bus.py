"""
Notification Bus - Async event bus for real-time trading notifications.
Publishers call .publish(event_type, data).
Dashboard SSE handler subscribes via .subscribe() and reads from the queue.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List


class NotificationBus:
    def __init__(self):
        self._subscribers: List[asyncio.Queue] = []
        self._history: List[Dict[str, Any]] = []
        self._max_history = 100

    def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.remove(q)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._history[-limit:]

    def trade_opened(self, bot_name: str, symbol: str, side: str, price: float,
                     amount: float, stop_loss: float, take_profit: float, strategy: str):
        self.publish("TRADE_OPENED", {
            "bot": bot_name, "symbol": symbol, "side": side.upper(),
            "price": price, "amount": amount, "stop_loss": stop_loss,
            "take_profit": take_profit, "strategy": strategy,
        })

    def trade_closed(self, bot_name: str, symbol: str, side: str, entry: float,
                     exit_price: float, pnl: float, pnl_pct: float, reason: str):
        self.publish("TRADE_CLOSED", {
            "bot": bot_name, "symbol": symbol, "side": side.upper(),
            "entry": entry, "exit": exit_price,
            "pnl": round(pnl, 4), "pnl_pct": round(pnl_pct * 100, 2),
            "reason": reason, "profitable": pnl > 0,
        })

    def stop_loss_hit(self, bot_name: str, symbol: str, price: float, loss_pct: float):
        self.publish("STOP_LOSS_HIT", {
            "bot": bot_name, "symbol": symbol,
            "price": price, "loss_pct": round(loss_pct * 100, 2),
        })

    def take_profit_hit(self, bot_name: str, symbol: str, price: float, profit_pct: float):
        self.publish("TAKE_PROFIT_HIT", {
            "bot": bot_name, "symbol": symbol,
            "price": price, "profit_pct": round(profit_pct * 100, 2),
        })

    def kill_switch_activated(self, reason: str, daily_drawdown_pct: float):
        self.publish("KILL_SWITCH_ACTIVATED", {
            "reason": reason,
            "daily_drawdown_pct": round(daily_drawdown_pct * 100, 2),
        })

    def kill_switch_deactivated(self):
        self.publish("KILL_SWITCH_DEACTIVATED", {"message": "Kill switch lifted. Bots resuming."})

    def bot_status_change(self, bot_name: str, status: str, reason: str = ""):
        self.publish("BOT_STATUS_CHANGE", {"bot": bot_name, "status": status, "reason": reason})

    def error_alert(self, bot_name: str, message: str):
        self.publish("ERROR_ALERT", {"bot": bot_name, "message": message})


# Global singleton bus shared by all bots and dashboard
bus = NotificationBus()
