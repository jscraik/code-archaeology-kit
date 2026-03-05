---
title: feat: Add adaptive baseline precision re-ranking
type: feat
status: active
date: 2026-03-04
origin: docs/brainstorms/2026-03-04-adaptive-signal-precision-brainstorm.md
---

<!-- markdownlint-configure-file { "MD025": false } -->

# feat: Add adaptive baseline precision re-ranking

## Table of Contents

- [Overview](#overview)
- [Problem Statement / Motivation](#problem-statement--motivation)
- [Premortem (6 Months Later: Failure Scenario)](#premortem-6-months-later-failure-scenario)
- [Plan Revisions from Premortem](#plan-revisions-from-premortem)
- [Proposed Solution](#proposed-solution)
- [Technical Considerations](#technical-considerations)
- [System-Wide Impact](#system-wide-impact)
- [Acceptance Criteria](#acceptance-criteria)
- [Success Metrics](#success-metrics)
- [Dependencies & Risks](#dependencies--risks)
- [Clarifications Locked for Planning](#clarifications-locked-for-planning)
- [Implementation Notes (Standard depth)](#implementation-notes-standard-depth)
- [Expanded Test Matrix](#expanded-test-matrix)
- [Technical Review Addendum](#technical-review-addendum)
- [Sources & References](#sources--references)

## Overview

Add adaptive baseline precision so `cak scan` can reduce false-positive top actions in daily local usage by re-ranking actionability output against a prior successful scan baseline, while preserving raw findings and deterministic output behavior (see brainstorm: `docs/brainstorms/2026-03-04-adaptive-signal-precision-brainstorm.md`).

## Problem Statement / Motivation

Current top actions are useful but can repeatedly surface benign coupling patterns, reducing trust and increasing manual triage. The brainstorm selected adaptive baseline precision (Approach B) specifically to improve top-action relevance over time without hiding underlying detector data (see brainstorm: `docs/brainstorms/2026-03-04-adaptive-signal-precision-brainstorm.md`).

This change should improve operator confidence while keeping contract-first, CI-safe behavior that the project already emphasizes (`docs/competition-matrix.md`, `README.md`).

## Premortem (6 Months Later: Failure Scenario)

Assume it is **2026-09-05** and this initiative failed.

### What went wrong

- Ranking changed unpredictably between runs, so users stopped trusting top actions.
- Baselines were frequently invalid (branch switches/settings drift), so adaptive mode rarely activated and produced little value.
- CI jobs became flaky because baseline reuse behavior differed across environments and output directories.
- Performance regressed on larger repos due repeated baseline parsing/scoring work.
- Report output showed reordered items without clear explanation, leading to “why did this move?” frustration.

### False assumptions

- “Last successful artifact” would be easy to identify and stable across local + CI contexts.
- Precision-first reranking would not materially hide newly risky patterns.
- Existing deterministic guarantees would naturally hold after adaptive scoring was added.
- Users would accept behavior changes without explicit explainability metadata.

### Edge cases we likely missed

- Concurrent scans reading/writing the same artifact.
- Baseline from another branch/worktree or stale repo identity.
- Baseline created with different critical settings but reused anyway.
- Corrupted/partial baseline files that pass superficial checks.
- Very large artifact files causing latency spikes.

### Integration issues overlooked

- `diff` and downstream tooling expecting legacy semantics for `top_actions`.
- Incomplete schema migration notes causing consumer breakage.
- Wrapper JSON mode and report mode diverging in adaptive notices/metadata.

### What users would hate

- “It hides important things.”
- “It changes its mind every run.”
- “I can’t tell why this recommendation appeared/disappeared.”
- “It slowed down my normal scan and gave me less confidence, not more.”

## Plan Revisions from Premortem

- Introduce a **baseline fingerprint contract** (repo identity + critical settings hash + schema/tool version) and reject reuse when mismatched.
- Add **shadow mode** first: compute adaptive ranking side-by-side without changing default top actions until quality gates pass.
- Add explicit **adaptive explainability fields** in output/report for each changed top action (reason + baseline reference).
- Add a **performance budget gate** (no significant runtime regression in representative repos).
- Add **determinism gates** in CI comparing repeat runs with fixed baseline inputs.
- Make baseline storage explicit and safer (dedicated baseline snapshot path or strict read-before-write ordering with fallback).

## Proposed Solution

Introduce an adaptive ranking phase between raw dig-plan generation and final `actionability.top_actions` selection:

1. Generate raw candidate actions exactly as today.
2. Attempt baseline load from explicit snapshot source and validate with fingerprint checks (repo identity, critical settings hash, schema/tool version).
3. If no usable baseline exists, run in **learn mode** and preserve raw ranking.
4. Run **shadow mode** first (compute adaptive order + reasons, but do not replace default top actions) until quality gates pass.
5. After shadow gate passes, run **adaptive mode** and re-rank only `actionability.top_actions`.
6. Preserve `detectors` and raw findings; do not filter them out by default.

### Planned file touch list

- [x] `src/code_archaeology/cli.py` — add adaptive-related CLI flags/forwarding (if flag-gated rollout is chosen).
- [x] `src/code_archaeology/analyze.py` — baseline load orchestration, learn/adaptive mode, notices, metadata, rerank wiring.
- [x] `src/code_archaeology/metrics.py` — adaptive rerank helper with deterministic tie-breaks.
- [x] `config/schemas/archaeology.schema.json` — contract updates for adaptive metadata/fields.
- [x] `src/code_archaeology/reporters.py` — optional transparent mode line in report output.
- [x] `tests/test_scan.py` — end-to-end mode behavior + notices + ordering assertions.
- [x] `tests/test_metrics_base.py` — reranker determinism/unit behavior.
- [x] `tests/test_analyze_io.py` — schema fixture compatibility updates.
- [x] `README.md` and `CHANGELOG.md` — feature behavior and rollout notes.

## Technical Considerations

- **Contract strictness:** schema uses `additionalProperties: false`; adaptive fields require explicit schema updates (`config/schemas/archaeology.schema.json`).
- **Current seam:** `analyze.py` currently computes `dig_plan` and `actionability.top_actions` via separate `build_dig_plan(...)` calls (`src/code_archaeology/analyze.py:204-205`). Refactor to avoid semantic drift and ensure raw vs adaptive outputs are coherent.
- **Determinism:** adaptive scoring must include stable tie-breakers and avoid runtime-variant inputs.
- **Baseline validity:** baseline must parse, be schema-compatible, and pass fingerprint compatibility checks (repo/settings/tool/schema).
- **Rollout safety:** shadow mode must prove value before adaptive reorder becomes default behavior.
- **Performance budget:** adaptive logic must stay within an agreed runtime budget for normal scans.
- **Compatibility:** if payload semantics change materially, bump schema version from `1.2.0` with test updates.

## System-Wide Impact

- **Interaction graph**: `cak scan` CLI argument parsing (`src/code_archaeology/cli.py`) → `analyze_repo(...)` (`src/code_archaeology/analyze.py`) → raw action generation (`src/code_archaeology/metrics.py`) → adaptive rerank step (`metrics.py` or `analyze.py`) → schema validation (`analyze.py`) → report/render output (`src/code_archaeology/reporters.py`) and artifact writes.
- **Error propagation**: baseline read/parse/schema mismatch should produce machine-readable notices and degrade to learn mode; only hard contract or explicit fatal modes should return `SCAN_ERROR`.
- **State lifecycle risks**: baseline artifact reuse can race with concurrent runs writing `archaeology.json`; must avoid partial-read failures and define safe fallback behavior.
- **API surface parity**: both human report (`archaeology_report.md`) and JSON wrapper (`--json`) must reflect the same final `actionability.top_actions`; raw detector outputs remain unchanged.
- **Integration test scenarios**: cold-start learn mode, shadow-mode parity, valid baseline adaptive mode, baseline mismatch fallback, deterministic repeat-run behavior, and schema compatibility regression.

## Acceptance Criteria

- [x] **Brainstorm alignment:** Implementation follows chosen approach and constraints from the brainstorm (adaptive baseline, learn-mode cold start, rerank-only policy, preserve raw findings) (see brainstorm: `docs/brainstorms/2026-03-04-adaptive-signal-precision-brainstorm.md`).
- [x] **Baseline discovery:** Scan attempts baseline load from deterministic default source and optional explicit source when configured.
- [x] **Baseline fingerprinting:** Baseline reuse requires repo identity + critical settings hash + schema/tool compatibility.
- [x] **Cold start:** Missing/invalid baseline enters learn mode and still succeeds.
- [x] **Shadow gate:** Adaptive ordering runs in shadow mode first and does not replace default top actions until defined quality thresholds are met.
- [x] **Adaptive mode:** Valid baseline triggers adaptive mode and re-ranks only `actionability.top_actions`.
- [x] **Raw findings preserved:** `detectors` and baseline-free raw signal sets are not filtered away by default.
- [x] **Determinism:** Same repo + same baseline + same flags => stable top-action ordering.
- [x] **Explainability:** Changed rankings include machine-readable reason metadata and user-visible rationale.
- [x] **Contract compliance:** Updated payload validates against `config/schemas/archaeology.schema.json`; tests updated accordingly.
- [x] **Structured observability:** Notices/metadata indicate adaptive mode (`learn|adaptive`) and baseline fallback reasons.
- [x] **No regression:** Existing CLI paths (`--json`, `--share-snippet`, overwrite safety) continue to behave correctly.
- [ ] **Performance guardrail:** Runtime overhead stays within agreed budget on representative repositories.

## Success Metrics

- Primary: top actions are judged materially more relevant in routine local runs (goal from brainstorm: “minimal manual filtering”).
- Shadow quality: adaptive ordering improves relevance without increasing missed-high-risk complaints during shadow evaluation.
- Quality: deterministic ordering regression tests pass consistently.
- Reliability: zero new schema validation failures in scan tests.
- Performance: adaptive/shadow mode stays within runtime budget against baseline scan behavior.
- Safety: baseline failures degrade gracefully without blocking standard scan output.

## Dependencies & Risks

### Dependencies

- Existing analysis and ranking flow in:
  - `src/code_archaeology/analyze.py`
  - `src/code_archaeology/metrics.py`
- Contract and schema validation:
  - `config/schemas/archaeology.schema.json`
  - `tests/test_analyze_io.py`
  - `tests/test_scan.py`

### Risks

- Over-suppression risk from precision-first posture could hide newly risky but low-frequency patterns.
- Baseline mismatch risk across repo/branch/settings if compatibility checks are too permissive.
- Contract drift risk if schema/versioning updates are incomplete.
- Concurrency risk when reading and writing artifacts in near-simultaneous scans.

### Mitigations

- Start with rerank-only behavior (no raw filtering) as selected in brainstorm.
- Encode explicit fallback notices and mode metadata.
- Add deterministic tie-break tests and cold-start/adaptive/fallback integration tests.
- Gate baseline compatibility on repo identity + key settings hash.

## Clarifications Locked for Planning

To remove ambiguity identified during SpecFlow analysis, this plan locks the following assumptions:

- **Rollout mode (v1):** adaptive ranking is flag-gated + shadow-first, then can become default after validation.
- **Baseline scope:** use explicit baseline snapshot semantics in active output context to avoid ambiguous “last successful” detection.
- **Baseline success definition:** baseline is reusable when JSON parse + schema compatibility + repo identity match pass, and prior run has no hard errors.
- **Settings drift policy:** baseline reuse is invalidated when key ranking-impact settings differ (`since_days`, `max_files_per_commit`, `large_commit_strategy`, `top_actions`, ignore configuration).

## Implementation Notes (Standard depth)

### Phase A — Baseline plumbing and mode semantics

- Define baseline source resolution and validity rules in `src/code_archaeology/analyze.py`.
- Add learn/shadow/adaptive mode branch with notices and metadata.

### Phase B — Adaptive reranker

- Implement deterministic adaptive scoring/reranking helper in `src/code_archaeology/metrics.py`.
- Ensure `dig_plan` remains raw and `actionability.top_actions` is derived via rerank policy.

### Phase C — Contract + reporting + docs

- Update schema for adaptive metadata fields in `config/schemas/archaeology.schema.json`.
- Add report transparency note (mode + reason) in `src/code_archaeology/reporters.py` if needed.
- Document usage and behavior in `README.md` and `CHANGELOG.md`.

### Phase D — Validation

- Expand coverage in `tests/test_scan.py`, `tests/test_metrics_base.py`, `tests/test_analyze_io.py`, and `tests/test_cli_main.py` (if wrapper behavior changes).

### Phase E — Shadow rollout and promotion criteria

- Run shadow mode in CI/local evaluation to compare raw vs adaptive ordering outcomes.
- Promote to adaptive default only after determinism, relevance, and performance thresholds are satisfied.

## Expanded Test Matrix

- **Unit — deterministic rerank**
  - `metrics.py`: pure rerank function returns stable order with fixed input.
  - Tie-break order remains stable for equal adaptive scores.
- **Unit — baseline validation**
  - Reject malformed JSON, incompatible schema versions, repo mismatch.
  - Fallback to learn mode with notice codes (non-fatal).
- **Integration — mode transitions**
  - No baseline => learn mode; valid baseline => shadow/adaptive mode.
  - Baseline settings drift => learn mode fallback + explicit notice.
  - Branch/worktree mismatch => baseline rejected via fingerprint check.
- **Integration — contract integrity**
  - Payload validates against updated schema with adaptive metadata.
  - `--json` wrapper continues to emit `ok/schema/top_actions/notices/errors`.
- **Integration — regression and stability**
  - Repeat-run determinism check: same repo + same baseline + same flags yields identical top-action ordering.
  - Concurrent scans do not produce fatal baseline read/write races.
  - Existing share snippet and atomic write behavior unaffected.
- **Integration — user explainability**
  - Top-action changes include baseline-influenced rationale in JSON/report output.
- **Performance**
  - Adaptive/shadow scans meet runtime budget compared with baseline scan path.

## Technical Review Addendum

### Priority findings

1. **P1 — Baseline race risk**
   - Reading and writing `archaeology.json` in close succession can cause stale-baseline behavior in concurrent runs.
   - **Plan adjustment:** prefer a dedicated baseline snapshot path (for example `archaeology_baseline.json`) or explicit read-before-write ordering with fallback on race detection.

2. **P1 — Baseline trust boundary**
   - A reused artifact must not silently apply across different repo contexts.
   - **Plan adjustment:** enforce baseline compatibility checks (repo identity, key settings hash, schema compatibility, and no hard errors in source run).

3. **P2 — Contract migration clarity**
   - Schema is strict; additive fields can still break consumers if semantics drift.
   - **Plan adjustment:** document version policy explicitly (additive optional fields first, compatibility window, then tighten requirements).

4. **P2 — Rollout safety**
   - Adaptive reranking should avoid abrupt behavioral change.
   - **Plan adjustment:** ship flag-gated first, then default-on only after determinism and relevance regressions pass in CI.

5. **P3 — Explainability completeness**
   - Users need to understand why ranking changed.
   - **Plan adjustment:** include adaptive mode + reason metadata and surface at least one baseline-influenced rationale in report/JSON output.

## Sources & References

- **Origin brainstorm:** [`docs/brainstorms/2026-03-04-adaptive-signal-precision-brainstorm.md`](/Users/jamiecraik/dev/code-archaeology-kit/docs/brainstorms/2026-03-04-adaptive-signal-precision-brainstorm.md) — carried forward decisions: adaptive baseline approach, learn-mode cold start, rerank top-actions only, preserve raw findings.
- Similar implementations / architecture anchors:
  - `src/code_archaeology/analyze.py:60`
  - `src/code_archaeology/analyze.py:204`
  - `src/code_archaeology/analyze.py:205`
  - `src/code_archaeology/metrics.py:316`
  - `src/code_archaeology/reporters.py:7`
  - `config/schemas/archaeology.schema.json:5`
- SpecFlow validation highlights captured from planning analysis:
  - baseline lifecycle definition,
  - learn/adaptive mode contract,
  - deterministic tie-break requirements,
  - cross-layer fallback and schema tests.
- Institutional learnings:
  - `docs/competition-matrix.md` (deterministic CI positioning),
  - `README.md` (safety/contract posture),
  - No `docs/solutions/` directory currently present.
- External references (framework docs):
  - [argparse docs](https://docs.python.org/3/library/argparse.html)
  - [pathlib docs](https://docs.python.org/3/library/pathlib.html)
  - [tempfile docs](https://docs.python.org/3/library/tempfile.html)
  - [os docs (`replace`, `fsync`)](https://docs.python.org/3/library/os.html)
  - [jsonschema docs](https://python-jsonschema.readthedocs.io/en/stable/)
