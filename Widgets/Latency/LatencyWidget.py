"""
LatencyWidget.py - affiche en direct les statistiques de latence mesurées
par Engines/LatencyMonitor.py : détection (tick -> signal) et exécution
(soumission d'ordre -> exécution), en p50/p95/p99/max.

Rafraîchi par QTimer (indépendant du flux de données, donc jamais un
goulot d'étranglement lui-même).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QGroupBox
)

from Engines.LatencyMonitor import LatencyMonitor


def _row(grid: QGridLayout, row: int, label: str, stats: dict) -> None:
    grid.addWidget(QLabel(label), row, 0)
    grid.addWidget(QLabel(f"{stats['p50']:.2f} ms"), row, 1)
    grid.addWidget(QLabel(f"{stats['p95']:.2f} ms"), row, 2)
    grid.addWidget(QLabel(f"{stats['p99']:.2f} ms"), row, 3)
    grid.addWidget(QLabel(f"{stats['max']:.2f} ms"), row, 4)


class LatencyWidget(QWidget):
    def __init__(self, monitor: LatencyMonitor, refresh_ms: int = 500, parent=None) -> None:
        super().__init__(parent)
        self.monitor = monitor

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        box = QGroupBox("Latence pipeline (fenêtre glissante)")
        self.grid = QGridLayout(box)
        headers = ["", "p50", "p95", "p99", "max"]
        for col, text in enumerate(headers):
            lbl = QLabel(f"<b>{text}</b>")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid.addWidget(lbl, 0, col)
        layout.addWidget(box)

        self.n_label = QLabel("En attente de données...")
        self.n_label.setStyleSheet("color:#8a93a1;")
        layout.addWidget(self.n_label)
        layout.addStretch()

        self._row_widgets: dict[str, list[QLabel]] = {}
        for i, (key, label) in enumerate([
            ("detection", "Détection (tick → signal)"),
            ("execution", "Exécution (ordre → fill)"),
        ], start=1):
            self.grid.addWidget(QLabel(label), i, 0)
            cells = []
            for col in range(1, 5):
                cell = QLabel("—")
                cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.grid.addWidget(cell, i, col)
                cells.append(cell)
            self._row_widgets[key] = cells

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(refresh_ms)
        self._refresh()

    def _refresh(self) -> None:
        stats = self.monitor.stats()
        for key, cells in self._row_widgets.items():
            s = stats[key]
            values = [f"{s['p50']:.2f} ms", f"{s['p95']:.2f} ms", f"{s['p99']:.2f} ms", f"{s['max']:.2f} ms"]
            for cell, value in zip(cells, values):
                cell.setText(value if s["n"] else "—")

        n_detect, n_exec = stats["detection"]["n"], stats["execution"]["n"]
        self.n_label.setText(f"{n_detect} signaux et {n_exec} exécutions mesurés (fenêtre glissante).")
