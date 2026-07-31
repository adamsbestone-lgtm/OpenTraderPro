"""
PluginEngine.py - découvre et charge les plugins dans Plugins/<Nom>/.
Chaque plugin fournit plugin.json (métadonnées) et plugin.py (classe
Plugin héritant de PluginBase).
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
from typing import Dict

from Plugins.PluginBase import PluginBase

PLUGINS_DIR = Path(__file__).parent


class PluginEngine:
    def __init__(self, bus) -> None:
        self.bus = bus
        self.loaded: Dict[str, PluginBase] = {}

    def discover(self) -> list[str]:
        return [f.name for f in PLUGINS_DIR.iterdir()
                if f.is_dir() and (f / "plugin.json").exists() and (f / "plugin.py").exists()]

    def load(self, plugin_name: str, main_window) -> PluginBase | None:
        folder = PLUGINS_DIR / plugin_name
        meta_path, plugin_path = folder / "plugin.json", folder / "plugin.py"
        if not meta_path.exists() or not plugin_path.exists():
            return None
        json.loads(meta_path.read_text(encoding="utf-8"))  # validation

        spec = importlib.util.spec_from_file_location(f"plugins.{plugin_name}.plugin", plugin_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        instance: PluginBase = module.Plugin(self.bus, main_window)
        instance.on_load()
        self.loaded[plugin_name] = instance
        return instance

    def unload(self, plugin_name: str) -> None:
        plugin = self.loaded.pop(plugin_name, None)
        if plugin:
            plugin.on_unload()
