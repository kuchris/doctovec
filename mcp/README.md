# DocMemory MCP Setup

This folder contains handoff notes for configuring the DocMemory MCP server for `doctovec`.

The MCP server code lives in:

```text
docmemory_tool
```

This `mcp` folder only stores setup/config examples.

## Codex Config

Use `codex_mcp_example.toml` as the config snippet.

Replace `<absolute-path-to-doctovec>` with the full local path to this folder, for example:

```text
C:\Users\alten\Desktop\ku\ct\doctovec
```

## Behavior

The MCP tool `docmemory_search` searches the DocMemory SQLite/vector index:

```text
.docmemory\docmemory.sqlite
```

It does not automatically read `document_index.md` first. The intended LLM flow is:

```text
skills\md-search\SKILL.md -> document_index.md -> docmemory_search -> source .txt evidence
```

Use `document_index.md` as the routing map, then cite the source `.txt` files returned or confirmed by search.

## Rebuild

If the MCP reports a missing or stale index, run this from `doctovec`:

```text
0_run_text_vector.bat
```

For vector-only rebuild after text output already exists:

```text
drop_text_to_vector_dml.bat
```
