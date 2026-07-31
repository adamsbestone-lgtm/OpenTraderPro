"""
plugin.py - couche d'intégration OpenTrader Pro de l'Order Flow Suite
(portage de addon/EsOrderFlowAddon.java + addon/TradingEngine.java).

Contrairement à la version Bookmap originale, cette couche n'a AUCUNE
incertitude d'API : elle se branche directement sur l'EventBus et
l'OrderEngine d'OpenTrader Pro, déjà fonctionnels. Toute la logique de
détection (detectors.py, state.py, model.py) reste un portage fidèle,
indépendant de Bookmap comme de PySide6.

Adaptations nécessaires par rapport à la version Bookmap :
- `onDepth` de Bookmap livre des mises à jour PAR NIVEAU ; le MarketEngine
  d'OpenTrader Pro livre un snapshot complet (DepthSnapshot) à chaque
  cycle. On calcule donc un diff avec le snapshot précédent pour détecter
  les niveaux qui ont disparu (mis à 0) et alimenter OrderBookState de la
  même façon qu'un flux incrémental.
- Le tick simulé d'OpenTrader Pro donne déjà `side` ("buy"/"sell") sans
  ambiguïté, alors que Bookmap ne donne qu'un flag `isBidAggressor` -- la
  conversion est donc directe, sans inférence.
- Le MBO complet (send/replace/cancel par ID d'ordre) n'existe pas dans le
  flux simulé : `OrderReuseDetector` est alimenté par une approximation
  (un niveau qui apparaît avec une taille significative après avoir été
  balayé est traité comme un "nouvel ordre passif"), nettement moins fiable
  que le vrai MBO -- déjà présenté comme une inférence, pas une certitude,
  dans la version Java originale.
- `TradingEngine` original laissait l'envoi d'ordre réel en commentaire
  (incertitude sur l'API Bookmap). Ici, l'envoi est actif dès l'activation
  du mode auto, car OrderEngine.submit() est une API déjà stable et testée
  d'OpenTrader Pro.
"""
from __future__ import annotations
import time
from typing import Dict, Optional

from Core.EventBus import EventBus
from Engines.MarketEngine import DepthSnapshot
from Engines.OrderEngine import Order, OrderType, OrderSide

from Plugins.PluginBase import PluginBase
from Plugins.OrderFlowSuite.model import Direction, Signal, SignalType, BASE_SIGNAL_TYPES, TapePrint
from Plugins.OrderFlowSuite.state import OrderBookState, TapeWindow, CrossInstrumentRegistry
from Plugins.OrderFlowSuite.detectors import (
    ImbalanceDetector, AbsorptionDetector, Texture, SweepDetector, StopCascadeDetector,
    OutOfSpreadDetector, DefendedZoneDetector, InsidePrintDetector, OrderReuseDetector,
    SweepDefenseDetector, SweepDefenseOutcome, ConfluenceScorer,
)

# Événement custom (non déclaré dans Core/EventBus.py, mais l'EventBus est
# générique par nom de chaîne : n'importe quel module peut publier/écouter
# une clé supplémentaire sans modifier le bus).
EVT_ORDERFLOW_SIGNAL = "orderflow.signal"

# Signaux jugés assez significatifs pour remonter aussi dans la fenêtre
# Alerts générale (les autres restent visibles uniquement dans la fenêtre
# Order Flow, pour ne pas la noyer).
_ALERT_WORTHY_TYPES = {
    SignalType.SWEEP_DEFENSE, SignalType.CROSS_CONFIRMED,
    SignalType.CONFLUENCE, SignalType.DEFENDED_ZONE,
}


def _side_to_direction(side: str) -> Direction:
    return Direction.BUY if side == "buy" else Direction.SELL


class OrderFlowEngine:
    """Logique de détection pour UN symbole. Une instance par fenêtre DOM
    suivie ; plusieurs symboles peuvent tourner en parallèle (utile pour la
    confirmation croisée ES/MES, cf. CrossInstrumentRegistry)."""

    TICK_RETENTION_MS = 10_000
    SWEEP_WINDOW_MS = 1500
    CASCADE_WINDOW_MS = 3000
    CASCADE_SMALL_ORDER_MAX_SIZE = 3
    CASCADE_MIN_VOLUME = 60
    OOS_WINDOW_MS = 1500
    OOS_MIN_VOLUME = 20
    DEFENDED_MIN_SIZE = 100
    DEFENDED_MIN_COUNT = 3
    SWEEP_DEFENSE_WINDOW_MS = 8_000
    SWEEP_DEFENSE_MAX_DISTANCE_TICKS = 6
    CROSS_CONFIRM_WINDOW_MS = 3_000
    CONFLUENCE_WINDOW_MS = 5_000
    CONFLUENCE_MAX_DISTANCE_TICKS = 4
    ORDER_REUSE_WINDOW_MS = 4_000
    ORDER_REUSE_MAX_DISTANCE_TICKS = 3

    def __init__(self, bus: EventBus, order_engine, symbol: str, tick_size: float = 0.25) -> None:
        self.bus = bus
        self.order_engine = order_engine
        self.symbol = symbol
        self.tick_size = tick_size

        # --- réglages ajustables à chaud (équivalent des champs @Parameter) ---
        self.imbalance_ratio = 3.0
        self.min_stacked_levels = 3
        self.min_level_volume = 15
        self.absorption_refill_ratio = 2.0
        self.absorption_min_volume = 150
        self.sweep_min_volume = 80
        self.sweep_min_levels = 3
        self.cascade_min_small_prints = 12
        self.order_quantity = 1
        self.peer_alias = ""  # ex: "MES" si ce symbole est "ES" ; vide = désactivé
        self.confluence_min_distinct_types = 3
        self.inside_print_min_volume = 20
        self.inside_print_min_ratio = 3.0
        self.order_reuse_min_residual_size = 20
        self.auto_trading_enabled = False

        self.book = OrderBookState(tick_size)
        self.tape = TapeWindow(self.TICK_RETENTION_MS)
        self.oos_tape = TapeWindow(self.TICK_RETENTION_MS)

        self._last_bid_ticks: set[int] = set()
        self._last_ask_ticks: set[int] = set()

        self.rebuild_detectors()

    def rebuild_detectors(self) -> None:
        """Reconstruit les détecteurs à partir des réglages actuels
        (équivalent de EsOrderFlowAddon.rebuildDetectors(), appelé au
        démarrage et à chaque changement de réglage depuis le widget)."""
        self.imbalance_detector = ImbalanceDetector(self.imbalance_ratio, self.min_stacked_levels, self.min_level_volume)
        self.absorption_detector = AbsorptionDetector(self.absorption_refill_ratio, self.absorption_min_volume)
        self.sweep_detector = SweepDetector(self.SWEEP_WINDOW_MS, self.sweep_min_volume, self.sweep_min_levels, self.tick_size)
        self.cascade_detector = StopCascadeDetector(
            self.CASCADE_WINDOW_MS, self.CASCADE_SMALL_ORDER_MAX_SIZE, self.cascade_min_small_prints, self.CASCADE_MIN_VOLUME)
        self.oos_detector = OutOfSpreadDetector(self.OOS_WINDOW_MS, self.OOS_MIN_VOLUME)
        self.defended_zone_detector = DefendedZoneDetector(self.DEFENDED_MIN_SIZE, self.DEFENDED_MIN_COUNT)
        self.sweep_defense_detector = SweepDefenseDetector(
            self.SWEEP_DEFENSE_WINDOW_MS, self.SWEEP_DEFENSE_MAX_DISTANCE_TICKS, self.tick_size)
        self.confluence_scorer = ConfluenceScorer(
            self.CONFLUENCE_WINDOW_MS, self.CONFLUENCE_MAX_DISTANCE_TICKS, self.tick_size, self.confluence_min_distinct_types)
        self.inside_print_detector = InsidePrintDetector(self.inside_print_min_volume, self.inside_print_min_ratio)
        self.order_reuse_detector = OrderReuseDetector(
            self.ORDER_REUSE_WINDOW_MS, self.ORDER_REUSE_MAX_DISTANCE_TICKS, self.tick_size, self.order_reuse_min_residual_size)

    # -- réception des données de marché -------------------------------------------
    def on_depth(self, snapshot: DepthSnapshot) -> None:
        if snapshot.symbol != self.symbol:
            return
        now = snapshot.ts * 1000

        current_bids = {self.book.price_to_ticks(l.price): l.size for l in snapshot.bids}
        current_asks = {self.book.price_to_ticks(l.price): l.size for l in snapshot.asks}

        # niveaux disparus depuis le dernier snapshot -> remis à zéro
        # (équivalent d'un onDepth(size=0) explicite côté Bookmap)
        for ticks in self._last_bid_ticks - current_bids.keys():
            self.book.update_bid(ticks, 0, now)
        for ticks in self._last_ask_ticks - current_asks.keys():
            self.book.update_ask(ticks, 0, now)

        for ticks, size in current_bids.items():
            self.book.update_bid(ticks, size, now)
            # approximation MBO : un niveau bid qui apparaît/grossit significativement
            # est traité comme un "nouvel ordre passif" pour OrderReuseDetector
            if ticks not in self._last_bid_ticks and size >= self.order_reuse_min_residual_size:
                self._maybe_order_reuse(is_bid=True, price=self.book.ticks_to_price(ticks), size=size, now=now)
        for ticks, size in current_asks.items():
            self.book.update_ask(ticks, size, now)
            if ticks not in self._last_ask_ticks and size >= self.order_reuse_min_residual_size:
                self._maybe_order_reuse(is_bid=False, price=self.book.ticks_to_price(ticks), size=size, now=now)

        self._last_bid_ticks = set(current_bids.keys())
        self._last_ask_ticks = set(current_asks.keys())

    def _maybe_order_reuse(self, is_bid: bool, price: float, size: int, now: float) -> None:
        direction = self.order_reuse_detector.evaluate_new_resting_order(is_bid, price, size, now)
        if direction is not None:
            self._emit(Signal(
                SignalType.ORDER_REUSE, direction, price, size, now,
                "nouveau niveau passif cohérent avec le reliquat d'un sweep récent "
                "(corrélation par niveau/taille, pas un vrai ID MBO -- inférence, pas certitude)",
            ))

    def on_trade(self, tick: dict) -> None:
        if tick.get("symbol") != self.symbol:
            return
        now = tick["time"] * 1000
        side = _side_to_direction(tick["side"])
        price, size = tick["price"], tick["size"]

        price_ticks = self.book.price_to_ticks(price)
        is_inside = self._is_at_inside_market(price_ticks, side)

        print_ = TapePrint(price, size, side, now, is_inside)
        self.tape.add(print_)
        self.book.record_traded_volume(price_ticks, size)
        if is_inside:
            self.book.record_inside_print(price_ticks, side is Direction.BUY, size)

        if self.oos_detector.is_out_of_spread(self.book, price, side, self.tick_size):
            self.oos_tape.add(print_)

        self._run_detectors(now, price_ticks, side, size)

    def _is_at_inside_market(self, price_ticks: int, side: Direction) -> bool:
        best_bid, best_ask = self.book.best_bid_ticks(), self.book.best_ask_ticks()
        if best_bid is None or best_ask is None:
            return True
        return price_ticks == best_bid if side is Direction.SELL else price_ticks == best_ask

    # -- coeur de la détection (portage de EsOrderFlowAddon.runDetectors) -----------
    def _run_detectors(self, now: float, price_ticks: int, side: Direction, size: int) -> None:
        wall = self.imbalance_detector.find_stacked_wall(self.book)
        if wall is not None:
            level_ticks = wall.top_ticks if wall.direction is Direction.BUY else wall.bottom_ticks
            self._emit(Signal(
                SignalType.IMBALANCE_WALL, wall.direction, self.book.ticks_to_price(level_ticks),
                0, now, f"{wall.level_count} niveaux empilés",
            ))

        if self.absorption_detector.is_absorbing(self.book, price_ticks):
            classification = self.absorption_detector.classify(self.book, price_ticks, now)
            texture_label = {
                Texture.BLOCK: "bloc (1 gros acteur probable)",
                Texture.FRAGMENTED: "fragmentée (plusieurs petits acteurs)",
            }.get(classification.texture, "texture indéterminée")
            self._emit(Signal(
                SignalType.ABSORPTION, side, self.book.ticks_to_price(price_ticks),
                self.book.traded_volume_at(price_ticks), now,
                f"volume tradé >> taille affichée max -- {texture_label} "
                f"({classification.refill_count} refills, moy. {classification.avg_refill_size:.1f})",
            ))

        inside_direction = self.inside_print_detector.evaluate(self.book, price_ticks)
        if inside_direction is not None:
            reading = self.inside_print_detector.read_level(self.book, price_ticks)
            self._emit(Signal(
                SignalType.INSIDE_PRINT, inside_direction, self.book.ticks_to_price(price_ticks),
                max(reading.buy_volume, reading.sell_volume), now,
                f"inside buy={reading.buy_volume}({reading.buy_count} prints) "
                f"sell={reading.sell_volume}({reading.sell_count} prints)",
            ))

        sweep = self.sweep_detector.evaluate(self.tape, now)
        if sweep is not None:
            self._emit(Signal(SignalType.SWEEP, sweep.direction, sweep.end_price, sweep.total_volume, now,
                               f"{sweep.distinct_levels} niveaux traversés"))

            continuation = self.sweep_defense_detector.check_continuation(sweep.direction, sweep.end_price, now)
            if continuation is not None:
                self._emit(Signal(
                    SignalType.SWEEP_DEFENSE, sweep.direction, sweep.end_price, sweep.total_volume, now,
                    "continuation -- second sweep dans la même direction sans défense opposée entre-temps",
                ))
            self.sweep_defense_detector.register_sweep(sweep.direction, sweep.end_price, now)
            self.order_reuse_detector.register_sweep(sweep.direction, sweep.end_price, now)

        cascade = self.cascade_detector.evaluate(self.tape, now)
        if cascade is not None:
            self._emit(Signal(SignalType.STOP_CASCADE, cascade.direction, self.book.ticks_to_price(price_ticks),
                               cascade.total_volume, now, f"{cascade.small_prints_count} petits prints"))

        oos = self.oos_detector.evaluate_burst(self.oos_tape, now, self.CASCADE_SMALL_ORDER_MAX_SIZE)
        if oos is not None:
            self._emit(Signal(SignalType.OUT_OF_SPREAD, oos.direction, self.book.ticks_to_price(price_ticks),
                               oos.total_volume, now, "block" if oos.is_block else "fragmenté"))

        # Zone défendue : approximation avant/après identique à la version Java
        # (currentSize = taille du côté attaqué APRÈS le print courant).
        current_size = self.book.ask_size_at(price_ticks) if side is Direction.BUY else self.book.bid_size_at(price_ticks)
        defender_side = self.defended_zone_detector.register_attack_and_check(
            price_ticks, current_size + size, current_size, side)
        if defender_side is not None:
            price = self.book.ticks_to_price(price_ticks)
            self._emit(Signal(SignalType.DEFENDED_ZONE, defender_side, price, current_size, now,
                               "niveau défendu à plusieurs reprises"))

            outcome = self.sweep_defense_detector.check_defense(defender_side, price, now)
            if outcome is not None:
                self._emit(Signal(
                    SignalType.SWEEP_DEFENSE, defender_side, price, current_size, now,
                    "reversal-context -- sweep récent stoppé par une défense opposée",
                ))

        confluence = self.confluence_scorer.evaluate_around_last_signal()
        if confluence is not None:
            types_label = ", ".join(t.value for t in confluence.agreeing_types)
            self._emit(Signal(
                SignalType.CONFLUENCE, confluence.direction, confluence.center_price, 0, now,
                f"{confluence.score * 100:.0f}% -- types d'accord: {{{types_label}}}",
            ))

    # -- émission (portage de EsOrderFlowAddon.emit) --------------------------------
    def _emit(self, signal: Signal) -> None:
        self.bus.publish(EVT_ORDERFLOW_SIGNAL, {"symbol": self.symbol, "signal": signal})
        self.bus.publish(EventBus.EVT_LOG, {"level": "INFO", "msg": f"[OrderFlow][{self.symbol}] {signal}"})
        if signal.type in _ALERT_WORTHY_TYPES:
            self.bus.publish(EventBus.EVT_ALERT, {"message": f"[{self.symbol}] {signal}"})

        if signal.type in BASE_SIGNAL_TYPES:
            self.confluence_scorer.register(signal)

        if self.peer_alias.strip():
            CrossInstrumentRegistry.publish(self.symbol, signal)
            if signal.type is SignalType.SWEEP and CrossInstrumentRegistry.has_matching_peer_signal(
                self.peer_alias, SignalType.SWEEP, signal.direction, signal.timestamp_ms, self.CROSS_CONFIRM_WINDOW_MS
            ):
                cross = Signal(
                    SignalType.CROSS_CONFIRMED, signal.direction, signal.price, signal.size, signal.timestamp_ms,
                    f"sweep confirmé par {self.peer_alias} dans la même direction",
                )
                self.bus.publish(EVT_ORDERFLOW_SIGNAL, {"symbol": self.symbol, "signal": cross})
                self.bus.publish(EventBus.EVT_ALERT, {"message": f"[{self.symbol}] {cross}"})
                self._maybe_execute_signal(cross)

        self._maybe_execute_signal(signal)

    # -- exécution (portage de TradingEngine) ---------------------------------------
    def _maybe_execute_signal(self, signal: Signal) -> None:
        if not self.auto_trading_enabled or not self.order_engine:
            return
        self.send_market_order(signal.direction is Direction.BUY)

    def send_market_order(self, is_buy: bool) -> None:
        if not self.order_engine:
            return
        side = OrderSide.BUY if is_buy else OrderSide.SELL
        self.order_engine.submit(Order(symbol=self.symbol, side=side, order_type=OrderType.MARKET, quantity=self.order_quantity))
        self.bus.publish(EventBus.EVT_LOG, {
            "level": "INFO",
            "msg": f"[OrderFlow][{self.symbol}] Ordre {'ACHAT' if is_buy else 'VENTE'} qty={self.order_quantity} envoyé.",
        })


class Plugin(PluginBase):
    """Point d'entrée du plugin pour PluginEngine/AddonManagerWidget."""

    name = "Order Flow Suite"

    def on_load(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QDockWidget
        from Plugins.OrderFlowSuite.widget import OrderFlowWidget

        settings = getattr(self.main_window, "settings", None)
        order_engine = getattr(self.main_window, "order_engine", None)
        symbol = settings.get("default_symbol", "ESU6") if settings else "ESU6"
        tick_size = settings.get("dom_tick_size", 0.25) if settings else 0.25

        self.engine = OrderFlowEngine(self.bus, order_engine, symbol=symbol, tick_size=tick_size)
        self.bus.subscribe(EventBus.EVT_DEPTH, self.engine.on_depth)
        self.bus.subscribe(EventBus.EVT_TRADE_PRINT, self.engine.on_trade)

        self._dock = QDockWidget("Order Flow", self.main_window)
        self._dock.setObjectName("Order Flow")
        self._dock.setWidget(OrderFlowWidget(self.bus, self.engine, settings=settings))
        self.main_window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dock)

        self.bus.publish(EventBus.EVT_LOG, {
            "level": "INFO",
            "msg": f"Plugin 'Order Flow Suite' chargé sur {symbol} (tick={tick_size}).",
        })

    def on_unload(self) -> None:
        self.bus.unsubscribe(EventBus.EVT_DEPTH, self.engine.on_depth)
        self.bus.unsubscribe(EventBus.EVT_TRADE_PRINT, self.engine.on_trade)
        if hasattr(self, "_dock"):
            self.main_window.removeDockWidget(self._dock)
            self._dock.deleteLater()
