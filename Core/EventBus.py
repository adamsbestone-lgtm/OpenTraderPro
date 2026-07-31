"""
EventBus.py - bus d'événements central d'OpenTrader Pro.

Toute communication entre GUI, Widgets et Engines (Market/Order/Position/
Risk/Bot/Plugin/Broker) passe exclusivement par ce bus. Aucun engine ne
doit importer directement un widget, et aucun widget ne doit appeler
un engine autrement que via publish/subscribe (sauf actions utilisateur
explicites comme "envoyer un ordre", qui restent des appels directs
autorisés vers OrderEngine pour la latence).
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any, Callable, DefaultDict, List

from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    _raw_signal = Signal(str, object)

    # --- Market Engine ---
    EVT_TICK = "market.tick"
    EVT_DEPTH = "market.depth"
    EVT_TRADE_PRINT = "market.trade_print"
    EVT_BAR = "market.bar"
    EVT_TAPE_RECONSTRUCTED = "market.tape_reconstructed"
    EVT_PACE_OF_TAPE = "market.pace_of_tape"
    # --- Order Engine ---
    EVT_ORDER_NEW = "order.new"
    EVT_ORDER_UPDATE = "order.update"
    EVT_ORDER_FILLED = "order.filled"
    EVT_ORDER_CANCELED = "order.canceled"
    EVT_ORDER_REJECTED = "order.rejected"
    # --- Position Engine ---
    EVT_POSITION_UPDATE = "position.update"
    # --- Account / Broker Engine ---
    EVT_ACCOUNT_UPDATE = "account.update"
    EVT_BROKER_CONNECTED = "broker.connected"
    EVT_BROKER_DISCONNECTED = "broker.disconnected"
    EVT_BROKER_ERROR = "broker.error"
    # --- Risk Engine ---
    EVT_RISK_LOCKOUT = "risk.lockout"
    EVT_RISK_KILL_SWITCH = "risk.kill_switch"
    # --- Alerts / News / Journal ---
    EVT_ALERT = "alert.new"
    EVT_NEWS = "news.new"
    EVT_LOG = "journal.log"
    # --- Replay Engine ---
    EVT_REPLAY_STATE = "replay.state"

    def __init__(self) -> None:
        super().__init__()
        self._subscribers: DefaultDict[str, List[Callable[[Any], None]]] = defaultdict(list)
        self._raw_signal.connect(self._dispatch)

    def subscribe(self, event_name: str, callback: Callable[[Any], None]) -> None:
        self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable[[Any], None]) -> None:
        if callback in self._subscribers.get(event_name, []):
            self._subscribers[event_name].remove(callback)

    def publish(self, event_name: str, payload: Any = None) -> None:
        """Thread-safe : peut être appelé depuis n'importe quel thread (Market
        Engine, Broker Engine...), le signal Qt garantit l'exécution des
        callbacks sur le thread propriétaire du bus (thread GUI)."""
        self._raw_signal.emit(event_name, payload)

    def _dispatch(self, event_name: str, payload: Any) -> None:
        for callback in list(self._subscribers.get(event_name, [])):
            try:
                callback(payload)
            except Exception as exc:  # noqa: BLE001
                self.publish(self.EVT_LOG, {"level": "ERROR", "msg": f"{event_name} handler failed: {exc}"})
