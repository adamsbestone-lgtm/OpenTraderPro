"""
Scalper - bot d'exemple : détecte une rafale de trades agressifs du même
côté, entre au marché puis pose un bracket (stop + target en ticks).
"""
from Bots.Strategy import BaseStrategy
from Engines.OrderEngine import OrderSide, OrderType


class Strategy(BaseStrategy):
    name = "Scalper"

    def on_start(self) -> None:
        self._buy_streak = 0
        self._sell_streak = 0
        self._cooldown = 0
        self.symbol = self.params.get("symbol", "ESU6")
        self.quantity = self.params.get("quantity", 1)
        self.window = self.params.get("aggressive_window", 5)
        self.target_ticks = self.params.get("target_ticks", 4)
        self.stop_ticks = self.params.get("stop_ticks", 3)
        self.tick_size = self.params.get("tick_size", 0.25)
        self.cooldown_ticks = self.params.get("cooldown_ticks", 20)

    def on_tick(self, tick) -> None:
        if self._cooldown > 0:
            self._cooldown -= 1
            return
        if tick.get("symbol") != self.symbol or not tick.get("aggressive"):
            self._buy_streak = self._sell_streak = 0
            return

        if tick["side"] == "buy":
            self._buy_streak += 1
            self._sell_streak = 0
        else:
            self._sell_streak += 1
            self._buy_streak = 0

        if self._buy_streak >= self.window:
            self._enter(OrderSide.BUY, tick["price"])
        elif self._sell_streak >= self.window:
            self._enter(OrderSide.SELL, tick["price"])

    def _enter(self, side: OrderSide, price: float) -> None:
        if not self.order_engine:
            return
        offset = self.target_ticks * self.tick_size
        stop_offset = self.stop_ticks * self.tick_size
        if side == OrderSide.BUY:
            stop_loss, take_profit = price - stop_offset, price + offset
        else:
            stop_loss, take_profit = price + stop_offset, price - offset

        self.order_engine.submit_bracket(
            symbol=self.symbol, side=side, quantity=self.quantity,
            entry_price=None, stop_loss=stop_loss, take_profit=take_profit,
            entry_type=OrderType.MARKET,
        )
        self._buy_streak = self._sell_streak = 0
        self._cooldown = self.cooldown_ticks

    def on_stop(self) -> None:
        self._buy_streak = self._sell_streak = 0
