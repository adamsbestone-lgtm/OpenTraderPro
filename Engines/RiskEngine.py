"""
RiskEngine.py - perte max journalière, perte max compte, taille max,
nombre max d'ordres, verrouillage automatique, arrêt d'urgence (Kill Switch).
"""
from __future__ import annotations
from Core.EventBus import EventBus


class RiskEngine:
    def __init__(self, bus: EventBus, settings, order_engine=None) -> None:
        self.bus = bus
        self.settings = settings
        self.order_engine = order_engine  # peut être assigné après coup (référence circulaire évitée)
        self.locked = False
        self.kill_switch_active = False
        self.daily_realized_pnl = 0.0
        self.daily_unrealized_pnl = 0.0
        self.account_realized_pnl = 0.0

        self.bus.subscribe(EventBus.EVT_POSITION_UPDATE, self._on_position_update)

    def _cfg(self) -> dict:
        return self.settings.get("risk", {})

    # -- vérification appelée par OrderEngine avant tout envoi -------------------
    def allow_order(self, order) -> bool:
        if self.kill_switch_active or self.locked:
            self.bus.publish(EventBus.EVT_LOG, {"level": "WARNING",
                              "msg": f"Ordre {order.id} bloqué (kill switch ou verrouillage risque actif)."})
            return False

        max_size = self._cfg().get("max_position_size", 10)
        if order.quantity > max_size:
            self.bus.publish(EventBus.EVT_LOG, {"level": "WARNING",
                              "msg": f"Ordre {order.id} refusé : taille {order.quantity} > max {max_size}."})
            return False

        if self.order_engine:
            max_orders = self._cfg().get("max_open_orders", 20)
            if self.order_engine.open_orders_count() >= max_orders:
                self.bus.publish(EventBus.EVT_LOG, {"level": "WARNING",
                                  "msg": f"Ordre {order.id} refusé : nombre max d'ordres ouverts atteint ({max_orders})."})
                return False
        return True

    def _on_position_update(self, pos) -> None:
        self.daily_realized_pnl = pos.realized_pnl
        self.daily_unrealized_pnl = pos.unrealized_pnl
        self.account_realized_pnl = pos.realized_pnl
        total = self.daily_realized_pnl + self.daily_unrealized_pnl

        max_daily = self._cfg().get("max_daily_loss", 1000.0)
        max_account = self._cfg().get("max_account_loss", 5000.0)

        if not self.locked and total <= -abs(max_daily):
            self._trigger_lockout("max_daily_loss", total, max_daily)
        if not self.locked and self.account_realized_pnl <= -abs(max_account):
            self._trigger_lockout("max_account_loss", self.account_realized_pnl, max_account)

    def _trigger_lockout(self, reason: str, pnl: float, limit: float) -> None:
        self.locked = True
        if self._cfg().get("lockout_on_max_loss", True) and self.order_engine:
            self.order_engine.cancel_all()
        self.bus.publish(EventBus.EVT_RISK_LOCKOUT, {"reason": reason, "pnl": pnl, "limit": limit})
        self.bus.publish(EventBus.EVT_LOG, {"level": "CRITICAL",
                          "msg": f"Verrouillage risque ({reason}) : P&L {pnl:.2f} / limite {limit:.2f}"})

    # -- kill switch (arrêt d'urgence manuel) -----------------------------------
    def activate_kill_switch(self) -> None:
        self.kill_switch_active = True
        if self.order_engine:
            self.order_engine.cancel_all()
        self.bus.publish(EventBus.EVT_RISK_KILL_SWITCH, {"active": True})
        self.bus.publish(EventBus.EVT_LOG, {"level": "CRITICAL", "msg": "KILL SWITCH ACTIVÉ : tous les ordres annulés."})

    def deactivate_kill_switch(self) -> None:
        self.kill_switch_active = False
        self.bus.publish(EventBus.EVT_RISK_KILL_SWITCH, {"active": False})

    def reset_daily(self) -> None:
        self.locked = False
        self.daily_realized_pnl = 0.0
        self.daily_unrealized_pnl = 0.0

    def unlock(self) -> None:
        self.locked = False
        self.bus.publish(EventBus.EVT_LOG, {"level": "INFO", "msg": "Compte déverrouillé manuellement."})
