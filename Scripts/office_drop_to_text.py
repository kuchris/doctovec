from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


OFFICE_EXTS = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}
SKIP_DIRS = {
    ".docmemory",
    "_history",
    "docmemory_tool",
    "markdown",
    "markdown_glm",
    "markdown_paddle",
    "markdown_paddle_vl",
    "markdown_ppstructure",
    "pdf",
    "skills",
    "text",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Office files directly to UTF-8 text for LLM/vector search.")
    parser.add_argument("inputs", nargs="+", type=Path, help="Office files or folders containing Office files.")
    parser.add_argument("--recursive", action="store_true", help="When an input is a folder, include subfolders too.")
    return parser.parse_args()


def find_soffice() -> str | None:
    found = shutil.which("soffice")
    if found:
        return found
    candidates = [
        Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
        Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def windows_long_path(path: Path) -> str:
    path_text = str(path.resolve())
    if sys.platform != "win32" or path_text.startswith("\\\\?\\"):
        return path_text
    if path_text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path_text[2:]
    return "\\\\?\\" + path_text


def path_exists(path: Path) -> bool:
    return os.path.exists(windows_long_path(path))


def mkdirs(path: Path) -> None:
    os.makedirs(windows_long_path(path), exist_ok=True)


def write_text_file(path: Path, text: str) -> None:
    with open(windows_long_path(path), "w", encoding="utf-8", newline="") as f:
        f.write(text)


def display_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def collect_office_files(inputs: list[Path], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        path = item.expanduser().resolve()
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            for child in sorted(path.glob(pattern)):
                if not child.is_file():
                    continue
                if child.name.startswith("~$"):
                    continue
                if child.suffix.lower() not in OFFICE_EXTS:
                    continue
                if SKIP_DIRS.intersection({part.lower() for part in child.parts}):
                    continue
                files.append(child)
        elif path.is_file() and path.suffix.lower() in OFFICE_EXTS and not path.name.startswith("~$"):
            files.append(path)
        else:
            print(f"[skip] not an Office file or folder: {path}")
    return files


def text_root_for(source: Path) -> Path:
    return source.parent / "text"


def expected_text(root: Path, stem: str) -> Path:
    return root / stem / "txt" / f"{stem}.txt"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(windows_long_path(path), "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def state_file_for(output_root: Path) -> Path:
    return output_root / "office_to_text_state.tsv"


def read_state(output_root: Path) -> dict[str, str]:
    state_file = state_file_for(output_root)
    if not path_exists(state_file):
        return {}
    state: dict[str, str] = {}
    with open(windows_long_path(state_file), "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("output_stem\t"):
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                state[parts[0]] = parts[2]
    return state


def write_state(output_root: Path, output_stem: str, source: Path, source_hash: str, text: Path, root: Path) -> None:
    state_file = state_file_for(output_root)
    rows: dict[str, tuple[str, str, str]] = {}
    if path_exists(state_file):
        with open(windows_long_path(state_file), "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line or line.startswith("output_stem\t"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 4:
                    rows[parts[0]] = (parts[1], parts[2], parts[3])
    rows[output_stem] = (display_path(source, root), source_hash, display_path(text, root))
    mkdirs(output_root)
    with open(windows_long_path(state_file), "w", encoding="utf-8", newline="") as f:
        f.write("output_stem\tsource_office\tsha256\ttext\n")
        for stem in sorted(rows):
            source_file, hash_value, text_file = rows[stem]
            f.write(f"{stem}\t{source_file}\t{hash_value}\t{text_file}\n")


def append_log(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8", newline="") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")


def clean_markitdown_text(text: str) -> str:
    cleaned_lines: list[str] = []
    blank_count = 0
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        if is_embedded_image_line(line):
            continue
        if is_noise_table_row(line):
            continue
        line = clean_nan_table_cells(line)
        if not line.strip():
            blank_count += 1
            if blank_count <= 2:
                cleaned_lines.append("")
            continue
        blank_count = 0
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip() + "\n"


def is_embedded_image_line(line: str) -> bool:
    return bool(re.match(r"^\s*!\[[^\]]*\]\(data:image/[^)]+\)\s*$", line))


def is_noise_table_row(line: str) -> bool:
    if "|" not in line:
        return False
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if not cells:
        return False
    if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
        return False
    return all(cell == "" or cell.lower() == "nan" for cell in cells)


def clean_nan_table_cells(line: str) -> str:
    if "|" not in line:
        return line
    cells = line.split("|")
    return "|".join("" if cell.strip().lower() == "nan" else cell for cell in cells)


def convert_legacy_with_libreoffice(source: Path) -> Path:
    soffice = find_soffice()
    if not soffice:
        raise RuntimeError("LibreOffice soffice.exe was not found for legacy Office fallback")
    suffix = ".docx" if source.suffix.lower() == ".doc" else ".pptx"
    stage = Path(tempfile.mkdtemp(prefix="office_to_text_legacy_"))
    staged_source = stage / source.name
    shutil.copy2(windows_long_path(source), windows_long_path(staged_source))
    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        suffix.lstrip("."),
        "--outdir",
        str(stage),
        str(staged_source),
    ]
    completed = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    converted = stage / f"{source.stem}{suffix}"
    if completed.returncode != 0 or not converted.exists():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"LibreOffice legacy conversion failed: {detail}")
    return converted


def convert_one(markitdown, source: Path, expected: Path, script_dir: Path) -> None:
    converted_stage: Path | None = None
    try:
        read_source = source
        if source.suffix.lower() in {".doc", ".ppt"}:
            converted_stage = convert_legacy_with_libreoffice(source)
            read_source = converted_stage
        result = markitdown.convert(str(read_source))
    finally:
        if converted_stage is not None:
            shutil.rmtree(converted_stage.parent, ignore_errors=True)
    body = clean_markitdown_text(result.text_content)
    header = [
        f"# {source.stem}",
        "",
        f"Source: {display_path(source, script_dir)}",
        f"Converted: {datetime.now().isoformat(timespec='seconds')}",
        "",
    ]
    mkdirs(expected.parent)
    write_text_file(expected, "\n".join(header) + body)


def progress_line(index: int, total: int, source: Path) -> str:
    percent = int((index / total) * 100) if total else 100
    return f"[{index}/{total}] {percent:3d}% {source.name}"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    doctovec_root = script_dir.parent
    log_dir = doctovec_root / "Logs"
    mkdirs(log_dir)
    run_log = log_dir / "office_to_text_last_run.log"
    failure_log = log_dir / "office_to_text_failures.tsv"
    run_log.write_text(f"Office to text run: {datetime.now().isoformat(timespec='seconds')}\n", encoding="utf-8")
    failure_log.write_text("source\texpected_text\terror\n", encoding="utf-8")

    sources = collect_office_files(args.inputs, args.recursive)
    if not sources:
        print("No Office files found.")
        return 1

    from markitdown import MarkItDown

    markitdown = MarkItDown()
    failures = 0
    total = len(sources)
    for index, source in enumerate(sources, start=1):
        output_root = text_root_for(source)
        output_stem = source.stem
        expected = expected_text(output_root, output_stem)
        source_hash = sha256_file(source)
        state = read_state(output_root)

        print()
        print(progress_line(index, total, source))
        print(f"[out] {output_root}")
        if path_exists(expected) and state.get(output_stem) == source_hash:
            print(f"[skip] Office content unchanged: {expected}")
            append_log(run_log, f"SKIP_UNCHANGED\t{display_path(source, doctovec_root)}\t{display_path(expected, doctovec_root)}")
            continue

        try:
            convert_one(markitdown, source, expected, doctovec_root)
            write_state(output_root, output_stem, source, source_hash, expected, doctovec_root)
            append_log(run_log, f"DONE\t{display_path(source, doctovec_root)}\t{display_path(expected, doctovec_root)}")
            print(f"[done] {expected}")
        except Exception as exc:
            failures += 1
            append_log(failure_log, f"{display_path(source, doctovec_root)}\t{display_path(expected, doctovec_root)}\t{exc}")
            print(f"[error] {exc}", file=sys.stderr)

    if failures:
        print(f"Finished with {failures} failure(s).")
        print(f"Failure list: {failure_log}")
        return 1
    print(f"Log file: {run_log}")
    print("Finished successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
