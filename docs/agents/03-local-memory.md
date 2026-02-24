# Local memory workflow

## Local-memory MCP usage

Use local-memory only for durable cross-run context.

## Required before writing durable notes

1. `bootstrap(mode="minimal", include_questions=true, session_id="repo:code-archaeology-kit:task:<id>")`
2. `search(query="...", session_id="repo:code-archaeology-kit:task:<id>")`

## Recording durable facts

- Use `observe(...)` with `level="observation"` or `level="learning"`.
- Store durable facts only.
- Never store secrets, tokens, API keys, or PII.

## If memory tools are unavailable

- Continue with repository-backed evidence and skip memory writes.
