"""
MarketEngine.py - responsable du Tick, DOM, Trades, Volume, cache et
synchronisation. En mode simulation, génère un flux réaliste ; en mode
réel, reçoit les données via le BrokerEngine actif. Alimente aussi le
Recorder (Core/Database) pour permettre le Replay ultérieur.
"""
from __future__ import annotations
import asyncio
import random
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

from Core.EventBus import EventBus
from Core.Database import Database


@dataclass
class DepthLevel:
    price: float
    size: int
    iceberg: bool = False
    pulling: bool = False
    stacking: bool = False
    swept: bool = False


@dataclass
class DepthSnapshot:
    symbol: str
    bids: List[DepthLevel] = field(default_factory=list)
    asks: List[DepthLevel] = field(default_factory=list)
    last_price: float = 0.0
    last_size: int = 0
    volume: int = 0
    ts: float = field(default_factory=time.time)


class MarketEngine:
    """Source de données de marché. `broker` est optionnel : si fourni et
    connecté, le broker pousse lui-même les événements EVT_DEPTH/EVT_TRADE_PRINT
    et MarketEngine se contente de les relayer au Recorder. Sinon, un flux
    simulé interne (thread asyncio) est utilisé (mode SIM / développement)."""

    def __init__(self, bus: EventBus, db: Optional[Database] = None, symbol: str = "ESU6",
                 tick_size: float = 0.25, levels: int = 20, record: bool = True) -> None:
        self.bus = bus
        self.db = db
        self.symbol = symbol
        self.tick_size = tick_size
        self.levels = levels
        self.record = record and db is not None

        self._mid_price = 5000.00
        self._volume = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        self.bus.subscribe(EventBus.EVT_DEPTH, self._maybe_record_depth)
        self.bus.subscribe(EventBus.EVT_TRADE_PRINT, self._maybe_record_tick)

    # -- cycle de vie (mode simulation) --------------------------------------
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="MarketEngine")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._produce())
        finally:
            self._loop.close()

    async def _produce(self) -> None:
        while self._running:
            snapshot = self._generate_snapshot()
            self.bus.publish(EventBus.EVT_DEPTH, snapshot)
            if snapshot.last_size:
                self.bus.publish(EventBus.EVT_TRADE_PRINT, {
                    "symbol": self.symbol,
                    "time": snapshot.ts,
                    "price": snapshot.last_price,
                    "size": snapshot.last_size,
                    "side": "buy" if random.random() > 0.5 else "sell",
                    "aggressive": random.random() > 0.6,
                })
            await asyncio.sleep(1 / 20)

    def _generate_snapshot(self) -> DepthSnapshot:
        if random.random() < 0.05:
            self._mid_price += random.choice([-1, 1]) * self.tick_size

        snap = DepthSnapshot(symbol=self.symbol, last_price=self._mid_price)
        for i in range(1, self.levels + 1):
            snap.bids.append(DepthLevel(
                price=round(self._mid_price - i * self.tick_size, 2),
                size=random.randint(1, 250),
                iceberg=random.random() < 0.03,
                pulling=random.random() < 0.05,
                stacking=random.random() < 0.05,
                swept=random.random() < 0.02,
            ))
            snap.asks.append(DepthLevel(
                price=round(self._mid_price + i * self.tick_size, 2),
                size=random.randint(1, 250),
                iceberg=random.random() < 0.03,
                pulling=random.random() < 0.05,
                stacking=random.random() < 0.05,
                swept=random.random() < 0.02,
            ))
        if random.random() < 0.3:
            snap.last_size = random.randint(1, 50)
            self._volume += snap.last_size
        snap.volume = self._volume
        return snap

    # -- recorder ---------------------------------------------------------------
    def _maybe_record_tick(self, tick: dict) -> None:
        if self.record and tick.get("symbol") == self.symbol:
            self.db.record_tick(tick["symbol"], tick["time"], tick["price"],
                                 tick["size"], tick["side"], tick.get("aggressive", False))

    def _maybe_record_depth(self, snapshot: DepthSnapshot) -> None:
        if self.record and snapshot.symbol == self.symbol:
            payload = {
                "bids": [(l.price, l.size) for l in snapshot.bids],
                "asks": [(l.price, l.size) for l in snapshot.asks],
                "last_price": snapshot.last_price,
                "volume": snapshot.volume,
            }
            self.db.record_depth(snapshot.symbol, snapshot.ts, payload)
