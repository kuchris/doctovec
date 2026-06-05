from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


KEYWORDS = [
    "マルスホスト",
    "マルス",
    "ロジックサーバ",
    "シミュレータ",
    "エラー",
    "タイムアウト",
    "リトライ",
    "シーケンス",
    "インタフェース",
    "電文",
    "DB",
    "データベース",
    "ログ",
    "Splunk",
    "TCP",
    "UDP",
    "ポート",
    "端末",
    "中継サーバ",
    "ハンドラ",
    "プロセス",
    "設定値",
    "監視",
    "トランザクション",
    "照会",
    "応答",
    "要求",
]

DOC_ID_PATTERNS = [
    r"PG\d{4}[A-Z]-\d{3}",
    r"Qシ開-A-\d{5}-\d{2}",
    r"Qシ開-[A-Z]-\d{5}-\d{2}",
    r"\bA-\d{5}-\d{2}\b",
]
DOC_ID_RE = re.compile("|".join(f"(?:{pattern})" for pattern in DOC_ID_PATTERNS))
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
NUMBERED_HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+){0,5}|[０-９]+(?:[．.][０-９]+){0,5})[.\-－．)]?\s+(.{2,100})$")
SOURCE_RE = re.compile(r"^Source:\s*(.+?)\s*$")
SKIP_DIRS = {".docmemory", "docmemory_tool", "__pycache__", "node_modules", ".git", ".svn"}


@dataclass
class DocumentInfo:
    path: Path
    rel_path: str
    title: str
    source: str
    kind: str
    modified: str
    size: int
    line_count: int
    ids: list[str]
    references: list[str]
    headings: list[str]
    keywords: Counter[str]


def parse_args() -> argparse.Namespace:
    doctovec_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Generate a deterministic Markdown index for doctovec text documents.")
    parser.add_argument("--root", type=Path, default=doctovec_root, help="doctovec folder path.")
    parser.add_argument("--output", type=Path, default=None, help="Output Markdown file. Defaults to <root>/document_index.md.")
    parser.add_argument("--max-headings", type=int, default=18, help="Max headings to list per document.")
    parser.add_argument("--max-keywords", type=int, default=8, help="Max keyword counts to list per document.")
    return parser.parse_args()


def windows_long_path(path: Path) -> str:
    path_text = str(path.resolve())
    if sys.platform != "win32" or path_text.startswith("\\\\?\\"):
        return path_text
    if path_text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path_text[2:]
    return "\\\\?\\" + path_text


def read_text(path: Path) -> str:
    with open(windows_long_path(path), "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def write_text(path: Path, text: str) -> None:
    os.makedirs(windows_long_path(path.parent), exist_ok=True)
    with open(windows_long_path(path), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def stat_path(path: Path) -> os.stat_result:
    return os.stat(windows_long_path(path))


def relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def iter_text_files(document_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in document_dir.rglob("*.txt"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files, key=lambda p: str(p).casefold())


def classify(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    if "meeting" in parts:
        return "meeting transcript"
    if "text" in parts and "txt" in parts:
        return "generated office text"
    return "text note"


def extract_title(lines: list[str], path: Path) -> str:
    for line in lines[:40]:
        match = HEADING_RE.match(line)
        if match:
            title = clean_inline(match.group(2))
            if title:
                return title
    return path.stem


def extract_source(lines: list[str]) -> str:
    for line in lines[:20]:
        match = SOURCE_RE.match(line)
        if match:
            return clean_inline(match.group(1))
    return ""


def extract_headings(lines: list[str], max_headings: int) -> list[str]:
    headings: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = clean_inline(line)
        if not stripped or stripped.startswith("|") or stripped.startswith("["):
            continue
        heading = ""
        match = HEADING_RE.match(line)
        if match:
            heading = clean_inline(match.group(2))
        else:
            numbered = NUMBERED_HEADING_RE.match(stripped)
            if numbered:
                heading = f"{numbered.group(1)} {clean_inline(numbered.group(2))}"
        if not heading:
            continue
        if len(heading) > 140:
            heading = heading[:137] + "..."
        if heading in seen:
            continue
        seen.add(heading)
        headings.append(heading)
        if len(headings) >= max_headings:
            break
    return headings


def clean_inline(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_ids(text: str, path: Path) -> list[str]:
    values = set(DOC_ID_RE.findall(text))
    values.update(DOC_ID_RE.findall(str(path)))
    return sorted(values)


def extract_references(text: str, path: Path, ids: list[str]) -> list[str]:
    self_ids = set(DOC_ID_RE.findall(path.stem))
    self_ids.update(DOC_ID_RE.findall(str(path.parent)))
    body_ids = set(DOC_ID_RE.findall(text))
    refs = sorted(doc_id for doc_id in body_ids if doc_id not in self_ids)
    if not refs and ids:
        refs = []
    return refs


def count_keywords(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for keyword in KEYWORDS:
        count = text.count(keyword)
        if count:
            counts[keyword] = count
    return counts


def collect_document(path: Path, root: Path, max_headings: int) -> DocumentInfo:
    text = read_text(path)
    lines = text.splitlines()
    source = extract_source(lines)
    ids = extract_ids(text, path)
    stat = stat_path(path)
    return DocumentInfo(
        path=path,
        rel_path=relative_path(path, root),
        title=extract_title(lines, path),
        source=source,
        kind=classify(path),
        modified=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        size=stat.st_size,
        line_count=len(lines),
        ids=ids,
        references=extract_references(text, path, ids),
        headings=extract_headings(lines, max_headings),
        keywords=count_keywords(text),
    )


def markdown_escape(text: str) -> str:
    return text.replace("|", "\\|")


def format_keyword_counts(counter: Counter[str], max_items: int) -> str:
    if not counter:
        return "-"
    items = counter.most_common(max_items)
    return ", ".join(f"{key}: {value}" for key, value in items)


def make_anchor(index: int, doc: DocumentInfo) -> str:
    label = doc.ids[0] if doc.ids else doc.title
    return f"{index:03d}-{label}"


def render_index(docs: list[DocumentInfo], root: Path, max_keywords: int) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_keywords: Counter[str] = Counter()
    reverse_refs: dict[str, list[DocumentInfo]] = defaultdict(list)
    kind_counts: Counter[str] = Counter()

    for doc in docs:
        kind_counts[doc.kind] += 1
        all_keywords.update(doc.keywords)
        for ref in doc.references:
            reverse_refs[ref].append(doc)

    out: list[str] = []
    out.append("# Document Index")
    out.append("")
    out.append(f"Generated: {now}")
    out.append(f"Root: `{root}`")
    out.append("")
    out.append("This index is generated by deterministic file scanning. It does not use an LLM.")
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append(f"- Text files indexed: {len(docs)}")
    out.append(f"- Generated office text files: {kind_counts.get('generated office text', 0)}")
    out.append(f"- Meeting transcript files: {kind_counts.get('meeting transcript', 0)}")
    out.append(f"- Other text notes: {kind_counts.get('text note', 0)}")
    out.append("")
    out.append("## Keyword Overview")
    out.append("")
    if all_keywords:
        for keyword, count in all_keywords.most_common():
            out.append(f"- {keyword}: {count}")
    else:
        out.append("- No tracked keywords found.")
    out.append("")
    out.append("## Documents")
    out.append("")
    out.append("| No. | IDs | Title | Kind | Lines | Updated |")
    out.append("| --- | --- | --- | --- | ---: | --- |")
    for index, doc in enumerate(docs, 1):
        ids = ", ".join(doc.ids) if doc.ids else "-"
        out.append(
            f"| {index} | {markdown_escape(ids)} | {markdown_escape(doc.title)} | "
            f"{doc.kind} | {doc.line_count} | {doc.modified} |"
        )
    out.append("")

    out.append("## Document Details")
    out.append("")
    for index, doc in enumerate(docs, 1):
        out.append(f"### {make_anchor(index, doc)}")
        out.append("")
        out.append(f"- Title: {doc.title}")
        out.append(f"- Kind: {doc.kind}")
        out.append(f"- Text path: `{doc.rel_path}`")
        if doc.source:
            out.append(f"- Source: `{doc.source}`")
        out.append(f"- Updated: {doc.modified}")
        out.append(f"- Lines: {doc.line_count}")
        out.append(f"- IDs: {', '.join(doc.ids) if doc.ids else '-'}")
        out.append(f"- Keywords: {format_keyword_counts(doc.keywords, max_keywords)}")
        out.append(f"- References: {', '.join(doc.references[:20]) if doc.references else '-'}")
        if len(doc.references) > 20:
            out.append(f"- References omitted: {len(doc.references) - 20}")
        out.append("")
        out.append("Headings:")
        if doc.headings:
            for heading in doc.headings:
                out.append(f"- {heading}")
        else:
            out.append("- No headings detected.")
        out.append("")

    out.append("## Reference Map")
    out.append("")
    if reverse_refs:
        for ref in sorted(reverse_refs):
            out.append(f"### {ref}")
            for doc in sorted(reverse_refs[ref], key=lambda d: d.rel_path.casefold())[:20]:
                title = doc.ids[0] if doc.ids else doc.title
                out.append(f"- {title}: `{doc.rel_path}`")
            if len(reverse_refs[ref]) > 20:
                out.append(f"- ...and {len(reverse_refs[ref]) - 20} more")
            out.append("")
    else:
        out.append("No cross-document references detected.")
        out.append("")

    out.append("## Notes")
    out.append("")
    out.append("- Keyword counts are exact substring counts, not semantic counts.")
    out.append("- Heading extraction is rule-based and may miss headings flattened by Office-to-text conversion.")
    out.append("- Meeting transcripts may contain ASR errors; unclear terms should be checked against the audio or original meeting notes.")
    out.append("")
    return "\n".join(out)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    root = args.root.resolve()
    document_dir = root / "document"
    output = args.output or (root / "document_index.md")

    if not document_dir.exists():
        print(f"Document folder not found: {document_dir}", file=sys.stderr)
        return 1

    paths = iter_text_files(document_dir)
    docs = [collect_document(path, root, args.max_headings) for path in paths]
    write_text(output, render_index(docs, root, args.max_keywords))
    print(f"Wrote: {output}")
    print(f"Text files indexed: {len(docs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
