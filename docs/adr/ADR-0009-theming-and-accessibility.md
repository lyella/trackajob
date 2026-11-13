# ADR-0009: Explicit light and dark themes, light by default

## Status

Accepted

## Context

The app needs to look right in both light and dark. Browsers expose the user's
operating system preference through `prefers-color-scheme`, and the obvious
implementation is to follow it automatically.

The visual direction is "notebook and folder": paper surfaces, ruled lines,
folder tabs, index cards, serif headings. That direction is fundamentally a
*paper* metaphor.

## Options considered

1. Follow `prefers-color-scheme` automatically, no toggle.
2. Explicit toggle only, with light as the default.
3. Toggle that defaults to the OS preference on first visit.

## Decision

Option 2. Light is the default for everyone who has not chosen. A toggle in the
header and on the login screen switches to dark, and the choice is stored in
`localStorage` under `trackajob-theme`.

Reasons:

- **The metaphor is paper.** A first-time user should see the notebook, not a
  dark screen that contradicts the design language.
- **Option 1 removes control.** A user who wants the paper look on a dark-mode
  OS has no way to get it.
- **Option 3 is a compromise that helps nobody.** It still surprises a dark-OS
  user with a theme they did not ask for, and it makes the default
  unpredictable, which makes screenshots, support and testing harder.

## Implementation

- The theme is the attribute `data-theme="light|dark"` on `<html>`. Every
  colour is a CSS custom property defined in the two token blocks at the top of
  `web/src/styles.css`. Components never hard-code a hex value.
- `web/src/theme.tsx` owns the state. `ThemeToggle` renders the switch.
- An inline script in `web/index.html` reads `localStorage` and sets the
  attribute **before first paint**. Without it the page renders light and then
  flips to dark, which looks like a bug.
- `color-scheme` is set alongside the attribute so native controls (scrollbars,
  select popups, form widgets) match.

## Consequences

- Adding a colour means adding it to both token blocks. A token present in one
  theme and missing from the other falls back to its light value, which is
  usually invisible against a dark surface. Check both.
- The resume preview stays on white paper in both themes. It mirrors the
  exported file, and the exported file is white. Inverting it would make the
  preview a lie about what the ATS receives.
- Print always uses light tokens regardless of the active theme, so a printed
  report is black on white.
- Screenshot and visual tests must set the theme explicitly rather than relying
  on the OS.
