# doctovec

![doctovec concept map](Docs/concept_map.png)

Japanese: [README_ja.md](README_ja.md)

`doctovec` is a local document-search workflow for project documents.

It converts Office files to UTF-8 text, builds a DocMemory vector index, and gives LLMs a clear map for finding source `.txt` evidence.

## Quick Start

1. Put Word/Excel/PowerPoint files under:

```text
document
```

2. For a new PC, run:

```text
install_cli.bat
```

3. Check setup:

```text
installation_status.bat
```

4. Run the full update flow:

```text
0_run_text_vector.bat
```

## What Each File Does

- `0_run_text_vector.bat` converts Office files, syncs vectors, and refreshes `document_index.md`.
- `drop_office_to_text.bat` converts Office files to `.txt`.
- `drop_remove_passwords.bat` removes Office/PDF open-password protection only when local passwords are listed in local `Config/pass.txt`.
- `drop_text_to_vector_dml.bat` builds the vector index using DirectML, which can use the PC's iGPU/GPU to speed up embedding. It is not Vulkan.
- `generate_document_index.bat` refreshes the human-readable document map.
- `installation_status.bat` checks tools, folders, skill handoff files, MCP notes, and the DocMemory index.
- `install_cli.bat` asks before setup actions and can download/warm the embedding model without indexing documents.

## Important Rule

`document_index.md` is a map for finding which document to inspect.

For fact checks and answers, cite the generated source `.txt` files under `document`.

## What This Does

This folder turns Office documents into a form that an LLM can search reliably.

First, it converts Word / Excel / PowerPoint files into searchable `.txt` files. Office files are not ideal as the direct search target because LLM tools and command-line search cannot always read their contents consistently.

Next, it registers the generated `.txt` files in the DocMemory database. The reason we make a database is to avoid sending every document to the LLM every time. When there are many documents, reading everything is slow, uses many tokens, and can mix in unrelated information.

The DocMemory database stores document text and search vectors. This lets the workflow find only the documents or paragraphs close to the question before sending evidence to the LLM.

`document_index.md` is the table of contents / map. Use it to find likely documents. Do not use it as the final evidence.

The final evidence should always come from generated `.txt` files under `document`.

## Password Privacy

`Config/pass.example.txt` is committed as the safe template.

Do not put real passwords in Git. If password removal is needed, copy it to `Config/pass.txt` on the local PC and add real passwords there. `Config/pass.txt` is ignored by Git.

If `Config/pass.txt` is missing or has no passwords, password removal is skipped.

Normal flow:

```text
1. Put Office documents in document
2. Run 0_run_text_vector.bat
3. The LLM uses document_index.md to find candidates
4. DocMemory searches related .txt files
5. The answer cites the found .txt evidence
```
