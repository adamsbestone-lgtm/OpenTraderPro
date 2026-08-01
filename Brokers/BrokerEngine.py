"""
BrokerEngine.py - gère la connexion à plusieurs brokers simultanément et
route les ordres vers le broker actif (ou celui spécifié par l'ordre).
C'est l'unique point que voit OrderEngine (send_order/cancel_order/...) ;
BrokerEngine délègue ensuite au bon connecteur (BaseBroker).
"""
from __future__ import annotations
from typing import Callable, Dict, Optional

from Core.EventBus import EventBus
from Brokers.BaseBroker import BaseBroker
from Brokers.SimBroker import SimBroker
from Brokers.TradovateBroker import TradovateBroker
from Brokers.FuturesBrokers import RithmicBroker, CQGBroker, InteractiveBrokersBroker
from Brokers.CryptoBrokers import BinanceBroker, BybitBroker, BitgetBroker, KrakenBroker, CoinbaseBroker

AVAILABLE_BROKERS: Dict[str, type[BaseBroker]] = {
    "Simulation": SimBroker,
    "Tradovate": TradovateBroker,
    "Rithmic": RithmicBroker,
    "CQG": CQGBroker,
    "InteractiveBrokers": InteractiveBrokersBroker,
    "Binance": BinanceBroker,
    "Bybit": BybitBroker,
    "Bitget": BitgetBroker,
    "Kraken": KrakenBroker,
    "Coinbase": CoinbaseBroker,
}


class BrokerEngine:
    def __init__(self, bus: EventBus, default_broker: str = "Simulation") -> None:
        self.bus = bus
        self.brokers: Dict[str, BaseBroker] = {}
        self.active_broker_name = default_broker
        self._on_fill: Optional[Callable] = None
        self._on_ack: Optional[Callable] = None
        self._on_reject: Optional[Callable] = None
        self.load_broker(default_broker)

    def load_broker(self, name: str) -> BaseBroker:
        if name not in self.brokers:
            broker_cls = AVAILABLE_BROKERS.get(name)
            if not broker_cls:
                raise ValueError(f"Broker inconnu : {name}")
            broker = broker_cls(self.bus)
            if self._on_fill:
                broker.set_fill_callback(self._on_fill)
            if self._on_ack:
                broker.set_ack_callback(self._on_ack)
            if self._on_reject:
                broker.set_reject_callback(self._on_reject)
            self.brokers[name] = broker
        return self.brokers[name]

    def set_active(self, name: str) -> None:
        self.load_broker(name)
        self.active_broker_name = name

    @property
    def active(self) -> BaseBroker:
        return self.brokers[self.active_broker_name]

    def connect(self, name: Optional[str] = None, **credentials) -> bool:
        broker = self.load_broker(name) if name else self.active
        return broker.connect(**credentials)

    # -- callbacks partagés par tous les brokers chargés (propagés à OrderEngine) --
    def set_fill_callback(self, cb: Callable[[int, int, float], None]) -> None:
        self._on_fill = cb
        for broker in self.brokers.values():
            broker.set_fill_callback(cb)

    def set_ack_callback(self, cb: Callable[[int], None]) -> None:
        self._on_ack = cb
        for broker in self.brokers.values():
            broker.set_ack_callback(cb)

    def set_reject_callback(self, cb: Callable[[int, str], None]) -> None:
        self._on_reject = cb
        for broker in self.brokers.values():
            broker.set_reject_callback(cb)

    # -- délégation vers le broker actif (ou celui rattaché au compte de l'ordre) --
    def send_order(self, order) -> None:
        self.active.send_order(order)

    def cancel_order(self, order_id: int) -> None:
        self.active.cancel_order(order_id)

    def modify_order(self, order_id: int, new_price: float) -> None:
        self.active.modify_order(order_id, new_price)

    def fetch_accounts(self) -> dict:
        return self.active.fetch_accounts()

    def fetch_positions(self) -> dict:
        return self.active.fetch_positions()
