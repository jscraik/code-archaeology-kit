# code-archaeology-kit Greptile rules

## Scope

These rules define repository-specific expectations for Greptile and Codex-assisted reviews.

## Rule set

### 1) Independent validation is mandatory

- The coding agent must not self-approve a PR it authored.
- Greptile/Codex artifacts should be produced by an independent review step.

### 2) Governance and docs consistency

When a PR changes policy, tooling, or workflows, reviewers must verify related docs and templates stay aligned:

- \/AGENTS.md
- \/CONTRIBUTING.md (if present)
- \/.github\/PULL_REQUEST_TEMPLATE.md (if present)

### 3) Security and evidence expectations

- PRs changing policy or gates must include explicit risk notes and rollback guidance.
- Any reduction in required checks or review gates is high-risk and requires reviewer justification.

### 4) Merge confidence threshold

- Confidence below 4\/5 is merge-blocking.
- Confidence 4\/5 may merge only when remaining findings are non-logic polish.
- Confidence 5\/5 is merge-ready.
