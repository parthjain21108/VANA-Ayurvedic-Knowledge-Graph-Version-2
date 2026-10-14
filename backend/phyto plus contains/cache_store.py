"""Disk-backed cache for the IMPPAT/ChEMBL phytochemical builder.

Legacy cache files are single JSON objects that can exceed 100 MB. Loading them
with json.loads expands every HTML string into Python objects and can consume
close to a gigabyte of RAM. This module migrates that legacy object to SQLite
one key/value at a time, then provides a dict-like interface without loading
all values into memory.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections.abc import MutableMapping, Iterator
from json import JSONDecodeError, JSONDecoder
from pathlib import Path
from typing import Any

try:  # This module is used by the Linux backend container.
    import fcntl
except ImportError:  # pragma: no cover - Windows test fallback
    fcntl = None


def iter_json_object_items(path: Path, chunk_size: int = 1024 * 1024) -> Iterator[tuple[str, Any]]:
    """Stream top-level key/value pairs from a JSON object using stdlib only."""
    decoder = JSONDecoder()
    with Path(path).open("r", encoding="utf-8") as handle:
        buffer = ""
        pos = 0
        eof = False

        def refill() -> None:
            nonlocal buffer, pos, eof
            if pos:
                buffer = buffer[pos:]
                pos = 0
            chunk = handle.read(chunk_size)
            if chunk:
                buffer += chunk
            else:
                eof = True

        def skip_ws() -> str | None:
            nonlocal pos
            while True:
                while pos < len(buffer) and buffer[pos].isspace():
                    pos += 1
                if pos < len(buffer):
                    return buffer[pos]
                if eof:
                    return None
                refill()

        def decode_value() -> Any:
            nonlocal pos
            while True:
                skip_ws()
                try:
                    value, end = decoder.raw_decode(buffer, pos)
                    pos = end
                    return value
                except JSONDecodeError:
                    if eof:
                        raise
                    refill()

        first = skip_ws()
        if first != "{":
            raise ValueError(f"Expected a JSON object at top level in {path}")
        pos += 1

        while True:
            char = skip_ws()
            if char == "}":
                pos += 1
                # Reject trailing non-whitespace content.
                if skip_ws() is not None:
                    raise ValueError(f"Trailing content after JSON object in {path}")
                return
            if char is None:
                raise ValueError(f"Unexpected EOF in JSON object {path}")

            key = decode_value()
            if not isinstance(key, str):
                raise ValueError(f"Expected string key in JSON object {path}")
            char = skip_ws()
            if char != ":":
                raise ValueError(f"Expected ':' after key {key!r} in {path}")
            pos += 1
            value = decode_value()
            yield key, value

            char = skip_ws()
            if char == ",":
                pos += 1
                continue
            if char == "}":
                pos += 1
                if skip_ws() is not None:
                    raise ValueError(f"Trailing content after JSON object in {path}")
                return
            if char is None:
                raise ValueError(f"Unexpected EOF after key {key!r} in {path}")
            raise ValueError(f"Expected ',' or '}}' after key {key!r} in {path}")


class SQLiteJSONCache(MutableMapping[str, Any]):
    """SQLite-backed mapping; accepts the old JSON cache as a migration source."""

    def __init__(self, database_path: Path, legacy_json_path: Path | None = None):
        self.database_path = Path(database_path)
        self.legacy_json_path = Path(legacy_json_path) if legacy_json_path else None
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_database()
        self._conn = sqlite3.connect(str(self.database_path), timeout=60)
        self._conn.execute("PRAGMA busy_timeout=60000")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)")
        self._conn.commit()

    def _ready(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            with sqlite3.connect(str(path), timeout=5) as conn:
                row = conn.execute("SELECT value FROM meta WHERE key='initialized'").fetchone()
                return bool(row and row[0] == "1")
        except sqlite3.Error:
            return False

    def _ensure_database(self) -> None:
        if self._ready(self.database_path):
            return

        lock_path = self.database_path.with_suffix(self.database_path.suffix + ".migrate.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as lock_handle:
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                if self._ready(self.database_path):
                    return
                temp_path = self.database_path.with_name(
                    self.database_path.name + f".tmp.{os.getpid()}"
                )
                if temp_path.exists():
                    temp_path.unlink()
                conn = sqlite3.connect(str(temp_path), timeout=60)
                try:
                    conn.execute("CREATE TABLE cache (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)")
                    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                    count = 0
                    legacy = self.legacy_json_path
                    if legacy is not None and legacy.is_file() and legacy.stat().st_size:
                        size_mb = legacy.stat().st_size / (1024 * 1024)
                        print(
                            f"[IMPPAT CACHE] Streaming {size_mb:.1f} MB legacy cache "
                            f"into SQLite: {legacy}", flush=True
                        )
                        batch: list[tuple[str, str]] = []
                        for key, value in iter_json_object_items(legacy):
                            batch.append((key, json.dumps(value, ensure_ascii=False, separators=(",", ":"))))
                            if len(batch) >= 250:
                                conn.executemany("INSERT OR REPLACE INTO cache(key,value_json) VALUES (?,?)", batch)
                                conn.commit()
                                count += len(batch)
                                batch.clear()
                                if count and count % 10000 == 0:
                                    print(f"[IMPPAT CACHE] migrated {count} entries", flush=True)
                        if batch:
                            conn.executemany("INSERT OR REPLACE INTO cache(key,value_json) VALUES (?,?)", batch)
                            count += len(batch)
                        conn.commit()
                    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('initialized','1')")
                    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('legacy_entries',?)", (str(count),))
                    conn.commit()
                finally:
                    conn.close()
                os.replace(temp_path, self.database_path)
                print(f"[IMPPAT CACHE] SQLite cache ready; legacy entries imported: {count}", flush=True)
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def __getitem__(self, key: str) -> Any:
        row = self._conn.execute("SELECT value_json FROM cache WHERE key=?", (str(key),)).fetchone()
        if row is None:
            raise KeyError(key)
        return json.loads(row[0])

    def __setitem__(self, key: str, value: Any) -> None:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO cache(key,value_json) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
            (str(key), encoded),
        )
        self._conn.commit()

    def __delitem__(self, key: str) -> None:
        cur = self._conn.execute("DELETE FROM cache WHERE key=?", (str(key),))
        self._conn.commit()
        if cur.rowcount == 0:
            raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        cur = self._conn.execute("SELECT key FROM cache ORDER BY key")
        for (key,) in cur:
            yield key

    def __len__(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()
        return int(row[0]) if row else 0

    def __contains__(self, key: object) -> bool:
        row = self._conn.execute("SELECT 1 FROM cache WHERE key=?", (str(key),)).fetchone()
        return row is not None

    def flush(self) -> None:
        self._conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()
