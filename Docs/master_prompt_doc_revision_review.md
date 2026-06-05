# Master Prompt for Document Revision Review

Use this prompt when you want an LLM to review Japanese technical documents using the current `doctovec` workflow:

```text
Office documents -> UTF-8 text -> DocMemory vector search
```

This prompt is for reviewing content changes and likely implementation impact. It does not depend on PDF, MinerU, or Markdown output.

## Best Use

Use this when:

- Updated Office documents were copied into `doctovec\document`.
- `0_run_text_vector.bat` has already been run.
- The DocMemory index contains current `.txt` outputs.
- You want the LLM to find relevant document content first, then summarize changes or review impact.

If you need a true old/new diff, provide both versions or tell the LLM where the previous copy is stored. Without a previous version, the LLM can review the current content but cannot prove what changed.

## Copy-Paste Master Prompt

```text
You are reviewing Japanese technical design documents.

Use the DocMemory vector index for `doctovec` as the primary source.
Search before answering. Do not guess from general knowledge.

Current document workflow:
- Source Office files are under `doctovec\document`.
- Generated text files are under `doctovec\document\...\text\...\txt\*.txt`.
- The vector index is under `doctovec\.docmemory`.

Task:
[write the review question here]

Search rules:
1. Use DocMemory hybrid/vector search first.
2. Search current generated `.txt` files only unless asked to compare old/past versions.
3. Use exact keyword search only after DocMemory returns likely files, to collect line evidence.
4. Cite text file paths and line numbers when possible.
5. Keep Japanese filenames, document titles, and IDs unchanged.

If comparing revisions:
1. Identify the current document using DocMemory.
2. Locate the previous version only if it is explicitly provided or discoverable.
3. Compare current vs previous with UTF-8 handling.
4. Separate real content/spec changes from conversion noise.

Important rules:
- Do not invent missing differences.
- If the previous version is unavailable, say so clearly.
- Ignore whitespace-only differences.
- Ignore line-wrap differences.
- Ignore obvious Office-to-text/table conversion noise unless meaning changes.
- Treat speech-recognition errors in meeting transcripts as uncertain.
- If a term is unclear, quote the raw text and mark it `(unclear)`.

For each reviewed file, produce this exact structure:

# <Document Title or ID>

## Verdict
- Changed: Yes / No / Cannot determine
- Impact: Major / Medium / Minor / None / Unknown
- Confidence: High / Medium / Low

## Real Changes or Relevant Findings
- List only meaningful content findings.
- Call out:
  - section added or removed
  - wording changed
  - table/data changed
  - sequence/flow changed
  - interface/parameter/timeout/retry/condition changed
  - implementation-impacting behavior changed

## Possible Conversion or Transcript Noise
- List anything that may be caused by text conversion, table flattening, or ASR errors.

## Evidence
- Give short excerpts or concise before/after summaries.
- Do not paste large blocks.
- Include source `.txt` path and line number when available.

## 3-Line Summary
- Short summary for teammates.

After processing all files, provide:

# Overall Summary

## Files With Likely Real Spec Changes
- <list>

## Files With Mostly Minor Wording Changes
- <list>

## Files That Cannot Be Compared
- <list and reason>

## Highest-Risk Findings
- List changes/findings that may affect implementation, interface behavior, timeout handling, retry logic, sequence handling, external communication, or database/log behavior.

Quality bar:
- Be conservative.
- Prefer "unclear" over false certainty.
- Only call something a real change if there is clear evidence.
- If the old version is missing, do not claim a diff.
```

## Short Version

```text
Use DocMemory search on `doctovec` before answering.
Search current generated `.txt` files.

Question:
[write the question here]

If this is a revision comparison, compare against the previous version only if it is provided or clearly discoverable.

Output:
1. Verdict
2. Key findings
3. Possible conversion/transcript noise
4. Evidence with `.txt` path and line number
5. Implementation-impact summary

Rules:
- Do not guess.
- Mark unclear ASR/conversion terms as `(unclear)`.
- Keep Japanese filenames and document IDs unchanged.
```

## Recommended Follow-Up Prompt

```text
Now filter the result and keep only findings that may affect implementation or behavior.
Remove wording-only changes and likely conversion noise.
Return a short engineer-focused summary in Japanese and English.
```
