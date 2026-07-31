"""
InstitutionalOrderFlow - bot expérimental répliquant des techniques
d'entrée utilisées par les traders order-flow avancés et certains desks
institutionnels, à partir des signaux déjà détectés par
Plugins/OrderFlowSuite (événement "orderflow.signal") :

  - sweep_fade             : fade d'un sweep de liquidité (souvent un piège
                              à stops avant retournement)
  - rejection_absorption   : rejet de prix quand un gros ordre passif
                              absorbe l'agressivité sans céder le niveau
  - sweep_defense_reversal : retournement confirmé après défense d'un sweep
                              (signal composite SWEEP_DEFENSE)
  - imbalance_breakout     : suivi de cassure sur déséquilibre de carnet
                              (mur d'ordres qui cède)
  - stop_cascade_follow    : suivi d'une cascade de stops déclenchée
                              (momentum)
  - confluence_high_conviction : plusieurs concepts alignés en même temps
                              (score de confluence élevé -> conviction forte)

⚠️ Bot expérimental/éducatif, désactivé tant qu'il n'est pas démarré depuis
le menu "Bots". Chaque règle peut être activée/désactivée et paramétrée
dans bot.json. À backtester et surveiller avant tout usage en argent réel :
rien ici ne constitue un conseil en investissement.
"""
from __future__ import annotations
import time

from Bots.Strategy import BaseStrategy
from Engines.OrderEngine import OrderSide, OrderType
from Engines.SignalAI import SignalAI
from Plugins.OrderFlowSuite.plugin import EVT_ORDERFLOW_SIGNAL
from Plugins.OrderFlowSuite.model import Direction
from Plugins.OrderFlowSuite.rules import RULE_FOR_SIGNAL


class Strategy(BaseStrategy):
    name = "InstitutionalOrderFlow"

    def on_start(self) -> None:
        self.symbol = self.params.get("symbol", "ESU6")
        self.tick_size = self.params.get("tick_size", 0.25)
        self.default_quantity = self.params.get("default_quantity", 1)
        self.stop_loss_ticks = self.params.get("stop_loss_ticks", 8)
        self.take_profit_ticks = self.params.get("take_profit_ticks", 12)
        self.max_concurrent_positions = self.params.get("max_concurrent_positions", 1)
        self.cooldown_s = self.params.get("cooldown_s", 15)
        self.rules = self.params.get("rules", {})
        self._last_entry_ts = 0.0

        ai_cfg = self.params.get("ai_filter", {})
        self.ai_enabled = ai_cfg.get("enabled", False)
        self.ai_min_probability = ai_cfg.get("min_probability", 0.55)
        self.ai = SignalAI() if self.ai_enabled else None

        if self.bus:
            self.bus.subscribe(EVT_ORDERFLOW_SIGNAL, self._on_signal)

    def on_stop(self) -> None:
        if self.bus:
            self.bus.unsubscribe(EVT_ORDERFLOW_SIGNAL, self._on_signal)

    # -- coeur de la logique --------------------------------------------------
    def _on_signal(self, payload: dict) -> None:
        if payload.get("symbol") != self.symbol:
            return
        signal = payload.get("signal")
        mapping = RULE_FOR_SIGNAL.get(getattr(signal, "type", None))
        if mapping is None:
            return

        rule_name, mode = mapping
        rule_cfg = self.rules.get(rule_name, {})
        if not rule_cfg.get("enabled", False):
            return
        if signal.size < rule_cfg.get("min_size", 0):
            return
        if not self._passes_risk_gates():
            return
        if self.ai_enabled and self.ai is not None:
            proba = self.ai.predict_proba(signal.type.value, signal.size, rule_name, mode)
            if proba < self.ai_min_probability:
                return

        direction = signal.direction if mode == "with" else signal.direction.opposite
        quantity = max(1, int(self.default_quantity * rule_cfg.get("quantity_multiplier", 1.0)))
        self._enter(direction, signal.price, quantity, rule_name)

    def _passes_risk_gates(self) -> bool:
        now = time.time()
        if (now - self._last_entry_ts) < self.cooldown_s:
            return False  # anti sur-trading : cooldown entre 2 entrées auto
        if self.position_engine:
            position = self.position_engine.get(self.symbol)
            if abs(position.quantity) >= self.max_concurrent_positions:
                return False
        return True

    def _enter(self, direction: Direction, price: float, quantity: int, rule_name: str) -> None:
        if not self.order_engine:
            return
        stop_offset = self.stop_loss_ticks * self.tick_size
        target_offset = self.take_profit_ticks * self.tick_size
        side = OrderSide.BUY if direction is Direction.BUY else OrderSide.SELL

        if side == OrderSide.BUY:
            stop_loss, take_profit = price - stop_offset, price + target_offset
        else:
            stop_loss, take_profit = price + stop_offset, price - target_offset

        self.order_engine.submit_bracket(
            symbol=self.symbol, side=side, quantity=quantity,
            entry_price=price, stop_loss=stop_loss, take_profit=take_profit,
            entry_type=OrderType.LIMIT,
        )
        self._last_entry_ts = time.time()

        if self.bus:
            from Core.EventBus import EventBus
            self.bus.publish(EventBus.EVT_ALERT, {
                "message": f"🤖 [{self.name}/{rule_name}] {side.name} {quantity} {self.symbol} @ {price:.2f}"
            })
