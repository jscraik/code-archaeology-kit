---
date: 2026-03-04
topic: adaptive-signal-precision
---

# Adaptive Signal Precision Brainstorm

## Table of Contents

- [What We're Building](#what-were-building)
- [Why This Approach](#why-this-approach)
- [Key Decisions](#key-decisions)
- [Resolved Questions](#resolved-questions)
- [Open Questions](#open-questions)
- [Next Steps](#next-steps)

## What We're Building

We are improving Code Archaeology Kit output quality by introducing an adaptive precision mode that reduces false-positive triage burden in day-to-day local runs. The primary goal is to make top actions feel immediately relevant without removing access to full underlying findings.

The feature will use a repo-aware baseline model so the tool can better distinguish routine coupling from meaningful signal changes. This directly addresses trust erosion caused by recurring benign pairs in current top-ranked actions.

## Why This Approach

We considered three paths: (A) static conservative weighting, (B) adaptive baseline precision, and (C) dual-output focus/full modes. We chose **Approach B (adaptive baseline)** because it provides the strongest long-term relevance improvement while still fitting the project's contract-first architecture.

Approach B is more complex than static heuristics, but the value is better alignment with each repository's normal behavior. That makes precision gains durable rather than one-size-fits-all.

## Key Decisions

- **Primary objective:** reduce false positives for daily local use, optimizing trust in top actions.
- **Success criterion:** top actions should feel genuinely actionable with minimal manual filtering.
- **Tradeoff stance:** favor precision over recall in the first iteration.
- **Baseline source default:** use the last successful scan artifact.
- **Cold-start behavior:** first run enters learn mode (captures baseline, does not fail policy).
- **Output behavior:** keep raw findings visible; re-rank top actions using adaptive precision signals.

## Resolved Questions

- **How should baseline be sourced by default?** Last successful scan artifact.
- **What should happen when no baseline exists?** Learn mode bootstrap on first run.
- **Should adaptive logic filter findings or re-rank?** Re-rank top actions only by default.

## Open Questions

- None at this stage.

## Next Steps

Proceed to implementation planning to define policy semantics, baseline lifecycle rules, and acceptance tests for relevance improvements.

Run /prompts:workflow-plan for implementation details.
