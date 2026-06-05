from __future__ import annotations

import json
import os
import sqlite3
from enum import Enum
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from . import cli


mcp = FastMCP("docmemory_mcp")


class SearchMode(str, Enum):
    KEYWORD = "keyword"
    VECTOR = "vector"
    HYBRID = "hybrid"


class SearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(..., description="Search query, for example 'payment retry design'.", min_length=1)
    target: str | None = Field(
        default=None,
        description="Indexed Markdown folder. Defaults to DOCMEMORY_TARGET or current directory.",
    )
    mode: SearchMode = Field(
        default=SearchMode.HYBRID,
        description="Search mode: keyword for SQLite FTS, vector for embeddings, hybrid for both.",
    )
    limit: int = Field(default=5, description="Maximum results to return.", ge=1, le=20)
    context: int = Field(default=0, description="Previous chunks to include per result.", ge=0, le=3)


class StatusInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    target: str | None = Field(
        default=None,
        description="Indexed Markdown folder. Defaults to DOCMEMORY_TARGET or current directory.",
    )


@mcp.tool(
    name="docmemory_search",
    annotations={
        "title": "Search DocMemory Markdown Index",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def docmemory_search(params: SearchInput) -> str:
    """Search an indexed Markdown documentation folder.

    Args:
        params: SearchInput containing query, optional target folder, mode, limit, and context.

    Returns:
        JSON string with target, query, mode, index metadata, and ranked results.
        Each result includes path, title, line_start, line_end, score, snippet, and optional context.
    """
    try:
        target = _resolve_target(params.target)
        db = cli.db_path(target)
        _require_db(db, target)
        if params.mode == SearchMode.KEYWORD:
            rows = cli.bm25_search(db, params.query, params.limit)
        elif params.mode == SearchMode.VECTOR:
            rows = cli.vector_search(db, params.query, params.limit)
        else:
            rows = cli.hybrid_search(db, params.query, params.limit)

        results = [_format_result(db, row, params.context) for row in rows]
        return _json_response(
            {
                "target": str(target),
                "query": params.query,
                "mode": params.mode.value,
                "limit": params.limit,
                "index": _read_index_meta(db),
                "count": len(results),
                "results": results,
            }
        )
    except Exception as exc:
        return _json_response(_error_response(exc, "Search failed"))


@mcp.tool(
    name="docmemory_status",
    annotations={
        "title": "Show DocMemory Index Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def docmemory_status(params: StatusInput) -> str:
    """Return status for an indexed Markdown documentation folder.

    Args:
        params: StatusInput containing an optional target folder.

    Returns:
        JSON string with DB path, counts, tokenizer, vector model, and ignored folders.
    """
    try:
        target = _resolve_target(params.target)
        db = cli.db_path(target)
        _require_db(db, target)
        config = cli.read_config(target)
        status = {
            "target": str(target),
            "db": str(db),
            "ignore": config["ignore"],
            **_read_index_meta(db),
        }
        return _json_response(status)
    except Exception as exc:
        return _json_response(_error_response(exc, "Status failed"))


def _resolve_target(value: str | None) -> Path:
    target_value = value or os.environ.get("DOCMEMORY_TARGET") or "."
    return cli.resolve_target(target_value)


def _require_db(db: Path, target: Path) -> None:
    if not db.exists():
        raise cli.DocMemoryError(
            f"index not found for target {target}; run docmemory init or sync first"
        )


def _read_index_meta(db: Path) -> dict[str, Any]:
    with sqlite3.connect(db) as conn:
        files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        vectors = conn.execute("SELECT COUNT(*) FROM chunk_vectors").fetchone()[0]
        return {
            "files": files,
            "chunks": chunks,
            "vectors": vectors,
            "tokenizer": cli.read_meta(conn, "tokenizer") or "unknown",
            "vector_model": cli.read_meta(conn, "vector_model") or "",
            "vector_dim": cli.read_meta(conn, "vector_dim") or "",
        }


def _format_result(db: Path, row: tuple[Any, ...], context: int) -> dict[str, Any]:
    path, title, line_start, line_end, snippet, score = row
    result = {
        "path": path,
        "title": title,
        "line_start": line_start,
        "line_end": line_end,
        "score": float(score),
        "snippet": cli.clean_snippet(snippet),
    }
    if context > 0:
        result["context_before"] = cli.surrounding_chunks(db, path, line_start, context)
    return result


def _error_response(exc: Exception, message: str) -> dict[str, Any]:
    return {
        "error": message,
        "type": type(exc).__name__,
        "message": str(exc),
        "suggestion": "Check the target path, run docmemory status, or rebuild vectors if using vector/hybrid search.",
    }


def _json_response(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
