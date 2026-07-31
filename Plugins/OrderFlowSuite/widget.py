"""
widget.py - fenêtre "Order Flow" : flux des signaux détectés en direct,
réglages ajustables à chaud (équivalent des champs @Parameter Bookmap),
boutons Buy/Sell manuels, et bascule "trading automatique" avec boîte de
dialogue de confirmation (portage de addon/SettingsPanel.java, en Qt au
lieu de Swing).
"""
from __future__ import annotations
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDoubleSpinBox, QSpinBox, QLineEdit, QPushButton, QCheckBox,
    QMessageBox, QLabel, QScrollArea
)

from Core.EventBus import EventBus
from Plugins.OrderFlowSuite.model import Direction
from Plugins.OrderFlowSuite.plugin import EVT_ORDERFLOW_SIGNAL, OrderFlowEngine

SIGNAL_COLUMNS = ["Heure", "Type", "Sens", "Prix", "Taille", "Détail"]
MAX_ROWS = 300


class OrderFlowWidget(QWidget):
    def __init__(self, bus: EventBus, engine: OrderFlowEngine, settings=None, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.engine = engine
        self.colors = settings.get("colors", {}) if settings else {}
        self.icons = settings.get("icons", {}) if settings else {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        tabs = QTabWidget()
        tabs.addTab(self._build_signals_tab(), "Signaux")
        tabs.addTab(self._build_settings_tab(), "Réglages")
        tabs.addTab(self._build_execution_tab(), "Exécution")
        layout.addWidget(tabs)

        self.bus.subscribe(EVT_ORDERFLOW_SIGNAL, self._on_signal)

    # -- onglet Signaux --------------------------------------------------------
    def _build_signals_tab(self) -> QWidget:
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        self.signals_table = QTableWidget(0, len(SIGNAL_COLUMNS))
        self.signals_table.setHorizontalHeaderLabels(SIGNAL_COLUMNS)
        self.signals_table.verticalHeader().setVisible(False)
        self.signals_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.signals_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        tab_layout.addWidget(self.signals_table)
        return tab

    def _on_signal(self, payload: dict) -> None:
        if payload.get("symbol") != self.engine.symbol:
            return
        signal = payload["signal"]

        self.signals_table.insertRow(0)
        icon = self.icons.get(signal.type.value, "")
        type_label = f"{icon} {signal.type.value}".strip()
        values = [
            datetime.fromtimestamp(signal.timestamp_ms / 1000).strftime("%H:%M:%S"),
            type_label, signal.direction.value, f"{signal.price:.2f}",
            str(signal.size), signal.detail,
        ]
        if signal.direction is Direction.BUY:
            color = QColor(self.colors.get("aggressive_buy", "#43a047"))
        else:
            color = QColor(self.colors.get("aggressive_sell", "#e53935"))
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col < 5 else Qt.AlignmentFlag.AlignLeft)
            item.setForeground(QBrush(color))
            self.signals_table.setItem(0, col, item)

        if self.signals_table.rowCount() > MAX_ROWS:
            self.signals_table.removeRow(self.signals_table.rowCount() - 1)

    # -- onglet Réglages (équivalent des champs @Parameter Bookmap) ------------------
    def _build_settings_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QFormLayout(container)

        def double_spin(value, lo, hi, step, on_change):
            box = QDoubleSpinBox()
            box.setRange(lo, hi)
            box.setSingleStep(step)
            box.setValue(value)
            box.valueChanged.connect(on_change)
            return box

        def int_spin(value, lo, hi, on_change):
            box = QSpinBox()
            box.setRange(lo, hi)
            box.setValue(value)
            box.valueChanged.connect(on_change)
            return box

        e = self.engine

        def set_and_rebuild(attr):
            def handler(value):
                setattr(e, attr, value)
                e.rebuild_detectors()
            return handler

        form.addRow("Imbalance ratio", double_spin(e.imbalance_ratio, 1.5, 10.0, 0.1, set_and_rebuild("imbalance_ratio")))
        form.addRow("Niveaux empilés min", int_spin(e.min_stacked_levels, 2, 10, set_and_rebuild("min_stacked_levels")))
        form.addRow("Volume min/niveau (imbalance)", int_spin(e.min_level_volume, 5, 200, set_and_rebuild("min_level_volume")))
        form.addRow("Ratio refill absorption", double_spin(e.absorption_refill_ratio, 1.2, 5.0, 0.1, set_and_rebuild("absorption_refill_ratio")))
        form.addRow("Volume min absorption", int_spin(e.absorption_min_volume, 20, 1000, set_and_rebuild("absorption_min_volume")))
        form.addRow("Sweep - volume min", int_spin(e.sweep_min_volume, 10, 500, set_and_rebuild("sweep_min_volume")))
        form.addRow("Sweep - niveaux min", int_spin(e.sweep_min_levels, 2, 10, set_and_rebuild("sweep_min_levels")))
        form.addRow("Cascade - petits prints min", int_spin(e.cascade_min_small_prints, 3, 50, set_and_rebuild("cascade_min_small_prints")))
        form.addRow("Confluence - types distincts min", int_spin(e.confluence_min_distinct_types, 2, 6, set_and_rebuild("confluence_min_distinct_types")))
        form.addRow("Inside print - volume min", int_spin(e.inside_print_min_volume, 5, 300, set_and_rebuild("inside_print_min_volume")))
        form.addRow("Inside print - ratio min", double_spin(e.inside_print_min_ratio, 1.5, 10.0, 0.5, set_and_rebuild("inside_print_min_ratio")))
        form.addRow("Reliquat post-sweep - taille min", int_spin(e.order_reuse_min_residual_size, 5, 300, set_and_rebuild("order_reuse_min_residual_size")))

        peer_edit = QLineEdit(e.peer_alias)
        peer_edit.setPlaceholderText("ex: MES si ce symbole est ES (laisser vide pour désactiver)")
        peer_edit.textChanged.connect(lambda text: setattr(e, "peer_alias", text))
        form.addRow("Alias instrument jumeau (cross-confirmation)", peer_edit)

        note = QLabel(
            "Les changements s'appliquent immédiatement, sans redémarrer le plugin\n"
            "(les détecteurs sont reconstruits à chaque modification)."
        )
        note.setWordWrap(True)
        form.addRow(note)

        scroll.setWidget(container)
        return scroll

    # -- onglet Exécution (portage de SettingsPanel.java) -----------------------------
    def _build_execution_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        qty_row = QHBoxLayout()
        qty_row.addWidget(QLabel("Quantité par ordre :"))
        qty_spin = QSpinBox()
        qty_spin.setRange(1, 50)
        qty_spin.setValue(self.engine.order_quantity)
        qty_spin.valueChanged.connect(lambda v: setattr(self.engine, "order_quantity", v))
        qty_row.addWidget(qty_spin)
        qty_row.addStretch()
        layout.addLayout(qty_row)

        manual_row = QHBoxLayout()
        buy_btn = QPushButton("ACHAT (manuel)")
        buy_btn.setObjectName("buyButton")
        buy_btn.clicked.connect(lambda: self.engine.send_market_order(True))
        sell_btn = QPushButton("VENTE (manuel)")
        sell_btn.setObjectName("sellButton")
        sell_btn.clicked.connect(lambda: self.engine.send_market_order(False))
        manual_row.addWidget(buy_btn)
        manual_row.addWidget(sell_btn)
        layout.addLayout(manual_row)

        layout.addWidget(QLabel(
            "<b>Trading automatique</b> : exécute un ordre marché à chaque signal détecté, "
            "dans la direction du signal."
        ))
        self.auto_checkbox = QCheckBox("Activer l'exécution automatique sur signaux")
        self.auto_checkbox.toggled.connect(self._on_auto_toggle)
        layout.addWidget(self.auto_checkbox)

        warning = QLabel(
            "⚠️ Testez d'abord en Simulation. Chaque signal détecté (y compris les faux "
            "positifs) déclenchera un ordre réel si le broker actif n'est pas la Simulation."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color:#ffb300;")
        layout.addWidget(warning)
        layout.addStretch()
        return tab

    def _on_auto_toggle(self, checked: bool) -> None:
        if checked:
            confirm = QMessageBox.warning(
                self, "Confirmation requise",
                "Vous êtes sur le point d'activer l'exécution AUTOMATIQUE d'ordres à partir "
                "des signaux Order Flow détectés.\n\n"
                "Chaque signal déclenchera un ordre marché réel (selon le broker actif).\n\n"
                "Confirmez-vous l'activation ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                self.auto_checkbox.blockSignals(True)
                self.auto_checkbox.setChecked(False)
                self.auto_checkbox.blockSignals(False)
                return
        self.engine.auto_trading_enabled = checked
        self.bus.publish(EventBus.EVT_LOG, {
            "level": "WARNING" if checked else "INFO",
            "msg": f"[OrderFlow][{self.engine.symbol}] Trading automatique {'ACTIVÉ' if checked else 'désactivé'}.",
        })
