"""
TradovateBroker.py - connecteur réel pour Tradovate (futures).

Documentation officielle : https://api.tradovate.com/
- Auth REST     : POST {base}/auth/accesstokenrequest
- Comptes       : GET  {base}/account/list
- Positions     : GET  {base}/position/list
- Ordres        : POST {base}/order/placeorder, /order/cancelorder
- Données (DOM) : WebSocket wss://md.tradovateapi.com/v1/websocket (protocole
  "wall of text" Tradovate : préfixe 'o'/'h'/'a'/'c' + JSON, heartbeat requis)

Nécessite un compte Tradovate (demo gratuite ou live) + une "App" créée
sur https://trader.tradovate.com (onglet API) pour obtenir app_id/cid/sec.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional

import requests

from Brokers.BaseBroker import BaseBroker
from Core.EventBus import EventBus
from Engines.MarketEngine import DepthLevel, DepthSnapshot
from Engines.OrderEngine import Order, OrderSide, OrderStatus, OrderType

try:
    import websocket  # websocket-client
    _HAS_WEBSOCKET = True
except ImportError:  # pragma: no cover - dégradation gracieuse
    _HAS_WEBSOCKET = False

_ORDER_TYPE_MAP = {
    OrderType.MARKET: "Market",
    OrderType.LIMIT: "Limit",
    OrderType.STOP: "Stop",
    OrderType.STOP_LIMIT: "StopLimit",
}


class TradovateBroker(BaseBroker):
    name = "Tradovate"
    required_credentials = ("username", "password", "app_id", "cid", "sec")
    has_environment = True

    REST_DEMO = "https://demo.tradovateapi.com/v1"
    REST_LIVE = "https://live.tradovateapi.com/v1"
    MD_WS_DEMO = "wss://md-demo.tradovateapi.com/v1/websocket"
    MD_WS_LIVE = "wss://md.tradovateapi.com/v1/websocket"

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        self._access_token: Optional[str] = None
        self._md_access_token: Optional[str] = None
        self._rest_base: str = self.REST_DEMO
        self._md_ws_url: str = self.MD_WS_DEMO
        self._account_id: Optional[int] = None
        self._account_spec: Optional[str] = None
        self._session = requests.Session()
        self._ws_app = None
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_running = False
        self._subscribed_symbols: set[str] = set()
        self._order_id_map: Dict[int, int] = {}  # id interne -> id Tradovate

    # -- connexion ----------------------------------------------------------------
    def connect(self, **credentials) -> bool:
        missing = [k for k in self.required_credentials if not credentials.get(k)]
        if missing:
            self._log_error(f"Identifiants manquants : {', '.join(missing)}")
            return False

        environment = credentials.get("environment", "demo")
        self._rest_base = self.REST_LIVE if environment == "live" else self.REST_DEMO
        self._md_ws_url = self.MD_WS_LIVE if environment == "live" else self.MD_WS_DEMO

        payload = {
            "name": credentials["username"],
            "password": credentials["password"],
            "appId": credentials["app_id"],
            "appVersion": "1.0",
            "cid": credentials["cid"],
            "sec": credentials["sec"],
        }
        try:
            resp = self._session.post(
                f"{self._rest_base}/auth/accesstokenrequest", json=payload, timeout=10
            )
        except requests.RequestException as exc:
            self._log_error(f"Échec réseau lors de l'authentification Tradovate : {exc}")
            return False

        if resp.status_code != 200:
            self._log_error(f"Authentification Tradovate refusée (HTTP {resp.status_code}) : {resp.text[:300]}")
            return False

        data = resp.json()
        if "errorText" in data and data.get("errorText"):
            self._log_error(f"Authentification Tradovate refusée : {data['errorText']}")
            return False

        self._access_token = data.get("accessToken")
        self._md_access_token = data.get("mdAccessToken")
        if not self._access_token:
            self._log_error("Réponse d'authentification Tradovate inattendue (pas de accessToken).")
            return False

        self._session.headers.update({"Authorization": f"Bearer {self._access_token}"})

        # Récupère le compte par défaut (le premier compte actif de l'utilisateur)
        try:
            accounts_resp = self._session.get(f"{self._rest_base}/account/list", timeout=10)
            accounts_resp.raise_for_status()
            accounts = accounts_resp.json()
            if accounts:
                self._account_id = accounts[0]["id"]
                self._account_spec = accounts[0].get("name")
        except requests.RequestException as exc:
            self._log_error(f"Connecté, mais impossible de récupérer les comptes : {exc}")

        self.connected = True
        self.bus.publish(EventBus.EVT_BROKER_CONNECTED, {"broker": self.name})
        self.bus.publish(EventBus.EVT_LOG, {
            "level": "INFO",
            "msg": f"Tradovate connecté ({environment}) — compte {self._account_spec or self._account_id}",
        })

        if _HAS_WEBSOCKET and self._md_access_token:
            self._start_market_data_socket()
        elif not _HAS_WEBSOCKET:
            self._log_error(
                "Paquet 'websocket-client' manquant : le flux DOM temps réel Tradovate "
                "ne sera pas disponible (pip install websocket-client). Comptes/positions/ordres restent fonctionnels."
            )

        return True

    def disconnect(self) -> None:
        self.connected = False
        self._ws_running = False
        if self._ws_app:
            try:
                self._ws_app.close()
            except Exception:
                pass
        self.bus.publish(EventBus.EVT_BROKER_DISCONNECTED, {"broker": self.name})

    # -- données de marché (DOM) via WebSocket ------------------------------------------
    def _start_market_data_socket(self) -> None:
        self._ws_running = True

        def on_open(ws):
            ws.send(f"authorize\n0\n\n{self._md_access_token}")

        def on_message(ws, message: str):
            self._handle_ws_frame(message)

        def on_error(ws, error):
            self._log_error(f"Erreur WebSocket Tradovate (données de marché) : {error}")

        def on_close(ws, *_args):
            if self._ws_running:
                self._log_error("Connexion WebSocket Tradovate (données de marché) interrompue.")

        self._ws_app = websocket.WebSocketApp(
            self._md_ws_url,
            on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close,
        )
        self._ws_thread = threading.Thread(
            target=self._ws_app.run_forever, daemon=True, name="TradovateMD",
            kwargs={"ping_interval": 10},
        )
        self._ws_thread.start()

    def _handle_ws_frame(self, message: str) -> None:
        # Protocole Tradovate : premier caractère = type de trame.
        if not message:
            return
        frame_type, _, rest = message[0], None, message[1:]
        if frame_type == "o":
            return  # ouverture du socket
        if frame_type == "h":
            return  # heartbeat, rien à faire (le client répond automatiquement au niveau TCP)
        if frame_type == "c":
            self._ws_running = False
            return
        if frame_type != "a":
            return
        try:
            events = json.loads(rest) if rest else []
        except (json.JSONDecodeError, TypeError):
            return
        for event in events:
            self._handle_md_event(event)

    def _handle_md_event(self, event: Dict[str, Any]) -> None:
        e_type = event.get("e")
        if e_type == "md":
            data = event.get("d", {})
            for dom_entry in data.get("doms", []):
                self._publish_depth(dom_entry)
        elif e_type == "props" and event.get("d", {}).get("entityType") == "order":
            self._handle_order_event(event["d"])

    def _publish_depth(self, dom_entry: Dict[str, Any]) -> None:
        symbol = dom_entry.get("contractId") and self._symbol_for_contract(dom_entry["contractId"])
        if not symbol:
            return
        snap = DepthSnapshot(symbol=symbol)
        for level in dom_entry.get("bids", []):
            snap.bids.append(DepthLevel(price=level.get("price", 0.0), size=level.get("size", 0)))
        for level in dom_entry.get("offers", []):
            snap.asks.append(DepthLevel(price=level.get("price", 0.0), size=level.get("size", 0)))
        self.bus.publish(EventBus.EVT_DEPTH, snap)

    def _symbol_for_contract(self, contract_id: int) -> Optional[str]:
        return self._subscribed_symbols_by_id.get(contract_id) if hasattr(self, "_subscribed_symbols_by_id") else None

    def subscribe_market_data(self, symbol: str) -> None:
        self._subscribed_symbols.add(symbol)
        if not hasattr(self, "_subscribed_symbols_by_id"):
            self._subscribed_symbols_by_id: Dict[int, str] = {}
        if not self._ws_app:
            return
        try:
            contract_resp = self._session.get(
                f"{self._rest_base}/contract/find", params={"name": symbol}, timeout=10
            )
            contract_resp.raise_for_status()
            contract = contract_resp.json()
            contract_id = contract.get("id")
            if contract_id:
                self._subscribed_symbols_by_id[contract_id] = symbol
                self._ws_app.send(f"md/subscribeDOM\n1\n\n{json.dumps({'symbol': symbol})}")
        except requests.RequestException as exc:
            self._log_error(f"Impossible de s'abonner au DOM Tradovate pour {symbol} : {exc}")

    def unsubscribe_market_data(self, symbol: str) -> None:
        self._subscribed_symbols.discard(symbol)

    # -- ordres ------------------------------------------------------------------
    def send_order(self, order: Order) -> None:
        if not self.connected or not self._account_id:
            if self._on_reject:
                self._on_reject(order.id, "Tradovate non connecté ou compte introuvable")
            return
        body = {
            "accountId": self._account_id,
            "accountSpec": self._account_spec,
            "action": "Buy" if order.side == OrderSide.BUY else "Sell",
            "symbol": order.symbol,
            "orderQty": order.quantity,
            "orderType": _ORDER_TYPE_MAP.get(order.order_type, "Market"),
        }
        if order.price is not None:
            body["price"] = order.price
        if order.stop_price is not None:
            body["stopPrice"] = order.stop_price
        try:
            resp = self._session.post(f"{self._rest_base}/order/placeorder", json=body, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            if self._on_reject:
                self._on_reject(order.id, f"Erreur réseau : {exc}")
            return
        if data.get("failureReason"):
            if self._on_reject:
                self._on_reject(order.id, data["failureReason"])
            return
        tradovate_order_id = data.get("orderId")
        if tradovate_order_id:
            self._order_id_map[order.id] = tradovate_order_id
        if self._on_ack:
            self._on_ack(order.id)

    def cancel_order(self, order_id: int) -> None:
        tradovate_id = self._order_id_map.get(order_id)
        if not tradovate_id:
            return
        try:
            self._session.post(
                f"{self._rest_base}/order/cancelorder", json={"orderId": tradovate_id}, timeout=10
            )
        except requests.RequestException as exc:
            self._log_error(f"Échec d'annulation de l'ordre {order_id} : {exc}")

    def modify_order(self, order_id: int, new_price: float) -> None:
        tradovate_id = self._order_id_map.get(order_id)
        if not tradovate_id:
            return
        try:
            self._session.post(
                f"{self._rest_base}/order/modifyorder",
                json={"orderId": tradovate_id, "price": new_price},
                timeout=10,
            )
        except requests.RequestException as exc:
            self._log_error(f"Échec de modification de l'ordre {order_id} : {exc}")

    def _handle_order_event(self, event_data: Dict[str, Any]) -> None:
        # Traduction simplifiée des statuts Tradovate -> callbacks OrderEngine.
        entity = event_data.get("entity", {})
        ordinal_status = entity.get("ordStatus")
        internal_id = next((k for k, v in self._order_id_map.items() if v == entity.get("id")), None)
        if internal_id is None:
            return
        if ordinal_status == "Filled" and self._on_fill:
            self._on_fill(internal_id, entity.get("filledQty", 0), entity.get("avgPrice", 0.0))
        elif ordinal_status == "Rejected" and self._on_reject:
            self._on_reject(internal_id, entity.get("rejectReason", "Rejeté par Tradovate"))

    # -- comptes / positions --------------------------------------------------------
    def fetch_accounts(self) -> Dict[str, Any]:
        if not self.connected:
            return {}
        try:
            resp = self._session.get(f"{self._rest_base}/account/list", timeout=10)
            resp.raise_for_status()
            cash_resp = self._session.get(f"{self._rest_base}/cashBalance/list", timeout=10)
            cash_resp.raise_for_status()
            return {"accounts": resp.json(), "balances": cash_resp.json()}
        except requests.RequestException as exc:
            self._log_error(f"Échec de récupération des comptes Tradovate : {exc}")
            return {}

    def fetch_positions(self) -> Dict[str, Any]:
        if not self.connected:
            return {}
        try:
            resp = self._session.get(f"{self._rest_base}/position/list", timeout=10)
            resp.raise_for_status()
            return {"positions": resp.json()}
        except requests.RequestException as exc:
            self._log_error(f"Échec de récupération des positions Tradovate : {exc}")
            return {}

    # -- utilitaires --------------------------------------------------------------
    def _log_error(self, message: str) -> None:
        self.bus.publish(EventBus.EVT_LOG, {"level": "ERROR", "msg": f"[Tradovate] {message}"})
