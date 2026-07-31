"""
PositionEngine.py - suivi des positions : ouverture, fermeture, reverse,
scale in / scale out, P&L latent et réalisé.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional

from Core.EventBus import EventBus
from Engines.OrderEngine import Order, OrderSide, OrderType


@dataclass
class Position:
    symbol: str
    quantity: int = 0
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    last_price: float = 0.0


class PositionEngine:
    def __init__(self, bus: EventBus, point_value: float = 50.0) -> None:
        self.bus = bus
        self.point_value = point_value
        self.positions: Dict[str, Position] = {}
        self.bus.subscribe(EventBus.EVT_ORDER_FILLED, self._on_fill)
        self.bus.subscribe(EventBus.EVT_DEPTH, self._on_depth)

    def get(self, symbol: str) -> Position:
        return self.positions.setdefault(symbol, Position(symbol=symbol))

    def _on_fill(self, order: Order) -> None:
        pos = self.get(order.symbol)
        signed_qty = order.filled_qty if order.side == OrderSide.BUY else -order.filled_qty

        if pos.quantity == 0 or (pos.quantity > 0) == (signed_qty > 0):
            new_qty = pos.quantity + signed_qty  # ouverture ou scale-in (renforcement)
            if new_qty != 0:
                pos.avg_price = (pos.avg_price * pos.quantity + order.avg_fill_price * signed_qty) / new_qty
            pos.quantity = new_qty
        else:
            closing_qty = min(abs(signed_qty), abs(pos.quantity))  # scale-out / fermeture / reverse
            direction = 1 if pos.quantity > 0 else -1
            pos.realized_pnl += direction * (order.avg_fill_price - pos.avg_price) * closing_qty * self.point_value
            pos.quantity += signed_qty
            if pos.quantity != 0 and (pos.quantity > 0) != (direction > 0):
                pos.avg_price = order.avg_fill_price

        self.bus.publish(EventBus.EVT_POSITION_UPDATE, pos)

    def _on_depth(self, snapshot) -> None:
        pos = self.positions.get(snapshot.symbol)
        if not pos or pos.quantity == 0:
            return
        pos.last_price = snapshot.last_price or pos.last_price
        pos.unrealized_pnl = (pos.last_price - pos.avg_price) * pos.quantity * self.point_value
        self.bus.publish(EventBus.EVT_POSITION_UPDATE, pos)

    # -- actions rapides -----------------------------------------------------------
    def flatten(self, order_engine, symbol: str) -> Optional[Order]:
        pos = self.positions.get(symbol)
        if not pos or pos.quantity == 0:
            return None
        side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
        return order_engine.submit(Order(symbol=symbol, side=side, order_type=OrderType.MARKET, quantity=abs(pos.quantity)))

    def reverse(self, order_engine, symbol: str) -> Optional[Order]:
        pos = self.positions.get(symbol)
        if not pos or pos.quantity == 0:
            return None
        side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
        return order_engine.submit(Order(symbol=symbol, side=side, order_type=OrderType.MARKET, quantity=abs(pos.quantity) * 2))

    def scale_in(self, order_engine, symbol: str, quantity: int) -> Optional[Order]:
        pos = self.positions.get(symbol)
        if not pos or pos.quantity == 0:
            return None
        side = OrderSide.BUY if pos.quantity > 0 else OrderSide.SELL
        return order_engine.submit(Order(symbol=symbol, side=side, order_type=OrderType.MARKET, quantity=quantity))

    def scale_out(self, order_engine, symbol: str, quantity: int) -> Optional[Order]:
        pos = self.positions.get(symbol)
        if not pos or pos.quantity == 0:
            return None
        quantity = min(quantity, abs(pos.quantity))
        side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
        return order_engine.submit(Order(symbol=symbol, side=side, order_type=OrderType.MARKET, quantity=quantity))
