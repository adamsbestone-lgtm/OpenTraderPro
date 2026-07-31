"""
OrdersWidget.py - onglets Ordres actifs / Exécutés / Historique.
"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QAbstractItemView, QTabWidget
)

from Core.EventBus import EventBus
from Engines.OrderEngine import OrderEngine, OrderStatus

COLUMNS = ["ID", "Symbole", "Sens", "Type", "Qté", "Prix", "Statut", "Rempli"]


class OrdersWidget(QWidget):
    def __init__(self, bus: EventBus, order_engine: OrderEngine, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.order_engine = order_engine
        self._executed_log: list[dict] = []
        self._build_ui()

        for evt in (EventBus.EVT_ORDER_NEW, EventBus.EVT_ORDER_UPDATE,
                    EventBus.EVT_ORDER_FILLED, EventBus.EVT_ORDER_REJECTED):
            self.bus.subscribe(evt, lambda payload: self._refresh())
        self.bus.subscribe(EventBus.EVT_ORDER_FILLED, self._on_fill_logged)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        toolbar = QHBoxLayout()
        cancel_all_btn = QPushButton("Annuler tout")
        cancel_all_btn.clicked.connect(lambda: self.order_engine.cancel_all())
        toolbar.addWidget(cancel_all_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.tabs = QTabWidget()
        self.active_table = self._make_table()
        self.executed_table = self._make_table()
        self.history_table = self._make_table()
        self.tabs.addTab(self.active_table, "Actifs")
        self.tabs.addTab(self.executed_table, "Exécutés")
        self.tabs.addTab(self.history_table, "Historique")
        layout.addWidget(self.tabs)

    def _make_table(self) -> QTableWidget:
        table = QTableWidget(0, len(COLUMNS))
        table.setHorizontalHeaderLabels(COLUMNS)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.cellDoubleClicked.connect(self._cancel_selected)
        return table

    def _fill_table(self, table: QTableWidget, orders: list) -> None:
        table.setRowCount(len(orders))
        for row, order in enumerate(orders):
            values = [str(order.id), order.symbol, order.side.name, order.order_type.name,
                      str(order.quantity), f"{order.price:.2f}" if order.price else "-",
                      order.status.name, str(order.filled_qty)]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, col, item)

    def _refresh(self) -> None:
        all_orders = list(self.order_engine.orders.values())
        active = [o for o in all_orders if o.status in (OrderStatus.WORKING, OrderStatus.PARTIALLY_FILLED, OrderStatus.PENDING)]
        executed = [o for o in all_orders if o.status == OrderStatus.FILLED]
        history = all_orders
        self._fill_table(self.active_table, active)
        self._fill_table(self.executed_table, executed)
        self._fill_table(self.history_table, history)

    def _on_fill_logged(self, order) -> None:
        self._executed_log.append({"id": order.id, "symbol": order.symbol})

    def _cancel_selected(self, row: int, _column: int) -> None:
        id_item = self.active_table.item(row, 0)
        if id_item:
            self.order_engine.cancel(int(id_item.text()))
