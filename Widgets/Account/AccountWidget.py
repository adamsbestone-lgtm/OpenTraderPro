"""
AccountWidget.py - Solde, Marge, Buying Power, Drawdown, Commission,
Frais, avec Kill Switch et déverrouillage manuel.
"""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QPushButton, QVBoxLayout, QHBoxLayout

from Core.EventBus import EventBus
from Engines.RiskEngine import RiskEngine


class AccountWidget(QWidget):
    def __init__(self, bus: EventBus, risk_engine: RiskEngine, broker_engine, settings, parent=None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.risk_engine = risk_engine
        self.broker_engine = broker_engine
        self.settings = settings

        accounts = broker_engine.fetch_accounts()
        first_account = next(iter(accounts.values()), {"balance": 0.0, "margin_used": 0.0, "buying_power": 0.0})
        self.balance = first_account.get("balance", 0.0)
        self.peak_equity = self.balance

        self._build_ui()
        self.bus.subscribe(EventBus.EVT_POSITION_UPDATE, lambda p: self._refresh())
        self.bus.subscribe(EventBus.EVT_RISK_LOCKOUT, self._on_lockout)
        self.bus.subscribe(EventBus.EVT_RISK_KILL_SWITCH, self._on_kill_switch)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.balance_label = QLabel(f"{self.balance:.2f} $")
        self.margin_used_label = QLabel("0.00 $")
        self.buying_power_label = QLabel(f"{self.balance:.2f} $")
        self.drawdown_label = QLabel("0.00 $")
        self.commission_label = QLabel("0.00 $")
        self.max_risk_label = QLabel(f"{self.settings.get('risk', {}).get('max_daily_loss', 0):.2f} $")
        self.daily_pnl_label = QLabel("0.00 $")
        self.status_label = QLabel("🟢 Compte actif")

        form.addRow("Solde :", self.balance_label)
        form.addRow("Marge utilisée :", self.margin_used_label)
        form.addRow("Buying Power :", self.buying_power_label)
        form.addRow("Drawdown :", self.drawdown_label)
        form.addRow("Commissions :", self.commission_label)
        form.addRow("Risque max journalier :", self.max_risk_label)
        form.addRow("P&L journalier :", self.daily_pnl_label)
        form.addRow("État :", self.status_label)
        layout.addLayout(form)

        actions = QHBoxLayout()
        unlock_btn = QPushButton("Déverrouiller")
        unlock_btn.clicked.connect(self._unlock)
        actions.addWidget(unlock_btn)

        kill_btn = QPushButton("⛔ KILL SWITCH")
        kill_btn.setObjectName("killSwitchButton")
        kill_btn.clicked.connect(self.risk_engine.activate_kill_switch)
        actions.addWidget(kill_btn)

        resume_btn = QPushButton("Réactiver")
        resume_btn.clicked.connect(self.risk_engine.deactivate_kill_switch)
        actions.addWidget(resume_btn)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addStretch()

    def _refresh(self) -> None:
        total_pnl = self.risk_engine.daily_realized_pnl + self.risk_engine.daily_unrealized_pnl
        equity = self.balance + total_pnl
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = self.peak_equity - equity

        self.daily_pnl_label.setText(f"{total_pnl:+.2f} $")
        self.buying_power_label.setText(f"{equity:.2f} $")
        self.drawdown_label.setText(f"{drawdown:.2f} $")

    def _on_lockout(self, payload: dict) -> None:
        self.status_label.setText(f"🔴 VERROUILLÉ ({payload['reason']}, P&L={payload['pnl']:.2f})")

    def _on_kill_switch(self, payload: dict) -> None:
        self.status_label.setText("⛔ KILL SWITCH ACTIF" if payload["active"] else "🟢 Compte actif")

    def _unlock(self) -> None:
        self.risk_engine.unlock()
        self.status_label.setText("🟢 Compte actif")
