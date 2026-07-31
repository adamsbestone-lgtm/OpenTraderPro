"""
EventLogWidget.py - journal complet des événements système.
"""
from __future__ import annotations
from datetime import datetime
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem

from Core.EventBus import EventBus

LEVEL_COLORS = {"INFO": "#9aa0a6", "WARNING": "#ffb300", "ERROR": "#e53935", "CRITICAL": "#ff1744"}


class EventLogWidget(QWidget):
    def __init__(self, bus: EventBus, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)
        self.bus.subscribe(EventBus.EVT_LOG, self._on_log)

    def _on_log(self, entry: dict) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        level = entry.get("level", "INFO")
        item = QListWidgetItem(f"[{ts}] [{level}] {entry.get('msg', '')}")
        item.setForeground(QBrush(QColor(LEVEL_COLORS.get(level, "#d9e4f2"))))
        self.list_widget.insertItem(0, item)
        if self.list_widget.count() > 2000:
            self.list_widget.takeItem(self.list_widget.count() - 1)
