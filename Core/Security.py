"""
Security.py - chiffrement des identifiants de connexion aux brokers.

Utilise Fernet (cryptographie symétrique, module `cryptography`) : la
clé est générée une fois et stockée dans Database/secret.key (à exclure
du contrôle de version et à sauvegarder séparément par l'utilisateur).
Les identifiants ne sont donc jamais stockés en clair dans la base ou
les fichiers de configuration.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

try:
    from cryptography.fernet import Fernet
    _HAS_CRYPTO = True
except ImportError:  # pragma: no cover - dégradation gracieuse si le paquet manque
    _HAS_CRYPTO = False

KEY_PATH = Path("Database/secret.key")


class CredentialVault:
    def __init__(self) -> None:
        self._fernet = None
        if _HAS_CRYPTO:
            KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not KEY_PATH.exists():
                KEY_PATH.write_bytes(Fernet.generate_key())
            self._fernet = Fernet(KEY_PATH.read_bytes())

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def encrypt(self, credentials: Dict[str, Any]) -> str:
        raw = json.dumps(credentials).encode("utf-8")
        if not self._fernet:
            # Dégradation : pas de paquet `cryptography` installé -> avertit
            # clairement plutôt que de stocker en clair silencieusement.
            raise RuntimeError(
                "Le paquet 'cryptography' est requis pour chiffrer les identifiants "
                "(pip install cryptography)."
            )
        return self._fernet.encrypt(raw).decode("utf-8")

    def decrypt(self, token: str) -> Dict[str, Any]:
        if not self._fernet:
            raise RuntimeError("Le paquet 'cryptography' est requis pour déchiffrer les identifiants.")
        raw = self._fernet.decrypt(token.encode("utf-8"))
        return json.loads(raw.decode("utf-8"))
