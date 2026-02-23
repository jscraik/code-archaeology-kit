# Frontend website rules

Use this policy for any GitHub Pages or browser-visible output work.

## Confirmed scope
- This repository is associated with GitHub Pages at: `https://jscraik.github.io/unfinished-cemetery/`.

## AGENTS.md – Frontend Website Rules

- **Always do first (before any frontend code):** invoke `$ui-ux-creative-coding` and `$interface-craft`.
- If a reference image is provided:
  - Match layout, spacing, typography, and color exactly.
  - Use placeholders (`https://placehold.co/`) only when content is missing.
  - Do not improve or add design beyond the reference.
- If no reference image: design from scratch using this repository's existing docs/brand constraints.
- For screenshots and visual checks, use `agent-browser`:
  - `agent-browser open http://localhost:2000` then capture screenshots.
  - Start a local server before screenshot loops; reuse a running server when present.
  - If the repo has no existing local server command for the site, confirm one before starting screenshot workflows.
- Pair execution with `$agentation` for screenshot pass tracking.

## Screenshot naming convention
- Full page: `screenshot-page-<name>-<pass>.png`
- Component: `screenshot-component-<type>-<state>-<pass>.png`
  - examples: `screenshot-component-card-default-1.png`, `screenshot-component-button-hover-2.png`
- Never overwrite; increment pass number for reruns.

## Runtime checks for screenshot workflows
- Run at least 2 rounds for visual parity.
- Compare each pass on: spacing/padding, typography scale, color hex, alignment, border radii, shadows, and sizing.
- Include component type in component screenshot filenames (`card`, `button`, `modal`, `form`, etc.).
