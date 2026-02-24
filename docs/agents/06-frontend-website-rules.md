# Frontend website rules

Apply this file only for frontend or GitHub Pages tasks.

## Activation rules

Use this policy when at least one is true:

- The user explicitly asks for frontend/UI implementation or visual parity.
- The task targets browser-visible output for GitHub Pages.
- The repo task includes frontend assets or page rendering workflows.

## Required workflow

- Invoke `$ui-ux-creative-coding` and `$interface-craft` before writing frontend code.
- If a reference image exists, match layout, spacing, typography, and colors exactly.
- Use `https://placehold.co/` only when source content is missing.
- Use `agent-browser` for navigation and screenshots.
- Run at least two screenshot comparison passes before sign-off.

## Screenshot naming convention

- Full page: `screenshot-page-<name>-<pass>.png`
- Component: `screenshot-component-<type>-<state>-<pass>.png`
- Never overwrite prior captures; increment `<pass>`.

## Comparison checklist

- Spacing and padding
- Typography scale and weight
- Color values
- Alignment
- Border radius and shadows
- Component sizing and states
