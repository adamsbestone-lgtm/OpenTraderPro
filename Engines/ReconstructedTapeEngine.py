"""
ReconstructedTapeEngine.py - "Reconstructed Tape" façon Jigsaw daytradr.

De nombreux brokers/flux de données livrent un gros ordre agressif comme
plusieurs petites exécutions fragmentées ("child fills") au même prix, dans
le même sens, à quelques millisecondes d'intervalle. Cet engine les
regroupe en un seul "vrai" print, pour retrouver la taille réelle de
l'ordre initial - exactement ce que fait la Reconstructed Tape de Jigsaw.

Algorithme : pour chaque symbole, un groupe "en attente" accumule les
ticks EVT_TRADE_PRINT tant qu'ils arrivent au même prix, dans le même
sens, et à moins de `merge_window_ms` du dernier tick du groupe. Dès
qu'un tick rompt une de ces conditions (ou que la fenêtre expire sans
nouveau tick), le groupe est finalisé et republié sur EVT_TAPE_RECONSTRUCTED.

Paramètres configurables (Settings -> "reconstructed_tape") :
  - merge_window_ms : fenêtre de fusion en millisecondes (défaut 150 ms)
"""
from __future__ import annotations
import time
from typing import Dict

from PySide6.QtCore import QObject, QTimer

from Core.EventBus import EventBus


class _PendingGroup:
    __slots__ = ("symbol", "price", "side", "size", "first_time", "last_time", "aggressive", "fragments")

    def __init__(self, tick: dict) -> None:
        self.symbol = tick["symbol"]
        self.price = tick["price"]
        self.side = tick["side"]
        self.size = tick["size"]
        self.first_time = tick["time"]
        self.last_time = tick["time"]
        self.aggressive = bool(tick.get("aggressive"))
        self.fragments = 1

    def merge(self, tick: dict) -> None:
        self.size += tick["size"]
        self.last_time = tick["time"]
        self.aggressive = self.aggressive or bool(tick.get("aggressive"))
        self.fragments += 1

    def to_payload(self) -> dict:
        return {
            "symbol": self.symbol,
            "time": self.first_time,
            "end_time": self.last_time,
            "price": self.price,
            "size": self.size,
            "side": self.side,
            "aggressive": self.aggressive,
            "fragments": self.fragments,
        }


class ReconstructedTapeEngine(QObject):
    """Regroupe les fills fragmentés en prints uniques (Reconstructed Tape)."""

    def __init__(self, bus: EventBus, settings=None, poll_ms: int = 40, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.settings = settings
        self._pending: Dict[str, _PendingGroup] = {}

        self.bus.subscribe(EventBus.EVT_TRADE_PRINT, self._on_trade)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._flush_stale)
        self._timer.start(poll_ms)

    def _merge_window_s(self) -> float:
        cfg = self.settings.get("reconstructed_tape", {}) if self.settings else {}
        return cfg.get("merge_window_ms", 150) / 1000.0

    def _on_trade(self, tick: dict) -> None:
        symbol = tick.get("symbol")
        if symbol is None:
            return
        window_s = self._merge_window_s()
        pending = self._pending.get(symbol)

        same_group = (
            pending is not None
            and pending.price == tick["price"]
            and pending.side == tick["side"]
            and (tick["time"] - pending.last_time) <= window_s
        )
        if same_group:
            pending.merge(tick)
            return

        if pending is not None:
            self._flush(symbol)
        self._pending[symbol] = _PendingGroup(tick)

    def _flush(self, symbol: str) -> None:
        pending = self._pending.pop(symbol, None)
        if pending is not None:
            self.bus.publish(EventBus.EVT_TAPE_RECONSTRUCTED, pending.to_payload())

    def _flush_stale(self) -> None:
        now = time.time()
        window_s = self._merge_window_s()
        for symbol, pending in list(self._pending.items()):
            if (now - pending.last_time) > window_s:
                self._flush(symbol)
