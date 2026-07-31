"""
BacktestWidget.py - dock permettant de rejouer l'historique enregistré
(jours ou mois passés, via Core/Database) pour évaluer chaque technique
(rejection, sweep, reversal, cassure de déséquilibre, cascade de stops,
confluence -- les mêmes règles que Bots/InstitutionalOrderFlow) AVANT de
les activer en direct, puis d'entraîner le filtre IA
(Engines/SignalAI.py) sur les résultats obtenus.

Le backtest tourne dans un QThread pour ne pas geler l'interface, même
sur plusieurs mois de données.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QObject, QDateTime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QDateTimeEdit, QDoubleSpinBox, QSpinBox, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QCheckBox, QProgressBar
)

from Core.Database import Database
from Engines.BacktestEngine import BacktestEngine, BacktestReport
from Engines.SignalAI import SignalAI
from Plugins.OrderFlowSuite.rules import RULE_MODE

BOT_JSON_PATH = Path("Bots/InstitutionalOrderFlow/bot.json")
RULE_LABELS = {
    "sweep_fade": "Fade de sweep (rejet)",
    "rejection_absorption": "Rejet sur absorption",
    "sweep_defense_reversal": "Retournement après défense de sweep",
    "imbalance_breakout": "Cassure sur déséquilibre",
    "stop_cascade_follow": "Suivi de cascade de stops",
    "confluence_high_conviction": "Confluence (conviction forte)",
}


class _BacktestWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(object)  # BacktestReport
    failed = Signal(str)

    def __init__(self, db: Database, symbol: str, tick_size: float,
                 ts_from: float, ts_to: float, rules_cfg: dict,
                 stop_loss_ticks: float, take_profit_ticks: float, timeout_s: float) -> None:
        super().__init__()
        self.db, self.symbol, self.tick_size = db, symbol, tick_size
        self.ts_from, self.ts_to, self.rules_cfg = ts_from, ts_to, rules_cfg
        self.stop_loss_ticks, self.take_profit_ticks, self.timeout_s = stop_loss_ticks, take_profit_ticks, timeout_s

    def run(self) -> None:
        try:
            engine = BacktestEngine(self.db, self.symbol, self.tick_size)
            report = engine.run(
                self.ts_from, self.ts_to, self.rules_cfg,
                stop_loss_ticks=self.stop_loss_ticks, take_profit_ticks=self.take_profit_ticks,
                timeout_s=self.timeout_s, progress_cb=lambda i, n: self.progress.emit(i, n),
            )
            self.finished.emit(report)
        except Exception as exc:  # remonte proprement plutôt que de crasher le thread
            self.failed.emit(str(exc))


class BacktestWidget(QWidget):
    def __init__(self, db: Database, symbol: str = "ESU6", settings=None, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.symbol = symbol
        self.tick_size = settings.get("dom_tick_size", 0.25) if settings else 0.25
        self._last_report: BacktestReport | None = None
        self._thread: QThread | None = None
        self._worker: _BacktestWorker | None = None
        self.ai = SignalAI()

        self._rules_cfg = self._load_default_rules()
        self._build_ui()

    # -- config par défaut (identique au bot temps réel) -----------------------
    def _load_default_rules(self) -> dict:
        try:
            data = json.loads(BOT_JSON_PATH.read_text(encoding="utf-8"))
            return data.get("params", {}).get("rules", {})
        except Exception:
            return {name: {"enabled": True, "min_size": 0} for name in RULE_LABELS}

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        period_box = QGroupBox("Période historique à rejouer")
        period_form = QFormLayout(period_box)
        self.date_from = QDateTimeEdit()
        self.date_to = QDateTimeEdit()
        for w in (self.date_from, self.date_to):
            w.setCalendarPopup(True)
            w.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._prefill_dates()
        period_form.addRow("Du :", self.date_from)
        period_form.addRow("Au :", self.date_to)

        quick_row = QHBoxLayout()
        for label, days in (("1 jour", 1), ("1 semaine", 7), ("1 mois", 30), ("3 mois", 90), ("Tout", None)):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, d=days: self._quick_range(d))
            quick_row.addWidget(btn)
        period_form.addRow(quick_row)
        layout.addWidget(period_box)

        risk_box = QGroupBox("Paramètres de trade simulé")
        risk_form = QFormLayout(risk_box)
        self.stop_ticks = QDoubleSpinBox()
        self.stop_ticks.setRange(1, 100)
        self.stop_ticks.setValue(6)
        self.target_ticks = QDoubleSpinBox()
        self.target_ticks.setRange(1, 100)
        self.target_ticks.setValue(3)
        self.target_ticks.setToolTip("Objectif en ticks (ex : entre 1 et 5, ou plus)")
        self.timeout_s = QSpinBox()
        self.timeout_s.setRange(5, 3600)
        self.timeout_s.setValue(180)
        risk_form.addRow("Stop (ticks) :", self.stop_ticks)
        risk_form.addRow("Objectif (ticks) :", self.target_ticks)
        risk_form.addRow("Timeout (s) :", self.timeout_s)
        layout.addWidget(risk_box)

        rules_box = QGroupBox("Techniques à tester")
        rules_layout = QVBoxLayout(rules_box)
        self._rule_checks: dict[str, QCheckBox] = {}
        self._rule_min_size: dict[str, QSpinBox] = {}
        for rule_name, label in RULE_LABELS.items():
            row = QHBoxLayout()
            cfg = self._rules_cfg.get(rule_name, {})
            chk = QCheckBox(label)
            chk.setChecked(cfg.get("enabled", True))
            row.addWidget(chk)
            row.addWidget(QLabel("taille min :"))
            spin = QSpinBox()
            spin.setRange(0, 5000)
            spin.setValue(cfg.get("min_size", 0))
            row.addWidget(spin)
            row.addStretch()
            rules_layout.addLayout(row)
            self._rule_checks[rule_name] = chk
            self._rule_min_size[rule_name] = spin
        layout.addWidget(rules_box)

        action_row = QHBoxLayout()
        self.run_btn = QPushButton("▶ Lancer le backtest")
        self.run_btn.clicked.connect(self._run_backtest)
        action_row.addWidget(self.run_btn)
        self.train_btn = QPushButton("🤖 Entraîner l'IA sur ces résultats")
        self.train_btn.setEnabled(False)
        self.train_btn.clicked.connect(self._train_ai)
        action_row.addWidget(self.train_btn)
        layout.addLayout(action_row)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel("Prêt.")
        layout.addWidget(self.status_label)

        self.results_table = QTableWidget(0, 6)
        self.results_table.setHorizontalHeaderLabels(
            ["Technique", "Trades", "Gagnés", "Taux de réussite", "Ticks moy./trade", "Ticks total"])
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.results_table)

    def _prefill_dates(self) -> None:
        rng = self.db.get_recorded_range(self.symbol)
        now = QDateTime.currentDateTime()
        if rng:
            ts_from, ts_to = rng
            self.date_from.setDateTime(QDateTime.fromSecsSinceEpoch(int(ts_from)))
            self.date_to.setDateTime(QDateTime.fromSecsSinceEpoch(int(ts_to)))
        else:
            self.date_from.setDateTime(now.addDays(-30))
            self.date_to.setDateTime(now)

    def _quick_range(self, days) -> None:
        rng = self.db.get_recorded_range(self.symbol)
        to_dt = QDateTime.fromSecsSinceEpoch(int(rng[1])) if rng else QDateTime.currentDateTime()
        self.date_to.setDateTime(to_dt)
        if days is None and rng:
            self.date_from.setDateTime(QDateTime.fromSecsSinceEpoch(int(rng[0])))
        else:
            self.date_from.setDateTime(to_dt.addDays(-(days or 30)))

    # -- exécution du backtest (thread séparé) ---------------------------------
    def _run_backtest(self) -> None:
        if self._thread is not None:
            return  # backtest déjà en cours

        rules_cfg = {
            name: {"enabled": self._rule_checks[name].isChecked(), "min_size": self._rule_min_size[name].value()}
            for name in RULE_LABELS
        }
        ts_from = self.date_from.dateTime().toSecsSinceEpoch()
        ts_to = self.date_to.dateTime().toSecsSinceEpoch()

        self.run_btn.setEnabled(False)
        self.status_label.setText("Chargement de l'historique et rejeu en cours...")
        self.progress_bar.setValue(0)

        self._thread = QThread(self)
        self._worker = _BacktestWorker(
            self.db, self.symbol, self.tick_size, ts_from, ts_to, rules_cfg,
            self.stop_ticks.value(), self.target_ticks.value(), self.timeout_s.value(),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress_bar.setMaximum(max(1, total))
        self.progress_bar.setValue(done)

    def _on_finished(self, report: BacktestReport) -> None:
        self._last_report = report
        self._populate_results(report)
        n = len(report.trades)
        self.status_label.setText(f"Terminé : {report.events_processed} événements rejoués, {n} trades simulés.")
        self.train_btn.setEnabled(n >= 20)
        self.run_btn.setEnabled(True)

    def _on_failed(self, message: str) -> None:
        self.status_label.setText(f"Échec du backtest : {message}")
        self.run_btn.setEnabled(True)

    def _cleanup_thread(self) -> None:
        self._thread = None
        self._worker = None

    def _populate_results(self, report: BacktestReport) -> None:
        stats = report.by_rule()
        self.results_table.setRowCount(len(stats))
        for row, (rule_name, s) in enumerate(sorted(stats.items(), key=lambda kv: -kv[1]["trades"])):
            values = [
                RULE_LABELS.get(rule_name, rule_name), str(s["trades"]), str(s["wins"]),
                f"{s['win_rate'] * 100:.1f} %", f"{s['avg_ticks']:+.2f}", f"{s['total_ticks']:+.1f}",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.results_table.setItem(row, col, item)

    # -- entraînement IA ---------------------------------------------------------
    def _train_ai(self) -> None:
        if not self._last_report:
            return
        report = self.ai.train(self._last_report.trades, RULE_MODE)
        if not report.get("trained"):
            self.status_label.setText(f"IA non entraînée : {report.get('reason')}")
            return
        extra = f", précision entraînement={report['train_accuracy']*100:.1f}%" if "train_accuracy" in report else ""
        self.status_label.setText(
            f"IA entraînée sur {report['n']} trades ({report['backend']}){extra}. "
            f"Activez 'ai_filter' dans Bots/InstitutionalOrderFlow/bot.json pour l'utiliser en direct."
        )
