"""
model.py - structures neutres représentant un signal détecté et un print
du Time & Sales classifié. Portage fidèle de model/Signal.java et
model/TapePrint.java de l'add-on Bookmap original (aucune dépendance à
Bookmap dans ce fichier, comme dans la version Java).
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class SignalType(Enum):
    IMBALANCE_WALL = "IMBALANCE_WALL"
    ABSORPTION = "ABSORPTION"
    SWEEP = "SWEEP"
    STOP_CASCADE = "STOP_CASCADE"
    OUT_OF_SPREAD = "OUT_OF_SPREAD"
    DEFENDED_ZONE = "DEFENDED_ZONE"
    INSIDE_PRINT = "INSIDE_PRINT"
    ORDER_REUSE = "ORDER_REUSE"
    # Signaux composites, construits à partir des concepts de base :
    SWEEP_DEFENSE = "SWEEP_DEFENSE"
    CROSS_CONFIRMED = "CROSS_CONFIRMED"
    CONFLUENCE = "CONFLUENCE"


# Les 7 concepts de base pris en compte par ConfluenceScorer (dénominateur du score).
BASE_SIGNAL_TYPES = frozenset({
    SignalType.IMBALANCE_WALL, SignalType.ABSORPTION, SignalType.SWEEP,
    SignalType.STOP_CASCADE, SignalType.OUT_OF_SPREAD, SignalType.DEFENDED_ZONE,
    SignalType.INSIDE_PRINT,
})


class Direction(Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def opposite(self) -> "Direction":
        return Direction.SELL if self is Direction.BUY else Direction.BUY


@dataclass(frozen=True)
class Signal:
    type: SignalType
    direction: Direction
    price: float
    size: int
    timestamp_ms: float
    detail: str

    def __str__(self) -> str:
        arrow = "^" if self.direction is Direction.BUY else "v"
        return f"[{self.type.value}] {self.direction.value} {arrow} @ {self.price:.2f} (size={self.size}) - {self.detail}"


@dataclass(frozen=True)
class TapePrint:
    price: float
    size: int
    aggressor_side: Direction
    timestamp_ms: float
    is_inside: bool  # True = exécuté au meilleur bid/ask du moment
