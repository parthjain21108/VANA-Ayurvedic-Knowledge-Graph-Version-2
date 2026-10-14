"""Read-only live stats and plant directory endpoints for Vana's staging UI.

This module does not alter query orchestration, plant resolution, ingestion, or Neo4j sync.
It queries the existing production graph schema through the configured Neo4j credentials.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from neo4j import GraphDatabase

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])

NODE_QUERIES: dict[str, str] = {
    "plants": "MATCH (n:`Plant Name`) RETURN count(n) AS count",
    "plant_parts": "MATCH (n:`Plant Part`) RETURN count(n) AS count",
    "phytochemicals": "MATCH (n:`Phytochemicals`) RETURN count(n) AS count",
    "bioactivities": "MATCH (n:`Bio-Activity`) RETURN count(n) AS count",
    "targets": "MATCH (n:`Targets`) RETURN count(n) AS count",
    "therapeutic_uses": "MATCH (n:`Therapeutic Uses`) RETURN count(n) AS count",
    "documents": "MATCH (n:`Documents`) RETURN count(n) AS count",
}

# These relationship types must match REL_CONFIG in phase1_release/data_manager/neo4j_sync.py.
# Neo4j stores them with spaces and title case, not as uppercase underscore names.
RELATIONSHIP_QUERIES: dict[str, str] = {
    "has_part": "MATCH ()-[r:`Has Part`]->() RETURN count(r) AS count",
    "contains": "MATCH ()-[r:`Contains`]->() RETURN count(r) AS count",
    "used_for": "MATCH ()-[r:`Used For`]->() RETURN count(r) AS count",
    "has_bioactivity": "MATCH ()-[r:`Has Bioactivity`]->() RETURN count(r) AS count",
    "measured_on": "MATCH ()-[r:`Measured On`]->() RETURN count(r) AS count",
    "reported_in": "MATCH ()-[r:`Reported In`]->() RETURN count(r) AS count",
}

TOTAL_RELATIONSHIPS_QUERY = "MATCH ()-[r]->() RETURN count(r) AS count"

STATS_QUERY = """
CALL { MATCH (n:`Plant Name`) RETURN count(n) AS plants }
CALL { MATCH (n:`Plant Part`) RETURN count(n) AS plant_parts }
CALL { MATCH (n:`Phytochemicals`) RETURN count(n) AS phytochemicals }
CALL { MATCH (n:`Bio-Activity`) RETURN count(n) AS bioactivities }
CALL { MATCH (n:`Targets`) RETURN count(n) AS targets }
CALL { MATCH (n:`Therapeutic Uses`) RETURN count(n) AS therapeutic_uses }
CALL { MATCH (n:`Documents`) RETURN count(n) AS documents }
CALL { MATCH ()-[r:`Has Part`]->() RETURN count(r) AS has_part }
CALL { MATCH ()-[r:`Contains`]->() RETURN count(r) AS contains }
CALL { MATCH ()-[r:`Used For`]->() RETURN count(r) AS used_for }
CALL { MATCH ()-[r:`Has Bioactivity`]->() RETURN count(r) AS has_bioactivity }
CALL { MATCH ()-[r:`Measured On`]->() RETURN count(r) AS measured_on }
CALL { MATCH ()-[r:`Reported In`]->() RETURN count(r) AS reported_in }
CALL { MATCH ()-[r]->() RETURN count(r) AS total_relationships }
RETURN plants, plant_parts, phytochemicals, bioactivities, targets,
       therapeutic_uses, documents, has_part, contains, used_for,
       has_bioactivity, measured_on, reported_in, total_relationships
"""


def _connection_details() -> tuple[str, str, str, str]:
    uri = os.getenv("NEO4J_URI", "").strip()
    user = os.getenv("NEO4J_USER", os.getenv("NEO4J_USERNAME", "")).strip()
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j"
    if not uri or not user or password is None:
        raise RuntimeError("Neo4j connection environment variables are incomplete.")
    return uri, user, password, database


def _first_common_name(value: Any) -> str | None:
    """Return the first common name while tolerating list and JSON-list storage."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            text = str(item).strip()
            if text:
                return text
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return _first_common_name(parsed)
        return text
    return str(value).strip() or None


def _read_with_session(callback):
    uri, user, password, database = _connection_details()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            return callback(session)
    finally:
        driver.close()


def _count(session, query: str) -> int:
    record = session.run(query).single()
    return int(record["count"] if record else 0)


@router.get("/stats")
def knowledge_base_stats() -> dict[str, Any]:
    """Read all dashboard counts in one Neo4j round trip."""
    try:
        def read(session):
            record = session.run(STATS_QUERY).single()
            if record is None:
                raise RuntimeError("Neo4j stats query returned no record.")
            nodes = {
                key: int(record[key] or 0)
                for key in NODE_QUERIES
            }
            relationships = {
                key: int(record[key] or 0)
                for key in RELATIONSHIP_QUERIES
            }
            return {
                "nodes": nodes,
                "relationships": relationships,
                "total_nodes": sum(nodes.values()),
                "total_relationships": int(record["total_relationships"] or 0),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        return _read_with_session(read)
    except Exception as exc:
        print(f"KNOWLEDGE BASE /stats FAILED: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Knowledge base statistics are temporarily unavailable.",
        ) from exc


@router.get("/plants")
def knowledge_base_plants() -> list[dict[str, str | None]]:
    """Return the live plant list in the exact array format expected by the UI."""
    try:
        def read(session):
            records = session.run(
                """
                MATCH (p:`Plant Name`)
                RETURN p.scientific_name AS scientific_name,
                       p.common_names AS common_names
                ORDER BY toLower(coalesce(p.scientific_name, ''))
                """
            )
            plants: list[dict[str, str | None]] = []
            for record in records:
                scientific_name = str(record.get("scientific_name") or "").strip()
                if not scientific_name:
                    continue
                plants.append({
                    "scientific_name": scientific_name,
                    "common_names": _first_common_name(record.get("common_names")),
                })
            return plants
        return _read_with_session(read)
    except Exception as exc:
        print(f"KNOWLEDGE BASE /plants FAILED: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Plant directory is temporarily unavailable.",
        ) from exc
