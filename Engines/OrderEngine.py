"""
OrderEngine.py - création, suivi, modification et annulation des ordres.
Types : Market, Limit, Stop, StopLimit, MIT, OCO, Bracket, TrailingStop.
Journalise chaque changement d'état dans Database (orders_history).
"""
from __future__ import annotations
import itertools
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional

from Core.EventBus import EventBus
from Core.Database import Database


class OrderType(Enum):
    MARKET = auto()
    LIMIT = auto()
    STOP = auto()
    STOP_LIMIT = auto()
    MIT = auto()             # Market-If-Touched
    OCO = auto()
    BRACKET = auto()
    TRAILING_STOP = auto()


class OrderSide(Enum):
    BUY = auto()
    SELL = auto()


class OrderStatus(Enum):
    PENDING = auto()
    WORKING = auto()
    FILLED = auto()
    PARTIALLY_FILLED = auto()
    CANCELED = auto()
    REJECTED = auto()


_id_counter = itertools.count(1)


@dataclass
class Order:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: Optional[float] = None
    stop_price: Optional[float] = None
    trail_offset: Optional[float] = None
    linked_ids: List[int] = field(default_factory=list)
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    account: str = "SIM"
    id: int = field(default_factory=lambda: next(_id_counter))
    # horodatage haute résolution (perf_counter, pas persisté/sérialisé) pour
    # mesurer la latence interne submit -> fill, cf. Engines/LatencyMonitor.py
    created_perf: float = field(default_factory=time.perf_counter, compare=False)


class OrderEngine:
    def __init__(self, bus: EventBus, broker_engine, db: Optional[Database] = None,
                 risk_engine=None) -> None:
        self.bus = bus
        self.broker_engine = broker_engine
        self.db = db
        self.risk_engine = risk_engine
        self.orders: Dict[int, Order] = {}

        broker_engine.set_fill_callback(self._on_broker_fill)
        broker_engine.set_ack_callback(self._on_broker_ack)
        broker_engine.set_reject_callback(self._on_broker_reject)

    # -- API publique -----------------------------------------------------------
    def submit(self, order: Order) -> Order:
        if self.risk_engine and not self.risk_engine.allow_order(order):
            order.status = OrderStatus.REJECTED
            self.bus.publish(EventBus.EVT_ORDER_REJECTED, {"order": order, "reason": "risk_engine"})
            return order

        self.orders[order.id] = order
        self.bus.publish(EventBus.EVT_ORDER_NEW, order)
        self._log_history(order)
        self.broker_engine.send_order(order)
        return order

    def submit_bracket(self, symbol: str, side: OrderSide, quantity: int,
                        entry_price: Optional[float], stop_loss: float, take_profit: float,
                        entry_type: OrderType = OrderType.LIMIT) -> Order:
        entry = Order(symbol=symbol, side=side, order_type=entry_type, quantity=quantity, price=entry_price)
        opposite = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY
        stop = Order(symbol=symbol, side=opposite, order_type=OrderType.STOP, quantity=quantity, stop_price=stop_loss)
        target = Order(symbol=symbol, side=opposite, order_type=OrderType.LIMIT, quantity=quantity, price=take_profit)
        entry.linked_ids = [stop.id, target.id]
        stop.linked_ids = [target.id]
        target.linked_ids = [stop.id]
        self.orders[stop.id] = stop
        self.orders[target.id] = target
        self.submit(entry)
        return entry

    def cancel(self, order_id: int) -> None:
        order = self.orders.get(order_id)
        if not order or order.status in (OrderStatus.FILLED, OrderStatus.CANCELED):
            return
        self.broker_engine.cancel_order(order_id)

    def cancel_all(self, symbol: Optional[str] = None) -> None:
        for order in list(self.orders.values()):
            if order.status == OrderStatus.WORKING and (symbol is None or order.symbol == symbol):
                self.cancel(order.id)

    def modify_price(self, order_id: int, new_price: float) -> None:
        order = self.orders.get(order_id)
        if order and order.status == OrderStatus.WORKING:
            self.broker_engine.modify_order(order_id, new_price)

    def open_orders_count(self, symbol: Optional[str] = None) -> int:
        return sum(1 for o in self.orders.values()
                    if o.status in (OrderStatus.WORKING, OrderStatus.PENDING)
                    and (symbol is None or o.symbol == symbol))

    # -- callbacks broker ---------------------------------------------------------
    def _on_broker_ack(self, order_id: int) -> None:
        order = self.orders.get(order_id)
        if order:
            order.status = OrderStatus.WORKING
            self.bus.publish(EventBus.EVT_ORDER_UPDATE, order)
            self._log_history(order)

    def _on_broker_fill(self, order_id: int, fill_qty: int, fill_price: float) -> None:
        order = self.orders.get(order_id)
        if not order:
            return
        total_qty = order.filled_qty + fill_qty
        order.avg_fill_price = (order.avg_fill_price * order.filled_qty + fill_price * fill_qty) / total_qty
        order.filled_qty = total_qty
        order.status = OrderStatus.FILLED if total_qty >= order.quantity else OrderStatus.PARTIALLY_FILLED

        if order.status == OrderStatus.FILLED:
            self.bus.publish(EventBus.EVT_ORDER_FILLED, order)
            for linked_id in order.linked_ids:
                linked = self.orders.get(linked_id)
                if linked and linked.status == OrderStatus.PENDING:
                    self.submit(linked)
        else:
            self.bus.publish(EventBus.EVT_ORDER_UPDATE, order)
        self._log_history(order)

    def _on_broker_reject(self, order_id: int, reason: str) -> None:
        order = self.orders.get(order_id)
        if order:
            order.status = OrderStatus.REJECTED
            self.bus.publish(EventBus.EVT_ORDER_REJECTED, {"order": order, "reason": reason})
            self._log_history(order)

    def _log_history(self, order: Order) -> None:
        if self.db:
            self.db.record_order_event(order.id, order.symbol, order.side.name, order.order_type.name,
                                        order.quantity, order.price, order.status.name, time.time())
