---
name: literature-review
description: Find, verify, and synthesize biomedical and life-science literature. Use for seminal-paper lookups, evidence reviews, method comparisons, contested claims, research gaps, PMID sets, DOI verification, retraction checks, and citation-graph expansion.
---

# Literature review

Ground every substantive claim in retrieved records. Use memory to frame the
question, never to invent citations.

## Choose the deliverable

- For a specific-paper request, return one or two verified primary papers.
- For an evidence question, synthesize findings by theme rather than listing papers.
- For a comparison, state the trade-off and recommendation.
- For a gap analysis, identify concrete missing evidence and show what establishes the gap.

State a scope assumption only when the request is ambiguous enough to change
the search, such as human trials versus animal studies.

## Retrieve evidence

1. Use the `pubmed` MCP `search_articles` tool for biomedical searches.
2. Fetch records for the most relevant PMIDs with `get_article_metadata`.
3. Use `find_related_articles` to broaden a strong seed set by similarity.
4. For broad reviews, run the helper's `search-openalex` command to cover work
   that keyword-ranked PubMed results may miss.
5. For two or three key papers, run `expand-citations` in both directions and
   add relevant seminal, extending, or contradicting work.

The PubMed server exposes only these three tools. If `/mcp` does not show
`pubmed`, report that the project MCP is unavailable instead of fabricating
results.

## Run deterministic helpers

Write a versioned JSON request to a workspace temporary file, then invoke:

```bash
pixi run --frozen literature-helper <command> <input.json>
```

Commands and request shapes:

```json
{"version":1,"dois":["10.1000/example"]}
{"version":1,"reference":"Author. Paper title. Journal (2024)."}
{"version":1,"query":"disease target","limit":10,"filters":""}
{"version":1,"doi":"10.1000/example","backward_limit":50,"forward_limit":15}
{"version":1,"text":"draft containing DOI 10.1000/example"}
{"version":1,"draft":"full markdown review"}
```

Use them with `verify-dois`, `crossref-lookup`, `search-openalex`,
`expand-citations`, `extract-dois`, and `style-pass`, respectively. Read the
JSON result from stdout. Diagnostics go to stderr.

Verify every emitted DOI. Treat `ok: null` as unverified, not fabricated.
Check retraction metadata for surprising, high-profile, or contested claims.

## Synthesize

- Organize around claims, themes, agreement, disagreement, and evidence strength.
- Prefer primary research for factual claims; use reviews for orientation.
- Distinguish preprints, observational studies, randomized trials, and replicated results.
- Calibrate language to the design and amount of evidence.
- Say when a requested claim is unsupported or retracted.
- Do not present a bibliography as a synthesis.

For a substantial review, aim for enough distinct primary sources to support
the scope; do not enforce a citation count when the evidence base is small.

## Write the result

Lead with the substantive answer. Use inline DOI links:

```markdown
[Author Year](https://doi.org/10.xxxx/example)
```

Save a substantial review as a Markdown workspace file when useful, but keep
the main conclusion in the response. Do not add process narration such as
"DOIs verified" or "current as of today."

Before finalizing a substantial review, run `style-pass` once and address its
reported issues. Do not loop on the linter.
