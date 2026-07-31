"""
ReplayEngine.py - relit une séance enregistrée par le Recorder (via
Database.fetch_ticks / fetch_depth) et republie les événements sur
l'EventBus comme s'ils arrivaient en direct, à une vitesse réglable
(x1, x2, x4, x10, x100), avec pause / retour arrière / avance.

Pendant un replay, il est recommandé de ne pas démarrer le MarketEngine
simulé en parallèle (les deux publieraient sur EVT_DEPTH/EVT_TRADE_PRINT).
"""
from __future__ import annotations
import json
import threading
import time
from typing import List, Optional

from Core.EventBus import EventBus
from Core.Database import Database
from Engines.MarketEngine import DepthSnapshot, DepthLevel


class ReplayEngine:
    def __init__(self, bus: EventBus, db: Database) -> None:
        self.bus = bus
        self.db = db
        self.symbol: Optional[str] = None
        self.speed: float = 1.0
        self._playing = False
        self._thread: Optional[threading.Thread] = None
        self._events: List[tuple] = []  # (ts, kind, payload)
        self._cursor = 0

    def load_session(self, symbol: str, ts_from: float, ts_to: float) -> int:
        """Charge en mémoire les ticks + snapshots de profondeur d'une plage
        temporelle, fusionnés et triés par timestamp. Retourne le nb d'événements."""
        self.symbol = symbol
        events: List[tuple] = []

        for row in self.db.fetch_ticks(symbol, ts_from, ts_to):
            events.append((row["ts"], "tick", {
                "symbol": row["symbol"], "time": row["ts"], "price": row["price"],
                "size": row["size"], "side": row["side"], "aggressive": bool(row["aggressive"]),
            }))

        for row in self.db.fetch_depth(symbol, ts_from, ts_to):
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
        self._events = events
        self._cursor = 0
        return len(events)

    def play(self) -> None:
        if self._playing or not self._events:
            return
        self._playing = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="ReplayEngine")
        self._thread.start()
        self.bus.publish(EventBus.EVT_REPLAY_STATE, {"state": "playing", "cursor": self._cursor, "total": len(self._events)})

    def pause(self) -> None:
        self._playing = False
        self.bus.publish(EventBus.EVT_REPLAY_STATE, {"state": "paused", "cursor": self._cursor, "total": len(self._events)})

    def seek(self, index: int) -> None:
        self._cursor = max(0, min(index, len(self._events) - 1))
        self.bus.publish(EventBus.EVT_REPLAY_STATE, {"state": "seek", "cursor": self._cursor, "total": len(self._events)})

    def step_forward(self, n: int = 1) -> None:
        self.seek(self._cursor + n)

    def step_backward(self, n: int = 1) -> None:
        self.seek(self._cursor - n)

    def set_speed(self, speed: float) -> None:
        self.speed = speed  # x1, x2, x4, x10, x100...

    def _run(self) -> None:
        prev_ts = None
        while self._playing and self._cursor < len(self._events):
            ts, kind, payload = self._events[self._cursor]
            if prev_ts is not None:
                delay = max(0.0, (ts - prev_ts) / max(self.speed, 0.01))
                time.sleep(min(delay, 1.0))  # borne pour rester réactif à la pause
            prev_ts = ts

            if kind == "tick":
                self.bus.publish(EventBus.EVT_TRADE_PRINT, payload)
            else:
                self.bus.publish(EventBus.EVT_DEPTH, payload)

            self._cursor += 1
            self.bus.publish(EventBus.EVT_REPLAY_STATE, {"state": "playing", "cursor": self._cursor, "total": len(self._events)})

        self._playing = False
        self.bus.publish(EventBus.EVT_REPLAY_STATE, {"state": "ended", "cursor": self._cursor, "total": len(self._events)})
