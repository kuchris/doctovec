from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import time
import warnings
from array import array
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path


DEFAULT_IGNORES = [".docmemory", "_history", ".git", ".svn", "__pycache__", "node_modules"]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_CACHE_DIR = PROJECT_ROOT / ".models"
INDEX_DIR = ".docmemory"
DB_NAME = "docmemory.sqlite"
CONFIG_NAME = "config.json"
CHUNK_MAX_CHARS = 1800
DEFAULT_VECTOR_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
VECTOR_BATCH_SIZE = 64
VECTOR_PARALLEL = int(os.environ.get("DOCMEMORY_VECTOR_PARALLEL", "0"))
VECTOR_MAX_CHARS = int(os.environ.get("DOCMEMORY_VECTOR_MAX_CHARS", "0"))
HYBRID_CANDIDATES = 40
RRF_K = 60


@dataclass
class Chunk:
    title: str
    body: str
    line_start: int
    line_end: int


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted. Existing committed index was left as-is.", file=sys.stderr)
        return 130
    except DocMemoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="docmemory")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="create or rebuild a doc index")
    init_p.add_argument("target", nargs="?", default=".", help="document folder")
    init_p.add_argument("-i", "--interactive", action="store_true", help="accepted for CodeGraph-style init")
    init_p.add_argument("--ignore", action="append", default=[], help="folder name or glob to ignore")
    init_p.add_argument("--vector", action="store_true", help="also build local embedding vectors")
    init_p.add_argument("--model", default=DEFAULT_VECTOR_MODEL, help="FastEmbed model for --vector")
    init_p.set_defaults(func=cmd_init)

    sync_p = sub.add_parser("sync", help="rebuild the existing index")
    sync_p.add_argument("target", nargs="?", default=".", help="document folder")
    sync_p.add_argument("--vector", action="store_true", help="also rebuild local embedding vectors")
    sync_p.add_argument("--model", default="", help="FastEmbed model for --vector")
    sync_p.set_defaults(func=cmd_sync)

    status_p = sub.add_parser("status", help="show index status")
    status_p.add_argument("target", nargs="?", default=".", help="document folder")
    status_p.set_defaults(func=cmd_status)

    search_p = sub.add_parser("search", help="search indexed text snippets")
    search_p.add_argument("items", nargs="+", help='query, or "target query" when first item is a folder')
    search_p.add_argument("-n", "--limit", type=int, default=10, help="maximum results")
    search_p.add_argument("-C", "--context", type=int, default=0, help="extra surrounding chunks per result")
    search_p.add_argument("--vector", action="store_true", help="use vector search only")
    search_p.add_argument("--hybrid", action="store_true", help="combine BM25 and vector results")
    search_p.set_defaults(func=cmd_search)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    target = resolve_target(args.target)
    ignores = merge_ignores(DEFAULT_IGNORES, args.ignore)
    write_config(target, ignores, args.model if args.vector else "")
    indexed = rebuild_index(target, ignores, vector=args.vector, model_name=args.model)
    print(f"Initialized: {target}")
    print(f"DB: {db_path(target)}")
    print(f"Ignored: {', '.join(ignores)}")
    print(f"Indexed files: {indexed['files']} | Chunks: {indexed['chunks']}")
    print(f"Tokenizer: {indexed['tokenizer']}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    target = resolve_target(args.target)
    config = read_config(target)
    model_name = args.model or config.get("vector_model") or DEFAULT_VECTOR_MODEL
    indexed = rebuild_index(target, config["ignore"], vector=args.vector, model_name=model_name)
    print(f"Synced: {target}")
    print(f"Indexed files: {indexed['files']} | Chunks: {indexed['chunks']}")
    print(f"Tokenizer: {indexed['tokenizer']}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    target = resolve_target(args.target)
    db = db_path(target)
    config = read_config(target)
    if not db.exists():
        raise DocMemoryError(f"index not found: {db}")
    with sqlite3.connect(db) as conn:
        files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        vectors = conn.execute("SELECT COUNT(*) FROM chunk_vectors").fetchone()[0]
        tokenizer = conn.execute("SELECT value FROM meta WHERE key = 'tokenizer'").fetchone()
        vector_model = conn.execute("SELECT value FROM meta WHERE key = 'vector_model'").fetchone()
    print(f"Target: {target}")
    print(f"DB: {db}")
    print(f"Files: {files} | Chunks: {chunks} | Vectors: {vectors}")
    print(f"Tokenizer: {tokenizer[0] if tokenizer else 'unknown'}")
    print(f"Vector model: {vector_model[0] if vector_model else 'none'}")
    print(f"Ignored: {', '.join(config['ignore'])}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    target, query = parse_search_target_and_query(args.items)
    config = read_config(target)
    db = db_path(target)
    if not db.exists():
        raise DocMemoryError(f"index not found: {db}")
    if args.vector and args.hybrid:
        raise DocMemoryError("use --vector or --hybrid, not both")
    if args.vector:
        results = vector_search(db, query, max(1, args.limit))
    elif args.hybrid:
        results = hybrid_search(db, query, max(1, args.limit))
    else:
        results = bm25_search(db, query, max(1, args.limit))
    if not results:
        print("No matches.")
        return 0
    print(f"Target: {target}")
    print(f"Query: {query}")
    print("")
    for index, row in enumerate(results, start=1):
        path, title, line_start, line_end, snippet, score = row
        print(f"[{index}] {path}:{line_start}-{line_end} score={score:.4f}")
        if title:
            print(f"    # {title}")
        print(indent_snippet(clean_snippet(snippet)))
        if args.context > 0:
            for extra in surrounding_chunks(db, path, line_start, args.context):
                print(indent_snippet(extra))
        print("")
    _ = config
    return 0


def resolve_target(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise DocMemoryError(f"target does not exist: {path}")
    if not path.is_dir():
        raise DocMemoryError(f"target is not a folder: {path}")
    return path


def parse_search_target_and_query(items: list[str]) -> tuple[Path, str]:
    if len(items) >= 2:
        possible_target = Path(items[0]).expanduser()
        if possible_target.exists() and possible_target.is_dir():
            return resolve_target(items[0]), " ".join(items[1:]).strip()
    query = " ".join(items).strip()
    if not query:
        raise DocMemoryError("empty query")
    return resolve_target("."), query


def merge_ignores(defaults: list[str], extras: list[str]) -> list[str]:
    merged: list[str] = []
    for item in defaults + extras:
        normalized = item.strip().replace("\\", "/")
        if normalized and normalized not in merged:
            merged.append(normalized)
    return merged


def index_dir(target: Path) -> Path:
    return target / INDEX_DIR


def db_path(target: Path) -> Path:
    return index_dir(target) / DB_NAME


def config_path(target: Path) -> Path:
    return index_dir(target) / CONFIG_NAME


def write_config(target: Path, ignores: list[str], vector_model: str = "") -> None:
    index_dir(target).mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "ignore": ignores,
        "pattern": "**/*.txt",
        "vector_model": vector_model,
    }
    config_path(target).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (index_dir(target) / ".gitignore").write_text("*\n", encoding="utf-8")


def read_config(target: Path) -> dict:
    path = config_path(target)
    if not path.exists():
        raise DocMemoryError(f"config not found; run init first: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    ignores = data.get("ignore")
    if not isinstance(ignores, list):
        ignores = DEFAULT_IGNORES
    vector_model = data.get("vector_model")
    return {
        "ignore": [str(item) for item in ignores],
        "vector_model": str(vector_model) if vector_model else "",
    }


def rebuild_index(target: Path, ignores: list[str], vector: bool = False, model_name: str = DEFAULT_VECTOR_MODEL) -> dict:
    index_dir(target).mkdir(parents=True, exist_ok=True)
    db = db_path(target)
    markdown_files = list(iter_markdown_files(target, ignores))
    total_files = len(markdown_files)
    if not sys.stdout.isatty():
        print(f"Indexing {total_files} text file(s)...")
    with sqlite3.connect(db) as conn:
        create_schema(conn, tokenizer="trigram")
        tokenizer = conn.execute("SELECT value FROM meta WHERE key = 'tokenizer'").fetchone()[0]
        conn.execute("DELETE FROM chunk_vectors")
        conn.execute("DELETE FROM chunks_fts")
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM files")
        chunk_count = 0
        for index, file_path in enumerate(markdown_files, start=1):
            show_progress(index, total_files, file_path.relative_to(target).as_posix())
            rel_path = file_path.relative_to(target).as_posix()
            text = read_text(file_path)
            stat = stat_path(file_path)
            cursor = conn.execute(
                """
                INSERT INTO files(path, mtime_ns, size_bytes)
                VALUES (?, ?, ?)
                """,
                (rel_path, stat.st_mtime_ns, stat.st_size),
            )
            file_id = cursor.lastrowid
            for chunk in chunk_markdown(text):
                chunk_cursor = conn.execute(
                    """
                    INSERT INTO chunks(file_id, path, title, body, line_start, line_end)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (file_id, rel_path, chunk.title, chunk.body, chunk.line_start, chunk.line_end),
                )
                chunk_id = chunk_cursor.lastrowid
                conn.execute(
                    """
                    INSERT INTO chunks_fts(rowid, title, body, path, chunk_id, line_start, line_end)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (chunk_id, chunk.title, chunk.body, rel_path, chunk_id, chunk.line_start, chunk.line_end),
                )
                chunk_count += 1
        if vector:
            embed_chunks(conn, model_name)
    finish_progress(total_files)
    return {"files": len(markdown_files), "chunks": chunk_count, "tokenizer": tokenizer}


def create_schema(conn: sqlite3.Connection, tokenizer: str) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS chunks_fts;
        CREATE TABLE IF NOT EXISTS meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS files(
            file_id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            mtime_ns INTEGER NOT NULL,
            size_bytes INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunks(
            chunk_id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            FOREIGN KEY(file_id) REFERENCES files(file_id)
        );
        CREATE TABLE IF NOT EXISTS chunk_vectors(
            chunk_id INTEGER PRIMARY KEY,
            path TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            embedding BLOB NOT NULL,
            FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id)
        );
        """
    )
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                title,
                body,
                path UNINDEXED,
                chunk_id UNINDEXED,
                line_start UNINDEXED,
                line_end UNINDEXED,
                tokenize = 'trigram'
            )
            """
        )
        chosen = tokenizer
    except sqlite3.OperationalError:
        conn.execute(
            """
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                title,
                body,
                path UNINDEXED,
                chunk_id UNINDEXED,
                line_start UNINDEXED,
                line_end UNINDEXED
            )
            """
        )
        chosen = "unicode61"
    conn.execute(
        """
        INSERT INTO meta(key, value) VALUES('tokenizer', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (chosen,),
    )
    conn.execute("DELETE FROM meta WHERE key = 'vector_model'")
    conn.execute("DELETE FROM meta WHERE key = 'vector_dim'")


def iter_markdown_files(target: Path, ignores: list[str]):
    for path in target.rglob("*.txt"):
        if path.name.startswith("~$"):
            continue
        rel = path.relative_to(target)
        if should_ignore(rel, ignores):
            continue
        yield path


def should_ignore(rel: Path, ignores: list[str]) -> bool:
    parts = [part.lower() for part in rel.parts]
    rel_text = rel.as_posix().lower()
    for pattern in ignores:
        normalized = pattern.lower().strip().replace("\\", "/")
        if not normalized:
            continue
        if "/" not in normalized and normalized in parts:
            return True
        if fnmatch(rel_text, normalized) or any(fnmatch(part, normalized) for part in parts):
            return True
    return False


def chunk_markdown(text: str) -> list[Chunk]:
    lines = text.splitlines()
    chunks: list[Chunk] = []
    title = ""
    buffer: list[str] = []
    start_line = 1

    def flush(end_line: int) -> None:
        nonlocal buffer, start_line
        body = "\n".join(buffer).strip()
        if body:
            chunks.append(Chunk(title=title, body=body, line_start=start_line, line_end=end_line))
        buffer = []
        start_line = end_line + 1

    for idx, line in enumerate(lines, start=1):
        heading = parse_heading(line)
        if heading:
            flush(idx - 1)
            title = heading
            start_line = idx
            buffer = [line]
            continue
        if not buffer:
            start_line = idx
        buffer.append(line)
        if sum(len(item) + 1 for item in buffer) >= CHUNK_MAX_CHARS:
            flush(idx)
    flush(len(lines))
    return chunks


def parse_heading(line: str) -> str:
    match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
    if not match:
        return ""
    return match.group(2).strip().strip("#").strip()


def bm25_search(db: Path, query: str, limit: int) -> list[tuple]:
    match_query = build_match_query(query)
    with sqlite3.connect(db) as conn:
        try:
            return conn.execute(
                """
                SELECT
                    path,
                    title,
                    line_start,
                    line_end,
                    snippet(chunks_fts, 1, '[', ']', '...', 18) AS snippet_text,
                    bm25(chunks_fts) AS score
                FROM chunks_fts
                WHERE chunks_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (match_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return conn.execute(
                """
                SELECT
                    path,
                    title,
                    line_start,
                    line_end,
                    snippet(chunks_fts, 1, '[', ']', '...', 18) AS snippet_text,
                    bm25(chunks_fts) AS score
                FROM chunks_fts
                WHERE chunks_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (quote_fts_phrase(query), limit),
            ).fetchall()


def embed_chunks(conn: sqlite3.Connection, model_name: str) -> None:
    print(f"Embedding chunks with {model_name}...")
    show_setup_progress(0, 3, "Reading chunks from SQLite")
    rows = conn.execute(
        """
        SELECT chunk_id, path, line_start, title, body
        FROM chunks
        ORDER BY chunk_id
        """
    ).fetchall()
    show_setup_progress(1, 3, "Read chunks from SQLite")
    if not rows:
        finish_setup_progress()
        return
    show_setup_progress(1, 3, "Loading FastEmbed and ONNX Runtime")
    load_start = time.perf_counter()
    TextEmbedding = load_fastembed()
    show_setup_progress(
        2,
        3,
        "Loaded FastEmbed and ONNX Runtime",
        elapsed_seconds=time.perf_counter() - load_start,
    )
    show_setup_progress(2, 3, "Opening ONNX model and creating runtime session")
    model_start = time.perf_counter()
    model = make_embedding_model(TextEmbedding, model_name)
    show_setup_progress(
        3,
        3,
        "Runtime session ready",
        elapsed_seconds=time.perf_counter() - model_start,
    )
    finish_setup_progress()
    print(f"Embedding {len(rows)} chunk(s) with {model_name}...")
    vector_dim = 0
    total_batches = math.ceil(len(rows) / VECTOR_BATCH_SIZE)
    embed_total_start = time.perf_counter()
    for start in range(0, len(rows), VECTOR_BATCH_SIZE):
        batch = rows[start : start + VECTOR_BATCH_SIZE]
        batch_no = (start // VECTOR_BATCH_SIZE) + 1
        note = "warmup/compile" if batch_no == 1 else ""
        show_embedding_progress(start, len(rows), model_name, batch_no, total_batches, note=note)
        batch_start = time.perf_counter()
        texts = [
            prepare_embedding_text(format_passage(title, body, model_name))
            for _, _, _, title, body in batch
        ]
        embed_texts = pad_final_batch_texts(texts)
        embeddings = embed_texts_with_model(model, embed_texts)[: len(batch)]
        embed_seconds = time.perf_counter() - batch_start
        records = []
        for row, embedding in zip(batch, embeddings):
            chunk_id, path, line_start, _title, _body = row
            packed = pack_vector(embedding)
            vector_dim = len(embedding)
            records.append((chunk_id, path, line_start, packed))
        conn.executemany(
            """
            INSERT INTO chunk_vectors(chunk_id, path, line_start, embedding)
            VALUES (?, ?, ?, ?)
            """,
            records,
        )
        show_embedding_progress(
            min(start + len(batch), len(rows)),
            len(rows),
            model_name,
            batch_no,
            total_batches,
            embed_seconds=embed_seconds,
            note=note,
        )
    finish_embedding_progress(len(rows))
    print(f"Embedding done: {len(rows)} chunk(s) in {format_duration(time.perf_counter() - embed_total_start)}")
    conn.execute(
        """
        INSERT INTO meta(key, value) VALUES('vector_model', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (model_name,),
    )
    conn.execute(
        """
        INSERT INTO meta(key, value) VALUES('vector_dim', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(vector_dim),),
    )


def load_fastembed():
    try:
        warnings.filterwarnings(
            "ignore",
            message=".*now uses mean pooling instead of CLS embedding.*",
            category=UserWarning,
        )
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise DocMemoryError(
            "vector search needs FastEmbed; run from DocMemory with: uv run --extra vector docmemory ..."
        ) from exc
    return TextEmbedding


def make_embedding_model(TextEmbedding, model_name: str):
    cache_dir = Path(os.environ.get("DOCMEMORY_MODEL_DIR", str(MODEL_CACHE_DIR))).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(model_name=model_name, cache_dir=str(cache_dir))


def vector_search(db: Path, query: str, limit: int) -> list[tuple]:
    with sqlite3.connect(db) as conn:
        model_name = read_meta(conn, "vector_model")
        if not model_name:
            raise DocMemoryError("no vectors found; run: docmemory sync TARGET --vector")
        TextEmbedding = load_fastembed()
        model = make_embedding_model(TextEmbedding, model_name)
        query_embedding = list(model.embed([format_query(query, model_name)]))[0]
        query_vector = [float(item) for item in query_embedding]
        scored = []
        for chunk_id, embedding_blob in conn.execute(
            "SELECT chunk_id, embedding FROM chunk_vectors"
        ):
            score = cosine_similarity(query_vector, unpack_vector(embedding_blob))
            scored.append((score, chunk_id))
        scored.sort(reverse=True)
        ids = [chunk_id for _score, chunk_id in scored[:limit]]
        rows = rows_for_chunk_ids(conn, ids)
        rank_score = {chunk_id: score for score, chunk_id in scored[:limit]}
        return [
            make_result_row(row, rank_score[row[0]])
            for row in rows
        ]


def hybrid_search(db: Path, query: str, limit: int) -> list[tuple]:
    bm25_rows = bm25_search(db, query, HYBRID_CANDIDATES)
    vector_rows = vector_search(db, query, HYBRID_CANDIDATES)
    scores: dict[tuple[str, int], float] = {}
    rows_by_key: dict[tuple[str, int], tuple] = {}
    for rank, row in enumerate(bm25_rows, start=1):
        key = (row[0], row[2])
        scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
        rows_by_key[key] = row
    for rank, row in enumerate(vector_rows, start=1):
        key = (row[0], row[2])
        scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
        rows_by_key[key] = row
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    results = []
    for key, score in ordered:
        path, title, line_start, line_end, snippet, _old_score = rows_by_key[key]
        results.append((path, title, line_start, line_end, snippet, score))
    return results


def read_meta(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else ""


def rows_for_chunk_ids(conn: sqlite3.Connection, chunk_ids: list[int]) -> list[tuple]:
    if not chunk_ids:
        return []
    placeholders = ",".join("?" for _ in chunk_ids)
    rows = conn.execute(
        f"""
        SELECT chunk_id, path, title, line_start, line_end, body
        FROM chunks
        WHERE chunk_id IN ({placeholders})
        """,
        chunk_ids,
    ).fetchall()
    by_id = {row[0]: row for row in rows}
    return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]


def make_result_row(row: tuple, score: float) -> tuple:
    _chunk_id, path, title, line_start, line_end, body = row
    return (path, title, line_start, line_end, clean_snippet(body), score)


def format_query(text: str, model_name: str) -> str:
    text = text.strip()
    return f"query: {text}" if uses_e5_prefix(model_name) else text


def format_passage(title: str, body: str, model_name: str) -> str:
    prefix = f"{title}\n" if title else ""
    text = f"{prefix}{body}"
    return f"passage: {text}" if uses_e5_prefix(model_name) else text


def pad_final_batch_texts(texts: list[str]) -> list[str]:
    if not texts or len(texts) >= VECTOR_BATCH_SIZE:
        return texts
    return texts + [texts[-1]] * (VECTOR_BATCH_SIZE - len(texts))


def prepare_embedding_text(text: str) -> str:
    if VECTOR_MAX_CHARS > 0 and len(text) > VECTOR_MAX_CHARS:
        return text[:VECTOR_MAX_CHARS]
    return text


def embed_texts_with_model(model, texts: list[str]) -> list:
    if VECTOR_PARALLEL > 0:
        return list(model.embed(texts, parallel=VECTOR_PARALLEL))
    return list(model.embed(texts))


def uses_e5_prefix(model_name: str) -> bool:
    return "e5" in model_name.lower()


def pack_vector(values) -> bytes:
    vec = array("f", (float(item) for item in values))
    return vec.tobytes()


def unpack_vector(value: bytes) -> array:
    vec = array("f")
    vec.frombytes(value)
    return vec


def cosine_similarity(left, right) -> float:
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        af = float(a)
        bf = float(b)
        dot += af * bf
        left_norm += af * af
        right_norm += bf * bf
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


def build_match_query(query: str) -> str:
    query = query.strip()
    if not query:
        raise DocMemoryError("empty query")
    terms = re.findall(r'"[^"]+"|\S+', query)
    cleaned = [term if term.startswith('"') else quote_fts_phrase(term) for term in terms]
    return " ".join(cleaned)


def quote_fts_phrase(value: str) -> str:
    escaped = value.strip().strip('"').replace('"', '""')
    return f'"{escaped}"'


def show_progress(current: int, total: int, label: str) -> None:
    if total <= 0 or not sys.stdout.isatty():
        return
    step = max(1, total // 20)
    if current not in {1, total} and current % step != 0:
        return
    width = 28
    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    clipped = label[-70:] if len(label) > 70 else label
    write_progress_line(f"Indexing [{bar}] {current}/{total} {clipped}")


def finish_progress(total: int) -> None:
    if total > 0 and sys.stdout.isatty():
        sys.stdout.write("\n")
        sys.stdout.flush()


def show_setup_progress(
    current: int,
    total: int,
    label: str,
    elapsed_seconds: float | None = None,
) -> None:
    if total <= 0:
        return
    timing_label = f" {elapsed_seconds:.2f}s" if elapsed_seconds is not None else ""
    if not sys.stdout.isatty():
        print(f"Vector setup: {current}/{total} {label}{timing_label}")
        return
    width = 28
    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    clipped = label[-70:] if len(label) > 70 else label
    write_progress_line(f"Vector setup [{bar}] {current}/{total} {clipped}{timing_label}")


def finish_setup_progress() -> None:
    if sys.stdout.isatty():
        sys.stdout.write("\n")
        sys.stdout.flush()


def show_embedding_progress(
    current: int,
    total: int,
    model_name: str,
    batch_no: int | None = None,
    total_batches: int | None = None,
    embed_seconds: float | None = None,
    note: str = "",
) -> None:
    if total <= 0:
        return
    batch_label = ""
    if batch_no is not None and total_batches is not None:
        batch_label = f" batch {batch_no}/{total_batches}"
    note_label = f" {note}" if note else ""
    timing_label = f" {embed_seconds:.2f}s" if embed_seconds is not None else ""
    if not sys.stdout.isatty():
        if current == 0:
            print(f"Embedding progress: 0/{total}{batch_label}{note_label}")
        elif current == total:
            print(f"Embedding progress: {total}/{total}{batch_label}{note_label}{timing_label}")
        elif batch_no is not None:
            print(f"Embedding progress: {current}/{total}{batch_label}{note_label}{timing_label}")
        return
    step = max(1, total // 20)
    if current not in {0, total} and current % step != 0:
        return
    width = 28
    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    label = model_name[-50:] if len(model_name) > 50 else model_name
    write_progress_line(f"Embedding [{bar}] {current}/{total}{batch_label}{note_label}{timing_label} {label}")


def finish_embedding_progress(total: int) -> None:
    if total > 0 and sys.stdout.isatty():
        sys.stdout.write("\n")
        sys.stdout.flush()


def write_progress_line(text: str) -> None:
    columns = shutil.get_terminal_size(fallback=(120, 20)).columns
    width = max(1, columns - 1)
    sys.stdout.write("\r" + text[:width].ljust(width))
    sys.stdout.flush()


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{seconds:.2f}s"


def read_text(path: Path) -> str:
    with open(long_path(path), "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def stat_path(path: Path) -> os.stat_result:
    return os.stat(long_path(path))


def long_path(path: Path) -> str:
    value = str(path.resolve())
    if os.name != "nt":
        return value
    if value.startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value.lstrip("\\")
    return "\\\\?\\" + value


def surrounding_chunks(db: Path, path: str, line_start: int, context: int) -> list[str]:
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            """
            SELECT body FROM chunks
            WHERE path = ? AND line_start < ?
            ORDER BY line_start DESC
            LIMIT ?
            """,
            (path, line_start, context),
        ).fetchall()
    return [clean_snippet(row[0]) for row in reversed(rows)]


def clean_snippet(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value[:700] + ("..." if len(value) > 700 else "")


def indent_snippet(value: str) -> str:
    return "    " + value


class DocMemoryError(Exception):
    pass


if __name__ == "__main__":
    raise SystemExit(main())
