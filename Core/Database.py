"""
Database.py - accès SQLite centralisé (Database/opentrader.db).

Tables :
- settings(key TEXT PRIMARY KEY, value TEXT)          -> config JSON sérialisée
- ticks(id, symbol, ts, price, size, side, aggressive) -> pour le Recorder/Replay
- depth(id, symbol, ts, payload_json)                  -> snapshots de profondeur
- orders_history(id, symbol, side, type, qty, price, status, ts)
- workspaces(name TEXT PRIMARY KEY, state_b64, geometry_b64)
- bots(name TEXT PRIMARY KEY, config_json, active INTEGER)

SQLite est utilisé en mode WAL pour permettre l'écriture (Recorder) et
la lecture (Replay/UI) sans se bloquer mutuellement.

-- Écriture haute fréquence : writer asynchrone par lots -------------------
record_tick()/record_depth()/record_order_event() sont sur le chemin
chaud du marché (potentiellement des centaines d'appels/seconde). Un
commit SQLite synchrone (fsync disque) à CHAQUE insertion coûte plusieurs
millisecondes -- et comme EventBus republie ces événements sur le thread
GUI (Qt marshalle automatiquement les signaux inter-thread vers le thread
propriétaire), un commit bloquant ici gèle directement l'interface.

Ces trois méthodes ne font donc plus qu'empiler un ordre SQL dans une
`queue.Queue` (opération O(1), pas de verrou de longue durée) ; un thread
d'écriture dédié (_writer_loop) vide la file par lots et ne commit qu'une
fois par lot (voir flush_interval_s/flush_batch_size), déchargeant tout
le travail disque du chemin critique. Contrepartie assumée : les lectures
(fetch_ticks, etc.) peuvent avoir un retard de quelques dizaines de
millisecondes sur les toutes dernières écritures -- sans impact pour du
Replay/Backtest sur historique déjà clos.
"""
from __future__ import annotations
import json
import queue
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional

DB_PATH = Path("Database/opentrader.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ticks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    ts REAL NOT NULL,
    price REAL NOT NULL,
    size INTEGER NOT NULL,
    side TEXT,
    aggressive INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ticks_symbol_ts ON ticks(symbol, ts);
CREATE TABLE IF NOT EXISTS depth_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    ts REAL NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_depth_symbol_ts ON depth_snapshots(symbol, ts);
CREATE TABLE IF NOT EXISTS orders_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    symbol TEXT,
    side TEXT,
    order_type TEXT,
    quantity INTEGER,
    price REAL,
    status TEXT,
    ts REAL
);
CREATE TABLE IF NOT EXISTS workspaces (
    name TEXT PRIMARY KEY,
    state_b64 TEXT,
    geometry_b64 TEXT
);
CREATE TABLE IF NOT EXISTS bots (
    name TEXT PRIMARY KEY,
    config_json TEXT,
    active INTEGER DEFAULT 0
);
"""


class Database:
    """Connexion SQLite partagée. Les lectures et les écritures ponctuelles
    (settings, workspaces) restent synchrones ; les écritures haute
    fréquence (ticks, depth, historique d'ordres) passent par un writer
    asynchrone par lots (voir docstring du module)."""

    def __init__(self, path: Path | str = DB_PATH, flush_interval_s: float = 0.05,
                 flush_batch_size: int = 500) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")  # sûr en WAL, évite un fsync par commit
        self._conn.executescript(SCHEMA)
        self._conn.commit()

        self._flush_interval_s = flush_interval_s
        self._flush_batch_size = flush_batch_size
        self._write_queue: "queue.Queue[tuple[str, tuple]]" = queue.Queue()
        self._writer_stop = threading.Event()
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True, name="DatabaseWriter")
        self._writer_thread.start()

    # -- writer asynchrone par lots ----------------------------------------------
    def _writer_loop(self) -> None:
        while not self._writer_stop.is_set():
            batch = self._collect_batch()
            if batch:
                self._flush_batch(batch)
        # à l'arrêt : vidange finale de tout ce qui reste en file
        remaining = self._drain_nowait()
        if remaining:
            self._flush_batch(remaining)

    def _collect_batch(self) -> list:
        batch: list = []
        try:
            batch.append(self._write_queue.get(timeout=self._flush_interval_s))
        except queue.Empty:
            return batch
        deadline = time.monotonic() + self._flush_interval_s
        while len(batch) < self._flush_batch_size and time.monotonic() < deadline:
            try:
                batch.append(self._write_queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _drain_nowait(self) -> list:
        remaining: list = []
        while True:
            try:
                remaining.append(self._write_queue.get_nowait())
            except queue.Empty:
                break
        return remaining

    def _flush_batch(self, batch: list) -> None:
        if not batch:
            return
        with self._lock:
            for sql, params in batch:
                self._conn.execute(sql, params)
            self._conn.commit()

    def flush(self, timeout_s: float = 2.0) -> None:
        """Attend que la file d'écriture soit vidée (utile avant un fetch
        qui doit absolument voir les toutes dernières lignes)."""
        deadline = time.monotonic() + timeout_s
        while not self._write_queue.empty() and time.monotonic() < deadline:
            time.sleep(0.01)

    # -- settings clé/valeur (JSON) -- écriture peu fréquente, reste synchrone --
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )
            self._conn.commit()

    # -- recorder : ticks & depth (chemin chaud -> file asynchrone) -------------
    def record_tick(self, symbol: str, ts: float, price: float, size: int, side: str, aggressive: bool) -> None:
        self._write_queue.put((
            "INSERT INTO ticks(symbol, ts, price, size, side, aggressive) VALUES (?,?,?,?,?,?)",
            (symbol, ts, price, size, side, int(aggressive)),
        ))

    def record_depth(self, symbol: str, ts: float, payload: dict) -> None:
        self._write_queue.put((
            "INSERT INTO depth_snapshots(symbol, ts, payload) VALUES (?,?,?)",
            (symbol, ts, json.dumps(payload)),
        ))

    def fetch_ticks(self, symbol: str, ts_from: float, ts_to: float) -> Iterable[sqlite3.Row]:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            cur = self._conn.execute(
                "SELECT * FROM ticks WHERE symbol=? AND ts BETWEEN ? AND ? ORDER BY ts ASC",
                (symbol, ts_from, ts_to),
            )
            return cur.fetchall()

    def fetch_depth(self, symbol: str, ts_from: float, ts_to: float) -> Iterable[sqlite3.Row]:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            cur = self._conn.execute(
                "SELECT * FROM depth_snapshots WHERE symbol=? AND ts BETWEEN ? AND ? ORDER BY ts ASC",
                (symbol, ts_from, ts_to),
            )
            return cur.fetchall()

    def get_recorded_range(self, symbol: str) -> Optional[tuple]:
        """Plage (ts_min, ts_max) des ticks enregistrés pour ce symbole, ou
        None si rien n'a encore été enregistré. Utile pour proposer une
        plage de dates par défaut dans l'UI de backtest/replay."""
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(ts), MAX(ts) FROM ticks WHERE symbol=?", (symbol,)
            ).fetchone()
        if not row or row[0] is None:
            return None
        return (row[0], row[1])

    # -- historique d'ordres (chemin chaud -> file asynchrone) -------------------
    def record_order_event(self, order_id: int, symbol: str, side: str, order_type: str,
                            quantity: int, price: Optional[float], status: str, ts: float) -> None:
        self._write_queue.put((
            "INSERT INTO orders_history(order_id, symbol, side, order_type, quantity, price, status, ts) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (order_id, symbol, side, order_type, quantity, price, status, ts),
        ))

    # -- workspaces (peu fréquent, reste synchrone) ------------------------------
    def save_workspace(self, name: str, state_b64: str, geometry_b64: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO workspaces(name, state_b64, geometry_b64) VALUES (?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET state_b64=excluded.state_b64, geometry_b64=excluded.geometry_b64",
                (name, state_b64, geometry_b64),
            )
            self._conn.commit()

    def load_workspace(self, name: str) -> Optional[tuple]:
        with self._lock:
            row = self._conn.execute(
                "SELECT state_b64, geometry_b64 FROM workspaces WHERE name=?", (name,)
            ).fetchone()
        return row

    def list_workspaces(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT name FROM workspaces ORDER BY name").fetchall()
        return [r[0] for r in rows]

    def close(self) -> None:
        self._writer_stop.set()
        self._writer_thread.join(timeout=max(2.0, self._flush_interval_s * 4))
        with self._lock:
            self._conn.close()
