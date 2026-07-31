"""
DOMWidget.py - carnet d'ordres (DOM/ladder), pièce maîtresse du logiciel.

Colonnes : Bid Size, Bid, Price, Ask, Ask Size, Last, Volume, Position,
PNL, Iceberg, Pulling, Stacking.

Fonctions : clic achat/vente, drag & drop d'ordre (déplacement de prix),
annulation (double-clic), modification, coloration dynamique, zoom
(Ctrl + molette), raccourcis clavier (F1/F2/F3/F4 configurables).
"""
from __future__ import annotations
from typing import Dict, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush, QKeySequence, QShortcut, QWheelEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QMenu, QLabel, QAbstractItemView, QPushButton, QSpinBox,
    QMessageBox
)

from Core.EventBus import EventBus
from Engines.MarketEngine import DepthSnapshot
from Engines.OrderEngine import Order, OrderType, OrderSide, OrderEngine

COLUMNS = [
    "Bid Size", "Bid", "Price", "Ask", "Ask Size",
    "Last", "Volume", "Position", "PNL", "Iceberg", "Pulling", "Stacking",
]
COL_IDX = {name: i for i, name in enumerate(COLUMNS)}


class DOMWidget(QWidget):
    def __init__(self, bus: EventBus, order_engine: OrderEngine, position_engine,
                 symbol: str = "ESU6", settings=None, fps: int = 60, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.order_engine = order_engine
        self.position_engine = position_engine
        self.symbol = symbol
        self.settings = settings
        self.colors = settings.get("colors", {}) if settings else {}
        self.icons = settings.get("icons", {}) if settings else {}
        self.dom_extra = settings.get("dom_extra", {}) if settings else {}
        self.orders_positions = settings.get("orders_positions", {}) if settings else {}
        self._base_font_size = 12
        self._prev_last_price: Optional[float] = None

        self._latest_snapshot: Optional[DepthSnapshot] = None
        self._working_orders_by_price: Dict[float, Order] = {}
        self._current_position = None

        self._build_ui()
        self._build_shortcuts()

        self.bus.subscribe(EventBus.EVT_DEPTH, self._on_depth)
        self.bus.subscribe(EventBus.EVT_ORDER_UPDATE, self._on_order_update)
        self.bus.subscribe(EventBus.EVT_ORDER_FILLED, self._on_order_update)
        self.bus.subscribe(EventBus.EVT_ORDER_CANCELED, self._on_order_removed)
        self.bus.subscribe(EventBus.EVT_POSITION_UPDATE, self._on_position_update)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._render)
        self._refresh_timer.start(max(1, int(1000 / fps)))

    # -- construction UI -----------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        header_bar = QHBoxLayout()
        header_color = self.colors.get("bid", "#5a9dff")
        self.symbol_label = QLabel(f"<b style='color:{header_color}; font-size:14px;'>{self.symbol}</b>")
        header_bar.addWidget(self.symbol_label)
        header_bar.addStretch()

        header_bar.addWidget(QLabel("Qté :"))
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 500)
        self.qty_spin.setValue(self.orders_positions.get("qty_increment", 1))
        self.qty_spin.setSingleStep(max(1, self.orders_positions.get("qty_increment", 1)))
        header_bar.addWidget(self.qty_spin)

        buy_btn = QPushButton("ACHAT")
        buy_btn.setObjectName("buyButton")
        buy_btn.clicked.connect(lambda: self._buy_market())
        header_bar.addWidget(buy_btn)

        sell_btn = QPushButton("VENTE")
        sell_btn.setObjectName("sellButton")
        sell_btn.clicked.connect(lambda: self._sell_market())
        header_bar.addWidget(sell_btn)

        flatten_btn = QPushButton("Flatten")
        flatten_btn.clicked.connect(lambda: self.position_engine.flatten(self.order_engine, self.symbol))
        header_bar.addWidget(flatten_btn)
        layout.addLayout(header_bar)

        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self.table)

    def _build_shortcuts(self) -> None:
        shortcuts = self.settings.get("shortcuts", {}) if self.settings else {}
        QShortcut(QKeySequence(shortcuts.get("buy_market", "F1")), self, activated=self._buy_market)
        QShortcut(QKeySequence(shortcuts.get("sell_market", "F2")), self, activated=self._sell_market)
        QShortcut(QKeySequence(shortcuts.get("flatten", "F3")), self,
                  activated=lambda: self.position_engine.flatten(self.order_engine, self.symbol))
        QShortcut(QKeySequence(shortcuts.get("cancel_all", "F4")), self,
                  activated=lambda: self.order_engine.cancel_all(self.symbol))

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = 1 if event.angleDelta().y() > 0 else -1
            self._base_font_size = max(8, min(24, self._base_font_size + delta))
            font = self.table.font()
            font.setPointSize(self._base_font_size)
            self.table.setFont(font)
        else:
            super().wheelEvent(event)

    def _would_flip(self, side: OrderSide) -> bool:
        pos = self._current_position
        if not pos or pos.quantity == 0:
            return False
        return (pos.quantity > 0 and side == OrderSide.SELL) or (pos.quantity < 0 and side == OrderSide.BUY)

    def _confirm_order(self, side: OrderSide, quantity: int, price: Optional[float] = None) -> bool:
        one_click = self.orders_positions.get("one_click_trading", False)
        confirm_on_flip = self.orders_positions.get("confirm_on_flip", True)
        needs_confirm = (not one_click) or (confirm_on_flip and self._would_flip(side))
        if not needs_confirm:
            return True
        verb = "ACHAT" if side == OrderSide.BUY else "VENTE"
        price_txt = f" @ {price:.2f}" if price is not None else " au marché"
        flip_txt = "\n\n⚠️ Cet ordre va INVERSER votre position actuelle." if self._would_flip(side) else ""
        answer = QMessageBox.question(
            self, "Confirmer l'ordre",
            f"{verb} {quantity} {self.symbol}{price_txt} ?{flip_txt}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _buy_market(self) -> None:
        qty = self.qty_spin.value()
        if not self._confirm_order(OrderSide.BUY, qty):
            return
        self.order_engine.submit(Order(symbol=self.symbol, side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=qty))

    def _sell_market(self) -> None:
        qty = self.qty_spin.value()
        if not self._confirm_order(OrderSide.SELL, qty):
            return
        self.order_engine.submit(Order(symbol=self.symbol, side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=qty))

    # -- réception des données ------------------------------------------------
    def _on_depth(self, snapshot: DepthSnapshot) -> None:
        if snapshot.symbol == self.symbol:
            self._latest_snapshot = snapshot

    def _on_order_update(self, order: Order) -> None:
        if order.symbol != self.symbol:
            return
        if order.status.name == "WORKING" and order.price is not None:
            self._working_orders_by_price[order.price] = order

    def _on_order_removed(self, order_id) -> None:
        for price, order in list(self._working_orders_by_price.items()):
            if order.id == order_id:
                del self._working_orders_by_price[price]

    def _on_position_update(self, position) -> None:
        if position.symbol == self.symbol:
            self._current_position = position

    def _format_price(self, price: float) -> str:
        text = f"{price:.2f}"
        lsd = self.dom_extra.get("least_significant_digits", 0)
        if lsd and 0 < lsd < len(text):
            return text[:-lsd] + "·" * lsd
        return text

    # -- rendu (piloté par QTimer, jamais directement par le flux réseau) --------
    def _render(self) -> None:
        snap = self._latest_snapshot
        if snap is None:
            return
        if self._prev_last_price is not None and snap.last_price != self._prev_last_price:
            self._last_direction = "up" if snap.last_price > self._prev_last_price else "down"
        elif not hasattr(self, "_last_direction"):
            self._last_direction = None
        self._prev_last_price = snap.last_price

        asks_sorted = sorted(snap.asks, key=lambda l: l.price, reverse=True)
        bids_sorted = sorted(snap.bids, key=lambda l: l.price, reverse=True)

        new_row_count = len(asks_sorted) + len(bids_sorted)
        if self.table.rowCount() != new_row_count:
            self.table.setRowCount(new_row_count)
        row = 0
        for level in asks_sorted:
            self._paint_row(row, level, side="ask")
            row += 1
        for level in bids_sorted:
            self._paint_row(row, level, side="bid")
            row += 1

    def _paint_row(self, row: int, level, side: str) -> None:
        def set_item(col_name: str, text: str, color: Optional[str] = None, bold: bool = False):
            col = COL_IDX[col_name]
            item = self.table.item(row, col)
            if item is None:
                # première fois qu'on peuple cette cellule : seule allocation
                # réelle de QTableWidgetItem, réutilisé à toutes les frames
                # suivantes (évite l'allocation + le passage GC à 60fps).
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
            if item.text() != text:
                item.setText(text)
            if color:
                item.setForeground(QBrush(QColor(color)))
            if bold:
                font = item.font()
                if not font.bold():
                    font.setBold(True)
                    item.setFont(font)
            if col_name == "Price":
                item.setBackground(QBrush(QColor(self.colors.get("price_bg", "#132238"))))
                item.setForeground(QBrush(QColor(self.colors.get("bid", "#5a9dff"))))
                font = item.font()
                if not font.bold():
                    font.setBold(True)
                    item.setFont(font)

        bid_color, ask_color = self.colors.get("bid", "#5a9dff"), self.colors.get("ask", "#e53935")
        price_text = self._format_price(level.price)

        if side == "ask":
            set_item("Ask Size", str(level.size), color=ask_color)
            set_item("Price", price_text, bold=True)
            set_item("Ask", price_text, color=ask_color)
            set_item("Bid", "")
            set_item("Bid Size", "")
        else:
            set_item("Bid Size", str(level.size), color=bid_color)
            set_item("Bid", price_text, color=bid_color)
            set_item("Price", price_text, bold=True)
            set_item("Ask", "")
            set_item("Ask Size", "")

        price_item = self.table.item(row, COL_IDX["Price"])
        if price_item:
            price_item.setData(Qt.ItemDataRole.UserRole, level.price)

        if self.dom_extra.get("highlight_sweep", True) and getattr(level, "swept", False) and price_item:
            price_item.setBackground(QBrush(QColor(self.colors.get("sweep", "#ffb300"))))
            price_item.setForeground(QBrush(QColor("#051020")))
            price_item.setText(f"{self.icons.get('sweep', '⚡')} {price_text}")

        snap = self._latest_snapshot
        is_last = abs(snap.last_price - level.price) < 0.01
        if is_last and self.dom_extra.get("color_mode") == "uptick_downtick" and getattr(self, "_last_direction", None):
            last_color = (self.colors.get("aggressive_buy", "#43a047") if self._last_direction == "up"
                          else self.colors.get("aggressive_sell", "#e53935"))
        else:
            last_color = self.colors.get("last", "#ffffff")
        set_item("Last", f"{snap.last_price:.2f}" if is_last else "", color=last_color if is_last else None)
        set_item("Volume", str(snap.volume) if is_last else "")
        if is_last:
            price_item = self.table.item(row, COL_IDX["Price"])
            if price_item:
                price_item.setBackground(QBrush(QColor(self.colors.get("stacking", "#2f7dfd"))))
                price_item.setForeground(QBrush(QColor("#051020")))

        set_item("Iceberg", self.icons.get("iceberg", "🧊") if level.iceberg else "", color=self.colors.get("iceberg", "#8ab4ff"))
        set_item("Pulling", self.icons.get("pulling", "🔻") if level.pulling else "", color=self.colors.get("pulling", "#5f7799"))
        set_item("Stacking", self.icons.get("stacking", "🔺") if level.stacking else "", color=self.colors.get("stacking", "#2f7dfd"))

        pos = self._current_position
        if pos and abs(pos.avg_price - level.price) < 0.01:
            pnl_color = self.colors.get("profit", "#43a047") if pos.unrealized_pnl >= 0 else self.colors.get("loss", "#e53935")
            set_item("PNL", f"{pos.unrealized_pnl:+.2f}", color=pnl_color)
            set_item("Position", str(pos.quantity), bold=True)
        else:
            set_item("PNL", "")
            set_item("Position", "")

        working = self._working_orders_by_price.get(level.price)
        if working:
            col = "Bid" if side == "bid" else "Ask"
            item = self.table.item(row, COL_IDX[col])
            if item:
                item.setBackground(QBrush(QColor("#3a3f45")))

    # -- interactions utilisateur ----------------------------------------------
    def _price_from_row(self, row: int) -> Optional[float]:
        item = self.table.item(row, COL_IDX["Price"])
        if not item or not item.text():
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is not None:
            return float(data)
        try:
            return float(item.text())
        except ValueError:
            return None

    def _on_cell_clicked(self, row: int, column: int) -> None:
        price = self._price_from_row(row)
        if price is None:
            return
        col_name = COLUMNS[column]
        if col_name == "Bid":
            self._place_order(OrderSide.BUY, price)
        elif col_name == "Ask":
            self._place_order(OrderSide.SELL, price)

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        price = self._price_from_row(row)
        if price is None:
            return
        order = self._working_orders_by_price.get(price)
        if order:
            self.order_engine.cancel(order.id)

    def _place_order(self, side: OrderSide, price: float, quantity: Optional[int] = None) -> None:
        qty = quantity if quantity is not None else self.qty_spin.value()
        if not self._confirm_order(side, qty, price=price):
            return
        self.order_engine.submit(Order(symbol=self.symbol, side=side, order_type=OrderType.LIMIT, price=price, quantity=qty))

    def _on_context_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        price = self._price_from_row(row) if row >= 0 else None

        menu = QMenu(self)
        buy_market = menu.addAction("Acheter au marché")
        sell_market = menu.addAction("Vendre au marché")
        menu.addSeparator()
        buy_limit = menu.addAction(f"Acheter Limit @ {price:.2f}") if price is not None else None
        sell_limit = menu.addAction(f"Vendre Limit @ {price:.2f}") if price is not None else None
        menu.addSeparator()
        flatten = menu.addAction("Flatten")
        cancel_all = menu.addAction("Annuler tous les ordres")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == buy_market:
            self._buy_market()
        elif action == sell_market:
            self._sell_market()
        elif price is not None and action == buy_limit:
            self._place_order(OrderSide.BUY, price)
        elif price is not None and action == sell_limit:
            self._place_order(OrderSide.SELL, price)
        elif action == flatten:
            self.position_engine.flatten(self.order_engine, self.symbol)
        elif action == cancel_all:
            self.order_engine.cancel_all(self.symbol)
