# Increased contrast: measured, not shipped

PR E of the UI-polish series proposed an "Increased contrast" preference inside Light and Dark. Its decision rule: ship only if it
can be done in the `theme` helpers and the page stylesheet **without per-widget edits**; otherwise write up the measured failures.
It does not meet that rule, so nothing was built. This page is the record.

Both scripts run on the real Windows platform (the offscreen platform ignores a forced colour scheme) and show no window:

```bash
uv run --no-sync python -I benchmarks/contrast/pairs.py
uv run --no-sync python -I benchmarks/contrast/borders.py
```

Thresholds are WCAG 2.2: normal text 4.5:1 (1.4.3); user-interface components and meaningful graphics 3:1 (1.4.11). Measured
2026-11-01 on Windows 11, Qt style `windows11`.

## 1. Qt's own palette already clears the text bar by a wide margin

| Pair | Light | Dark |
|---|---|---|
| Text on window | 18.93 | 16.67 |
| Text on base | 21.00 | 13.77 |
| Button text on button | 21.00 | 11.03 |
| Link on window | 8.99 | 12.45 |
| Highlighted text on highlight | 5.67 | 4.53 |
| Tooltip text on tooltip | 18.93 | 7.48 |
| Selection / focus colour against window | 5.11 | 3.68 |

An option that raises text contrast would be lifting 11 to 21 up toward 21. The only pair near its floor is selected text in
the dark look (4.53 against 4.5).

## 2. What does fail

**Control borders, in the dark look.** The palette's border roles (`Mid`, `Dark`) are 1.13 and 1.00 against the window; light's `Mid` is
2.36 against a 3.0 bar. Disabled button text in dark is 4.07 (an inactive control has no WCAG minimum).

**Four text colours in the default LIGHT look** (the theme's own literals, each held to 4.5:1 only on the dark side by
`tests/test_theme.py`):

| Light literal | Against white or `#f3f3f3` |
|---|---|
| `#777777` | 4.04 |
| `#8a6d3b` | 4.37 |
| `#8a6d00` | 4.43 |
| `#d55e00` | 3.49 (an Okabe-Ito severity hue; passes as large text) |

These are failures of the default, not of a missing option, and the fix is a darker light literal at each use, which is an edit per
site, so it is a separate change.

## 3. Why the option cannot be built the cheap way

Raising `Mid`, `Dark`, `Midlight`, `Light` and `Shadow` to white in the application palette and re-rendering a line edit, a push
button and a combo box in the dark look **moved no edge pixel** (`borders.py`: edges moved: all False; edge contrast against the
window stays 1.00). The `windows11` style draws control outlines from fixed colours, not from the palette. So:

- a palette-only option would raise text that is already fine and leave the borders that are not;
- lifting the borders needs either a different style (Fusion, which changes every control's look) or a stylesheet per control class,
  which is per-widget work and puts a style sheet on widgets that today follow the palette on their own (the very case
  `theme.repolish_styled_widgets` documents as fragile).

## Decision

Not shipped. Reopen it if one of these changes: the application moves to a style that honours the palette for borders, or the
light literals above are fixed first (then the remaining gap is the border, which is a style question and not a theme one).

## Not measured

Embedded web content (the 2D editor and the 3D viewers) and plotted series were not measured; they would be listed as not covered
by any such option. Display contrast settings in Windows itself (Contrast themes) were not tested.
