"""Route a resolved scientific name through Neo4j and ingestion.

This is a new orchestration layer. It does not modify any existing collector,
ingestion, Phase 1, Phase 2, or Neo4j sync code.

Decision rule:
- Neo4j says exists=True  -> stop; do not ingest.
- Neo4j says exists=False -> call the existing ingestion endpoint, then re-check.
- Neo4j check raises    -> stop; never treat the error as missing.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from typing import Any, Callable

from neo4j_existence import check_plant_exists
from plant_ingestion_endpoint import ingest_missing_plant


ExistenceChecker = Callable[..., dict[str, Any]]
IngestionCallable = Callable[..., dict[str, Any]]
ProgressCallback = Callable[[dict[str, Any]], None]
_LOCKS_GUARD = threading.Lock()
_PLANT_LOCKS: dict[str, threading.Lock] = {}


def _plant_lock(scientific_name: str) -> threading.Lock:
    key = scientific_name.strip().casefold()
    with _LOCKS_GUARD:
        return _PLANT_LOCKS.setdefault(key, threading.Lock())


def _notify(callback: ProgressCallback | None, **event: Any) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except Exception as exc:
        # UI telemetry must never interrupt the established ingestion process.
        print(f"INGESTION PROGRESS CALLBACK FAILED: {type(exc).__name__}")


def _has_healthy_parts(existence: dict[str, Any]) -> bool:
    if existence.get("exists") is not True:
        return False
    count = existence.get("has_part_relationships")
    # Preserve compatibility with older injected checkers that only return exists.
    return count is None or int(count or 0) > 0


def route_plant(
    scientific_name: str,
    *,
    existence_checker: ExistenceChecker = check_plant_exists,
    ingestion_callable: IngestionCallable = ingest_missing_plant,
    progress_callback: ProgressCallback | None = None,
    max_retries: int = 3,
    **neo4j_kwargs: Any,
) -> dict[str, Any]:
    """Ingest only when missing/incomplete, then verify a usable Has Part edge."""
    scientific_name = scientific_name.strip()
    if not scientific_name:
        raise ValueError("scientific_name must not be empty")
    if max_retries < 1:
        raise ValueError("max_retries must be at least 1")

    def check(context: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                return existence_checker(scientific_name, **neo4j_kwargs)
            except Exception as exc:
                last_error = exc
                if attempt == max_retries:
                    raise RuntimeError(
                        f"Neo4j {context} failed after {max_retries} attempt(s); ingestion state is not assumed safe."
                    ) from exc
        raise RuntimeError(f"Neo4j {context} failed") from last_error

    first = check("existence check")
    if first.get("exists") is True and _has_healthy_parts(first):
        return {
            "status": "exists", "scientific_name": scientific_name,
            "ingestion_started": False, "existence": first,
        }
    if first.get("exists") not in (True, False):
        raise RuntimeError("Neo4j existence checker returned an invalid result; ingestion was not started.")

    # Serialize by scientific name and re-check inside the lock so a simultaneous
    # request cannot launch a duplicate run for a plant that was just added.
    with _plant_lock(scientific_name):
        current = check("locked existence check")
        if current.get("exists") is True and _has_healthy_parts(current):
            return {
                "status": "exists", "scientific_name": scientific_name,
                "ingestion_started": False, "existence": current,
            }
        if current.get("exists") not in (True, False):
            raise RuntimeError("Neo4j existence checker returned an invalid result; ingestion was not started.")

        existed_before = current.get("exists") is True
        mode = "repair" if existed_before else "new"
        if mode == "new":
            _notify(
                progress_callback,
                status="started", active=True, complete=False, phase_index=-1,
                stage="Preparing scientific record", mode="new", plant_name=scientific_name,
                message="Thank you for expanding Vana's database. We are collecting and validating scientific details; this can take around 5–10 minutes.",
            )

        ingestion_kwargs = {
            "neo4j_uri": neo4j_kwargs.get("uri"),
            "neo4j_user": neo4j_kwargs.get("user"),
            "neo4j_password": neo4j_kwargs.get("password"),
            "neo4j_database": neo4j_kwargs.get("database"),
        }
        # Forward the existing telemetry callback into the ingestion runner.
        # The callback observes stage output only; it does not control ingestion.
        if progress_callback is not None and mode == "new":
            ingestion_kwargs["progress_callback"] = progress_callback
        ingestion_report = ingestion_callable(scientific_name, **ingestion_kwargs)
        final = check("post-ingestion verification")
        if not _has_healthy_parts(final):
            raise RuntimeError(
                "Ingestion finished, but Neo4j did not verify the Plant Name node and at least one Has Part relationship. The plant was not reported as successfully added."
            )

        return {
            "status": "repaired" if existed_before else "ingested",
            "scientific_name": scientific_name,
            "ingestion_started": True,
            "ingestion": ingestion_report,
            "existence": final,
        }

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Check an exact scientific_name in Neo4j; ingest only when the "
            "database definitively reports that it is missing."
        )
    )
    parser.add_argument(
        "--plant",
        required=True,
        help='Scientific plant name, e.g. "Acacia leucophloea"',
    )
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI"))
    parser.add_argument("--user", default=os.getenv("NEO4J_USER"))
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    try:
        result = route_plant(
            args.plant,
            max_retries=args.retries,
            uri=args.uri,
            user=args.user,
            password=args.password,
            database=args.database,
        )
        print(json.dumps(result, indent=2))
    except Exception as exc:
        print(f"PLANT QUERY ROUTER FAILED: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
