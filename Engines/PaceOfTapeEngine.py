"""
PaceOfTapeEngine.py - "Pace of Tape" Smart Gauge façon Jigsaw daytradr.

Mesure le rythme actuel des transactions (volume/seconde sur une fenêtre
courte) et le compare à une moyenne de référence sur une fenêtre plus
longue, pour repérer les accélérations/ralentissements du marché - utile
aux abords des niveaux de support/résistance ou pour juger la force
d'un pullback.

ratio = rythme court terme / rythme de référence (baseline)
  - ratio <= calm_threshold      -> "Calme"
  - ratio <= active_threshold    -> "Normal"
  - ratio <= extreme_threshold   -> "Actif"
  - ratio >  extreme_threshold   -> "Extrême"

Paramètres configurables (Settings -> "pace_of_tape") :
  - short_window_s, baseline_window_s
  - calm_threshold, active_threshold, extreme_threshold
"""
from __future__ import annotations
import time
from collections import deque
from typing import Deque, Dict, Tuple

from PySide6.QtCore import QObject, QTimer

from Core.EventBus import EventBus

DEFAULT_CFG = {
    "short_window_s": 10,
    "baseline_window_s": 300,
    "calm_threshold": 0.5,
    "active_threshold": 1.5,
    "extreme_threshold": 3.0,
}


class PaceOfTapeEngine(QObject):
    """Calcule et publie périodiquement le rythme de la tape par symbole."""

    def __init__(self, bus: EventBus, settings=None, update_ms: int = 500, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.settings = settings
        # historique (timestamp, taille) par symbole, borné à baseline_window_s
        self._history: Dict[str, Deque[Tuple[float, int]]] = {}

        self.bus.subscribe(EventBus.EVT_TRADE_PRINT, self._on_trade)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._compute_and_publish)
        self._timer.start(update_ms)

    def _cfg(self) -> dict:
        cfg = dict(DEFAULT_CFG)
        if self.settings:
            cfg.update(self.settings.get("pace_of_tape", {}))
        return cfg

    def _on_trade(self, tick: dict) -> None:
        symbol = tick.get("symbol")
        if symbol is None:
            return
        dq = self._history.setdefault(symbol, deque())
        dq.append((tick["time"], tick["size"]))

    def _compute_and_publish(self) -> None:
        cfg = self._cfg()
        short_s = cfg["short_window_s"]
        baseline_s = cfg["baseline_window_s"]
        now = time.time()

        for symbol, dq in list(self._history.items()):
            while dq and (now - dq[0][0]) > baseline_s:
                dq.popleft()
            if not dq:
                continue

            short_volume = sum(size for ts, size in dq if (now - ts) <= short_s)
            baseline_volume = sum(size for _ts, size in dq)
            short_rate = short_volume / short_s
            baseline_rate = baseline_volume / baseline_s

            ratio = (short_rate / baseline_rate) if baseline_rate > 0 else (1.0 if short_rate == 0 else 3.0)
            category = self._categorize(ratio, cfg)

            self.bus.publish(EventBus.EVT_PACE_OF_TAPE, {
                "symbol": symbol,
                "ratio": ratio,
                "category": category,
                "short_rate": short_rate,
                "baseline_rate": baseline_rate,
            })

    @staticmethod
    def _categorize(ratio: float, cfg: dict) -> str:
        if ratio <= cfg["calm_threshold"]:
            return "Calme"
        if ratio <= cfg["active_threshold"]:
            return "Normal"
        if ratio <= cfg["extreme_threshold"]:
            return "Actif"
        return "Extrême"
