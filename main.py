#!/usr/bin/env python3
"""
main.py - point d'entrée d'OpenTrader Pro.

Assemble : Database (SQLite) -> Settings -> EventBus -> BrokerEngine ->
MarketEngine -> OrderEngine -> PositionEngine -> RiskEngine -> BotEngine
-> PluginEngine -> ReplayEngine -> MainWindow (GUI).
"""
import sys
import signal

from PySide6.QtWidgets import QApplication

from Core.EventBus import EventBus
from Core.Database import Database
from Core.Settings import Settings

from Engines.MarketEngine import MarketEngine
from Engines.OrderEngine import OrderEngine
from Engines.PositionEngine import PositionEngine
from Engines.RiskEngine import RiskEngine
from Engines.BotEngine import BotEngine
from Engines.PluginEngine import PluginEngine
from Engines.ReplayEngine import ReplayEngine
from Engines.ReconstructedTapeEngine import ReconstructedTapeEngine
from Engines.PaceOfTapeEngine import PaceOfTapeEngine
from Engines.LatencyMonitor import LatencyMonitor

from Brokers.BrokerEngine import BrokerEngine

from GUI.MainWindow import MainWindow
from GUI.Theme import get_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("OpenTrader Pro")

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # --- Noyau applicatif -----------------------------------------------------
    db = Database()
    settings = Settings(db)
    app.setStyleSheet(get_theme(settings.get("theme", "dark_blue")))

    bus = EventBus()

    broker_engine = BrokerEngine(bus, default_broker=settings.get("brokers", {}).get("active", "Simulation"))
    broker_engine.connect()  # connecte le broker actif (Simulation par défaut : toujours OK)

    symbol = settings.get("default_symbol", "ESU6")
    market_engine = MarketEngine(bus, db=db, symbol=symbol)
    reconstructed_tape_engine = ReconstructedTapeEngine(bus, settings=settings)
    pace_of_tape_engine = PaceOfTapeEngine(bus, settings=settings)
    latency_monitor = LatencyMonitor(bus)

    risk_engine = RiskEngine(bus, settings)
    order_engine = OrderEngine(bus, broker_engine, db=db, risk_engine=risk_engine)
    risk_engine.order_engine = order_engine  # référence croisée nécessaire pour cancel_all() au lockout

    position_engine = PositionEngine(bus)
    bot_engine = BotEngine(bus, order_engine, position_engine, market_engine=market_engine)
    plugin_engine = PluginEngine(bus)
    replay_engine = ReplayEngine(bus, db)

    # --- Interface graphique ----------------------------------------------------
    window = MainWindow(
        bus=bus, db=db, settings=settings,
        order_engine=order_engine, position_engine=position_engine,
        risk_engine=risk_engine, bot_engine=bot_engine,
        plugin_engine=plugin_engine, broker_engine=broker_engine,
        replay_engine=replay_engine, latency_monitor=latency_monitor,
    )
    window.resize(1800, 1000)
    window.show()

    market_engine.start()

    exit_code = app.exec()
    market_engine.stop()
    settings.save()
    db.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
