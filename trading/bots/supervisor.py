"""
Bot Supervisor - Watchdog that manages all 3 trading bots.
Auto-restarts any bot that crashes within 5 seconds.
Provides centralized status tracking and emergency stop.
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable

from trading.notification_bus import bus


class BotSupervisor:
    """
    Manages lifecycle of all autonomous trading bots.
    Starts them, monitors heartbeats, and auto-restarts on failure.
    """

    def __init__(self):
        self.bots: Dict[str, Dict[str, Any]] = {}  # bot_name -> metadata
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._emergency_stop = False

    def register(self, name: str, factory: Callable, symbols: list,
                 poll_interval: float = 30.0, restart_delay: float = 5.0) -> None:
        """Register a bot factory function for supervision."""
        self.bots[name] = {
            "name": name,
            "factory": factory,
            "symbols": symbols,
            "poll_interval": poll_interval,
            "restart_delay": restart_delay,
            "status": "registered",
            "start_time": None,
            "last_heartbeat": None,
            "restart_count": 0,
            "error": None,
            "instance": None,
        }

    async def start_all(self) -> None:
        """Start all registered bots concurrently."""
        self._running = True
        self._emergency_stop = False
        for name in self.bots:
            self._tasks[name] = asyncio.create_task(
                self._supervise(name), name=f"supervisor_{name}"
            )
        print(f"[SUPERVISOR] Started {len(self.bots)} bots")

    async def _supervise(self, name: str) -> None:
        """Supervision loop for a single bot with auto-restart."""
        meta = self.bots[name]
        while self._running:
            if self._emergency_stop:
                meta["status"] = "stopped"
                bus.bot_status_change(name, "stopped", "Emergency stop active")
                await asyncio.sleep(5)
                continue
            try:
                meta["status"] = "starting"
                meta["start_time"] = datetime.now(timezone.utc).isoformat()
                bus.bot_status_change(name, "starting")

                bot_instance = meta["factory"]()
                meta["instance"] = bot_instance

                meta["status"] = "running"
                bus.bot_status_change(name, "running")

                await bot_instance.run()

                # Bot exited normally
                meta["status"] = "stopped"
                bus.bot_status_change(name, "stopped", "Clean exit")
            except asyncio.CancelledError:
                meta["status"] = "cancelled"
                break
            except Exception as e:
                meta["restart_count"] += 1
                meta["error"] = str(e)
                meta["status"] = "restarting"
                print(f"[SUPERVISOR] Bot {name} crashed: {e}. Restarting in {meta['restart_delay']}s...")
                bus.error_alert(name, f"Bot crashed: {e}. Restarting...")
                bus.bot_status_change(name, "restarting", str(e))
                await asyncio.sleep(meta["restart_delay"])

    def heartbeat(self, name: str) -> None:
        """Called by each bot periodically to signal it is alive."""
        if name in self.bots:
            self.bots[name]["last_heartbeat"] = datetime.now(timezone.utc).isoformat()

    def emergency_stop_all(self) -> None:
        """Halt all bots immediately. Does not kill tasks, just sets flag."""
        self._emergency_stop = True
        bus.kill_switch_activated("Manual emergency stop", 0.0)
        print("[SUPERVISOR] EMERGENCY STOP - all bots halted")

    def resume_all(self) -> None:
        """Resume all bots after an emergency stop."""
        self._emergency_stop = False
        bus.kill_switch_deactivated()
        print("[SUPERVISOR] All bots resumed")

    def pause_bot(self, name: str) -> bool:
        """Pause a specific bot."""
        if name in self.bots and self.bots[name].get("instance"):
            self.bots[name]["instance"].paused = True
            self.bots[name]["status"] = "paused"
            bus.bot_status_change(name, "paused")
            return True
        return False

    def resume_bot(self, name: str) -> bool:
        """Resume a specific paused bot."""
        if name in self.bots and self.bots[name].get("instance"):
            self.bots[name]["instance"].paused = False
            self.bots[name]["status"] = "running"
            bus.bot_status_change(name, "running", "Resumed")
            return True
        return False

    def get_status(self) -> Dict[str, Any]:
        """Return status of all bots."""
        result = {}
        for name, meta in self.bots.items():
            result[name] = {
                "name": name,
                "status": meta["status"],
                "symbols": meta["symbols"],
                "start_time": meta["start_time"],
                "last_heartbeat": meta["last_heartbeat"],
                "restart_count": meta["restart_count"],
                "error": meta["error"],
                "emergency_stop": self._emergency_stop,
            }
        return result

    def is_emergency_stopped(self) -> bool:
        return self._emergency_stop

    async def shutdown(self) -> None:
        """Gracefully shut down all bots."""
        self._running = False
        for name, task in self._tasks.items():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        print("[SUPERVISOR] All bots shut down")


# Global supervisor instance
supervisor = BotSupervisor()
