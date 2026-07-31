"""
state.py - portage fidèle de state/OrderBookState.java, state/TapeWindow.java
et state/CrossInstrumentRegistry.java de l'add-on Bookmap original.

Les prix sont représentés en "ticks" (entiers) plutôt qu'en float, pour
éviter les problèmes d'arrondi flottant typiques d'un DOM à haute
fréquence. Convertis avec price_to_ticks()/ticks_to_price().
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional

from Plugins.OrderFlowSuite.model import Direction, Signal, SignalType

REFILL_HISTORY_RETENTION_MS = 60_000


@dataclass
class RefillEvent:
    timestamp_ms: float
    increment_size: int


class OrderBookState:
    """Suivi de l'état du DOM : taille bid/ask par niveau, plus les
    compteurs auxiliaires utilisés par les détecteurs (volume tradé par
    niveau pour l'iceberg, taille affichée max historique, historique des
    refills pour distinguer absorption bloc/fragmentée, compteurs "inside
    print")."""

    def __init__(self, tick_size: float) -> None:
        self.tick_size = tick_size
        self._bid_sizes: Dict[int, int] = {}
        self._ask_sizes: Dict[int, int] = {}

        self._traded_volume_at_level: Dict[int, int] = {}
        self._max_displayed_size_at_level: Dict[int, int] = {}

        self._inside_buy_volume: Dict[int, int] = {}
        self._inside_sell_volume: Dict[int, int] = {}
        self._inside_buy_count: Dict[int, int] = {}
        self._inside_sell_count: Dict[int, int] = {}

        self._refill_history: Dict[int, Deque[RefillEvent]] = {}

    def price_to_ticks(self, price: float) -> int:
        return round(price / self.tick_size)

    def ticks_to_price(self, ticks: int) -> float:
        return ticks * self.tick_size

    def update_bid(self, price_ticks: int, size: int, timestamp_ms: float) -> None:
        previous_total = self.bid_size_at(price_ticks) + self.ask_size_at(price_ticks)
        if size <= 0:
            self._bid_sizes.pop(price_ticks, None)
        else:
            self._bid_sizes[price_ticks] = size
            self._max_displayed_size_at_level[price_ticks] = max(
                self._max_displayed_size_at_level.get(price_ticks, 0), size)
        self._record_refill_if_any(price_ticks, previous_total,
                                    self.bid_size_at(price_ticks) + self.ask_size_at(price_ticks), timestamp_ms)

    def update_ask(self, price_ticks: int, size: int, timestamp_ms: float) -> None:
        previous_total = self.bid_size_at(price_ticks) + self.ask_size_at(price_ticks)
        if size <= 0:
            self._ask_sizes.pop(price_ticks, None)
        else:
            self._ask_sizes[price_ticks] = size
            self._max_displayed_size_at_level[price_ticks] = max(
                self._max_displayed_size_at_level.get(price_ticks, 0), size)
        self._record_refill_if_any(price_ticks, previous_total,
                                    self.bid_size_at(price_ticks) + self.ask_size_at(price_ticks), timestamp_ms)

    def _record_refill_if_any(self, price_ticks: int, previous_total: int, new_total: int, timestamp_ms: float) -> None:
        delta = new_total - previous_total
        if delta <= 0:
            return
        history = self._refill_history.setdefault(price_ticks, deque())
        history.append(RefillEvent(timestamp_ms, delta))
        cutoff = timestamp_ms - REFILL_HISTORY_RETENTION_MS
        while history and history[0].timestamp_ms < cutoff:
            history.popleft()

    def refill_events_at(self, price_ticks: int, now_ms: float, window_ms: float) -> List[RefillEvent]:
        history = self._refill_history.get(price_ticks)
        if not history:
            return []
        cutoff = now_ms - window_ms
        return [e for e in history if e.timestamp_ms >= cutoff]

    def bid_size_at(self, price_ticks: int) -> int:
        return self._bid_sizes.get(price_ticks, 0)

    def ask_size_at(self, price_ticks: int) -> int:
        return self._ask_sizes.get(price_ticks, 0)

    def best_bid_ticks(self) -> Optional[int]:
        return max(self._bid_sizes) if self._bid_sizes else None

    def best_ask_ticks(self) -> Optional[int]:
        return min(self._ask_sizes) if self._ask_sizes else None

    def diagonal_ratio(self, price_ticks: int) -> Optional[float]:
        """Ratio diagonal classique du footprint : ask(P) / bid(P + 1 tick)."""
        ask = self.ask_size_at(price_ticks)
        bid_above = self.bid_size_at(price_ticks + 1)
        if bid_above == 0:
            return None
        return ask / bid_above

    def record_traded_volume(self, price_ticks: int, size: int) -> None:
        self._traded_volume_at_level[price_ticks] = self._traded_volume_at_level.get(price_ticks, 0) + size

    def traded_volume_at(self, price_ticks: int) -> int:
        return self._traded_volume_at_level.get(price_ticks, 0)

    def record_inside_print(self, price_ticks: int, is_buy: bool, size: int) -> None:
        if is_buy:
            self._inside_buy_volume[price_ticks] = self._inside_buy_volume.get(price_ticks, 0) + size
            self._inside_buy_count[price_ticks] = self._inside_buy_count.get(price_ticks, 0) + 1
        else:
            self._inside_sell_volume[price_ticks] = self._inside_sell_volume.get(price_ticks, 0) + size
            self._inside_sell_count[price_ticks] = self._inside_sell_count.get(price_ticks, 0) + 1

    def inside_buy_volume_at(self, price_ticks: int) -> int:
        return self._inside_buy_volume.get(price_ticks, 0)

    def inside_sell_volume_at(self, price_ticks: int) -> int:
        return self._inside_sell_volume.get(price_ticks, 0)

    def inside_buy_count_at(self, price_ticks: int) -> int:
        return self._inside_buy_count.get(price_ticks, 0)

    def inside_sell_count_at(self, price_ticks: int) -> int:
        return self._inside_sell_count.get(price_ticks, 0)

    def max_displayed_size_at(self, price_ticks: int) -> int:
        return self._max_displayed_size_at_level.get(price_ticks, 0)

    def has_liquidity_at(self, price_ticks: int) -> bool:
        return self.bid_size_at(price_ticks) > 0 or self.ask_size_at(price_ticks) > 0

    def lowest_tracked_ticks(self) -> Optional[int]:
        candidates = [min(self._bid_sizes)] if self._bid_sizes else []
        if self._ask_sizes:
            candidates.append(min(self._ask_sizes))
        return min(candidates) if candidates else None

    def highest_tracked_ticks(self) -> Optional[int]:
        candidates = [max(self._bid_sizes)] if self._bid_sizes else []
        if self._ask_sizes:
            candidates.append(max(self._ask_sizes))
        return max(candidates) if candidates else None


class TapeWindow:
    """Fenêtre glissante de prints du tape, utilisée par plusieurs
    détecteurs (sweep, cascade, out-of-spread)."""

    def __init__(self, max_retain_ms: float) -> None:
        self._prints: Deque = deque()
        self._max_retain_ms = max_retain_ms

    def add(self, print_) -> None:
        self._prints.append(print_)
        cutoff = print_.timestamp_ms - self._max_retain_ms
        while self._prints and self._prints[0].timestamp_ms < cutoff:
            self._prints.popleft()

    def since(self, now_ms: float, window_ms: float) -> List:
        cutoff = now_ms - window_ms
        return [p for p in self._prints if p.timestamp_ms >= cutoff]

    def volume_in_window(self, now_ms: float, window_ms: float, side: Direction) -> int:
        return sum(p.size for p in self.since(now_ms, window_ms) if p.aggressor_side == side)


class CrossInstrumentRegistry:
    """Registre PARTAGÉ (au niveau du module = équivalent du `static` Java)
    entre toutes les instances du plugin (une par symbole/alias). Permet à
    l'instance "ES" de savoir ce que l'instance "MES" vient de détecter, si
    les deux tournent en même temps dans OpenTrader Pro."""

    _MAX_HISTORY_PER_ALIAS = 200
    _signals_by_alias: Dict[str, Deque[tuple]] = {}

    # Table de correspondance indicative (E-mini / Micro E-mini CME), purement informative.
    COMMON_PEER_HINTS = {
        "ES": "MES", "MES": "ES",
        "NQ": "MNQ", "MNQ": "NQ",
        "RTY": "M2K", "M2K": "RTY",
        "YM": "MYM", "MYM": "YM",
    }

    @classmethod
    def publish(cls, alias: str, signal: Signal) -> None:
        key = cls._normalize(alias)
        history = cls._signals_by_alias.setdefault(key, deque())
        history.append((signal.type, signal.direction, signal.timestamp_ms))
        while len(history) > cls._MAX_HISTORY_PER_ALIAS:
            history.popleft()

    @classmethod
    def has_matching_peer_signal(cls, peer_alias: str, type_: SignalType, direction: Direction,
                                  now_ms: float, window_ms: float) -> bool:
        history = cls._signals_by_alias.get(cls._normalize(peer_alias))
        if not history:
            return False
        cutoff = now_ms - window_ms
        return any(ts >= cutoff and t == type_ and d == direction for t, d, ts in history)

    @staticmethod
    def _normalize(alias: str) -> str:
        return (alias or "").strip().upper()
