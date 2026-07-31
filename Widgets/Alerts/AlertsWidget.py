"""
AlertsWidget.py - alertes prix/volume/perte/profit/connexion.
"""
from __future__ import annotations
from datetime import datetime
from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem

from Core.EventBus import EventBus


class AlertsWidget(QWidget):
    def __init__(self, bus: EventBus, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        self.bus.subscribe(EventBus.EVT_ALERT, self._on_alert)
        self.bus.subscribe(EventBus.EVT_BROKER_DISCONNECTED, lambda p: self._add(f"Connexion perdue : {p.get('broker')}"))
        self.bus.subscribe(EventBus.EVT_RISK_LOCKOUT, lambda p: self._add(f"Perte max atteinte : {p.get('reason')}"))

    def _on_alert(self, alert: dict) -> None:
        self._add(alert.get("message", str(alert)))

    def _add(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.list_widget.insertItem(0, QListWidgetItem(f"[{ts}] {message}"))
