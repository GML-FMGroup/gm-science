---
name: literature-review
description: Search scholarly sources, build an evidence matrix, and register a cited review in gm-science.
---

# Literature Review

Use this workflow for literature discovery, evidence synthesis, and review reports in gm-science.

## Workflow

1. Read `project_id`, `session_id`, and `workspace` from `gm_science_context`.
2. Call `science_list_sources` before searching. Report unavailable sources instead of silently omitting them.
3. Call `science_search` with the project and session identifiers. Keep the returned paper artifact ID for every paper used.
4. Build an evidence matrix with one row per paper. Record the research question, methods, data, main findings, limitations, and paper artifact ID.
5. Separate claims supported by retrieved metadata from your own interpretation. Do not treat an abstract as proof of details it does not state.
6. Write the review as a Markdown file inside the project workspace.
7. Call `science_register_review` with the report path and exactly the paper artifact IDs cited in the report.

## Evidence Rules

- Do not invent DOI, PMID, arXiv ID, authors, findings, or citation counts.
- Do not cite a paper that was not returned by `science_search` or already present as a project paper artifact.
- Cite with the paper artifact ID so the report preserves a durable evidence chain.
- State which sources failed, were disabled, or needed configuration.
- Describe contradictory findings and missing evidence explicitly.
