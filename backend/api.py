"""
Phase 5 HTTP API for the Ayurvedic knowledge graph.

Thin HTTP boundary around query_orchestrator.run_query().
It does not modify the collector, ingestion pipeline, Phase 1, Phase 2,
Neo4j sync, entity resolver, or graph query engine.
"""

from __future__ import annotations

import argparse
import os
import uuid
from typing import Any

from query_orchestrator import run_query
from frontend_response_contract import build_frontend_response
from knowledge_base_endpoint import router as knowledge_base_router
from query_progress import get_query_progress, publish_query_progress, register_query


try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "Phase 5 requires FastAPI and Pydantic. "
        "Install with: pip install fastapi uvicorn"
    ) from exc


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language user query.")
    request_id: str | None = Field(default=None, min_length=1, max_length=100)


class QueryResponse(BaseModel):
    status: str
    request_id: str | None = None
    query: str | None = None
    intent: str | None = None
    entities: list[dict[str, Any]] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    ingestion: dict[str, Any] = Field(default_factory=dict)
    graph: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    llm_context: dict[str, Any] | None = None
    answer: dict[str, Any] | None = None
    frontend: dict[str, Any] | None = None
    clarification_question: str | None = None
    unresolved_entities: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ayurvedic Knowledge Graph API",
        version="0.2.0",
        description=(
            "HTTP API around the validated query orchestration, grounded answer, "
            "and deterministic frontend response-contract pipeline."
        ),
    )

    # Development-friendly CORS. Restrict this with FRONTEND_ORIGINS in production.
    origins_raw = os.getenv("FRONTEND_ORIGINS", "*")
    allow_origins = [x.strip() for x in origins_raw.split(",") if x.strip()]
    allow_credentials = allow_origins != ["*"]

    app.include_router(knowledge_base_router)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/query", response_model=QueryResponse)
    def query_endpoint(payload: QueryRequest) -> dict[str, Any]:
        text = payload.query.strip()
        if not text:
            raise HTTPException(status_code=400, detail="query must not be empty")

        request_id = payload.request_id or str(uuid.uuid4())
        register_query(request_id)

        def progress_callback(update: dict[str, Any]) -> None:
            publish_query_progress(request_id, update)

        try:
            result = run_query(text, progress_callback=progress_callback)
            result["frontend"] = build_frontend_response(result)
            result["request_id"] = request_id

            ingestion = result.get("ingestion") or {}
            router_result = ingestion.get("router") or {}
            current = get_query_progress(request_id) or {}
            is_verified_new_plant = (
                ingestion.get("required") is True
                and ingestion.get("started") is True
                and router_result.get("status") == "ingested"
                and bool((result.get("graph") or {}).get("nodes"))
            )
            if is_verified_new_plant and current.get("mode") == "new":
                publish_query_progress(request_id, {
                    "status": "complete", "active": True, "complete": True,
                    "phase_index": 0, "stage": "Plant graph verified",
                    "mode": "new", "plant_name": router_result.get("scientific_name"),
                    "message": "The plant and its relationships were verified, and the result is ready.",
                })
            else:
                publish_query_progress(request_id, {
                    "status": "complete", "active": False, "complete": True,
                    "message": "Query complete.",
                })
            return result
        except Exception as exc:
            current = get_query_progress(request_id) or {}
            is_new_flow = current.get("mode") == "new" and current.get("active") is True
            if current.get("status") != "failed":
                publish_query_progress(request_id, {
                    "status": "failed", "active": bool(is_new_flow), "complete": False,
                    "mode": "new" if is_new_flow else current.get("mode"),
                    "plant_name": current.get("plant_name"),
                    "message": "Vana could not verify the final graph result, so it has not reported this plant as successfully added. Check server logs before retrying.",
                })
            # Keep internal details server-side rather than returning credentials,
            # connection strings, or full stack traces to the browser.
            print(f"PHASE 5 /query FAILED: {type(exc).__name__}: {exc}")
            raise HTTPException(
                status_code=500,
                detail="Query processing failed. Check the API server logs.",
            ) from exc

    @app.get("/query-progress/{request_id}")
    def query_progress_endpoint(request_id: str) -> dict[str, Any]:
        progress = get_query_progress(request_id)
        if progress is None:
            raise HTTPException(status_code=404, detail="Query progress was not found.")
        return progress

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 5 HTTP API.")
    parser.add_argument("--host", default=os.getenv("API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("API_PORT", "8000")))
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Install Uvicorn first: pip install uvicorn"
        ) from exc

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
