"""Small in-process progress registry for one synchronous query/ingestion request.

This is telemetry only: it observes the existing pipeline and never controls,
skips, or changes a collector, canonical merge, or Neo4j sync operation.
"""
from __future__ import annotations

from threading import Lock
from time import time
from typing import Any

_MAX_ENTRIES = 512
_TTL_SECONDS = 60 * 60
_LOCK = Lock()
_PROGRESS: dict[str, dict[str, Any]] = {}
_PUBLIC_FIELDS = {
    "request_id",
    "status",
    "active",
    "phase_index",
    "stage",
    "mode",
    "plant_name",
    "complete",
    "message",
}


def _purge_locked(now: float) -> None:
    expired = [
        key for key, value in _PROGRESS.items()
        if now - float(value.get("_updated_at", now)) > _TTL_SECONDS
    ]
    for key in expired:
        _PROGRESS.pop(key, None)
    if len(_PROGRESS) > _MAX_ENTRIES:
        oldest = sorted(
            _PROGRESS,
            key=lambda key: float(_PROGRESS[key].get("_updated_at", 0)),
        )
        for key in oldest[: len(_PROGRESS) - _MAX_ENTRIES]:
            _PROGRESS.pop(key, None)


def register_query(request_id: str) -> None:
    now = time()
    with _LOCK:
        _purge_locked(now)
        _PROGRESS[request_id] = {
            "request_id": request_id,
            "status": "querying",
            "active": False,
            "phase_index": -1,
            "complete": False,
            "_updated_at": now,
        }


def publish_query_progress(request_id: str, update: dict[str, Any]) -> None:
    """Merge an allow-listed progress event into the request record."""
    now = time()
    clean = {key: value for key, value in update.items() if key in _PUBLIC_FIELDS and key != "request_id"}
    with _LOCK:
        _purge_locked(now)
        current = _PROGRESS.get(request_id)
        if current is None:
            current = {
                "request_id": request_id,
                "status": "querying",
                "active": False,
                "phase_index": -1,
                "complete": False,
            }
            _PROGRESS[request_id] = current
        current.update(clean)
        current["_updated_at"] = now


def get_query_progress(request_id: str) -> dict[str, Any] | None:
    now = time()
    with _LOCK:
        _purge_locked(now)
        current = _PROGRESS.get(request_id)
        if current is None:
            return None
        return {key: value for key, value in current.items() if key in _PUBLIC_FIELDS}
