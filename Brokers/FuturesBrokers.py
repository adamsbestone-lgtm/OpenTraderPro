"""
FuturesBrokers.py - squelettes des connecteurs futures.
Chacun hérite de StubBroker et déclare simplement les identifiants requis.
Implémentation réelle à faire via le SDK officiel de chaque fournisseur :
- Tradovate : API REST + WebSocket (https://api.tradovate.com)
- Rithmic   : R | API (protocole propriétaire, SDK C++/Python fourni par Rithmic)
- CQG       : CQG WebAPI / FIX
- Interactive Brokers : TWS API / IB Gateway (ibapi ou ib_insync)
"""
from Brokers.StubBroker import StubBroker


class TradovateBroker(StubBroker):
    name = "Tradovate"
    required_credentials = ("username", "password", "app_id", "app_secret", "cid", "sec")


class RithmicBroker(StubBroker):
    name = "Rithmic"
    required_credentials = ("username", "password", "system_name", "gateway")


class CQGBroker(StubBroker):
    name = "CQG"
    required_credentials = ("client_id", "client_secret", "username", "password")


class InteractiveBrokersBroker(StubBroker):
    name = "InteractiveBrokers"
    required_credentials = ("host", "port", "client_id")
