"""
CryptoBrokers.py - squelettes des connecteurs crypto.
Implémentation réelle recommandée via la librairie `ccxt` (unifie déjà
les API REST/WebSocket de ces exchanges) ou les SDK officiels.
"""
from Brokers.StubBroker import StubBroker


class BinanceBroker(StubBroker):
    name = "Binance"
    required_credentials = ("api_key", "api_secret")


class BybitBroker(StubBroker):
    name = "Bybit"
    required_credentials = ("api_key", "api_secret")


class BitgetBroker(StubBroker):
    name = "Bitget"
    required_credentials = ("api_key", "api_secret", "passphrase")


class KrakenBroker(StubBroker):
    name = "Kraken"
    required_credentials = ("api_key", "api_secret")


class CoinbaseBroker(StubBroker):
    name = "Coinbase"
    required_credentials = ("api_key", "api_secret", "passphrase")
