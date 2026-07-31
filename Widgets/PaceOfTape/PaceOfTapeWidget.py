"""
PaceOfTapeWidget.py - jauge "Pace of Tape" (Smart Gauge) façon Jigsaw
daytradr : visualise en un coup d'oeil le rythme actuel du marché
(rapide/lent) par rapport à sa moyenne récente. Alimentée par
Engines/PaceOfTapeEngine.py (EVT_PACE_OF_TAPE).
"""
from __future__ import annotations
import math

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from Core.EventBus import EventBus


class _GaugeCanvas(QWidget):
    """Dessin de la jauge en demi-cercle : zones colorées + aiguille."""

    def __init__(self, colors: dict, cfg: dict, parent=None) -> None:
        super().__init__(parent)
        self.colors = colors
        self.cfg = cfg
        self.ratio = 1.0
        self.setMinimumHeight(140)

    def set_ratio(self, ratio: float) -> None:
        self.ratio = max(0.0, ratio)
        self.update()

    @staticmethod
    def _angle_for_fraction(f: float) -> float:
        f = min(1.0, max(0.0, f))
        return 180.0 * (1.0 - f)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        margin = 16
        size = max(60, min(w - 2 * margin, (h - 40) * 2))
        rect = QRectF((w - size) / 2, margin, size, size)

        extreme = self.cfg.get("extreme_threshold", 3.0)
        max_ratio = extreme * 1.3 if extreme > 0 else 4.0
        zones = [
            (0.0, self.cfg.get("calm_threshold", 0.5), self.colors.get("pace_calm", "#5f7799")),
            (self.cfg.get("calm_threshold", 0.5), self.cfg.get("active_threshold", 1.5), self.colors.get("pace_normal", "#2f7dfd")),
            (self.cfg.get("active_threshold", 1.5), extreme, self.colors.get("pace_active", "#ffb300")),
            (extreme, max_ratio, self.colors.get("pace_extreme", "#ff1744")),
        ]

        pen_width = max(10, int(size * 0.08))
        arc_rect = rect.adjusted(pen_width / 2, pen_width / 2, -pen_width / 2, -pen_width / 2)
        for lo, hi, color in zones:
            f_lo, f_hi = lo / max_ratio, min(1.0, hi / max_ratio)
            start_angle = self._angle_for_fraction(f_hi)
            end_angle = self._angle_for_fraction(f_lo)
            span = end_angle - start_angle
            pen = QPen(QColor(color))
            pen.setWidth(pen_width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawArc(arc_rect, int(start_angle * 16), int(span * 16))

        cx, cy = rect.center().x(), rect.center().y()
        radius = size / 2 - pen_width
        f = min(1.0, self.ratio / max_ratio)
        angle_rad = math.radians(self._angle_for_fraction(f))
        needle_x = cx + radius * math.cos(angle_rad)
        needle_y = cy - radius * math.sin(angle_rad)

        needle_pen = QPen(QColor("#e6e9ee"))
        needle_pen.setWidth(3)
        painter.setPen(needle_pen)
        painter.drawLine(int(cx), int(cy), int(needle_x), int(needle_y))
        painter.setBrush(QColor("#e6e9ee"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(cx) - 5, int(cy) - 5, 10, 10)

        painter.end()


class PaceOfTapeWidget(QWidget):
    """Jauge de rythme du marché (Smart Gauge), façon Jigsaw daytradr."""

    def __init__(self, bus: EventBus, symbol: str = "ESU6", settings=None, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.symbol = symbol
        self.colors = settings.get("colors", {}) if settings else {}
        self.cfg = settings.get("pace_of_tape", {}) if settings else {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.canvas = _GaugeCanvas(self.colors, self.cfg, self)
        layout.addWidget(self.canvas)

        self.status_label = QLabel("Normal — ratio 1.00x")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        self.status_label.setFont(font)
        layout.addWidget(self.status_label)

        self.detail_label = QLabel("0.0 / 0.0 lots/s (court terme / référence)")
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setStyleSheet("color:#8a93a1;")
        layout.addWidget(self.detail_label)

        self.bus.subscribe(EventBus.EVT_PACE_OF_TAPE, self._on_pace)

    def _on_pace(self, payload: dict) -> None:
        if payload.get("symbol") != self.symbol:
            return
        ratio = payload.get("ratio", 1.0)
        category = payload.get("category", "Normal")
        self.canvas.set_ratio(ratio)

        color = {
            "Calme": self.colors.get("pace_calm", "#5f7799"),
            "Normal": self.colors.get("pace_normal", "#2f7dfd"),
            "Actif": self.colors.get("pace_active", "#ffb300"),
            "Extrême": self.colors.get("pace_extreme", "#ff1744"),
        }.get(category, "#e6e9ee")
        self.status_label.setStyleSheet(f"color:{color};")
        self.status_label.setText(f"{category} — ratio {ratio:.2f}x")
        self.detail_label.setText(
            f"{payload.get('short_rate', 0):.1f} / {payload.get('baseline_rate', 0):.1f} lots/s (court terme / référence)"
        )
