"""
MainWindow.py - fenêtre principale. Docking complet, multi-écran (géré
nativement par Qt via QMainWindow.restoreGeometry sur l'écran voulu),
thèmes, barre de menus, toolbar, status bar, sauvegarde du layout.

Docks affichés au lancement : DOM, Time & Sales, Orders, Positions,
Account, Alerts, News, Event Log, **Add-ons**, **HFT**.
"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QDockWidget, QMenuBar, QMenu, QToolBar,
    QInputDialog, QMessageBox, QFileDialog
)

from Core.EventBus import EventBus
from GUI.DockManager import DockManager
from GUI.Theme import get_theme

from Widgets.DOM.DOMWidget import DOMWidget
from Widgets.TimeSales.TimeSalesWidget import TimeSalesWidget
from Widgets.Orders.OrdersWidget import OrdersWidget
from Widgets.Positions.PositionsWidget import PositionsWidget
from Widgets.Account.AccountWidget import AccountWidget
from Widgets.Alerts.AlertsWidget import AlertsWidget
from Widgets.News.NewsWidget import NewsWidget
from Widgets.EventLog.EventLogWidget import EventLogWidget
from Widgets.AddonManager.AddonManagerWidget import AddonManagerWidget
from Widgets.HFT.HFTWidget import HFTWidget
from Widgets.ReconstructedTape.ReconstructedTapeWidget import ReconstructedTapeWidget
from Widgets.PaceOfTape.PaceOfTapeWidget import PaceOfTapeWidget
from Widgets.Backtest.BacktestWidget import BacktestWidget
from Widgets.Latency.LatencyWidget import LatencyWidget
from Engines.LatencyMonitor import LatencyMonitor


class MainWindow(QMainWindow):
    def __init__(self, bus: EventBus, db, settings, order_engine, position_engine,
                 risk_engine, bot_engine, plugin_engine, broker_engine, replay_engine,
                 latency_monitor=None) -> None:
        super().__init__()
        self.setWindowTitle("OpenTrader Pro")
        self.bus = bus
        self.db = db
        self.settings = settings
        self.order_engine = order_engine
        self.position_engine = position_engine
        self.risk_engine = risk_engine
        self.bot_engine = bot_engine
        self.plugin_engine = plugin_engine
        self.broker_engine = broker_engine
        self.replay_engine = replay_engine  # utilisé par le plugin Replay
        self.dock_manager = DockManager(self, db)

        symbol = settings.get("default_symbol", "ESU6")
        self.setDockNestingEnabled(True)
        self._docks: dict[str, QDockWidget] = {}

        self._add_dock("DOM", DOMWidget(bus, order_engine, position_engine, symbol=symbol, settings=settings),
                        Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("Time & Sales", TimeSalesWidget(bus, symbol=symbol),
                        Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("Reconstructed Tape", ReconstructedTapeWidget(bus, symbol=symbol, settings=settings),
                        Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("Pace of Tape", PaceOfTapeWidget(bus, symbol=symbol, settings=settings),
                        Qt.DockWidgetArea.RightDockWidgetArea)
        self._add_dock("Orders", OrdersWidget(bus, order_engine),
                        Qt.DockWidgetArea.RightDockWidgetArea)
        self._add_dock("Positions", PositionsWidget(bus, order_engine, position_engine, settings=settings),
                        Qt.DockWidgetArea.RightDockWidgetArea)
        self._add_dock("Account", AccountWidget(bus, risk_engine, broker_engine, settings),
                        Qt.DockWidgetArea.RightDockWidgetArea)
        self._add_dock("Alerts", AlertsWidget(bus),
                        Qt.DockWidgetArea.BottomDockWidgetArea)
        self._add_dock("News", NewsWidget(bus),
                        Qt.DockWidgetArea.BottomDockWidgetArea)
        self._add_dock("Event Log", EventLogWidget(bus),
                        Qt.DockWidgetArea.BottomDockWidgetArea)
        self._add_dock("Add-ons", AddonManagerWidget(bus, plugin_engine, self),
                        Qt.DockWidgetArea.RightDockWidgetArea)
        self._add_dock("HFT", HFTWidget(bus, bot_engine, settings, symbol=symbol),
                        Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("Backtest", BacktestWidget(db, symbol=symbol, settings=settings),
                        Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("Latence", LatencyWidget(latency_monitor or LatencyMonitor(bus)),
                        Qt.DockWidgetArea.RightDockWidgetArea)

        self._build_toolbar()
        self._build_menu()
        self._apply_default_layout_sizes()
        self.statusBar().showMessage(f"Connecté ({broker_engine.active_broker_name}) — {symbol}")

        bus.publish(EventBus.EVT_LOG, {"level": "INFO", "msg": "OpenTrader Pro démarré."})

    def _apply_default_layout_sizes(self) -> None:
        # Proportions par défaut façon Jigsaw daytradr : DOM étroit et haut
        # (ladder compact), tapes à sa droite, colonnes Orders/Positions/
        # Account plus larges, bandeau du bas (Alerts/News/Log) compact.
        # Jigsaw ne publie pas de dimensions officielles : ces valeurs sont
        # une disposition de départ raisonnable, ajustable puis enregistrable
        # via le menu "Espace de travail".
        left_docks = [self._docks[n] for n in ("DOM", "Time & Sales", "Reconstructed Tape", "HFT", "Backtest") if n in self._docks]
        if left_docks:
            self.resizeDocks(left_docks, [420, 220, 220, 180, 260], Qt.Orientation.Vertical)

        right_docks = [self._docks[n] for n in ("Pace of Tape", "Orders", "Positions", "Account", "Add-ons", "Latence") if n in self._docks]
        if right_docks:
            self.resizeDocks(right_docks, [160, 220, 220, 180, 160, 160], Qt.Orientation.Vertical)

        bottom_docks = [self._docks[n] for n in ("Alerts", "News", "Event Log") if n in self._docks]
        if bottom_docks:
            self.resizeDocks(bottom_docks, [1, 1, 1], Qt.Orientation.Horizontal)

    # -- docks --------------------------------------------------------------
    def _add_dock(self, title: str, widget, area) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(title)
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.addDockWidget(area, dock)
        self._docks[title] = dock
        return dock

    # -- toolbar ---------------------------------------------------------------
    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Principal", self)
        toolbar.setMovable(True)
        self.addToolBar(toolbar)

        flatten_action = toolbar.addAction("Flatten tout")
        flatten_action.triggered.connect(self._flatten_all)

        cancel_action = toolbar.addAction("Annuler tous les ordres")
        cancel_action.triggered.connect(lambda: self.order_engine.cancel_all())

        toolbar.addSeparator()
        kill_action = toolbar.addAction("⛔ Kill Switch")
        kill_action.triggered.connect(self.risk_engine.activate_kill_switch)

    def _flatten_all(self) -> None:
        for symbol, pos in list(self.position_engine.positions.items()):
            if pos.quantity != 0:
                self.position_engine.flatten(self.order_engine, symbol)

    # -- menu -----------------------------------------------------------------
    def _build_menu(self) -> None:
        menu_bar: QMenuBar = self.menuBar()

        file_menu: QMenu = menu_bar.addMenu("Fichier")
        file_menu.addAction("Quitter").triggered.connect(self.close)

        view_menu: QMenu = menu_bar.addMenu("Affichage")
        for title, dock in self._docks.items():
            action = view_menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(dock.setVisible)

        theme_menu: QMenu = menu_bar.addMenu("Thème")
        jigsaw_br_action = theme_menu.addAction("Jigsaw daytradr (bleu/rouge, défaut)")
        jigsaw_br_action.triggered.connect(lambda: self._apply_theme("jigsaw_blue_red"))
        jigsaw_gp_action = theme_menu.addAction("Jigsaw daytradr (vert/violet)")
        jigsaw_gp_action.triggered.connect(lambda: self._apply_theme("jigsaw_green_purple"))
        theme_menu.addSeparator()
        theme_action = theme_menu.addAction("Dark Blue (OpenTraderPro classique)")
        theme_action.triggered.connect(lambda: self._apply_theme("dark_blue"))

        workspace_menu: QMenu = menu_bar.addMenu("Espace de travail")
        workspace_menu.addAction("Enregistrer le layout...").triggered.connect(self._save_workspace)
        restore_menu = workspace_menu.addMenu("Restaurer un layout")
        self._restore_menu = restore_menu
        restore_menu.aboutToShow.connect(self._populate_restore_menu)
        workspace_menu.addAction("Exporter un layout...").triggered.connect(self._export_workspace)
        workspace_menu.addAction("Importer un layout...").triggered.connect(self._import_workspace)

        bots_menu: QMenu = menu_bar.addMenu("Bots")
        for bot_name in self.bot_engine.discover():
            action = bots_menu.addAction(bot_name)
            action.setCheckable(True)
            action.toggled.connect(lambda checked, n=bot_name: self.bot_engine.start(n) if checked else self.bot_engine.stop(n))

        brokers_menu: QMenu = menu_bar.addMenu("Brokers")
        from Brokers.BrokerEngine import AVAILABLE_BROKERS
        for broker_name in AVAILABLE_BROKERS:
            action = brokers_menu.addAction(broker_name)
            action.triggered.connect(lambda _, n=broker_name: self._switch_broker(n))

        addons_menu: QMenu = menu_bar.addMenu("Add-ons")
        addons_menu.addAction("Ouvrir le gestionnaire d'add-ons").triggered.connect(
            lambda: self._docks["Add-ons"].setVisible(True) or self._docks["Add-ons"].raise_()
        )

    def _apply_theme(self, name: str) -> None:
        self.settings.set("theme", name)
        from PySide6.QtWidgets import QApplication
        QApplication.instance().setStyleSheet(get_theme(name))

    def _switch_broker(self, name: str) -> None:
        self.broker_engine.set_active(name)
        connected = self.broker_engine.connect()
        status = "connecté" if connected else "échec de connexion (identifiants requis, voir Event Log)"
        self.statusBar().showMessage(f"Broker actif : {name} ({status})")

    def _save_workspace(self) -> None:
        name, ok = QInputDialog.getText(self, "Enregistrer l'espace de travail", "Nom du layout :")
        if ok and name:
            self.dock_manager.save(name)
            QMessageBox.information(self, "Espace de travail", f"Layout '{name}' enregistré.")

    def _populate_restore_menu(self) -> None:
        self._restore_menu.clear()
        for name in self.dock_manager.list_workspaces():
            self._restore_menu.addAction(name).triggered.connect(lambda _, n=name: self.dock_manager.restore(n))

    def _export_workspace(self) -> None:
        name, ok = QInputDialog.getText(self, "Exporter", "Nom du layout à exporter :")
        if not (ok and name):
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le layout", f"{name}.json", "JSON (*.json)")
        if path and self.dock_manager.export_to_file(name, path):
            QMessageBox.information(self, "Export", f"Layout exporté vers {path}.")

    def _import_workspace(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importer un layout", "", "JSON (*.json)")
        if path:
            name = self.dock_manager.import_from_file(path)
            QMessageBox.information(self, "Import", f"Layout '{name}' importé. Restaurez-le depuis le menu Espace de travail.")
