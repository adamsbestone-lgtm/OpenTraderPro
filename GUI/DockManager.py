"""
DockManager.py - sauvegarde/restauration des espaces de travail (layouts
illimités, import/export). Persisté dans la table `workspaces` de la
base SQLite plutôt qu'en fichiers JSON séparés (cf. Core/Database.py).
"""
from __future__ import annotations
import json
from pathlib import Path

from PySide6.QtCore import QByteArray

from Core.Database import Database


class DockManager:
    def __init__(self, main_window, db: Database) -> None:
        self.main_window = main_window
        self.db = db

    def list_workspaces(self) -> list[str]:
        return self.db.list_workspaces()

    def save(self, name: str) -> None:
        state = bytes(self.main_window.saveState().toBase64()).decode("ascii")
        geometry = bytes(self.main_window.saveGeometry().toBase64()).decode("ascii")
        self.db.save_workspace(name, state, geometry)

    def restore(self, name: str) -> bool:
        row = self.db.load_workspace(name)
        if not row:
            return False
        state_b64, geometry_b64 = row
        self.main_window.restoreGeometry(QByteArray.fromBase64(geometry_b64.encode("ascii")))
        self.main_window.restoreState(QByteArray.fromBase64(state_b64.encode("ascii")))
        return True

    # -- import / export (fichier JSON portable, pour partager un layout) -------
    def export_to_file(self, name: str, path: str | Path) -> bool:
        row = self.db.load_workspace(name)
        if not row:
            return False
        state_b64, geometry_b64 = row
        Path(path).write_text(json.dumps({"name": name, "state": state_b64, "geometry": geometry_b64}), encoding="utf-8")
        return True

    def import_from_file(self, path: str | Path) -> str:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.db.save_workspace(payload["name"], payload["state"], payload["geometry"])
        return payload["name"]
