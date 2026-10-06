---
name: code-review
description: Review proposed changes in the MaddenGM Dashboard repository for correctness, regressions, and security issues. Use when asked to review a diff, pull request, or code changes.
---

Review changes; do not implement them unless explicitly asked.

## Review process

1. Read the complete diff and identify the intended behavior. Inspect surrounding code and relevant tests before judging a change.
2. Trace affected data flows and callers. Pay particular attention to CSV input normalization, missing or malformed data, Streamlit reruns and caching, and changes to roster, trade, game-log, or season statistics.
3. Look for concrete correctness bugs, regressions, unsafe input handling, security issues, and missing tests. Verify each suspected issue against the code; do not report style preferences, speculative risks, or findings unrelated to the diff.
4. Report only actionable findings. For each finding, provide the severity, file and line, the triggering scenario, and the user-visible consequence. If there are no findings, say so and briefly note what was reviewed.
5. When validation is appropriate, use the repository's existing checks: `python -m pytest tests/`, the CI flake8 commands, and `python -m py_compile app.py`. CI runs Python 3.10 and 3.11.

## Reporting

List findings first, ordered by severity, with precise locations. Keep the summary concise. Separate validation results from findings, and state when checks were not run.
