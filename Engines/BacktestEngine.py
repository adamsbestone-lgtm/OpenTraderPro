"""
BacktestEngine.py - rejoue l'historique enregistré en base (Database
ticks/depth, sur des jours ou des mois passés) à travers les mêmes
détections qu'en direct (Plugins/OrderFlowSuite) et simule chaque
technique (rejection, sweep, reversal, cassure de déséquilibre, cascade
de stops, confluence -- cf. Plugins/OrderFlowSuite/rules.py) pour mesurer
leur performance AVANT de les activer en argent réel.

Chaque trade théorique est simulé avec un stop et un objectif fixés en
ticks (par défaut : objectif entre 1 et 5+ ticks, comme demandé), en
suivant le fil des prix réellement enregistrés après le signal jusqu'à
toucher l'un des deux, ou expirer (timeout).

Les résultats alimentent aussi Engines/SignalAI.py pour entraîner un
filtre IA (probabilité de succès par signal).

Ce moteur tourne hors-ligne (pas de QTimer, pas de vitesse de lecture) :
toutes les données sont déjà en mémoire, donc rejouer plusieurs mois
prend quelques secondes à quelques minutes, pas des mois.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from Core.Database import Database
from Core.EventBus import EventBus
from Engines.MarketEngine import DepthSnapshot, DepthLevel
from Plugins.OrderFlowSuite.plugin import OrderFlowEngine, EVT_ORDERFLOW_SIGNAL
from Plugins.OrderFlowSuite.model import Direction
from Plugins.OrderFlowSuite.rules import RULE_FOR_SIGNAL

DEFAULT_TIMEOUT_S = 180  # abandon si ni le stop ni l'objectif n'est touché à temps


@dataclass
class SimulatedTrade:
    rule_name: str
    signal_type: str
    direction: str
    entry_price: float
    entry_ts: float
    exit_price: float
    exit_ts: float
    outcome: str  # "win", "loss" ou "timeout"
    ticks_result: float
    signal_size: int


@dataclass
class BacktestReport:
    trades: List[SimulatedTrade] = field(default_factory=list)
    events_processed: int = 0

    def by_rule(self) -> Dict[str, dict]:
        stats: Dict[str, dict] = {}
        for t in self.trades:
            s = stats.setdefault(t.rule_name, {"trades": 0, "wins": 0, "losses": 0, "timeouts": 0, "total_ticks": 0.0})
            s["trades"] += 1
            s["total_ticks"] += t.ticks_result
            if t.outcome == "win":
                s["wins"] += 1
            elif t.outcome == "loss":
                s["losses"] += 1
            else:
                s["timeouts"] += 1
        for s in stats.values():
            decided = s["wins"] + s["losses"]
            s["win_rate"] = (s["wins"] / decided) if decided else 0.0
            s["avg_ticks"] = (s["total_ticks"] / s["trades"]) if s["trades"] else 0.0
        return stats


class BacktestEngine:
    def __init__(self, db: Database, symbol: str, tick_size: float = 0.25) -> None:
        self.db = db
        self.symbol = symbol
        self.tick_size = tick_size

    # -- chargement des données historiques -----------------------------------
    def _load_events(self, ts_from: float, ts_to: float) -> List[tuple]:
        events: List[tuple] = []
        for row in self.db.fetch_ticks(self.symbol, ts_from, ts_to):
            events.append((row["ts"], "tick", {
                "symbol": row["symbol"], "time": row["ts"], "price": row["price"],
                "size": row["size"], "side": row["side"], "aggressive": bool(row["aggressive"]),
            }))
        for row in self.db.fetch_depth(self.symbol, ts_from, ts_to):
            payload = json.loads(row["payload"])
            snap = DepthSnapshot(
                symbol=row["symbol"],
                bids=[DepthLevel(price=p, size=s) for p, s in payload.get("bids", [])],
                asks=[DepthLevel(price=p, size=s) for p, s in payload.get("asks", [])],
                last_price=payload.get("last_price", 0.0),
                volume=payload.get("volume", 0),
                ts=row["ts"],
            )
            events.append((row["ts"], "depth", snap))
        events.sort(key=lambda e: e[0])
        return events

    # -- exécution --------------------------------------------------------------
    def run(self, ts_from: float, ts_to: float, rules_cfg: dict,
            stop_loss_ticks: float = 8, take_profit_ticks: float = 3,
            timeout_s: float = DEFAULT_TIMEOUT_S,
            progress_cb: Optional[Callable[[int, int], None]] = None) -> BacktestReport:
        self.db.flush()
        events = self._load_events(ts_from, ts_to)
        if not events:
            return BacktestReport()

        # Bus local et isolé : on ne veut surtout pas publier des milliers de
        # signaux historiques sur le bus en direct pendant que l'appli tourne.
        local_bus = EventBus()
        engine = OrderFlowEngine(local_bus, order_engine=None, symbol=self.symbol, tick_size=self.tick_size)

        ticks_seen: List[dict] = []
        raw_signals: List[tuple] = []  # (index dans ticks_seen, Signal)
        local_bus.subscribe(EVT_ORDERFLOW_SIGNAL, lambda payload: raw_signals.append((len(ticks_seen), payload["signal"])))

        total = len(events)
        for i, (_ts, kind, payload) in enumerate(events):
            if kind == "tick":
                ticks_seen.append(payload)
                engine.on_trade(payload)
            else:
                engine.on_depth(payload)
            if progress_cb and (i % 2000 == 0 or i == total - 1):
                progress_cb(i + 1, total)

        trades: List[SimulatedTrade] = []
        for tick_index, signal in raw_signals:
            mapping = RULE_FOR_SIGNAL.get(signal.type)
            if mapping is None:
                continue
            rule_name, mode = mapping
            rule_cfg = rules_cfg.get(rule_name, {})
            if not rule_cfg.get("enabled", True):
                continue
            if signal.size < rule_cfg.get("min_size", 0):
                continue

            direction = signal.direction if mode == "with" else signal.direction.opposite
            trade = self._simulate_trade(
                ticks_seen, tick_index, direction, signal, rule_name,
                stop_loss_ticks, take_profit_ticks, timeout_s,
            )
            if trade is not None:
                trades.append(trade)

        return BacktestReport(trades=trades, events_processed=total)

    def _simulate_trade(self, ticks: List[dict], start_index: int, direction: Direction, signal,
                         rule_name: str, stop_loss_ticks: float, take_profit_ticks: float,
                         timeout_s: float) -> Optional[SimulatedTrade]:
        entry_price = signal.price
        entry_ts = signal.timestamp_ms / 1000.0
        stop_offset = stop_loss_ticks * self.tick_size
        target_offset = take_profit_ticks * self.tick_size
        is_buy = direction is Direction.BUY
        stop_price = entry_price - stop_offset if is_buy else entry_price + stop_offset
        target_price = entry_price + target_offset if is_buy else entry_price - target_offset

        for j in range(start_index, len(ticks)):
            tick = ticks[j]
            if tick["time"] < entry_ts:
                continue
            elapsed = tick["time"] - entry_ts
            price = tick["price"]

            hit_stop = price <= stop_price if is_buy else price >= stop_price
            hit_target = price >= target_price if is_buy else price <= target_price

            if hit_stop:
                return SimulatedTrade(rule_name, signal.type.value, direction.value, entry_price, entry_ts,
                                       price, tick["time"], "loss", -stop_loss_ticks, signal.size)
            if hit_target:
                return SimulatedTrade(rule_name, signal.type.value, direction.value, entry_price, entry_ts,
                                       price, tick["time"], "win", take_profit_ticks, signal.size)
            if elapsed > timeout_s:
                ticks_result = (price - entry_price) / self.tick_size * (1 if is_buy else -1)
                return SimulatedTrade(rule_name, signal.type.value, direction.value, entry_price, entry_ts,
                                       price, tick["time"], "timeout", ticks_result, signal.size)

        return None  # pas assez de données après le signal (fin de session) pour conclure
