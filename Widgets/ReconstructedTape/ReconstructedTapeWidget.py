"""
ReconstructedTapeWidget.py - affiche le flux de prints reconstitués
(Engines/ReconstructedTapeEngine.py), l'équivalent de la "Reconstructed
Tape" de Jigsaw daytradr : chaque ligne est un trade réel (fills
fragmentés déjà recollés), plus lisible que le Time & Sales brut.

Colonnes : Heure, Prix, Quantité, Fragments, Type, Bloc.
Les gros trades (>= block_trade_size) sont mis en évidence (icône +
couleur configurables via Settings -> "colors"/"icons") et peuvent
déclencher une alerte (Settings -> "reconstructed_tape" -> block_trade_alert).

Si Settings -> "reconstructed_tape" -> split_buy_sell_tape est activé,
2 tapes séparées (achats/ventes) sont affichées côte à côte, comme le
propose Jigsaw daytradr pour repérer plus vite les bascules de momentum.
"""
from __future__ import annotations
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QSpinBox, QAbstractItemView
)

from Core.EventBus import EventBus

COLUMNS = ["Heure", "Prix", "Quantité", "Fragments", "Type", "Bloc"]
MAX_ROWS = 500


class ReconstructedTapeWidget(QWidget):
    def __init__(self, bus: EventBus, symbol: str = "ESU6", settings=None, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.symbol = symbol
        self.colors = settings.get("colors", {}) if settings else {}
        self.icons = settings.get("icons", {}) if settings else {}
        cfg = settings.get("reconstructed_tape", {}) if settings else {}
        self.block_trade_size = cfg.get("block_trade_size", 50)
        self.split_buy_sell = cfg.get("split_buy_sell_tape", False)
        self.block_trade_alert = cfg.get("block_trade_alert", True)
        self._default_min_size = cfg.get("min_display_size", 1)

        self._build_ui()
        self.bus.subscribe(EventBus.EVT_TAPE_RECONSTRUCTED, self._on_print)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Volume min :"))
        self.min_volume = QSpinBox()
        self.min_volume.setRange(0, 10000)
        self.min_volume.setValue(self._default_min_size)
        filter_bar.addWidget(self.min_volume)

        filter_bar.addWidget(QLabel("Taille police :"))
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 24)
        self.font_size.setValue(12)
        self.font_size.valueChanged.connect(self._apply_font_size)
        filter_bar.addWidget(self.font_size)
        filter_bar.addStretch()
        layout.addLayout(filter_bar)

        tables_layout = QHBoxLayout()
        if self.split_buy_sell:
            buy_col = QVBoxLayout()
            buy_col.addWidget(QLabel("Tape ACHATS"))
            self.buy_table = self._make_table()
            buy_col.addWidget(self.buy_table)
            tables_layout.addLayout(buy_col)

            sell_col = QVBoxLayout()
            sell_col.addWidget(QLabel("Tape VENTES"))
            self.sell_table = self._make_table()
            sell_col.addWidget(self.sell_table)
            tables_layout.addLayout(sell_col)

            self.table = None
        else:
            self.table = self._make_table()
            tables_layout.addWidget(self.table)
            self.buy_table = self.sell_table = None

        layout.addLayout(tables_layout)

    def _make_table(self) -> QTableWidget:
        table = QTableWidget(0, len(COLUMNS))
        table.setHorizontalHeaderLabels(COLUMNS)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def _apply_font_size(self, size: int) -> None:
        tables = [t for t in (self.table, self.buy_table, self.sell_table) if t is not None]
        for table in tables:
            font = table.font()
            font.setPointSize(size)
            table.setFont(font)

    def _on_print(self, payload: dict) -> None:
        if payload.get("symbol") != self.symbol or payload.get("size", 0) < self.min_volume.value():
            return

        is_block = payload["size"] >= self.block_trade_size
        block_marker = self.icons.get("block_trade", "🐋") if is_block else ""

        values = [
            datetime.fromtimestamp(payload["time"]).strftime("%H:%M:%S.%f")[:-3],
            f"{payload['price']:.2f}", str(payload["size"]),
            f"×{payload['fragments']}" if payload["fragments"] > 1 else "1",
            "ACHAT" if payload["side"] == "buy" else "VENTE",
            block_marker,
        ]

        if is_block:
            base_color = QColor(self.colors.get("block_trade", "#29b6f6"))
        elif payload["side"] == "buy":
            base_color = QColor(self.colors.get("aggressive_buy", "#43a047"))
        else:
            base_color = QColor(self.colors.get("aggressive_sell", "#e53935"))

        target = self.table if not self.split_buy_sell else (
            self.buy_table if payload["side"] == "buy" else self.sell_table
        )
        self._insert_row(target, values, base_color, is_block)

        if is_block and self.block_trade_alert:
            self.bus.publish(EventBus.EVT_ALERT, {
                "message": (
                    f"{self.icons.get('block_trade', '🐋')} Bloc détecté : "
                    f"{payload['size']} {self.symbol} @ {payload['price']:.2f} "
                    f"({'achat' if payload['side'] == 'buy' else 'vente'})"
                )
            })

    def _insert_row(self, table: QTableWidget, values: list, color: QColor, is_block: bool) -> None:
        table.insertRow(0)
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QBrush(color))
            if is_block:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            table.setItem(0, col, item)

        if table.rowCount() > MAX_ROWS:
            table.removeRow(table.rowCount() - 1)
