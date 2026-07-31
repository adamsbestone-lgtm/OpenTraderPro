"""
SignalAI.py - filtre IA optionnel pour le bot InstitutionalOrderFlow.

Entraîne un classifieur (régression logistique, scikit-learn) sur les
trades simulés par Engines/BacktestEngine.py sur l'historique (replay)
pour estimer, pour un futur signal détecté en direct, la probabilité que
le trade atteigne son objectif (ex : 1 à 5 ticks ou plus) avant son stop.
Le bot peut alors n'entrer que sur les signaux dont la probabilité
dépasse un seuil configurable (ex : 0.55), au lieu de prendre chaque
signal détecté.

Dégradation gracieuse : si scikit-learn n'est pas installé, un score de
repli est utilisé (taux de réussite historique observé par règle sur le
backtest) -- moins fin qu'un modèle appris, mais fonctionnel sans
dépendance supplémentaire (cf. Core/Security.py pour le même principe
avec le paquet `cryptography`).

⚠️ Outil d'aide à la décision statistique sur données passées : les
performances passées (même backtestées) ne garantissent pas les
performances futures. Rien ici ne constitue un conseil en investissement.
"""
from __future__ import annotations
import pickle
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

try:
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    _HAS_SKLEARN = True
except ImportError:  # pragma: no cover - dégradation gracieuse si absent
    _HAS_SKLEARN = False

MODEL_PATH = Path("Database/signal_ai_model.pkl")

# Doit rester synchronisé avec Plugins/OrderFlowSuite/model.py (SignalType)
SIGNAL_TYPES = [
    "IMBALANCE_WALL", "ABSORPTION", "SWEEP", "STOP_CASCADE", "OUT_OF_SPREAD",
    "DEFENDED_ZONE", "INSIDE_PRINT", "ORDER_REUSE", "SWEEP_DEFENSE",
    "CROSS_CONFIRMED", "CONFLUENCE",
]


def _featurize(signal_type: str, size: int, mode: str):
    one_hot = [1.0 if signal_type == t else 0.0 for t in SIGNAL_TYPES]
    return one_hot + [min(size, 500) / 500.0, 1.0 if mode == "with" else 0.0]


class SignalAI:
    """Un seul modèle par symbole/instance ; persisté sur disque (pickle)."""

    def __init__(self, path: Path = MODEL_PATH) -> None:
        self.path = path
        self.model = None
        self._fallback_rates: Dict[str, float] = {}
        self.load()

    @property
    def available(self) -> bool:
        return self.model is not None or bool(self._fallback_rates)

    @property
    def backend(self) -> str:
        if self.model is not None:
            return "logistic_regression (scikit-learn)"
        if self._fallback_rates:
            return "taux de réussite historique (repli, sans scikit-learn)"
        return "non entraîné"

    def train(self, trades: List, rule_mode: Dict[str, str]) -> dict:
        """`trades` : liste d'Engines.BacktestEngine.SimulatedTrade.
        Retourne un petit rapport (backend utilisé, nb d'exemples, accuracy)."""
        usable = [t for t in trades if t.outcome in ("win", "loss")]
        if len(usable) < 20:
            return {"trained": False, "reason": "pas assez d'exemples (mini 20 trades gagnés/perdus)", "n": len(usable)}

        wins, total = defaultdict(int), defaultdict(int)
        for t in usable:
            total[t.rule_name] += 1
            wins[t.rule_name] += 1 if t.outcome == "win" else 0
        self._fallback_rates = {r: wins[r] / total[r] for r in total}

        if not _HAS_SKLEARN:
            self.save()
            return {"trained": True, "backend": self.backend, "n": len(usable)}

        X = np.array([_featurize(t.signal_type, t.signal_size, rule_mode.get(t.rule_name, "with")) for t in usable])
        y = np.array([1 if t.outcome == "win" else 0 for t in usable])
        self.model = LogisticRegression(max_iter=1000, class_weight="balanced")
        self.model.fit(X, y)
        train_accuracy = float(self.model.score(X, y))
        self.save()
        return {"trained": True, "backend": self.backend, "n": len(usable), "train_accuracy": train_accuracy}

    def predict_proba(self, signal_type: str, size: int, rule_name: str, mode: str) -> float:
        """Probabilité estimée [0, 1] que le trade atteigne son objectif."""
        if self.model is not None and _HAS_SKLEARN:
            x = np.array([_featurize(signal_type, size, mode)])
            return float(self.model.predict_proba(x)[0][1])
        return self._fallback_rates.get(rule_name, 0.5)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "wb") as f:
            pickle.dump({"model": self.model, "fallback_rates": self._fallback_rates}, f)

    def load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "rb") as f:
                    data = pickle.load(f)
                self.model = data.get("model")
                self._fallback_rates = data.get("fallback_rates", {})
            except Exception:
                self.model, self._fallback_rates = None, {}
