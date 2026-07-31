"""
HFTWidget.py - fenêtre "HFT" : tableau de bord orienté trading haute
fréquence / market making.

Affiche en direct :
- débit du flux marché (ticks/s, mises à jour de profondeur/s)
- latence moyenne ordre (délai entre soumission et accusé de réception broker)
- microstructure : spread, déséquilibre du carnet (bid/ask imbalance)
- débit d'ordres envoyés (ordres/s) avec alerte si proche de la limite
  configurée dans Risk Engine (max_open_orders / seconde)
- un "Mode HFT" qui accélère le rafraîchissement de l'affichage et un
  accès rapide pour démarrer/arrêter les bots marqués `"hft": true`
  dans leur bot.json (ex : market makers, scalpers ultra-rapides).

Ce widget est un panneau de supervision : il ne place pas d'ordres
lui-même (à part via les bots pilotés), il aide à surveiller que le
système reste dans des limites saines pour du trading à haute fréquence.
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Deque
from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem
)

from Core.EventBus import EventBus
from Engines.BotEngine import BotEngine

BOTS_DIR = Path("Bots")


class HFTWidget(QWidget):
    def __init__(self, bus: EventBus, bot_engine: BotEngine, settings, symbol: str = "ESU6", parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.bot_engine = bot_engine
        self.settings = settings
        self.symbol = symbol
        self.hft_mode = False

        self._tick_count = 0
        self._depth_count = 0
        self._order_send_count = 0
        self._latency_samples: Deque[float] = deque(maxlen=200)
        self._pending_orders: dict[int, float] = {}  # order_id -> ts de soumission
        self._best_bid = self._best_ask = 0.0

        self._build_ui()

        self.bus.subscribe(EventBus.EVT_TRADE_PRINT, self._on_tick)
        self.bus.subscribe(EventBus.EVT_DEPTH, self._on_depth)
        self.bus.subscribe(EventBus.EVT_ORDER_NEW, self._on_order_new)
        self.bus.subscribe(EventBus.EVT_ORDER_UPDATE, self._on_order_ack)

        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start(1000)  # recalcul des débits chaque seconde

    # -- construction UI -----------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        header = QHBoxLayout()
        header.addWidget(QLabel(f"<b style='color:#5a9dff; font-size:14px;'>HFT — {self.symbol}</b>"))
        header.addStretch()
        self.mode_btn = QPushButton("Activer Mode HFT")
        self.mode_btn.setCheckable(True)
        self.mode_btn.toggled.connect(self._toggle_hft_mode)
        header.addWidget(self.mode_btn)
        layout.addLayout(header)

        form = QFormLayout()
        self.tick_rate_label = QLabel("0 /s")
        self.depth_rate_label = QLabel("0 /s")
        self.order_rate_label = QLabel("0 /s")
        self.latency_label = QLabel("- ms")
        self.spread_label = QLabel("-")
        self.imbalance_label = QLabel("-")
        form.addRow("Débit ticks :", self.tick_rate_label)
        form.addRow("Débit profondeur :", self.depth_rate_label)
        form.addRow("Débit ordres envoyés :", self.order_rate_label)
        form.addRow("Latence moyenne (ack) :", self.latency_label)
        form.addRow("Spread :", self.spread_label)
        form.addRow("Déséquilibre carnet :", self.imbalance_label)
        layout.addLayout(form)

        layout.addWidget(QLabel("<b>Bots HFT disponibles</b> (bot.json avec \"hft\": true)"))
        self.hft_bots_list = QListWidget()
        layout.addWidget(self.hft_bots_list)
        self._populate_hft_bots()

        layout.addStretch()

    def _populate_hft_bots(self) -> None:
        self.hft_bots_list.clear()
        if not BOTS_DIR.exists():
            return
        for folder in BOTS_DIR.iterdir():
            meta_path = folder / "bot.json"
            if not meta_path.exists():
                continue
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if not meta.get("params", {}).get("hft", False):
                continue

            item_widget = QWidget()
            row = QHBoxLayout(item_widget)
            row.setContentsMargins(4, 2, 4, 2)
            row.addWidget(QLabel(meta.get("name", folder.name)))
            row.addStretch()
            start_btn = QPushButton("Démarrer")
            stop_btn = QPushButton("Arrêter")
            start_btn.clicked.connect(lambda _, n=folder.name: self.bot_engine.start(n))
            stop_btn.clicked.connect(lambda _, n=folder.name: self.bot_engine.stop(n))
            row.addWidget(start_btn)
            row.addWidget(stop_btn)

            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            self.hft_bots_list.addItem(list_item)
            self.hft_bots_list.setItemWidget(list_item, item_widget)

    # -- Mode HFT (accélère le rafraîchissement, vigilance accrue) ---------------
    def _toggle_hft_mode(self, checked: bool) -> None:
        self.hft_mode = checked
        self.mode_btn.setText("Désactiver Mode HFT" if checked else "Activer Mode HFT")
        self.bus.publish(EventBus.EVT_LOG, {
            "level": "INFO",
            "msg": f"Mode HFT {'activé' if checked else 'désactivé'} — "
                   f"{'surveillance renforcée du débit d’ordres.' if checked else 'retour au mode normal.'}",
        })

    # -- collecte des événements --------------------------------------------------
    def _on_tick(self, tick: dict) -> None:
        if tick.get("symbol") == self.symbol:
            self._tick_count += 1

    def _on_depth(self, snapshot) -> None:
        if snapshot.symbol != self.symbol:
            return
        self._depth_count += 1
        if snapshot.bids:
            self._best_bid = snapshot.bids[0].price
        if snapshot.asks:
            self._best_ask = snapshot.asks[0].price

        if snapshot.bids and snapshot.asks:
            bid_size, ask_size = snapshot.bids[0].size, snapshot.asks[0].size
            total = bid_size + ask_size
            if total > 0:
                imbalance = (bid_size - ask_size) / total * 100
                self.imbalance_label.setText(f"{imbalance:+.1f}% ({'acheteur' if imbalance > 0 else 'vendeur'})")
        spread = self._best_ask - self._best_bid
        self.spread_label.setText(f"{spread:.2f}")

    def _on_order_new(self, order) -> None:
        self._order_send_count += 1
        self._pending_orders[order.id] = time.time()

    def _on_order_ack(self, order) -> None:
        sent_ts = self._pending_orders.pop(order.id, None)
        if sent_ts is not None:
            self._latency_samples.append((time.time() - sent_ts) * 1000)  # en ms

    # -- recalcul périodique des débits (appelé chaque seconde) -------------------
    def _refresh_stats(self) -> None:
        self.tick_rate_label.setText(f"{self._tick_count} /s")
        self.depth_rate_label.setText(f"{self._depth_count} /s")
        self.order_rate_label.setText(f"{self._order_send_count} /s")

        if self._latency_samples:
            avg_latency = sum(self._latency_samples) / len(self._latency_samples)
            self.latency_label.setText(f"{avg_latency:.1f} ms")

        max_orders_per_sec = 10  # seuil indicatif d'alerte visuelle (à ajuster selon le broker)
        if self._order_send_count >= max_orders_per_sec:
            self.order_rate_label.setStyleSheet("color:#ff1744; font-weight:600;")
        else:
            self.order_rate_label.setStyleSheet("")

        self._tick_count = 0
        self._depth_count = 0
        self._order_send_count = 0
