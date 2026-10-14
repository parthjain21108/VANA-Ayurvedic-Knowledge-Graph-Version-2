"""Thin ingestion entry point for the existing plant ingestion pipeline.

This module intentionally contains no collection, normalization, canonical-store,
or Neo4j logic. It only delegates to the existing ingest_plant.py implementation.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

# When this file is executed directly, ensure the ingestion package directory is
# importable without changing the existing ingest_plant.py.
HERE = Path(__file__).resolve().parent
INGESTION_DIR = HERE / "phase1_release" / "ingestion"
if str(INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(INGESTION_DIR))

from ingest_plant import ingest_plant  # noqa: E402


def ingest_missing_plant(plant_name: str, **kwargs: Any) -> dict[str, Any]:
    """Delegate ingestion to the existing ingest_plant() implementation."""
    if not isinstance(plant_name, str) or not plant_name.strip():
        raise ValueError("plant_name must be a non-empty string")

    # Keep every failed run's collector output. A retry never collides with or
    # overwrites a previous plant folder; the collector/master logic is unchanged.
    if kwargs.get("output_dir") is None:
        safe = "_".join(plant_name.strip().split())
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", safe)
        safe = re.sub(r"_+", "_", safe).strip("._-") or "plant"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        kwargs["output_dir"] = HERE / f"{safe}_run_{stamp}"
    return ingest_plant(plant_name.strip(), **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Call the existing plant ingestion pipeline for one plant."
    )
    parser.add_argument(
        "--plant",
        required=True,
        help='Plant name, e.g. "Acacia leucophloea"',
    )
    args = parser.parse_args()

    try:
        report = ingest_missing_plant(args.plant)
        print(json.dumps(report, indent=2))
    except Exception as exc:
        print(f"INGESTION ENDPOINT FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
