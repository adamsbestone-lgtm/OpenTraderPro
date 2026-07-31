"""
PositionsWidget.py - positions ouvertes avec P&L et actions Reverse/Close/Flatten.
"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QAbstractItemView
)

from Core.EventBus import EventBus
from Engines.OrderEngine import OrderEngine
from Engines.PositionEngine import PositionEngine

COLUMNS = ["Symbole", "Position", "Prix moyen", "PNL latent", "PNL réalisé", "Contrats", "Actions"]


class PositionsWidget(QWidget):
    def __init__(self, bus: EventBus, order_engine: OrderEngine, position_engine: PositionEngine,
                 settings=None, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.order_engine = order_engine
        self.position_engine = position_engine
        self.orders_positions = settings.get("orders_positions", {}) if settings else {}
        self.tick_size = settings.get("dom_tick_size", 0.25) if settings else 0.25
        self._build_ui()
        self.bus.subscribe(EventBus.EVT_POSITION_UPDATE, lambda p: self._refresh())

    def _format_pnl(self, value: float) -> str:
        if self.orders_positions.get("pnl_display") == "ticks" and self.tick_size:
            return f"{value / self.tick_size:+.1f} ticks"
        return f"{value:+.2f}"

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    def _refresh(self) -> None:
        positions = [p for p in self.position_engine.positions.values() if p.quantity != 0]
        self.table.setRowCount(len(positions))

        for row, pos in enumerate(positions):
            values = [pos.symbol, str(pos.quantity), f"{pos.avg_price:.2f}",
                      self._format_pnl(pos.unrealized_pnl), self._format_pnl(pos.realized_pnl), str(abs(pos.quantity))]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 3:
                    item.setForeground(QBrush(QColor("#43a047" if pos.unrealized_pnl >= 0 else "#e53935")))
                self.table.setItem(row, col, item)

            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            reverse_btn, close_btn = QPushButton("Reverse"), QPushButton("Close")
            reverse_btn.clicked.connect(lambda _, s=pos.symbol: self.position_engine.reverse(self.order_engine, s))
            close_btn.clicked.connect(lambda _, s=pos.symbol: self.position_engine.flatten(self.order_engine, s))
            actions_layout.addWidget(reverse_btn)
            actions_layout.addWidget(close_btn)
            self.table.setCellWidget(row, 6, actions_widget)
