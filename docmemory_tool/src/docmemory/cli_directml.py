from __future__ import annotations

import os
from pathlib import Path

from . import cli


DIRECTML_VECTOR_MODEL = os.environ.get(
    "DOCMEMORY_DML_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
DIRECTML_BATCH_SIZE = int(os.environ.get("DOCMEMORY_DML_BATCH_SIZE", "32"))


def make_directml_embedding_model(TextEmbedding, model_name: str):
    cache_dir = Path(os.environ.get("DOCMEMORY_MODEL_DIR", str(cli.MODEL_CACHE_DIR))).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(
        model_name=model_name,
        cache_dir=str(cache_dir),
        providers=["DmlExecutionProvider", "CPUExecutionProvider"],
    )


def main(argv: list[str] | None = None) -> int:
    cli.DEFAULT_VECTOR_MODEL = DIRECTML_VECTOR_MODEL
    cli.VECTOR_BATCH_SIZE = DIRECTML_BATCH_SIZE
    cli.make_embedding_model = make_directml_embedding_model
    return cli.main(argv)
