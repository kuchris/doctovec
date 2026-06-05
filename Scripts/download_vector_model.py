from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import warnings
from pathlib import Path


DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download/warm the DocMemory embedding model without indexing documents.")
    parser.add_argument("--model", default=os.environ.get("DOCMEMORY_DML_MODEL", DEFAULT_MODEL))
    parser.add_argument("--directml", action="store_true", help="Use DirectML provider when available.")
    return parser.parse_args()


class ProgressBar:
    def __init__(self, label: str, width: int = 28) -> None:
        self.label = label
        self.width = width
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> "ProgressBar":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        self._thread.join()
        if exc_type is None:
            bar = "#" * self.width
            print(f"\r{self.label} [{bar}] done")
        else:
            print()

    def _run(self) -> None:
        position = 0
        direction = 1
        block = 7
        while not self._stop.is_set():
            chars = ["-"] * self.width
            for offset in range(block):
                index = position + offset
                if 0 <= index < self.width:
                    chars[index] = "#"
            sys.stdout.write(f"\r{self.label} [{''.join(chars)}]")
            sys.stdout.flush()
            position += direction
            if position <= 0 or position + block >= self.width:
                direction *= -1
            time.sleep(0.12)


def main() -> int:
    args = parse_args()
    doctovec_root = Path(__file__).resolve().parent.parent
    cache_dir = Path(os.environ.get("DOCMEMORY_MODEL_DIR", doctovec_root / "docmemory_tool" / ".models")).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)

    warnings.filterwarnings(
        "ignore",
        message=".*now uses mean pooling instead of CLS embedding.*",
        category=UserWarning,
    )
    from fastembed import TextEmbedding

    kwargs = {
        "model_name": args.model,
        "cache_dir": str(cache_dir),
    }
    if args.directml:
        kwargs["providers"] = ["DmlExecutionProvider", "CPUExecutionProvider"]

    print(f"Model: {args.model}")
    print(f"Cache: {cache_dir}")
    with ProgressBar("Downloading/loading model"):
        model = TextEmbedding(**kwargs)
        list(model.embed(["model download warmup"]))
    print("Model ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
