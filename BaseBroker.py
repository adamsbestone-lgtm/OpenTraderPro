"""
BaseBroker.py - interface commune à tous les connecteurs de courtier.

Chaque connecteur (Tradovate, Rithmic, CQG, InteractiveBrokers, Binance,
Bybit, Bitget, Kraken, Coinbase, Simulation...) DOIT implémenter ces
méthodes. Le reste du logiciel (OrderEngine, MarketEngine) ne dépend
jamais d'un broker particulier, uniquement de cette interface.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional


class BaseBroker(ABC):
    name: str = "BaseBroker"
    required_credentials: tuple = ()
    has_environment: bool = False  # affiche un choix Demo/Live dans la fenêtre de login

    def __init__(self, bus) -> None:
        self.bus = bus
        self.connected = False
        self._on_fill: Optional[Callable] = None
        self._on_ack: Optional[Callable] = None
        self._on_reject: Optional[Callable] = None

    def set_fill_callback(self, cb: Callable[[int, int, float], None]) -> None:
        self._on_fill = cb

    def set_ack_callback(self, cb: Callable[[int], None]) -> None:
        self._on_ack = cb

    def set_reject_callback(self, cb: Callable[[int, str], None]) -> None:
        self._on_reject = cb

    # -- connexion --------------------------------------------------------------
    @abstractmethod
    def connect(self, **credentials) -> bool:
        """Établit la connexion (API REST/WebSocket/FIX/DLL selon le broker)."""

    @abstractmethod
    def disconnect(self) -> None:
        ...

    # -- données de marché --------------------------------------------------------
    @abstractmethod
    def subscribe_market_data(self, symbol: str) -> None:
        """S'abonne au flux tick/DOM d'un symbole ; doit publier sur l'EventBus
        (EVT_DEPTH / EVT_TRADE_PRINT) au fur et à mesure de la réception."""

    @abstractmethod
    def unsubscribe_market_data(self, symbol: str) -> None:
        ...

    # -- ordres ------------------------------------------------------------------
    @abstractmethod
    def send_order(self, order) -> None:
        ...

    @abstractmethod
    def cancel_order(self, order_id: int) -> None:
        ...

    @abstractmethod
    def modify_order(self, order_id: int, new_price: float) -> None:
        ...

    # -- comptes / positions --------------------------------------------------------
    @abstractmethod
    def fetch_accounts(self) -> Dict[str, Any]:
        """Retourne les comptes disponibles (solde, marge, buying power...)."""

    @abstractmethod
    def fetch_positions(self) -> Dict[str, Any]:
        ...
