# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project aims to follow Semantic Versioning when releases begin.

## Unreleased

### Added

- `cak scan --share-snippet` to generate `archaeology_share.md` (share-ready summary) and `archaeology_events.jsonl` (local event log).
- Added `AGENTS.md` and modular `docs/agents/*.md` instruction files using progressive disclosure, including a dedicated frontend website rules document for the GitHub Pages site.
- Added adaptive top-action reranking controls:
  - `--adaptive-mode {disabled,shadow,adaptive}`
  - `--adaptive-baseline-artifact <path>`
  - New adaptive metadata in `run_metadata.adaptive_precision`
  - Optional `actionability.shadow_top_actions` and `actionability.adaptive_changes`
