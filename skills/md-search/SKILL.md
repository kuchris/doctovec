---
name: md-search
description: Search generated project documentation with DocMemory MCP or DocMemory CLI vector search. Use when answering questions from converted Office/text project documents, DocMemory SQLite/vector indexes, doctovec document text files, meeting transcripts, specs, design documents, or when the user asks to search project docs.
---

# Document Vector Search

Use `document_index.md` as a routing map, then use the DocMemory vector index and source `.txt` files as the source of truth. Do not use a standalone keyword-search script for normal answers.

## Search Order

1. Check `docmemory_status` if available.
2. Check `document_index.md` when available to identify likely document IDs, titles, keywords, and text paths.
3. Use `docmemory_search` with `mode: "hybrid"` and `limit: 5`, preferably with refined terms from the document index.
4. If hybrid search fails because vectors are missing, use `docmemory_search` with `mode: "vector"` to confirm the vector problem, then ask the user to rebuild the vector index.
5. If MCP tools are unavailable but the local DocMemory tool exists, use the DocMemory CLI with `--hybrid`.
6. Use `rg` only to collect exact line evidence from likely files returned by DocMemory or from likely paths found in `document_index.md`.
7. If DocMemory MCP and CLI search are both unavailable, say vector search is unavailable and ask the user to build or configure the DocMemory index.
8. If no evidence is found, say the answer was not found in the indexed project documents.

## Target

Use the current project document folder as the target. For this handoff workflow, the expected target is the `doctovec` folder that contains:

- `.docmemory/docmemory.sqlite`
- `document/**/text/**/txt/*.txt`
- generated UTF-8 text files from Office documents
- optional meeting transcripts under `document/meeting/**`
- `document_index.md` as a human/LLM routing map

If the MCP reports that the index is missing or stale, ask the user to run:

```text
0_run_text_vector.bat
```

Use `drop_text_to_vector_dml.bat` to rebuild only the vector index after text files already exist.

## Scope Rules

- Use `document_index.md` to narrow candidate documents, then search current generated text documents in `doctovec`.
- Do not search the old `doc` Markdown/PDF workflow unless the user explicitly asks for old Markdown, MinerU, PDF, or history.
- Do not search `_history` unless the user asks to compare old, previous, past, or historical versions.
- DocMemory indexes current text files by default. For old/current diff requests, use DocMemory to locate the current document, then compare against any available history or source Office files with direct file reads.
- Do not cite `document_index.md` as the only evidence for factual document content unless the question is about the inventory/index itself. Use it to find the source `.txt`, then cite the source `.txt`.
- Do not use general knowledge when the answer should come from the documents.
- Keep Japanese filenames, document titles, and identifiers unchanged.
- Cite source text file paths for all factual answers.
- Quote only the smallest relevant text needed; summarize the rest.

## Practical Flow

For normal document questions:

1. Confirm the index is usable and contains vectors:

```powershell
uv run --directory doctovec\docmemory_tool docmemory status "$((Resolve-Path doctovec).Path)"
```

2. Use `document_index.md` as a routing map when available. Prefer `rg` on the index for IDs, titles, or important keywords instead of reading the whole file:

```powershell
rg -n "question keyword|document ID" "doctovec\document_index.md"
```

3. Search with hybrid vector search using refined terms from the index:

```powershell
uv run --directory doctovec\docmemory_tool docmemory search "$((Resolve-Path doctovec).Path)" "question or keyword" --hybrid -n 5
```

4. Open or grep only the returned text file paths to collect exact line evidence.

5. If DocMemory returns broad or noisy matches, refine the query with document IDs, section names, Japanese terms, interface names, or dates from `document_index.md`.

6. If exact line evidence is needed after DocMemory returns likely files, use `rg` with text files only:

```powershell
rg -n -g "*.txt" "keyword" "doctovec\document"
```

## Change Comparison Flow

Use this flow when the user asks "what changed", "diff", "compare", "old", "previous", "past", or mentions `_history`:

1. Use DocMemory hybrid search to identify the current text document.
2. Find matching old text/history/source Office copies with PowerShell or `uv run --python 3.12 python`; do not use bare `python` on Windows because it may be the Microsoft Store alias.
3. Pick the newest `_history\<timestamp>` folder unless the user names a specific old version.
4. Compare current vs old with UTF-8 output and Windows long-path handling.
5. Separate real content changes from conversion/table noise. Treat ASR errors in meeting transcripts and obvious conversion drift as low-confidence unless supported by nearby text.
6. Answer with a business summary first, then evidence lines from the current text document.

For long `_history` paths, use Python with a `\\?\` long-path prefix and UTF-8 stdout. Avoid hardcoded long paths when possible; discover files with `Path.rglob()`.

## DocMemory CLI Fallback

When MCP is not available, still prefer the local DocMemory vector index:

```powershell
uv run --directory doctovec\docmemory_tool docmemory search "$((Resolve-Path doctovec).Path)" "question or keyword" --hybrid -n 5
```

Use keyword-only CLI search only when the vector index is not built:

```powershell
uv run --directory doctovec\docmemory_tool docmemory search "$((Resolve-Path doctovec).Path)" "keyword" -n 5
```

## Exact Line Evidence

After DocMemory finds the likely document, use `rg` to get precise text line references:

```powershell
rg -n "keyword" "doctovec\document" -g "*.txt" -g "!**/_history/**"
```

For old/past version comparison, remove the `_history` exclusion or search the selected `_history` folder directly.

## Answer Format

Use this shape:

```text
Short answer.

Evidence:
- path/to/file.txt:line - relevant finding

Uncertainty:
- missing or conflicting information, if any
```
