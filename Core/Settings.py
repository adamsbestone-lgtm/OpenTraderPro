"""
Settings.py - configuration applicative. Persistée dans la table
`settings` de la base SQLite (voir Core/Database.py), au format JSON
par clé logique : "colors", "shortcuts", "risk", "brokers", "theme"...
"""
from __future__ import annotations
from typing import Any, Dict

from Core.Database import Database

DEFAULTS: Dict[str, Any] = {
    "default_symbol": "ESU6",
    "dom_tick_size": 0.25,
    "dom_rows": 20,
    "colors": {
        # Palette "Jigsaw daytradr" (bleu/rouge par défaut) : bid en bleu,
        # ask en rouge, agressivité en vert/rouge vif, absorption en violet.
        "bid": "#2f7dfd",
        "ask": "#e53935",
        "last": "#ffffff",
        "iceberg": "#8ab4ff",
        "pulling": "#5f7799",
        "stacking": "#2f7dfd",
        "profit": "#43a047",
        "loss": "#e53935",
        "aggressive_buy": "#00c853",
        "aggressive_sell": "#ff1744",
        "absorption": "#ab47bc",
        "sweep": "#ffb300",
        "block_trade": "#29b6f6",
        "imbalance": "#ffd54f",
        "price_bg": "#132238",
        "pace_calm": "#5f7799",
        "pace_normal": "#2f7dfd",
        "pace_active": "#ffb300",
        "pace_extreme": "#ff1744",
    },
    "icons": {
        # Émoticônes/symboles affichés dans le DOM et le flux Order Flow,
        # dans l'esprit visuel de Jigsaw daytradr (histogrammes + pictos).
        "iceberg": "🧊",
        "pulling": "🔻",
        "stacking": "🔺",
        "sweep": "⚡",
        "absorption": "🛡️",
        "block_trade": "🐋",
        "aggressive_buy": "🟢",
        "aggressive_sell": "🔴",
        "imbalance": "⚖️",
        "cascade": "🌊",
        "confluence": "🎯",
        "alert": "🔔",
        "kill_switch": "🛑",
        # signaux Order Flow (Plugins/OrderFlowSuite), par SignalType.value
        "IMBALANCE_WALL": "⚖️",
        "ABSORPTION": "🛡️",
        "SWEEP": "⚡",
        "STOP_CASCADE": "🌊",
        "OUT_OF_SPREAD": "↔️",
        "DEFENDED_ZONE": "🧱",
        "INSIDE_PRINT": "🔎",
        "ORDER_REUSE": "♻️",
        "SWEEP_DEFENSE": "🛡️",
        "CROSS_CONFIRMED": "🔗",
        "CONFLUENCE": "🎯",
    },
    "shortcuts": {
        "buy_market": "F1",
        "sell_market": "F2",
        "flatten": "F3",
        "cancel_all": "F4",
        "kill_switch": "F12",
    },
    "risk": {
        "max_daily_loss": 1000.0,
        "max_account_loss": 5000.0,
        "max_position_size": 10,
        "max_open_orders": 20,
        "lockout_on_max_loss": True,
    },
    "brokers": {
        "active": "Simulation",
        "credentials": {},  # chiffrées séparément, voir Core/Security.py
    },
    "reconstructed_tape": {
        # Fenêtre de fusion des fills fragmentés en un seul print (Jigsaw
        # "Reconstructed Tape"). Un print est considéré comme un "gros
        # trade / bloc" à partir de block_trade_size.
        "merge_window_ms": 150,
        "min_display_size": 1,
        "block_trade_size": 50,
        "split_buy_sell_tape": False,   # 2 tapes séparées (achats/ventes), comme Jigsaw
        "block_trade_alert": True,      # alerte visuelle (Widgets/Alerts) sur bloc détecté
    },
    "dom_extra": {
        # Réglages avancés du DOM (Depth & Sales), façon Jigsaw daytradr.
        "color_mode": "bid_ask",        # "bid_ask" ou "uptick_downtick"
        "highlight_sweep": True,        # met en évidence les niveaux "balayés"
        "least_significant_digits": 0,  # nb de chiffres de prix à estomper (0 = désactivé)
        "min_trade_size_filter": 0,     # filtre par défaut du Time & Sales / tape
    },
    "orders_positions": {
        # Réglages façon "Order and Positions view" de Jigsaw daytradr.
        "qty_increment": 1,
        "default_order_type": "MARKET",  # "MARKET" ou "LIMIT"
        "confirm_on_flip": True,          # confirmation si l'ordre inverse la position
        "one_click_trading": False,       # si False, confirmation avant envoi
        "oco_simulation": True,           # simulation locale des ordres OCO
        "pnl_display": "currency",       # "currency" ou "ticks"
    },
    "connections": [
        # Profils de connexion façon "Connection Manager" de Jigsaw daytradr.
        # Chaque profil : nom, feed (clé de Brokers.BrokerEngine.AVAILABLE_BROKERS),
        # environnement (demo/live), auto-connexion + ordre, simulation OCO,
        # niveau de données et type d'instruments.
        {
            "name": "Simulation",
            "feed": "Simulation",
            "environment": "demo",
            "username": "",
            "auto_connect": True,
            "auto_connect_order": 0,
            "oco_simulation": True,
            "data_level": "level2",     # "level1" ou "level2"
            "instruments": "futures",   # "stocks", "futures" ou "spreads"
        },
    ],
    "pace_of_tape": {
        # Smart Gauge : rythme court terme (short_window_s) comparé à une
        # moyenne de référence (baseline_window_s). Seuils exprimés en
        # ratio court terme / référence.
        "short_window_s": 10,
        "baseline_window_s": 300,
        "calm_threshold": 0.5,
        "active_threshold": 1.5,
        "extreme_threshold": 3.0,
    },
    "theme": "jigsaw_blue_red",
    "last_workspace": "default",
}


class Settings:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._data: Dict[str, Any] = {k: v for k, v in DEFAULTS.items()}
        self.load()

    def load(self) -> None:
        for key, default_value in DEFAULTS.items():
            stored = self.db.get_setting(key, None)
            self._data[key] = stored if stored is not None else default_value

    def save(self) -> None:
        for key, value in self._data.items():
            self.db.set_setting(key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.db.set_setting(key, value)

    @property
    def data(self) -> Dict[str, Any]:
        return self._data
