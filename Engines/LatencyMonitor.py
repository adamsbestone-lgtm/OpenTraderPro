"""
LatencyMonitor.py - mesure en continu la latence RÉELLE du pipeline
(marché -> détection -> exécution), pour objectiver les efforts de
performance plutôt que de se contenter de les affirmer.

Deux mesures indépendantes, sur fenêtre glissante :

1. "détection" (tick -> signal Order Flow observé)
   Différence entre l'horodatage marché du tick (celui-là même utilisé
   par Plugins/OrderFlowSuite/plugin.py pour horodater ses signaux) et le
   moment où ce signal atteint ce moniteur. Comme l'EventBus marshalle
   automatiquement les publications inter-thread vers le thread
   propriétaire du bus (thread GUI), cette mesure inclut le vrai coût de
   ce passage inter-thread + le temps de calcul des détecteurs -- c'est
   la latence qui compte réellement pour un usage en direct, pas un
   chiffre théorique.

2. "exécution" (soumission d'ordre -> exécution)
   Différence entre Order.created_perf (horodatage perf_counter pris à
   la création de l'ordre, cf. Engines/OrderEngine.py) et l'instant de
   réception de EVT_ORDER_FILLED. perf_counter est monotone et à la
   résolution la plus fine disponible sur la plateforme -- adapté à des
   mesures sous la milliseconde, contrairement à time.time().

Statistiques glissantes (fenêtre des N derniers échantillons) : p50, p95,
p99, max -- affichées par Widgets/Latency/LatencyWidget.py.
"""
from __future__ import annotations
import time
from collections import deque
from typing import Deque, Dict

from Core.EventBus import EventBus
from Plugins.OrderFlowSuite.plugin import EVT_ORDERFLOW_SIGNAL

WINDOW_SIZE = 500


def _percentile(sorted_values: list, p: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * p
    f, c = int(k), min(int(k) + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def _summarize(values) -> dict:
    if not values:
        return {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "p50": _percentile(ordered, 0.50),
        "p95": _percentile(ordered, 0.95),
        "p99": _percentile(ordered, 0.99),
        "max": ordered[-1],
    }


class LatencyMonitor:
    def __init__(self, bus: EventBus, window_size: int = WINDOW_SIZE) -> None:
        self.bus = bus
        self._detection_ms: Deque[float] = deque(maxlen=window_size)
        self._execution_ms: Deque[float] = deque(maxlen=window_size)
        self._pending_orders: Dict[int, float] = {}  # order_id -> created_perf

        self.bus.subscribe(EVT_ORDERFLOW_SIGNAL, self._on_signal)
        self.bus.subscribe(EventBus.EVT_ORDER_NEW, self._on_order_new)
        self.bus.subscribe(EventBus.EVT_ORDER_FILLED, self._on_order_filled)

    def _on_signal(self, payload: dict) -> None:
        signal = payload.get("signal")
        if signal is None:
            return
        latency_ms = time.time() * 1000 - signal.timestamp_ms
        if 0 <= latency_ms < 60_000:  # ignore les valeurs aberrantes (replay/backtest en arrière-plan)
            self._detection_ms.append(latency_ms)

    def _on_order_new(self, order) -> None:
        self._pending_orders[order.id] = order.created_perf

    def _on_order_filled(self, order) -> None:
        created_perf = self._pending_orders.pop(order.id, None)
        if created_perf is None:
            return
        self._execution_ms.append((time.perf_counter() - created_perf) * 1000)

    def stats(self) -> dict:
        return {"detection": _summarize(self._detection_ms), "execution": _summarize(self._execution_ms)}
