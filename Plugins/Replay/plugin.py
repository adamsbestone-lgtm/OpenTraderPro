"""
Replay (plugin) - ajoute un dock avec les contrôles de relecture d'une
séance enregistrée : Play/Pause, vitesse, retour/avance, curseur de
progression. S'appuie sur Engines/ReplayEngine.py (déjà instancié dans
main.py et accessible via main_window.replay_engine).
"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QSlider, QLabel, QDockWidget, QDateTimeEdit, QLineEdit
)

from Plugins.PluginBase import PluginBase
from Core.EventBus import EventBus


class ReplayControlWidget(QWidget):
    def __init__(self, bus: EventBus, replay_engine, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.replay_engine = replay_engine
        self._build_ui()
        self.bus.subscribe(EventBus.EVT_REPLAY_STATE, self._on_state)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        load_row = QHBoxLayout()
        self.symbol_edit = QLineEdit("ESU6")
        load_row.addWidget(QLabel("Symbole :"))
        load_row.addWidget(self.symbol_edit)
        load_btn = QPushButton("Charger la séance du jour")
        load_btn.clicked.connect(self._load_today)
        load_row.addWidget(load_btn)
        layout.addLayout(load_row)

        controls_row = QHBoxLayout()
        back_btn = QPushButton("⏮ -10")
        back_btn.clicked.connect(lambda: self.replay_engine.step_backward(10))
        play_btn = QPushButton("▶ Lecture")
        play_btn.clicked.connect(self.replay_engine.play)
        pause_btn = QPushButton("⏸ Pause")
        pause_btn.clicked.connect(self.replay_engine.pause)
        fwd_btn = QPushButton("+10 ⏭")
        fwd_btn.clicked.connect(lambda: self.replay_engine.step_forward(10))

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["x1", "x2", "x4", "x10", "x100"])
        self.speed_combo.currentTextChanged.connect(
            lambda text: self.replay_engine.set_speed(float(text.replace("x", "")))
        )

        for w in (back_btn, play_btn, pause_btn, fwd_btn, self.speed_combo):
            controls_row.addWidget(w)
        layout.addLayout(controls_row)

        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.sliderReleased.connect(
            lambda: self.replay_engine.seek(self.progress_slider.value())
        )
        layout.addWidget(self.progress_slider)

        self.status_label = QLabel("Aucune séance chargée.")
        layout.addWidget(self.status_label)
        layout.addStretch()

    def _load_today(self) -> None:
        import time
        symbol = self.symbol_edit.text().strip() or "ESU6"
        now = time.time()
        count = self.replay_engine.load_session(symbol, now - 86400, now)
        self.progress_slider.setMaximum(max(0, count - 1))
        self.status_label.setText(f"Séance chargée : {count} événements pour {symbol}.")

    def _on_state(self, state: dict) -> None:
        self.progress_slider.setMaximum(max(0, state["total"] - 1))
        self.progress_slider.blockSignals(True)
        self.progress_slider.setValue(state["cursor"])
        self.progress_slider.blockSignals(False)
        self.status_label.setText(f"{state['state']} — {state['cursor']}/{state['total']}")


class Plugin(PluginBase):
    name = "Replay"

    def on_load(self) -> None:
        replay_engine = getattr(self.main_window, "replay_engine", None)
        if replay_engine is None:
            self.bus.publish(EventBus.EVT_LOG, {
                "level": "ERROR",
                "msg": "Plugin Replay : aucun ReplayEngine trouvé sur la fenêtre principale.",
            })
            return

        self._dock = QDockWidget("Replay", self.main_window)
        self._dock.setWidget(ReplayControlWidget(self.bus, replay_engine))
        self.main_window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._dock)
        self.bus.publish(EventBus.EVT_LOG, {"level": "INFO", "msg": "Plugin 'Replay' chargé."})

    def on_unload(self) -> None:
        if hasattr(self, "_dock"):
            self.main_window.removeDockWidget(self._dock)
            self._dock.deleteLater()
