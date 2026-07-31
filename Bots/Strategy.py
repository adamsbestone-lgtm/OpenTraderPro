"""
Strategy.py - classe de base à hériter par chaque bot (Bots/<Nom>/strategy.py).
"""
from __future__ import annotations
from typing import Any


class BaseStrategy:
    name: str = "UnnamedStrategy"

    def __init__(self, order_engine=None, position_engine=None, market_engine=None,
                 params: dict | None = None, bus=None) -> None:
        self.order_engine = order_engine
        self.position_engine = position_engine
        self.market_engine = market_engine
        self.params = params or {}
        self.bus = bus  # optionnel : permet à un bot avancé de s'abonner à des
                        # événements spécifiques (ex : orderflow.signal)

    def on_start(self) -> None:
        """Appelé quand le bot est activé."""

    def on_tick(self, tick: Any) -> None:
        """Trade print (dernier prix/quantité échangée)."""

    def on_depth(self, depth: Any) -> None:
        """Snapshot de profondeur de marché (DepthSnapshot)."""

    def on_bar(self, bar: Any) -> None:
        """Bougie OHLCV agrégée (si un agrégateur de bougies est branché)."""

    def on_order(self, order: Any) -> None:
        """Changement d'état d'un ordre."""

    def on_position(self, position: Any) -> None:
        """Mise à jour de position."""

    def on_timer(self) -> None:
        """Appelé périodiquement (ex : toutes les secondes) par le BotEngine."""

    def on_stop(self) -> None:
        """Appelé quand le bot est désactivé."""
