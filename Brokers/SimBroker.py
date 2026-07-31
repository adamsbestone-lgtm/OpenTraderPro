"""
SimBroker.py - courtier simulé, pleinement fonctionnel. Remplit les
ordres Market immédiatement au dernier prix connu, et les ordres
Limit/Stop dès que le marché simulé touche leur prix.
"""
from __future__ import annotations
import threading
from typing import Any, Dict

from Brokers.BaseBroker import BaseBroker
from Core.EventBus import EventBus
from Engines.OrderEngine import Order, OrderType, OrderSide


class SimBroker(BaseBroker):
    name = "Simulation"

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        self._last_price: float = 0.0
        self._working_orders: Dict[int, Order] = {}
        self._lock = threading.Lock()
        self._subscribed_symbols: set[str] = set()
        self.bus.subscribe(EventBus.EVT_DEPTH, self._on_depth)

    def connect(self, **credentials) -> bool:
        self.connected = True
        self.bus.publish(EventBus.EVT_BROKER_CONNECTED, {"broker": self.name})
        return True

    def disconnect(self) -> None:
        self.connected = False
        self.bus.publish(EventBus.EVT_BROKER_DISCONNECTED, {"broker": self.name})

    def subscribe_market_data(self, symbol: str) -> None:
        self._subscribed_symbols.add(symbol)  # le MarketEngine simulé pousse déjà les données

    def unsubscribe_market_data(self, symbol: str) -> None:
        self._subscribed_symbols.discard(symbol)

    def send_order(self, order: Order) -> None:
        with self._lock:
            if self._on_ack:
                self._on_ack(order.id)
            if order.order_type == OrderType.MARKET:
                self._fill(order, order.quantity, self._last_price or order.price or 0.0)
            else:
                self._working_orders[order.id] = order
                self._try_fill_working(order)

    def cancel_order(self, order_id: int) -> None:
        with self._lock:
            self._working_orders.pop(order_id, None)
            self.bus.publish(EventBus.EVT_ORDER_CANCELED, order_id)

    def modify_order(self, order_id: int, new_price: float) -> None:
        with self._lock:
            order = self._working_orders.get(order_id)
            if order:
                order.price = new_price
                self.bus.publish(EventBus.EVT_ORDER_UPDATE, order)

    def fetch_accounts(self) -> Dict[str, Any]:
        return {"SIM": {"balance": 25000.0, "margin_used": 0.0, "buying_power": 25000.0}}

    def fetch_positions(self) -> Dict[str, Any]:
        return {}

    # -- simulation interne --------------------------------------------------------
    def _on_depth(self, snapshot) -> None:
        if snapshot.last_price:
            self._last_price = snapshot.last_price
        with self._lock:
            for order in list(self._working_orders.values()):
                self._try_fill_working(order)

    def _try_fill_working(self, order: Order) -> None:
        price = self._last_price
        if not price:
            return
        should_fill = False
        if order.order_type == OrderType.LIMIT:
            should_fill = (order.side == OrderSide.BUY and price <= (order.price or 0)) or \
                          (order.side == OrderSide.SELL and price >= (order.price or 0))
        elif order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT, OrderType.MIT):
            trigger = order.stop_price or order.price or 0
            should_fill = (order.side == OrderSide.BUY and price >= trigger) or \
                          (order.side == OrderSide.SELL and price <= trigger)

        if should_fill:
            self._working_orders.pop(order.id, None)
            self._fill(order, order.quantity - order.filled_qty, order.price or price)

    def _fill(self, order: Order, qty: int, price: float) -> None:
        if qty <= 0:
            return
        if self._on_fill:
            self._on_fill(order.id, qty, price)
