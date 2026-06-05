# Local Document Tools

The parent `doctovec` folder is the current handoff workflow for project document search:

```text
Office documents -> UTF-8 text -> DocMemory SQLite/vector index
                 -> document_index.md
```

The old PDF/MinerU/Markdown workflow is not used in this `doctovec` folder.

## Setup for a New PC

Install these before using the tools:

1. Install `uv`:

```powershell
winget install astral-sh.uv
```

2. Install LibreOffice:

```powershell
winget install TheDocumentFoundation.LibreOffice
```

3. Confirm LibreOffice exists at the default path:

```text
C:\Program Files\LibreOffice\program\soffice.exe
```

4. Prepare the local command-line dependencies:

```text
install_cli.bat
```

This asks before each setup action. It can install missing `uv`/LibreOffice with `winget`, and it can download/warm the DirectML embedding model without indexing documents. It does not install skills or MCP config.

5. Check the local setup:

```text
installation_status.bat
```

For command-line or automation use:

```text
installation_status_cli.bat
```

6. Run the tools once while connected to the internet.

`uv` installs Python/package dependencies automatically. The DocMemory embedding model downloads automatically on first vector run.

Default embedding model:

```text
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

The vector indexing tools use the bundled `docmemory_tool` folder in `doctovec`. They do not require a separate DocMemory checkout.

## Recommended BAT Order

Normal workflow:

```text
0_run_text_vector.bat
```

This runs:

1. Office to text
2. Text to vector index
3. Document index

Manual workflow:

```text
drop_office_to_text.bat -> drop_text_to_vector_dml.bat -> generate_document_index.bat
```

Use `drop_text_to_vector_dml.bat` for the recommended DirectML GPU/iGPU vector path. If that fails on a PC, use `drop_text_to_vector.bat` as the CPU fallback.

`0_run_text_vector.bat` does not remove passwords. If Office files are password protected, run `drop_remove_passwords.bat` first. It reads password candidates only from `Config\pass.txt`. If that file has no passwords, password removal is skipped. Skip it for normal files.

When a specification or design document is updated:

1. Copy the updated file or folder into `doctovec\document`.
2. Run `0_run_text_vector.bat`.
3. Ask the LLM to use the `md-search` skill or DocMemory search before answering.

## 1. Office to Text

Files:

- `0_run_text_vector.bat`
- `drop_office_to_text.bat`
- `Scripts\office_drop_to_text.py`

Use:

1. Drag a Word/Excel/PowerPoint file or folder onto `drop_office_to_text.bat`, or run `0_run_text_vector.bat`.
2. The tool searches folders recursively.
3. It converts supported Office files to UTF-8 `.txt`:
   - `.doc`
   - `.docx`
   - `.xls`
   - `.xlsx`
   - `.ppt`
   - `.pptx`

Output rule:

- Text output is written beside the source document under:

```text
text\<source_stem>\txt\<source_stem>.txt
```

- Existing text output is skipped when the Office source content is unchanged.
- If the Office source content changed, the text output is regenerated.
- Conversion hashes are recorded in `text\office_to_text_state.tsv`.
- Office temporary files starting with `~$` are skipped.
- Generated `text` folders are skipped during recursive search.
- Long Japanese paths are handled with Windows long-path-safe file writes.

Logs:

- `Logs\office_to_text_last_run.log`
- `Logs\office_to_text_failures.tsv`

## 2. Text Vector Index

Files:

- `drop_text_to_vector_dml.bat`
- `drop_text_to_vector.bat`
- `docmemory_tool`

Use:

1. Run `drop_text_to_vector_dml.bat` from the `doctovec` folder, or let `0_run_text_vector.bat` call it.
2. The tool indexes this `doctovec` folder.
3. The tool creates or updates `.docmemory\docmemory.sqlite` inside the `doctovec` folder.

Notes:

- `drop_text_to_vector_dml.bat` uses Windows DirectML GPU/iGPU acceleration for embedding. It is not Vulkan.
- `drop_text_to_vector.bat` uses the normal CPU path and is useful as a fallback.
- The vector tools use `docmemory_tool` beside the BAT files.
- `uv` installs Python dependencies automatically on first use.
- Embedding models are downloaded automatically on first use.
- If `.docmemory\config.json` does not exist, the BAT initializes the index first.
- After initialization, later runs sync the existing index.
- The index stays inside the `doctovec` folder at `.docmemory\docmemory.sqlite`.
- `_history` folders are ignored by default.
- The current index pattern is `**/*.txt`.

## 3. Document Index

Files:

- `generate_document_index.bat`
- `Scripts\generate_document_index.py`
- `document_index.md`

Use:

1. Run `generate_document_index.bat` from the `doctovec` folder, or let `0_run_text_vector.bat` run it automatically.
2. The tool scans generated `.txt` files under `doctovec\document`.
3. It writes `document_index.md` in the `doctovec` folder.

The index is generated without an LLM. It uses deterministic rules to extract:

- document title
- source file path
- generated text path
- document IDs such as `PG4976C-507` and `Qシ開-A-25113-01`
- headings / section outlines
- important keyword counts
- cross-document references
- meeting transcript files

Use `document_index.md` as a quick map before asking detailed LLM questions. It does not replace vector search; it helps humans and LLMs understand what documents exist.

Recommended linked search flow:

```text
document_index.md -> likely document IDs/paths/keywords -> DocMemory vector search -> source .txt evidence
```

## Normal Flow

For normal documents:

```text
Office document -> text -> vector index
```

Human-readable map:

```text
generate_document_index.bat
```

`0_run_text_vector.bat` refreshes this map automatically after vector sync.

For password-protected files:

```text
drop_remove_passwords.bat -> 0_run_text_vector.bat
```

Password candidates are configured in:

```text
Config\pass.txt
```

Use one password per line. Blank lines and `#` comments are ignored.
The committed `Config\pass.txt` is intentionally fake/empty for privacy. Add real passwords only on the local PC when needed.

If files are not password protected, skip the password step.

If a document is renamed or removed, old generated `text` output may remain. For a clean rebuild, remove the old generated text folder or rebuild the index after cleanup.

## LLM Question for Searching Documents

If DocMemory MCP is configured, ask the LLM agent to use MCP search first:

```text
Use docmemory_search to search the doctovec vector index and answer this question:

[write the question here]

Use document_index.md first as a routing map, then search current generated text. Do not search _history unless comparing old/past versions. Cite source .txt file paths.
```

If MCP is not configured but skills are supported, ask the LLM agent to use the installed `md-search` skill:

```text
Use the md-search skill to search the doctovec text/vector index and answer this question:

[write the question here]

Use document_index.md only to find likely documents. Cite source .txt files for factual answers.
```

If the LLM tool does not support MCP or skills, use this question template instead:

```text
Search the generated text files and answer this question:

[write the question here]

Search targets:
- document/**/text/**/txt/*.txt
- document/meeting/**/*.txt

Please:
- Use exact keyword search first, then related terms if needed.
- Do not search `_history` unless the question asks to compare old/past versions.
- Cite the `.txt` file path for each answer.
- Quote only the smallest relevant text needed.
- If multiple documents disagree, show each source separately.
- If the answer is not found, say that clearly.
- Do not guess from general knowledge.
- Keep Japanese filenames and document titles unchanged.

Answer format:
1. Short answer.
2. Evidence with `.txt` file path.
3. Any uncertainty or missing information.
```

## LLM Skill and MCP

This folder includes a handoff copy of the Codex `md-search` skill:

```text
skills\md-search\SKILL.md
```

For Codex to use it automatically, install or copy that skill to:

```text
%USERPROFILE%\.codex\skills\md-search\SKILL.md
```

This skill tells the LLM to:

- Use `docmemory_search` first when the DocMemory MCP is available.
- Use the local DocMemory CLI with `--hybrid` when MCP is not configured.
- Search current generated `.txt` files before answering.
- Ignore `_history` unless comparing old/past versions.
- Cite `.txt` file paths.
- Use `rg` only after DocMemory finds likely files, to collect exact line evidence.

For normal handoff, MCP setup is optional. If MCP is not configured, an LLM agent can still use the local DocMemory vector index with:

```powershell
uv run --directory docmemory_tool docmemory search "$((Resolve-Path .).Path)" "question or keyword" --hybrid -n 5
```

MCP setup notes and an example config are included in:

```text
mcp\README.md
mcp\codex_mcp_example.toml
```

Example Codex MCP config:

```toml
[mcp_servers.docmemory]
command = "uv"
args = ["run", "--directory", "<path-to-doctovec>\\docmemory_tool", "--extra", "mcp", "docmemory-mcp"]

[mcp_servers.docmemory.env]
DOCMEMORY_TARGET = "<path-to-doctovec>"
```

Replace `<path-to-doctovec>` with the `doctovec` folder path, for example:

```text
<project-root>\doctovec
```

## Why Convert to Text

Text is simpler and faster for LLM search than Office or PDF files.

Benefits:

- Avoids PDF/OCR layout problems.
- Usually uses fewer tokens than Markdown with extra syntax.
- Speeds up LLM search and RAG workflows.
- Keeps document content searchable with normal tools.
- Works well with vector search because only relevant chunks are sent to the LLM.

Text output may lose some visual layout, table shape, and formatting. If exact layout matters, open the original Office document.

## Optional SQLite / Vector Indexing

The DocMemory index can reduce LLM token usage because the workflow becomes:

```text
Text files -> SQLite/vector search -> only relevant excerpts -> LLM
```

SQLite does not reduce tokens by itself. The token saving comes from searching first and sending only matching sections instead of whole documents.

## Meeting Transcript Summaries

Meeting transcripts can be stored under:

```text
document\meeting\<date>\
```

Use `Docs\meeting prompt.md` to summarize transcripts.

Important:

- Do not invent details.
- If speaker names are unclear, do not guess.
- If ASR/transcript terms are unclear, quote the raw phrase and mark it `(unclear)`.
- Output Japanese and English when requested.

## Notes

- Keep Japanese filenames as they are.
- If a file fails, check the matching `*_failures.tsv` file.
- Excel-to-text output depends on what MarkItDown can extract from the workbook.
- If search results look stale after document updates, rerun `0_run_text_vector.bat`.
