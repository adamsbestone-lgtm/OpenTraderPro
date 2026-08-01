"""
BrokerLoginDialog.py - fenêtre de connexion générique pour les brokers
nécessitant des identifiants (Tradovate, CQG, Rithmic, Interactive Brokers,
Binance...). Les champs affichés sont générés dynamiquement à partir de
`required_credentials` de chaque broker (voir Brokers/BaseBroker.py).

Les identifiants sont chiffrés (Core/Security.py, Fernet) et stockés dans
Settings sous "brokers.credentials.<nom_broker>" si l'utilisateur coche
"Se souvenir de moi". Rien n'est jamais stocké en clair.
"""
from __future__ import annotations
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
    QPushButton, QCheckBox, QRadioButton, QButtonGroup, QDialogButtonBox,
    QMessageBox,
)

from Core.Security import CredentialVault

# Champs traités comme des mots de passe (masqués à l'affichage)
_SECRET_FIELDS = {"password", "app_secret", "secret", "sec", "client_secret", "api_secret", "key"}

# Libellés plus parlants que les noms de clés bruts
_LABELS = {
    "username": "Nom d'utilisateur",
    "password": "Mot de passe",
    "app_id": "App ID",
    "app_secret": "App Secret",
    "cid": "CID (Client ID Tradovate)",
    "sec": "SEC (Client Secret Tradovate)",
    "client_id": "Client ID",
    "client_secret": "Client Secret",
    "system_name": "Nom du système (Rithmic)",
    "gateway": "Gateway (Rithmic)",
    "host": "Hôte",
    "port": "Port",
    "api_key": "Clé API",
    "api_secret": "Secret API",
}


class BrokerLoginDialog(QDialog):
    def __init__(self, broker_name: str, required_credentials: tuple[str, ...],
                 settings, supports_environment: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Connexion à {broker_name}")
        self.setMinimumWidth(380)
        self.broker_name = broker_name
        self.required_credentials = required_credentials
        self.settings = settings
        self._vault = CredentialVault()
        self._fields: Dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)

        title = QLabel(f"<b>Identifiants — {broker_name}</b>")
        layout.addWidget(title)

        form = QFormLayout()
        layout.addLayout(form)

        if supports_environment:
            env_row = QHBoxLayout()
            self.rb_demo = QRadioButton("Demo")
            self.rb_live = QRadioButton("Live")
            self.rb_demo.setChecked(True)
            group = QButtonGroup(self)
            group.addButton(self.rb_demo)
            group.addButton(self.rb_live)
            env_row.addWidget(self.rb_demo)
            env_row.addWidget(self.rb_live)
            form.addRow("Environnement :", env_row)
        else:
            self.rb_demo = None
            self.rb_live = None

        for key in required_credentials:
            field = QLineEdit()
            if key in _SECRET_FIELDS:
                field.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow(_LABELS.get(key, key.replace("_", " ").capitalize()) + " :", field)
            self._fields[key] = field

        self.remember_checkbox = QCheckBox("Se souvenir de moi sur cet ordinateur (chiffré)")
        layout.addWidget(self.remember_checkbox)

        self._prefill_saved_credentials()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Se connecter")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.result_credentials: Optional[Dict[str, Any]] = None

    # -- persistance (chiffrée) des identifiants -------------------------------------
    def _saved_blob(self) -> Optional[str]:
        return self.settings.get("brokers", {}).get("credentials", {}).get(self.broker_name)

    def _prefill_saved_credentials(self) -> None:
        blob = self._saved_blob()
        if not blob or not self._vault.available:
            return
        try:
            saved = self._vault.decrypt(blob)
        except Exception:
            return
        for key, field in self._fields.items():
            if key in saved:
                field.setText(str(saved[key]))
        if self.rb_live is not None and saved.get("environment") == "live":
            self.rb_live.setChecked(True)
        if saved:
            self.remember_checkbox.setChecked(True)

    def _save_credentials(self, credentials: Dict[str, Any]) -> None:
        if not self._vault.available:
            QMessageBox.warning(
                self, "Chiffrement indisponible",
                "Le paquet 'cryptography' est requis pour enregistrer les identifiants "
                "en toute sécurité. Ils ne seront pas mémorisés cette fois-ci.",
            )
            return
        brokers_cfg = dict(self.settings.get("brokers", {}))
        creds_map = dict(brokers_cfg.get("credentials", {}))
        creds_map[self.broker_name] = self._vault.encrypt(credentials)
        brokers_cfg["credentials"] = creds_map
        self.settings.set("brokers", brokers_cfg)

    def _forget_credentials(self) -> None:
        brokers_cfg = dict(self.settings.get("brokers", {}))
        creds_map = dict(brokers_cfg.get("credentials", {}))
        if self.broker_name in creds_map:
            del creds_map[self.broker_name]
            brokers_cfg["credentials"] = creds_map
            self.settings.set("brokers", brokers_cfg)

    # -- validation -------------------------------------------------------------------
    def _on_accept(self) -> None:
        credentials: Dict[str, Any] = {}
        missing = []
        for key, field in self._fields.items():
            value = field.text().strip()
            if not value:
                missing.append(_LABELS.get(key, key))
            credentials[key] = value

        if missing:
            QMessageBox.warning(
                self, "Champs manquants",
                "Merci de renseigner : " + ", ".join(missing),
            )
            return

        if self.rb_live is not None:
            credentials["environment"] = "live" if self.rb_live.isChecked() else "demo"

        if self.remember_checkbox.isChecked():
            self._save_credentials(credentials)
        else:
            self._forget_credentials()

        self.result_credentials = credentials
        self.accept()
