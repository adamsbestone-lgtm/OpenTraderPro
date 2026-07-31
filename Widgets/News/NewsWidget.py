"""
NewsWidget.py - flux d'actualités + calendrier économique (à brancher sur
un plugin de flux réel : publie sur EventBus.EVT_NEWS pour alimenter ce widget).
"""
from __future__ import annotations
from datetime import datetime
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QListWidget, QListWidgetItem

from Core.EventBus import EventBus


class NewsWidget(QWidget):
    def __init__(self, bus: EventBus, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        tabs = QTabWidget()
        self.news_list = QListWidget()
        self.calendar_list = QListWidget()
        tabs.addTab(self.news_list, "Actualités")
        tabs.addTab(self.calendar_list, "Calendrier économique")
        layout.addWidget(tabs)

        self.bus.subscribe(EventBus.EVT_NEWS, self._on_news)

    def _on_news(self, news: dict) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        target = self.calendar_list if news.get("category") == "calendar" else self.news_list
        target.insertItem(0, QListWidgetItem(f"[{ts}] {news.get('headline', str(news))}"))
