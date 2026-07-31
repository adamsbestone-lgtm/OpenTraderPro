"""
PluginBase.py - interface commune à tous les plugins (Plugins/<Nom>/).
Un plugin peut ajouter : widgets, menus, boutons, raccourcis, services,
indicateurs. Il reçoit le bus d'événements et la fenêtre principale.
"""
from __future__ import annotations
from abc import ABC, abstractmethod


class PluginBase(ABC):
    name: str = "UnnamedPlugin"

    def __init__(self, bus, main_window) -> None:
        self.bus = bus
        self.main_window = main_window

    @abstractmethod
    def on_load(self) -> None:
        """Enregistrer docks/menus/raccourcis/services ici."""

    def on_unload(self) -> None:
        """Nettoyer les widgets/menus ajoutés."""
