"""
BotEngine.py - découvre les bots dans Bots/<Nom>/, les charge dynamiquement
et relaie tick/depth/bar/order/position/timer vers chaque bot actif.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
from typing import Dict

from PySide6.QtCore import QTimer

from Core.EventBus import EventBus
from Bots.Strategy import BaseStrategy

BOTS_DIR = Path(__file__).parent


class BotEngine:
    def __init__(self, bus: EventBus, order_engine, position_engine, market_engine=None) -> None:
        self.bus = bus
        self.order_engine = order_engine
        self.position_engine = position_engine
        self.market_engine = market_engine
        self.loaded: Dict[str, BaseStrategy] = {}
        self.active: Dict[str, bool] = {}

        bus.subscribe(EventBus.EVT_TRADE_PRINT, lambda tick: self._dispatch("on_tick", tick))
        bus.subscribe(EventBus.EVT_DEPTH, lambda dom: self._dispatch("on_depth", dom))
        bus.subscribe(EventBus.EVT_BAR, lambda bar: self._dispatch("on_bar", bar))
        bus.subscribe(EventBus.EVT_ORDER_UPDATE, lambda o: self._dispatch("on_order", o))
        bus.subscribe(EventBus.EVT_ORDER_FILLED, lambda o: self._dispatch("on_order", o))
        bus.subscribe(EventBus.EVT_POSITION_UPDATE, lambda p: self._dispatch("on_position", p))

        self._timer = QTimer()
        self._timer.timeout.connect(lambda: self._dispatch("on_timer", None, no_arg=True))
        self._timer.start(1000)

    def discover(self) -> list[str]:
        return [f.name for f in BOTS_DIR.iterdir()
                if f.is_dir() and (f / "bot.json").exists() and (f / "strategy.py").exists()]

    def load(self, bot_name: str) -> BaseStrategy | None:
        folder = BOTS_DIR / bot_name
        meta_path, strategy_path = folder / "bot.json", folder / "strategy.py"
        if not meta_path.exists() or not strategy_path.exists():
            return None

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        spec = importlib.util.spec_from_file_location(f"bots.{bot_name}.strategy", strategy_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        instance: BaseStrategy = module.Strategy(
            order_engine=self.order_engine,
            position_engine=self.position_engine,
            market_engine=self.market_engine,
            params=meta.get("params", {}),
            bus=self.bus,
        )
        instance.name = meta.get("name", bot_name)
        self.loaded[bot_name] = instance
        return instance

    def start(self, bot_name: str) -> None:
        if bot_name not in self.loaded:
            self.load(bot_name)
        strategy = self.loaded.get(bot_name)
        if strategy:
            self.active[bot_name] = True
            strategy.on_start()
            self.bus.publish(EventBus.EVT_LOG, {"level": "INFO", "msg": f"Bot '{bot_name}' démarré."})

    def stop(self, bot_name: str) -> None:
        strategy = self.loaded.get(bot_name)
        if strategy:
            self.active[bot_name] = False
            strategy.on_stop()
            self.bus.publish(EventBus.EVT_LOG, {"level": "INFO", "msg": f"Bot '{bot_name}' arrêté."})

    def _dispatch(self, method_name: str, payload, no_arg: bool = False) -> None:
        for bot_name, is_active in self.active.items():
            if not is_active:
                continue
            strategy = self.loaded.get(bot_name)
            if strategy:
                getattr(strategy, method_name)() if no_arg else getattr(strategy, method_name)(payload)
