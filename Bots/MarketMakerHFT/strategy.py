"""
MarketMaker HFT (exemple) - cote en permanence des deux côtés autour du
meilleur bid/ask, avec un spread cible en ticks, et limite son inventaire
(max_inventory). Objectif pédagogique : illustrer un pattern HFT simple
(annulation/replace à chaque mise à jour de profondeur), pas une
stratégie de market making prête pour la production.

⚠️ Le rythme d'annulation/replace peut être très élevé (chaque `on_depth`) :
c'est volontairement représentatif d'un usage HFT, à surveiller via la
fenêtre HFT (débit d'ordres/s, latence).
"""
from Bots.Strategy import BaseStrategy
from Engines.OrderEngine import Order, OrderType, OrderSide


class Strategy(BaseStrategy):
    name = "MarketMakerHFT"

    def on_start(self) -> None:
        self.symbol = self.params.get("symbol", "ESU6")
        self.quantity = self.params.get("quantity", 1)
        self.target_spread = self.params.get("target_spread_ticks", 2) * self.params.get("tick_size", 0.25)
        self.max_inventory = self.params.get("max_inventory", 3)
        self._bid_order_id = None
        self._ask_order_id = None

    def on_depth(self, dom) -> None:
        if not self.order_engine or dom.symbol != self.symbol or not dom.bids or not dom.asks:
            return

        pos = self.position_engine.get(self.symbol) if self.position_engine else None
        inventory = pos.quantity if pos else 0

        mid = (dom.bids[0].price + dom.asks[0].price) / 2
        bid_price = round(mid - self.target_spread / 2, 2)
        ask_price = round(mid + self.target_spread / 2, 2)

        # annule les cotations précédentes avant de replacer (pattern HFT classique)
        if self._bid_order_id:
            self.order_engine.cancel(self._bid_order_id)
        if self._ask_order_id:
            self.order_engine.cancel(self._ask_order_id)

        if inventory < self.max_inventory:
            bid_order = self.order_engine.submit(
                Order(symbol=self.symbol, side=OrderSide.BUY, order_type=OrderType.LIMIT,
                      price=bid_price, quantity=self.quantity))
            self._bid_order_id = bid_order.id

        if inventory > -self.max_inventory:
            ask_order = self.order_engine.submit(
                Order(symbol=self.symbol, side=OrderSide.SELL, order_type=OrderType.LIMIT,
                      price=ask_price, quantity=self.quantity))
            self._ask_order_id = ask_order.id

    def on_stop(self) -> None:
        if self.order_engine:
            if self._bid_order_id:
                self.order_engine.cancel(self._bid_order_id)
            if self._ask_order_id:
                self.order_engine.cancel(self._ask_order_id)
