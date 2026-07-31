"""
rules.py - table de correspondance SignalType -> (nom de règle, mode)
partagée entre le bot temps réel (Bots/InstitutionalOrderFlow) et
Engines/BacktestEngine.py, pour garantir que le backtest évalue
exactement les mêmes règles que celles utilisées en live.

mode "with"  : on suit la direction du signal (continuation)
mode "fade"  : on prend la direction opposée (rejet/retournement)
"""
from __future__ import annotations

from Plugins.OrderFlowSuite.model import SignalType

RULE_FOR_SIGNAL = {
    SignalType.SWEEP: ("sweep_fade", "fade"),
    SignalType.ABSORPTION: ("rejection_absorption", "fade"),
    SignalType.SWEEP_DEFENSE: ("sweep_defense_reversal", "fade"),
    SignalType.IMBALANCE_WALL: ("imbalance_breakout", "with"),
    SignalType.STOP_CASCADE: ("stop_cascade_follow", "with"),
    SignalType.CONFLUENCE: ("confluence_high_conviction", "with"),
}

RULE_MODE = {rule_name: mode for rule_name, mode in RULE_FOR_SIGNAL.values()}
