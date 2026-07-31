"""
StubBroker.py - squelette commun aux connecteurs réels (Tradovate, Rithmic,
CQG, Interactive Brokers, Binance, Bybit, Bitget, Kraken, Coinbase).

Ces connecteurs nécessitent des identifiants API réels, des SDK tiers
(souvent sous licence, ou nécessitant un compte chez le fournisseur) et
ne peuvent pas être testés dans cet environnement de développement.
StubBroker fournit la structure exacte attendue par BaseBroker/OrderEngine
afin qu'implémenter un vrai connecteur revienne à remplir les méthodes
marquées TODO, sans toucher au reste du logiciel.

Exemple d'implémentation réelle à faire dans chaque sous-classe :
- connect()               -> authentification API (clé/secret, OAuth, FIX logon...)
- subscribe_market_data() -> ouverture d'un flux WebSocket/FIX pour le DOM
- send_order()            -> traduction Order -> requête API du broker
- fetch_accounts()        -> appel API compte(s) réel(s)
"""
from __future__ import annotations
from typing import Any, Dict

from Brokers.BaseBroker import BaseBroker
from Core.EventBus import EventBus


class StubBroker(BaseBroker):
    """A ne PAS utiliser en production tel quel : lève une erreur explicite
    à la connexion tant que le connecteur réel n'a pas été implémenté."""

    name = "Stub"
    required_credentials: tuple[str, ...] = ()

    def connect(self, **credentials) -> bool:
        missing = [k for k in self.required_credentials if k not in credentials]
        self.bus.publish(EventBus.EVT_LOG, {
            "level": "ERROR",
            "msg": f"Connecteur '{self.name}' non implémenté (squelette StubBroker). "
                   f"Identifiants requis : {', '.join(self.required_credentials) or 'aucun défini'}. "
                   f"{'Manquants : ' + ', '.join(missing) if missing else ''}",
        })
        return False

    def disconnect(self) -> None:
        self.connected = False

    def subscribe_market_data(self, symbol: str) -> None:
        raise NotImplementedError(f"{self.name}.subscribe_market_data() à implémenter (voir SDK/API du broker).")

    def unsubscribe_market_data(self, symbol: str) -> None:
        raise NotImplementedError(f"{self.name}.unsubscribe_market_data() à implémenter.")

    def send_order(self, order) -> None:
        raise NotImplementedError(f"{self.name}.send_order() à implémenter.")

    def cancel_order(self, order_id: int) -> None:
        raise NotImplementedError(f"{self.name}.cancel_order() à implémenter.")

    def modify_order(self, order_id: int, new_price: float) -> None:
        raise NotImplementedError(f"{self.name}.modify_order() à implémenter.")

    def fetch_accounts(self) -> Dict[str, Any]:
        raise NotImplementedError(f"{self.name}.fetch_accounts() à implémenter.")

    def fetch_positions(self) -> Dict[str, Any]:
        raise NotImplementedError(f"{self.name}.fetch_positions() à implémenter.")
