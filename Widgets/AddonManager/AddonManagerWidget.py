"""
AddonManagerWidget.py - fenêtre "Add-ons" : liste tous les plugins
découverts par PluginEngine (Plugins/<Nom>/plugin.json + plugin.py),
affiche nom/version/description, et permet de les charger/décharger
à chaud sans redémarrer l'application.
"""
from __future__ import annotations
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QAbstractItemView, QLabel, QCheckBox
)

from Core.EventBus import EventBus
from Engines.PluginEngine import PluginEngine

COLUMNS = ["Actif", "Nom", "Version", "Description"]
PLUGINS_DIR = Path("Plugins")


class AddonManagerWidget(QWidget):
    """Fenêtre de gestion des add-ons (plugins). Chaque ligne correspond à
    un dossier Plugins/<Nom>/ ; la case à cocher charge/décharge le plugin
    en direct via PluginEngine."""

    def __init__(self, bus: EventBus, plugin_engine: PluginEngine, main_window, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.plugin_engine = plugin_engine
        self.main_window = main_window
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("<b>Add-ons disponibles</b>"))
        toolbar.addStretch()
        refresh_btn = QPushButton("Rafraîchir")
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    def refresh(self) -> None:
        names = self.plugin_engine.discover()
        self.table.setRowCount(len(names))

        for row, name in enumerate(names):
            meta_path = PLUGINS_DIR / name / "plugin.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

            checkbox = QCheckBox()
            checkbox.setChecked(name in self.plugin_engine.loaded)
            checkbox.toggled.connect(lambda checked, n=name: self._toggle(n, checked))
            checkbox_container = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_container)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 0, checkbox_container)

            self.table.setItem(row, 1, QTableWidgetItem(meta.get("name", name)))
            self.table.setItem(row, 2, QTableWidgetItem(meta.get("version", "-")))
            self.table.setItem(row, 3, QTableWidgetItem(meta.get("description", "")))

    def _toggle(self, name: str, checked: bool) -> None:
        if checked:
            self.plugin_engine.load(name, self.main_window)
        else:
            self.plugin_engine.unload(name)
        self.bus.publish(EventBus.EVT_LOG, {
            "level": "INFO",
            "msg": f"Add-on '{name}' {'chargé' if checked else 'déchargé'} depuis le gestionnaire d'add-ons.",
        })
