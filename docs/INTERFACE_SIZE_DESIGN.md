# Interface size

Settings > Appearance > Interface size: Default, Larger (1.15), Large (1.3). Changes at once, no restart.

## Audit (before the spike)

- No application-level style sheet; `main.py` never called `setFont` or `setStyle`.
- Per-widget style sheets set colour and weight only, except **7 pixel font sizes**: `periodic_table_dialog.py` (five: the element cell, the isotope note, the decay legend, the legend, `_MUTED_NOTE`), `property_panel.py` (`_WIDE_ROW_CAPTION_STYLE`, which nothing uses) and `substance_card.py`.
- Painted text: `atom_diagram.py` derives its sizes from the painter's font (it follows); `nmr_view_widget.py` has two fixed point sizes, both in the PDF export, which is printed output and is deliberately not scaled.
- Web pages (the 2D editor, the 3D viewers) have their own zoom and are not touched.

## Spike

The real `MainWindow`, offscreen, `QApplication.setFont` at 1.0, 1.15, 1.3 and 1.5 of the platform default (`scratchpad/spike_scale.py`, kept out of the repository):

| factor | main window minimum size | font |
|---|---|---|
| 1.0 | 870 x 412 | 9.0 pt |
| 1.15 | 882 x 420 | 10.35 pt |
| 1.3 | 894 x 433 | 11.7 pt |
| 1.5 | 906 x 447 | 13.5 pt |

- `setFont` reaches windows that are already open (after the event loop turns), so no restart is needed.
- The layout is not the limit: the minimum grows about 4% for a 50% larger font.

## What the real window showed (driven, `benchmarks/visual/interface_size.json`)

1. **A widget with its own style sheet keeps the font it was polished with.** The Properties section headers (`QToolButton { font-weight: bold; }`) stayed small after a live change. Offscreen does not reproduce it. Fixed by setting the sheets again after the change, the same remedy as the palette's (`theme.repolish_styled_widgets`).
2. **The Settings section list had a width fixed at build time**, so a dialog open when the size changed clipped "Quantum chemistry". It is now refitted on a font change, with a margin of two line heights.
3. **1.5 was left out.** At the default dock width it elided "Run on: this molecule" and the batch status line. **At 1.3 only the batch status line clips**, which is by design one line with the full text on hover (`_StatusLabel`).

## Decisions

- Scaled from the platform default font captured at start, never from the current font, so repeating a step or returning to Default cannot drift.
- Pixel font sizes in style sheets are scaled in `theme.resolve`; a sheet that must follow is given through `theme.style`. The element cell and the substance card moved to it, and their entries left the direct-`setStyleSheet` allow list.
- Stored as the integer of `InterfaceSize` under `ui/interface_size`; an unreadable or out-of-range value is Default.

## Not measured

Display scales other than this machine's (100%/125%/150%/200%), the Help window's HTML, and keyboard-only operation of the new control.
