"""Production-oriented one-plant ingestion orchestrator.

Composition only; it does not modify master.py, collectors, Phase 1 updater,
Phase 2 sync, or the Neo4j schema.

Pipeline:
    existing master.py -> Phase 1 Data Manager -> Phase 2 Neo4j sync

Important compatibility behavior:
- master.py in this project catches its own exceptions and may exit with code 0
  even after printing ``MASTER PIPELINE FAILED``.  This orchestrator therefore
  treats that banner as a real failure and surfaces the actual master output.
- Collector output stays outside phase1_release, matching the project's
  existing layout and the direct master.py --output behavior.
- Phase 1 and Phase 2 are invoked only after their predecessors succeed.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_PROJECT_ROOT_FOR_CACHE = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_FOR_CACHE) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_FOR_CACHE))

from shared_ingestion_cache import (  # noqa: E402
    prepare_plant_caches,
    publish_plant_caches,
)
from phase1_release.data_manager.updater import assert_canonical_store_identity_compatible  # noqa: E402


@dataclass
class StageResult:
    name: str
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


MASTER_FAILURE_MARKER = "MASTER PIPELINE FAILED"

# The UI exposes 12 grouped phases. Internal helper passes (2B, 8B, 9B)
# map to the nearest primary phase so the displayed step never jumps backward.
# These patterns observe existing master.py stdout; master.py itself is unchanged.
_MASTER_PROGRESS_STAGES: tuple[tuple[str, int, str, str], ...] = (
    (r"\bSTEP\s+1/\d+\s*-\s*PLANT\b", 0, "Plant collection", "Collecting scientific details for the plant."),
    (r"\bSTEP\s+2/\d+\s*-\s*PLANT PART\b", 1, "Plant-part collection", "Collecting the plant parts reported by IMPPAT."),
    (r"\bSTEP\s+2B/\d+\s*-\s*NORMALIZE USER INPUT NAME\b", 1, "Plant-part collection", "Normalizing the requested plant name."),
    (r"\bSTEP\s+3/\d+\s*-\s*HAS_PART\b", 2, "Build plant relationships", "Building relationships between the plant and its parts."),
    (r"\bSTEP\s+4/\d+\s*-\s*PHYTOCHEMICAL MAPPING\b", 3, "Map phytochemicals", "Mapping phytochemicals to the collected plant parts."),
    (r"\bSTEP\s+5A/\d+\s*-\s*PHYTOCHEMICALS\b", 4, "Collect compounds + build CONTAINS", "Resolving compound identities and their details."),
    (r"\bSTEP\s+5B/\d+\s*-\s*CONTAINS\b", 4, "Collect compounds + build CONTAINS", "Linking compounds to the plant parts that contain them."),
    (r"\bSTEP\s+6/\d+\s*-\s*BIOACTIVITIES\b", 5, "Collect bioactivity + link compounds", "Collecting eligible bioactivity evidence."),
    (r"\bSTEP\s+7/\d+\s*-\s*HAS_BIOACTIVITY\b", 5, "Collect bioactivity + link compounds", "Linking bioactivity findings to compounds."),
    (r"\bSTEP\s+8/\d+\s*-\s*DOCUMENTS\b", 6, "Collect documents + REPORTED_IN", "Collecting research documents and source relationships."),
    (r"\bSTEP\s+8B/\d+\s*-\s*REPORTED_IN\b", 6, "Collect documents + REPORTED_IN", "Validating document-source relationships."),
    (r"\bSTEP\s+9/\d+\s*-\s*TARGETS\b", 7, "Resolve targets + MEASURED_ON", "Resolving targets and measurement relationships."),
    (r"\bSTEP\s+9B/\d+\s*-\s*MEASURED_ON\b", 7, "Resolve targets + MEASURED_ON", "Finalizing target measurement relationships."),
    (r"\bSTEP\s+9C/\d+\s*-\s*NORMALIZE BIOACTIVITY NODES\b", 8, "Normalize bioactivity nodes", "Normalizing bioactivity entities."),
    (r"\bSTEP\s+10/\d+\s*-\s*THERAPEUTIC USE COLLECTION\b", 9, "Collect therapeutic uses", "Collecting therapeutic-use associations."),
    (r"\bSTEP\s+11/\d+\s*-\s*THERAPEUTIC USE BUILD\b", 10, "Build therapeutic-use nodes", "Resolving and deduplicating therapeutic-use concepts."),
    (r"\bSTEP\s+12/\d+\s*-\s*USED_FOR\b", 11, "Build USED_FOR relationships", "Building therapeutic-use relationships for this plant."),
    (r"\bFINAL\s*-\s*HAS_PART NORMALIZE\b", 11, "Final graph validation", "Validating the completed collector output."),
    (r"\bFINAL\s*-\s*CSV EXPORT\b", 11, "Final graph validation", "Exporting the validated graph data."),
    (r"\bFINAL\s*-\s*GRAPH VALIDATION\b", 11, "Final graph validation", "Validating the final graph before publication."),
)


def _master_progress_event(line: str) -> dict[str, Any] | None:
    """Translate an existing master.py stage banner to the 0-based UI phase index."""
    import re as _re

    for pattern, phase_index, stage, message in _MASTER_PROGRESS_STAGES:
        if _re.search(pattern, line, _re.IGNORECASE):
            return {
                "status": "running",
                "active": True,
                "complete": False,
                "phase_index": phase_index,
                "stage": stage,
                "message": message,
            }
    return None


def _safe_progress_callback(
    progress_callback: Callable[[dict[str, Any]], None] | None,
    update: dict[str, Any],
) -> None:
    """Telemetry must never cause or change a collector failure."""
    if progress_callback is None:
        return
    try:
        progress_callback(update)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        print(
            f"WARNING: progress reporting failed ({type(exc).__name__}); ingestion continues.",
            file=sys.stderr,
            flush=True,
        )


def _report_master_progress_line(
    line: str,
    progress_callback: Callable[[dict[str, Any]], None] | None,
) -> None:
    update = _master_progress_event(line)
    if update is not None:
        _safe_progress_callback(progress_callback, update)

# These are the final CSVs produced by master.py only after the entire graph
# pipeline reaches FINAL - CSV EXPORT + FINAL - GRAPH VALIDATION.
MASTER_FINAL_OUTPUTS = [
    "Plant.csv",
    "PlantPart.csv",
    "Phytochemicals.csv",
    "TherapeuticUses.csv",
    "Bioactivities.csv",
    "Targets.csv",
    "Documents.csv",
    "HAS_PART.csv",
    "CONTAINS.csv",
    "USED_FOR.csv",
    "HAS_BIOACTIVITY.csv",
    "MEASURED_ON.csv",
    "REPORTED_IN.csv",
]


def _project_root() -> Path:
    # ingestion/ingest_plant.py lives at:
    # <project_root>/phase1_release/ingestion/ingest_plant.py
    return Path(__file__).resolve().parents[2]


def _phase1_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_plant_name(name: str) -> str:
    text = "_".join(name.strip().split())
    text = re.sub(r"[^A-Za-z0-9._-]", "_", text)
    text = re.sub(r"_+", "_", text).strip("._-")
    if not text:
        raise ValueError("Plant name produces an empty output directory name.")
    return text


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    stdout_line_callback: Callable[[str], None] | None = None,
) -> StageResult:
    """Run a child process while streaming its output and retaining logs."""
    import threading

    started = time.perf_counter()
    child_env = dict(env) if env is not None else os.environ.copy()
    # The child must flush progress while stdout is connected to a pipe.
    child_env.setdefault("PYTHONUNBUFFERED", "1")

    proc = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=child_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def stream_stdout() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            stdout_chunks.append(line)
            print(line, end="", flush=True)
            if stdout_line_callback is not None:
                try:
                    stdout_line_callback(line)
                except Exception as exc:  # Progress is telemetry, not pipeline control.
                    print(
                        f"WARNING: stdout progress observer failed ({type(exc).__name__}); ingestion continues.",
                        file=sys.stderr,
                        flush=True,
                    )

    def stream_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_chunks.append(line)
            print(line, end="", file=sys.stderr, flush=True)

    stdout_thread = threading.Thread(target=stream_stdout, daemon=True)
    stderr_thread = threading.Thread(target=stream_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    returncode = proc.wait()
    stdout_thread.join()
    stderr_thread.join()

    return StageResult(
        name=" ".join(command),
        returncode=returncode,
        stdout="".join(stdout_chunks),
        stderr="".join(stderr_chunks),
        duration_seconds=round(time.perf_counter() - started, 3),
    )


def _parse_json_stdout(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _write_stage_logs(output_dir: Path, result: StageResult, stem: str) -> tuple[Path, Path]:
    """Persist captured subprocess output so failures remain diagnosable."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / f"{stem}.stdout.log"
    stderr_path = output_dir / f"{stem}.stderr.log"
    stdout_path.write_text(result.stdout or "", encoding="utf-8")
    stderr_path.write_text(result.stderr or "", encoding="utf-8")
    return stdout_path, stderr_path


def _master_failed(result: StageResult) -> bool:
    """Detect both normal subprocess failures and master.py's swallowed failures."""
    if not result.ok:
        return True
    return MASTER_FAILURE_MARKER in result.stdout or MASTER_FAILURE_MARKER in result.stderr


def _master_failure_report(result: StageResult, output_dir: Path) -> str:
    stdout_path, stderr_path = _write_stage_logs(output_dir, result, "master")
    parts = [
        f"MASTER COLLECTOR FAILED (exit code {result.returncode}).",
        "The existing master.py can print a failure banner while still returning exit code 0; the orchestrator detected that banner.",
    ]
    if result.stdout.strip():
        parts.append(f"MASTER STDOUT:\n{result.stdout.strip()}")
    if result.stderr.strip():
        parts.append(f"MASTER STDERR:\n{result.stderr.strip()}")
    parts.append(f"Full stdout saved to: {stdout_path}")
    parts.append(f"Full stderr saved to: {stderr_path}")
    return "\n\n".join(parts)


def _require_output_folder(path: Path, master_result: StageResult) -> None:
    if not path.exists() or not path.is_dir():
        raise RuntimeError(f"Master output directory was not created: {path}")

    missing = [name for name in MASTER_FINAL_OUTPUTS if not (path / name).exists()]
    if missing:
        stdout_path, stderr_path = _write_stage_logs(path, master_result, "master")
        raise RuntimeError(
            "Master did not produce the complete final graph output. "
            f"Missing: {missing}\n"
            f"Partial collector output was kept at: {path}\n"
            f"Master stdout log: {stdout_path}\n"
            f"Master stderr log: {stderr_path}\n"
            "The Phase 1 updater was NOT started."
        )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _validate_plant_parts_and_edges(output_dir: Path, plant_name: str) -> dict[str, int]:
    """Fail before canonical update if master output omits this plant's part edges."""
    folded = plant_name.strip().casefold()
    plants = [r for r in _read_csv_rows(output_dir / "Plant.csv")
              if (r.get("scientific_name") or "").strip().casefold() == folded]
    parts = [r for r in _read_csv_rows(output_dir / "PlantPart.csv")
             if (r.get("plant_name") or "").strip().casefold() == folded
             and (r.get("plant_part_id") or "").strip()]
    part_ids = {(r.get("plant_part_id") or "").strip() for r in parts}
    edges = [r for r in _read_csv_rows(output_dir / "HAS_PART.csv")
             if (r.get("Source") or "").strip() == "Plant"
             and (r.get("Source Id") or "").strip().casefold() == folded
             and (r.get("Destination") or "").strip() == "PlantPart"
             and (r.get("Destination Id") or "").strip() in part_ids]
    if not plants or not parts or not edges:
        raise RuntimeError(
            f"Master output for {plant_name!r} failed graph-integrity checks: "
            f"plant_rows={len(plants)}, plant_parts={len(parts)}, has_part_edges={len(edges)}. "
            "Canonical update was NOT started; inspect the retained collector output."
        )
    return {"plant_rows": len(plants), "plant_parts": len(parts), "has_part_edges": len(edges)}


def _verify_synced_plant_parts(plant_name: str, env: dict[str, str], database: str) -> dict[str, Any]:
    """Read-only post-sync assertion: require Plant Name + Has Part -> Plant Part."""
    from neo4j import GraphDatabase
    uri = env.get("NEO4J_URI")
    user = env.get("NEO4J_USER") or env.get("NEO4J_USERNAME")
    password = env.get("NEO4J_PASSWORD")
    if not uri or not user or password is None:
        raise RuntimeError("Cannot verify synced graph: Neo4j connection settings are incomplete.")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            record = session.run(
                """
                OPTIONAL MATCH (p:`Plant Name`)
                WHERE toLower(trim(toString(p.scientific_name))) = toLower(trim($name))
                OPTIONAL MATCH (p)-[r:`Has Part`]->(:`Plant Part`)
                RETURN count(DISTINCT p) > 0 AS exists,
                       count(r) AS has_part_relationships
                """,
                name=plant_name,
            ).single()
            result = {
                "exists": bool(record["exists"]) if record else False,
                "has_part_relationships": int(record["has_part_relationships"] or 0) if record else 0,
            }
    finally:
        driver.close()
    if not result["exists"] or result["has_part_relationships"] < 1:
        raise RuntimeError(
            "Neo4j sync finished but graph verification found no Plant Name node with a Has Part relationship. "
            "The request is not considered successful; inspect canonical data and sync logs before retrying."
        )
    return result


def ingest_plant(
    plant_name: str,
    *,
    output_dir: Path | None = None,
    store_root: Path | None = None,
    neo4j_uri: str | None = None,
    neo4j_user: str | None = None,
    neo4j_password: str | None = None,
    neo4j_database: str | None = None,
    python_executable: str | None = None,
    no_cache: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run master -> Phase 1 -> Phase 2 for one plant.

    Raises RuntimeError on any failed stage. Returns a JSON-serializable
    report on success.
    """
    plant_name = plant_name.strip()
    if not plant_name:
        raise ValueError("plant_name must not be empty")

    project_root = _project_root()
    phase1_root = _phase1_root()
    python_exec = python_executable or sys.executable

    # Keep collector output outside phase1_release, exactly like a direct
    # master.py invocation from the project root.
    if output_dir is None:
        output_dir = project_root / _safe_plant_name(plant_name)
    else:
        output_dir = Path(output_dir).resolve()

    if store_root is None:
        store_root = phase1_root / "data" / "canonical"
    else:
        store_root = Path(store_root).resolve()

    # Fail early if canonical Phytochemical identity, current IMPPAT metadata,
    # or relationship endpoints violate the established InChIKey contract.
    # Do not scrape or publish shared caches when Phase 1 would refuse later.
    assert_canonical_store_identity_compatible(store_root)

    # Never reuse a partial or stale collector folder. This prevents a failed
    # previous run from masquerading as a successful fresh collection.
    if output_dir.exists():
        raise RuntimeError(
            f"Output directory already exists: {output_dir}\n"
            "Remove the failed/stale collector folder or choose a different --output path before retrying."
        )

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(project_root), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    env["VANA_SHARED_CACHE_DIR"] = str(
        phase1_root / "data" / "shared_cache"
    )
    env["VANA_SHARED_HTTP_CACHE_ENABLED"] = "0" if no_cache else "1"

    if neo4j_uri is not None:
        env["NEO4J_URI"] = neo4j_uri
    if neo4j_user is not None:
        env["NEO4J_USER"] = neo4j_user
    if neo4j_password is not None:
        env["NEO4J_PASSWORD"] = neo4j_password
    if neo4j_database is not None:
        env["NEO4J_DATABASE"] = neo4j_database

    # Preserve the supported legacy username variable, but normalize it to the
    # name consumed by the Phase 1/Phase 2 subprocesses.
    if not env.get("NEO4J_USER") and env.get("NEO4J_USERNAME"):
        env["NEO4J_USER"] = env["NEO4J_USERNAME"]

    # This workflow always proceeds to Phase 2. Validate credentials before
    # creating output directories, scraping, preparing/publishing shared caches,
    # or canonical-store mutation. Empty strings are incomplete credentials too.
    if not env.get("NEO4J_URI") or not env.get("NEO4J_USER") or not env.get("NEO4J_PASSWORD"):
        raise RuntimeError(
            "Neo4j connection settings are incomplete. No master run, shared-cache "
            "publication, or canonical publication was started. Set NEO4J_URI, "
            "NEO4J_USER (or NEO4J_USERNAME), NEO4J_PASSWORD, and NEO4J_DATABASE."
        )

    # Only create the collector output directory after both the identity and
    # database-configuration preflights have passed.
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=False)

    cache_prepare_stats = {}
    if not no_cache:
        cache_prepare_stats = prepare_plant_caches(
            project_root,
            output_dir,
        )

    stages: list[StageResult] = []

    # ------------------------------------------------------------------
    # Stage 1: existing master.py. DO NOT MODIFY MASTER.
    # ------------------------------------------------------------------
    master_cmd = [
        python_exec,
        str(project_root / "master.py"),
        "--plant",
        plant_name,
        "--output",
        str(output_dir),
    ]
    if no_cache:
        master_cmd.append("--no-cache")

    result = _run(
        master_cmd,
        cwd=project_root,
        env=env,
        stdout_line_callback=lambda line: _report_master_progress_line(line, progress_callback),
    )
    stages.append(result)

    if _master_failed(result):
        raise RuntimeError(_master_failure_report(result, output_dir))

    _require_output_folder(output_dir, result)
    output_graph_validation = _validate_plant_parts_and_edges(output_dir, plant_name)

    cache_publish_stats = {}
    if not no_cache:
        cache_publish_stats = publish_plant_caches(
            project_root,
            output_dir,
        )

    # ------------------------------------------------------------------
    # Stage 2: existing Phase 1 updater.
    # ------------------------------------------------------------------
    _safe_progress_callback(progress_callback, {
        "status": "running",
        "active": True,
        "complete": False,
        "phase_index": 11,
        "stage": "Final graph validation and canonical publication",
        "message": "Collector stages finished; validating and publishing canonical graph data.",
    })
    updater_cmd = [
        python_exec,
        "-m",
        "data_manager.updater",
        str(output_dir),
        "--store",
        str(store_root),
    ]
    result = _run(updater_cmd, cwd=phase1_root, env=env)
    stages.append(result)
    if not result.ok:
        stdout_path, stderr_path = _write_stage_logs(output_dir, result, "phase1")
        raise RuntimeError(
            _format_stage_failure(
                "PHASE 1 DATA MANAGER",
                result,
                extra=[
                    f"Phase 1 stdout log: {stdout_path}",
                    f"Phase 1 stderr log: {stderr_path}",
                ],
            )
        )

    phase1_report = _parse_json_stdout(result.stdout)
    if phase1_report is None:
        stdout_path, stderr_path = _write_stage_logs(output_dir, result, "phase1")
        raise RuntimeError(
            "Phase 1 completed but did not return the expected JSON report.\n"
            f"Phase 1 stdout log: {stdout_path}\n"
            f"Phase 1 stderr log: {stderr_path}\n"
            "Canonical data may have been updated; do not retry blindly until the store is inspected."
        )

    # ------------------------------------------------------------------
    # Stage 3: existing Phase 2 Neo4j sync.
    # ------------------------------------------------------------------
    database = env.get("NEO4J_DATABASE") or "neo4j"
    _safe_progress_callback(progress_callback, {
        "status": "running",
        "active": True,
        "complete": False,
        "phase_index": 11,
        "stage": "Synchronizing and verifying Neo4j graph",
        "message": "Canonical data is published; synchronizing the graph and verifying the plant relationships.",
    })
    sync_cmd = [
        python_exec,
        "-m",
        "data_manager.neo4j_sync",
        "--store",
        str(store_root),
        "--once",
        "--database",
        database,
    ]
    result = _run(sync_cmd, cwd=phase1_root, env=env)
    stages.append(result)
    if not result.ok:
        stdout_path, stderr_path = _write_stage_logs(output_dir, result, "phase2")
        raise RuntimeError(
            _format_stage_failure(
                "PHASE 2 NEO4J SYNC",
                result,
                extra=[
                    f"Phase 2 stdout log: {stdout_path}",
                    f"Phase 2 stderr log: {stderr_path}",
                ],
            )
        )

    phase2_report = _parse_json_stdout(result.stdout)
    if phase2_report is None:
        stdout_path, stderr_path = _write_stage_logs(output_dir, result, "phase2")
        raise RuntimeError(
            "Phase 2 completed but did not return the expected JSON report.\n"
            f"Phase 2 stdout log: {stdout_path}\n"
            f"Phase 2 stderr log: {stderr_path}\n"
            "Inspect Neo4j before considering ingestion complete."
        )

    graph_verification = _verify_synced_plant_parts(plant_name, env, database)

    return {
        "status": "success",
        "plant": plant_name,
        "graph_validation": output_graph_validation,
        "neo4j_verification": graph_verification,
        "collector_output": str(output_dir),
        "canonical_store": str(store_root),
        "shared_cache": {
            "prepared": cache_prepare_stats,
            "published": cache_publish_stats,
        },
        "phase1": phase1_report,
        "phase2": phase2_report,
        "stages": [
            {
                "name": stage.name,
                "returncode": stage.returncode,
                "duration_seconds": stage.duration_seconds,
            }
            for stage in stages
        ],
    }


def _format_stage_failure(
    label: str,
    result: StageResult,
    extra: list[str] | None = None,
) -> str:
    parts = [f"{label} failed (exit code {result.returncode})."]
    if result.stdout.strip():
        parts.append(f"STDOUT:\n{result.stdout.strip()}")
    if result.stderr.strip():
        parts.append(f"STDERR:\n{result.stderr.strip()}")
    if extra:
        parts.extend(extra)
    return "\n\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Production ingestion orchestrator: master.py -> Phase 1 -> Neo4j sync."
    )
    parser.add_argument(
        "--plant",
        required=True,
        help='Plant name, e.g. "Phyllanthus reticulatus"',
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional collector output directory. Relative paths are resolved from the project root (outside phase1_release).",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("data/canonical"),
        help="Phase 1 canonical store path, relative to phase1_release unless absolute.",
    )
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI"))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--database", default=os.getenv("NEO4J_DATABASE"))
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    try:
        output_dir = args.output
        if output_dir is not None and not output_dir.is_absolute():
            output_dir = (_project_root() / output_dir).resolve()

        store_root = args.store
        if not store_root.is_absolute():
            store_root = (_phase1_root() / store_root).resolve()

        report = ingest_plant(
            args.plant,
            output_dir=output_dir,
            store_root=store_root,
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password,
            neo4j_database=args.database,
            no_cache=args.no_cache,
        )
        print(json.dumps(report, indent=2))
    except Exception as exc:
        print(f"INGESTION FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
