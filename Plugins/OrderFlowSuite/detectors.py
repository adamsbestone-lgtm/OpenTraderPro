"""
detectors.py - portage fidèle des 10 détecteurs Java de l'add-on Bookmap
original (`detectors/*.java`). Logique inchangée ; seule la syntaxe change
(Optional[...] Python au lieu d'Optional<...> Java, dataclasses au lieu de
classes internes `static final`).

Chaque détecteur reste indépendant des autres et n'a aucune dépendance à
OpenTrader Pro : ils ne connaissent que `model.py` et `state.py`. C'est le
plugin.py qui fait le pont avec l'EventBus / MarketEngine.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Set

from Plugins.OrderFlowSuite.model import Direction, Signal, SignalType
from Plugins.OrderFlowSuite.state import OrderBookState, TapeWindow


# ---------------------------------------------------------------------------
# 1. Imbalance empilée
# ---------------------------------------------------------------------------
@dataclass
class ImbalanceWall:
    direction: Direction
    top_ticks: int
    bottom_ticks: int
    level_count: int


class ImbalanceDetector:
    """Murs d'imbalance empilée : plusieurs niveaux consécutifs où le ratio
    diagonal (ask(P)/bid(P+1)) dépasse un seuil dans la même direction."""

    def __init__(self, imbalance_ratio: float, min_stacked_levels: int, min_level_volume: int) -> None:
        self.imbalance_ratio = imbalance_ratio
        self.min_stacked_levels = min_stacked_levels
        self.min_level_volume = min_level_volume

    def find_stacked_wall(self, book: OrderBookState) -> Optional[ImbalanceWall]:
        low, high = book.lowest_tracked_ticks(), book.highest_tracked_ticks()
        if low is None or high is None:
            return None

        best: Optional[ImbalanceWall] = None
        run_direction: Optional[Direction] = None
        run_start = 0
        run_length = 0

        def flush(run_dir, start, length):
            nonlocal best
            if run_dir is not None and length >= self.min_stacked_levels:
                candidate = ImbalanceWall(run_dir, start + length - 1, start, length)
                if best is None or candidate.level_count > best.level_count:
                    best = candidate

        for ticks in range(low, high + 1):
            total = book.bid_size_at(ticks) + book.ask_size_at(ticks)
            direction = None
            if total >= self.min_level_volume:
                ratio = book.diagonal_ratio(ticks)
                if ratio is not None:
                    if ratio >= self.imbalance_ratio:
                        direction = Direction.BUY
                    elif ratio <= 1.0 / self.imbalance_ratio:
                        direction = Direction.SELL

            if direction is not None and direction == run_direction:
                run_length += 1
            else:
                flush(run_direction, run_start, run_length)
                run_direction = direction
                run_start = ticks
                run_length = 1 if direction is not None else 0

        flush(run_direction, run_start, run_length)
        return best


# ---------------------------------------------------------------------------
# 2. Absorption / iceberg (+ texture bloc vs fragmentée)
# ---------------------------------------------------------------------------
class Texture:
    BLOCK = "BLOCK"
    FRAGMENTED = "FRAGMENTED"
    UNKNOWN = "UNKNOWN"


@dataclass
class AbsorptionClassification:
    absorbing: bool
    texture: str
    refill_count: int
    avg_refill_size: float


class AbsorptionDetector:
    """Volume tradé cumulé qui dépasse largement la taille affichée max
    historique du niveau, alors qu'il reste actif -> iceberg/refill. La
    "texture" (BLOCK vs FRAGMENTED) distingue un gros acteur unique d'une
    mosaïque de petits participants, à partir de l'historique des refills."""

    def __init__(self, refill_ratio: float, min_traded_volume: int,
                 texture_window_ms: float = 15_000, block_max_refill_count: int = 3,
                 block_min_avg_refill_size: float = 40.0, fragmented_min_refill_count: int = 6) -> None:
        self.refill_ratio = refill_ratio
        self.min_traded_volume = min_traded_volume
        self.texture_window_ms = texture_window_ms
        self.block_max_refill_count = block_max_refill_count
        self.block_min_avg_refill_size = block_min_avg_refill_size
        self.fragmented_min_refill_count = fragmented_min_refill_count

    def is_absorbing(self, book: OrderBookState, price_ticks: int) -> bool:
        traded = book.traded_volume_at(price_ticks)
        max_displayed = book.max_displayed_size_at(price_ticks)
        if traded < self.min_traded_volume or max_displayed == 0:
            return False
        return traded >= self.refill_ratio * max_displayed and book.has_liquidity_at(price_ticks)

    def classify(self, book: OrderBookState, price_ticks: int, now_ms: float) -> AbsorptionClassification:
        absorbing = self.is_absorbing(book, price_ticks)
        events = book.refill_events_at(price_ticks, now_ms, self.texture_window_ms)
        if not events:
            return AbsorptionClassification(absorbing, Texture.UNKNOWN, 0, 0.0)

        avg_size = sum(e.increment_size for e in events) / len(events)
        count = len(events)
        if count <= self.block_max_refill_count and avg_size >= self.block_min_avg_refill_size:
            texture = Texture.BLOCK
        elif count >= self.fragmented_min_refill_count:
            texture = Texture.FRAGMENTED
        else:
            texture = Texture.UNKNOWN
        return AbsorptionClassification(absorbing, texture, count, avg_size)


# ---------------------------------------------------------------------------
# 3. Sweep
# ---------------------------------------------------------------------------
@dataclass
class SweepEvent:
    direction: Direction
    total_volume: int
    distinct_levels: int
    start_price: float
    end_price: float


class SweepDetector:
    """Rafale de prints du même côté agresseur qui traverse plusieurs
    niveaux de prix distincts en peu de temps."""

    def __init__(self, window_ms: float, min_volume: int, min_distinct_levels: int, tick_size: float) -> None:
        self.window_ms = window_ms
        self.min_volume = min_volume
        self.min_distinct_levels = min_distinct_levels
        self.tick_size = tick_size

    def evaluate(self, tape: TapeWindow, now_ms: float) -> Optional[SweepEvent]:
        recent = tape.since(now_ms, self.window_ms)
        if not recent:
            return None

        buy_volume = sell_volume = 0
        buy_levels: Set[int] = set()
        sell_levels: Set[int] = set()

        for p in recent:
            level_ticks = round(p.price / self.tick_size)
            if p.aggressor_side == Direction.BUY:
                buy_volume += p.size
                buy_levels.add(level_ticks)
            else:
                sell_volume += p.size
                sell_levels.add(level_ticks)

        buy_sweep = buy_volume >= self.min_volume and len(buy_levels) >= self.min_distinct_levels
        sell_sweep = sell_volume >= self.min_volume and len(sell_levels) >= self.min_distinct_levels
        if not buy_sweep and not sell_sweep:
            return None

        direction = Direction.BUY if buy_volume >= sell_volume else Direction.SELL
        volume = buy_volume if direction is Direction.BUY else sell_volume
        levels = len(buy_levels) if direction is Direction.BUY else len(sell_levels)

        return SweepEvent(direction, volume, levels, recent[0].price, recent[-1].price)


# ---------------------------------------------------------------------------
# 4. Cascade de stops
# ---------------------------------------------------------------------------
@dataclass
class CascadeEvent:
    direction: Direction
    small_prints_count: int
    total_volume: int


class StopCascadeDetector:
    """BEAUCOUP de petits prints indépendants dans la même direction sur une
    courte fenêtre -- cohérent avec une vague de stops déclenchés en chaîne
    plutôt qu'un seul participant agressif (approximation sans MBO complet)."""

    def __init__(self, window_ms: float, small_order_max_size: int, min_small_prints_count: int, min_total_volume: int) -> None:
        self.window_ms = window_ms
        self.small_order_max_size = small_order_max_size
        self.min_small_prints_count = min_small_prints_count
        self.min_total_volume = min_total_volume

    def evaluate(self, tape: TapeWindow, now_ms: float) -> Optional[CascadeEvent]:
        recent = tape.since(now_ms, self.window_ms)
        if not recent:
            return None

        buy_small = sell_small = 0
        buy_volume = sell_volume = 0
        for p in recent:
            if p.aggressor_side == Direction.BUY:
                buy_volume += p.size
                if p.size <= self.small_order_max_size:
                    buy_small += 1
            else:
                sell_volume += p.size
                if p.size <= self.small_order_max_size:
                    sell_small += 1

        buy_cascade = buy_small >= self.min_small_prints_count and buy_volume >= self.min_total_volume
        sell_cascade = sell_small >= self.min_small_prints_count and sell_volume >= self.min_total_volume
        if not buy_cascade and not sell_cascade:
            return None

        direction = Direction.BUY if buy_small >= sell_small else Direction.SELL
        count = buy_small if direction is Direction.BUY else sell_small
        volume = buy_volume if direction is Direction.BUY else sell_volume
        return CascadeEvent(direction, count, volume)


# ---------------------------------------------------------------------------
# 5. Out-of-spread
# ---------------------------------------------------------------------------
@dataclass
class OosEvent:
    direction: Direction
    total_volume: int
    is_block: bool  # True = peu de gros prints, False = beaucoup de petits (fragmenté)


class OutOfSpreadDetector:
    """Exécutions au-delà du meilleur bid/ask affiché au moment du print."""

    def __init__(self, window_ms: float, min_volume: int) -> None:
        self.window_ms = window_ms
        self.min_volume = min_volume

    def is_out_of_spread(self, book: OrderBookState, price: float, side: Direction, tick_size: float) -> bool:
        best_bid, best_ask = book.best_bid_ticks(), book.best_ask_ticks()
        if best_bid is None or best_ask is None:
            return False
        price_ticks = round(price / tick_size)
        return price_ticks > best_ask if side is Direction.BUY else price_ticks < best_bid

    def evaluate_burst(self, oos_only_tape: TapeWindow, now_ms: float, small_order_max_size: int) -> Optional[OosEvent]:
        recent = oos_only_tape.since(now_ms, self.window_ms)
        if not recent:
            return None

        buy_volume = sell_volume = buy_small = sell_small = buy_count = sell_count = 0
        for p in recent:
            if p.aggressor_side == Direction.BUY:
                buy_volume += p.size
                buy_count += 1
                if p.size <= small_order_max_size:
                    buy_small += 1
            else:
                sell_volume += p.size
                sell_count += 1
                if p.size <= small_order_max_size:
                    sell_small += 1

        if buy_volume < self.min_volume and sell_volume < self.min_volume:
            return None

        direction = Direction.BUY if buy_volume >= sell_volume else Direction.SELL
        volume = buy_volume if direction is Direction.BUY else sell_volume
        count = buy_count if direction is Direction.BUY else sell_count
        small = buy_small if direction is Direction.BUY else sell_small
        is_block = count > 0 and (small / count) < 0.5
        return OosEvent(direction, volume, is_block)


# ---------------------------------------------------------------------------
# 6. Zone défendue
# ---------------------------------------------------------------------------
class DefendedZoneDetector:
    """Niveau qui se recharge malgré plusieurs attaques agressives
    consécutives -- persistance sur plusieurs tests successifs, contrairement
    à l'absorption ponctuelle (AbsorptionDetector)."""

    def __init__(self, min_size: int, min_defense_count: int) -> None:
        self.min_size = min_size
        self.min_defense_count = min_defense_count
        self._defense_counter: Dict[int, int] = {}

    def register_attack_and_check(self, price_ticks: int, size_before_attack: int,
                                   size_after_attack: int, attack_direction: Direction) -> Optional[Direction]:
        if size_before_attack < self.min_size:
            return None

        defended = size_after_attack >= size_before_attack * 0.7
        if defended:
            count = self._defense_counter.get(price_ticks, 0) + 1
            self._defense_counter[price_ticks] = count
            if count >= self.min_defense_count:
                return attack_direction.opposite
        else:
            self._defense_counter.pop(price_ticks, None)
        return None

    def reset(self, price_ticks: int) -> None:
        self._defense_counter.pop(price_ticks, None)


# ---------------------------------------------------------------------------
# 7. Inside print
# ---------------------------------------------------------------------------
@dataclass
class InsideReading:
    buy_volume: int
    sell_volume: int
    buy_count: int
    sell_count: int


class InsidePrintDetector:
    """Déséquilibre entre volume acheteur et vendeur exécuté exactement au
    meilleur bid/ask du moment (par opposition aux prints "away"). Lit la
    pression RÉELLEMENT EXÉCUTÉE, qui peut diverger de l'imbalance de
    carnet (liquidité AFFICHÉE, cf. ImbalanceDetector)."""

    def __init__(self, min_volume: int, min_ratio: float) -> None:
        self.min_volume = min_volume
        self.min_ratio = min_ratio

    def read_level(self, book: OrderBookState, price_ticks: int) -> InsideReading:
        return InsideReading(
            book.inside_buy_volume_at(price_ticks), book.inside_sell_volume_at(price_ticks),
            book.inside_buy_count_at(price_ticks), book.inside_sell_count_at(price_ticks),
        )

    def evaluate(self, book: OrderBookState, price_ticks: int) -> Optional[Direction]:
        buy = book.inside_buy_volume_at(price_ticks)
        sell = book.inside_sell_volume_at(price_ticks)
        if buy + sell < self.min_volume:
            return None
        if sell == 0 or buy / sell >= self.min_ratio:
            return Direction.BUY
        if buy == 0 or sell / buy >= self.min_ratio:
            return Direction.SELL
        return None


# ---------------------------------------------------------------------------
# 8. Reliquat post-sweep (SPR honnête)
# ---------------------------------------------------------------------------
@dataclass
class _RecentSweep:
    direction: Direction
    price: float
    timestamp_ms: float


class OrderReuseDetector:
    """Corrèle un sweep récent avec l'apparition d'un nouvel ordre passif au
    même niveau, du côté cohérent avec un reliquat (sweep BUY -> nouveau
    bid ; sweep SELL -> nouvel ask).

    ⚠️ Honnêteté sur les limites (identique à la version Java) : sans ID
    d'agresseur réel (MBO complet non disponible dans le flux simulé
    d'OpenTrader Pro), ceci reste une corrélation par timing + prix + côté,
    pas une preuve d'identité d'ordre. À traiter comme une inférence
    plausible, pas une certitude."""

    def __init__(self, correlation_window_ms: float, max_distance_ticks: float, tick_size: float, min_residual_size: int) -> None:
        self.correlation_window_ms = correlation_window_ms
        self.max_distance_ticks = max_distance_ticks
        self.tick_size = tick_size
        self.min_residual_size = min_residual_size
        self._recent_sweeps: Deque[_RecentSweep] = deque()

    def register_sweep(self, direction: Direction, price: float, now_ms: float) -> None:
        self._recent_sweeps.append(_RecentSweep(direction, price, now_ms))
        cutoff = now_ms - self.correlation_window_ms
        while self._recent_sweeps and self._recent_sweeps[0].timestamp_ms < cutoff:
            self._recent_sweeps.popleft()

    def evaluate_new_resting_order(self, is_bid: bool, price: float, size: int, now_ms: float) -> Optional[Direction]:
        if size < self.min_residual_size:
            return None
        cutoff = now_ms - self.correlation_window_ms
        for sweep in self._recent_sweeps:
            if sweep.timestamp_ms < cutoff:
                continue
            side_matches = (sweep.direction is Direction.BUY) == is_bid
            if not side_matches:
                continue
            distance_ticks = abs(price - sweep.price) / self.tick_size
            if distance_ticks <= self.max_distance_ticks:
                return sweep.direction
        return None


# ---------------------------------------------------------------------------
# 9. Sweep + Défense (composite)
# ---------------------------------------------------------------------------
class SweepDefenseOutcome:
    REVERSAL_CONTEXT = "REVERSAL_CONTEXT"   # sweep stoppé par une défense opposée
    CONTINUATION = "CONTINUATION"            # second sweep confirmant le premier


class SweepDefenseDetector:
    """Combine SweepDetector et DefendedZoneDetector pour lire une séquence
    à deux temps : reversal-context (défense opposée après un sweep) ou
    continuation (second sweep dans la même direction)."""

    def __init__(self, confirmation_window_ms: float, max_distance_ticks: float, tick_size: float) -> None:
        self.confirmation_window_ms = confirmation_window_ms
        self.max_distance_ticks = max_distance_ticks
        self.tick_size = tick_size
        self._recent_sweeps: Deque[_RecentSweep] = deque()

    def register_sweep(self, direction: Direction, price: float, now_ms: float) -> None:
        self._recent_sweeps.append(_RecentSweep(direction, price, now_ms))
        cutoff = now_ms - self.confirmation_window_ms
        while self._recent_sweeps and self._recent_sweeps[0].timestamp_ms < cutoff:
            self._recent_sweeps.popleft()

    def check_defense(self, defender_direction: Direction, price: float, now_ms: float) -> Optional[str]:
        cutoff = now_ms - self.confirmation_window_ms
        for sweep in self._recent_sweeps:
            if sweep.timestamp_ms < cutoff:
                continue
            distance_ticks = abs(price - sweep.price) / self.tick_size
            if distance_ticks > self.max_distance_ticks:
                continue
            if defender_direction != sweep.direction:
                return SweepDefenseOutcome.REVERSAL_CONTEXT
        return None

    def check_continuation(self, direction: Direction, price: float, now_ms: float) -> Optional[str]:
        for sweep in self._recent_sweeps:
            if sweep.direction != direction:
                continue
            distance_ticks = abs(price - sweep.price) / self.tick_size
            age = now_ms - sweep.timestamp_ms
            if distance_ticks <= self.max_distance_ticks and 0 < age <= self.confirmation_window_ms:
                return SweepDefenseOutcome.CONTINUATION
        return None


# ---------------------------------------------------------------------------
# 10. Score de confluence (composite)
# ---------------------------------------------------------------------------
@dataclass
class _ConfluenceEntry:
    type_: SignalType
    direction: Direction
    price: float
    timestamp_ms: float


@dataclass
class ConfluenceResult:
    direction: Direction
    center_price: float
    agreeing_types: Set[SignalType]
    score: float  # 0.0 - 1.0


class ConfluenceScorer:
    """Regroupe les signaux émis par les différents détecteurs et cherche
    des zones où plusieurs types distincts s'accordent, dans une fenêtre de
    temps courte et à des prix proches. Score = types d'accord / 7 (les 7
    concepts de base, cf. model.BASE_SIGNAL_TYPES)."""

    TOTAL_TRACKED_TYPES = 7

    def __init__(self, window_ms: float, max_distance_ticks: float, tick_size: float, min_distinct_types: int) -> None:
        self.window_ms = window_ms
        self.max_distance_ticks = max_distance_ticks
        self.tick_size = tick_size
        self.min_distinct_types = min_distinct_types
        self._recent: Deque[_ConfluenceEntry] = deque()

    def register(self, signal: Signal) -> None:
        self._recent.append(_ConfluenceEntry(signal.type, signal.direction, signal.price, signal.timestamp_ms))
        cutoff = signal.timestamp_ms - self.window_ms
        while self._recent and self._recent[0].timestamp_ms < cutoff:
            self._recent.popleft()

    def evaluate_around_last_signal(self) -> Optional[ConfluenceResult]:
        if not self._recent:
            return None
        last = self._recent[-1]

        buy_types: Set[SignalType] = set()
        sell_types: Set[SignalType] = set()
        for e in self._recent:
            if abs(e.price - last.price) / self.tick_size > self.max_distance_ticks:
                continue
            (buy_types if e.direction is Direction.BUY else sell_types).add(e.type_)

        winning_set = buy_types if len(buy_types) >= len(sell_types) else sell_types
        winning_direction = Direction.BUY if len(buy_types) >= len(sell_types) else Direction.SELL

        if len(winning_set) < self.min_distinct_types:
            return None

        score = min(1.0, len(winning_set) / self.TOTAL_TRACKED_TYPES)
        return ConfluenceResult(winning_direction, last.price, winning_set, score)
