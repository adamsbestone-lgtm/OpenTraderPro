"""
TimeSalesWidget.py - flux des transactions. Colonnes : Heure, Prix,
Quantité, Bid, Ask, Type, Agressivité. Filtres : volume minimum,
couleur, taille de police.
"""
from __future__ import annotations
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QSpinBox, QAbstractItemView
)

from Core.EventBus import EventBus

COLUMNS = ["Heure", "Prix", "Quantité", "Bid", "Ask", "Type", "Agressif"]
MAX_ROWS = 500


class TimeSalesWidget(QWidget):
    def __init__(self, bus: EventBus, symbol: str = "ESU6", parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.symbol = symbol
        self._last_bid = self._last_ask = 0.0
        self._build_ui()
        self.bus.subscribe(EventBus.EVT_TRADE_PRINT, self._on_trade)
        self.bus.subscribe(EventBus.EVT_DEPTH, self._on_depth)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Volume min :"))
        self.min_volume = QSpinBox()
        self.min_volume.setRange(0, 10000)
        filter_bar.addWidget(self.min_volume)

        filter_bar.addWidget(QLabel("Taille police :"))
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 24)
        self.font_size.setValue(12)
        self.font_size.valueChanged.connect(self._apply_font_size)
        filter_bar.addWidget(self.font_size)
        filter_bar.addStretch()
        layout.addLayout(filter_bar)

        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    def _apply_font_size(self, size: int) -> None:
        font = self.table.font()
        font.setPointSize(size)
        self.table.setFont(font)

    def _on_depth(self, snapshot) -> None:
        if snapshot.symbol != self.symbol:
            return
        if snapshot.bids:
            self._last_bid = snapshot.bids[0].price
        if snapshot.asks:
            self._last_ask = snapshot.asks[0].price

    def _on_trade(self, tick: dict) -> None:
        if tick.get("symbol") != self.symbol or tick.get("size", 0) < self.min_volume.value():
            return

        self.table.insertRow(0)
        values = [
            datetime.fromtimestamp(tick["time"]).strftime("%H:%M:%S.%f")[:-3],
            f"{tick['price']:.2f}", str(tick["size"]),
            f"{self._last_bid:.2f}", f"{self._last_ask:.2f}",
            "ACHAT" if tick["side"] == "buy" else "VENTE",
            "●" if tick.get("aggressive") else "",
        ]
        color = QColor("#43a047") if tick["side"] == "buy" else QColor("#e53935")
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QBrush(color))
            self.table.setItem(0, col, item)

        if self.table.rowCount() > MAX_ROWS:
            self.table.removeRow(self.table.rowCount() - 1)
