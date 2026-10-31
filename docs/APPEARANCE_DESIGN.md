# Appearance: Light, Dark and Follow the system

Written 2026-10-26, with the measurements that decided it. The setting is **Settings ▸ Appearance** and **View ▸ Theme**; both are
one preference, `ui/appearance` (`app/settings.py` `APPEARANCE`), stored as an integer: **0 follow the system, 1 light, 2 dark.** A
value that does not parse, or is out of range, reads as 0.

## What was wrong

There was no setting. `main.py` made a plain `QApplication` and set no style or palette, so Qt followed Windows by itself and the
window was dark only when Windows was. Nothing in the program could turn it on or off, which is why it could not be found.

## The decisions, and what each rests on

**PySide6 minimum is 6.8** (`pyproject.toml`). `QStyleHints.setColorScheme` and `unsetColorScheme` arrived in Qt 6.8; the lock was
already 6.11.1 and the declared floor was 6.7. The program is installed from the lock, so a 6.7 branch would be untested code.

**The native Windows style is kept, with no custom palette.** This was a spike, not a taste: the native `windows11` style was run
with Windows itself in LIGHT and the scheme forced to Dark, then through Light, System, Dark, System. The palette followed every
time (window `#1e1e1e` / `#f3f3f3`), menus, tab bars, scroll bars, combos, tables and docks all rendered dark
(`tests/test_appearance_service.py`, real-platform tests), and so did the **title bar** of the real window (a `PrintWindow` capture
of the running application). So the application promises the title bar follows a forced scheme as well as Follow the system. The
Fusion-in-Dark-only alternative was rejected: it would change control metrics between modes.

**Follow the system is `unsetColorScheme()`**, not a read of Windows taken once. It hands the decision back to Qt, which keeps
following the operating system. Forced Light or Dark is `setColorScheme`.

**Qt's `offscreen` platform ignores a forced scheme** (`colorScheme()` stays Unknown, the palette does not move), which is the
suite's default platform. So the service's tests are in two layers: the request made of `QStyleHints` is recorded, and the platform
is stood in for by installing a palette (what Windows does when its theme changes); the tests that force a scheme and read the
palette skip on offscreen and run with `QT_QPA_PLATFORM=windows`. `benchmarks/visual/appearance.json` does the same on the real
window, with the real controls.

## One owner

`app/appearance_service.py` applies the choice and says when the look has **settled**. Qt documents that its scheme-changed signal
can arrive while the old palette is still installed, so the service does not trust it: it waits for `ApplicationPaletteChange` or
`StyleChange` on the application, lets a few milliseconds pass so a burst is one change, and reads the look from the palette's window
colour (`domain/appearance.effective_from_lightness`). It then calls `ui.theme.set_effective` first, so every stylesheet is already
rewritten, and publishes one `AppearanceChanged(effective)` on the bus (and a Qt signal). It reports the look that is on screen, not
the choice: with Follow the system chosen it fires when Windows changes, and never for a choice that leaves the look as it was.
`start()` reads the look silently, because nothing is built yet.

## Colours: `ui/theme.py`

A stylesheet with a colour in it is a cache of the look it was written in. A colour that means something is written through
`theme.style(widget, "color: #666666;")`: the text is written for a light window, exactly as before, resolved for the look on screen,
and rewritten when it changes. In light the resolved text is the text given, byte for byte, so nothing that was tested changed.

`_DARK_FOR_LIGHT` maps individual light literals, deliberately by meaning and not by "all greys": a muted note, an error, a success, a
caution and the structure checker's severities are different tokens that merely look alike in light. Every dark value is held to
4.5:1 against the lighter dark surface by `tests/test_theme.py`. A literal that is not in the table is left alone on purpose: the
colour-blind-safe series colours, the periodic table's category fills, anything whose hue is the data.

Painted colours use `theme.ink()` (the same colour, lifted in lightness only until it reads on a dark surface, hue kept),
`theme.faint()` for grid lines and `theme.panel_fill()` for a legend's box; a widget that draws redraws on a change through
`theme.repaint_on_change`. `theme.follow(widget, callback, slot=...)` is the general hook (rich text with a colour in it, an icon
drawn in the palette's text colour).

**The guard.** `tests/test_theme.py` scans every `setStyleSheet(` call under `src/openchem` and `plugins` and fails on one that is
neither routed through the theme nor in `_DIRECT_ALLOWED` with its reason (weight, size, spacing, a palette role, or a swatch whose fill
is data). The scan itself is checked to find at least fifteen calls, so an empty scan cannot pass.

### A finding only the running window showed

After a LIVE switch, widgets that carry a stylesheet of their own kept the palette they were polished with: a collapsible section's
header (`QToolButton { border: none; }`) stayed black on the dark window and the rail's buttons stayed pale grey with white icons.
Both were invisible in every test (offscreen cannot change scheme) and obvious in the first screenshot. `theme.repolish_styled_widgets`
sets each such widget's stylesheet again on every change, which makes the style resolve it afresh; the same drive run showed both fixed.

## The web pages

The pages are documents of their own, so neither the palette nor Windows reaches them, and the application can be forced against
Windows. Each is **told** the look, as the word `light` or `dark`, by a short script (`ui/widgets/web_appearance.py`).
`theme.effective()` is the single latest value, so there is no queue: a page not yet ready is told once when it becomes ready (the
value at that moment, so three switches while it loads settle on the last), and a ready page is told on every change. The scripts touch
the page's own surfaces only and never reload it, so the structure, camera and layers are as they were. Chromium is also given the
page's background colour so a dark window never flashes white. The QtWebEngine bindings have no colour-scheme setter, so none is used.

* **3D viewer** (`resources/viewer3d/viewer.html`): `setAppearance` sets the background, the gallery cells' backgrounds, the label ink
  and the overlay chrome.
* **Macromolecule viewer** (`resources/molstar/viewer.html`): the canvas background, the page, and (since 2026-10-31) Mol*'s own
  panels. Mol*'s skin is one light stylesheet with literal colours and no variables, so it cannot be re-themed by a variable; but its
  layout regions are stable `msp-layout-*` classes and the 3D canvas lives in `.msp-layout-main`. `setChromeLook` therefore filters
  `.msp-layout-top`, `-left`, `-right` and `-bottom` with the same `invert(0.88) hue-rotate(180deg)` the editor's toolbars use, in one
  `<style id="openchem-appearance">`, and light is no stylesheet. The structure's colours never pass through a filter:
  `tests/test_web_appearance_live.py` asserts every ancestor of `.msp-viewport` has `filter: none` while the three panels have one.
* **2D editor** (Ketcher): see below.

### Ketcher: dark toolbars, a dark drawing area, ink recoloured and nothing else

The four toolbars (top, left, right, bottom; `KETCHER_CHROME_SELECTORS`) are filtered with `invert(0.88) hue-rotate(180deg)`, which takes
the editor's white to the application's dark surface. **Nothing that holds or is held by the drawing area is filtered**, and
`tests/test_web_appearance_live.py` asserts in the live page that the canvas and every ancestor have `filter: none` while each toolbar
has one, and that each selector matches exactly one element, so a rebuilt editor that renames a CSS module fails a test instead of
leaving a toolbar light without a sound. **The editor's own dialogs** (atom and bond properties, settings, the periodic table and the
rest) used to stay a white box in a dark window; each is one `<dialog class="Dialog-module_dialog…">` that exists only while it is open,
inside `Modal-module_modalOverlay` and not inside the editor, so `KETCHER_DIALOG_SELECTORS` adds it to the same filter rule (it cannot
be counted at rest, so a live test opens a real Atom Properties dialog and asserts the filter, and that the canvas chain is still clean).
A hue rotation approximates the dialog's coloured buttons, as it does the toolbars'; a structure thumbnail inside a dialog is chrome too.

**The drawing area itself used to stay white (decided 2026-10-26, "an untouched drawing area") and went dark on 2026-10-27**, once
the DOM was read instead of filtered. Measured on the live page for a six-atom drawing: the editor writes its ink as the attribute
value black (`#000000`, on 11 `rect` and 5 `path` bonds, 3 `circle`s and a `text`) and every element colour as its own value
(nitrogen `#304ff7`, oxygen `#ff0d0d`, chlorine `#1fd01f`; selection and hover `#0097A8`). `KETCHER_INK_CSS` is two rules inside the
canvas container: `stroke` and `fill` set to the light ink where the attribute is `#000000`, `#000` or `black`. No rule names any other
value, so an atom colour cannot match, and nothing is filtered, which is why it has none of the clamping that sank the inversion below.
`tests/test_web_appearance.py` holds the stylesheet to that shape; the live test draws a molecule with N, O and Cl and compares the
computed colours dark against light (each element colour the same count, every black become the light ink, nothing painted black left;
`desc` and `defs` report the initial fill and draw nothing). **The editor's own image export is drawn from the structure, not the DOM:**
`generateImage` returned the same SVG dark and light, and a test holds that, so a picture saved or copied from a dark window is not
white-on-white. Stereo wedges, charges and hydrogen labels were checked in a magnified shot.

**Whole-page inversion was tried first and rejected, with numbers.** Inverting `#root` and inverting the drawing back looked right in a
screenshot, but the colours did not return: nitrogen `(48, 139, 249)` came back `(97, 120, 249)` and oxygen `(255, 13, 13)` as
`(255, 103, 103)`, and 91,392 of 702,000 pixels in the drawing region differed by more than 24. A hue rotation is clamped per channel
and does not undo. A drawing in which oxygen is pink is chemically misleading, so the approach is not in the code.

## The colour sweep (2026-10-31)

A second pass, after the first dark mode shipped, asked what the first one had missed. Method: every hex literal in the UI's own Python
and the plugins (about 190 sites, 81 distinct values) was classified, every panel and 19 dialogs were shot in dark, and the
literals' contrast was measured against the dark field `#2d2d2d` (the lighter of the two dark surfaces) and the base `#1e1e1e`.
Of the 81 values, 16 have a dark value, 39 already read at 4.5:1 or better on the field, and 26 do not and were each reviewed
(the 26 are the list in `tests/test_colour_literals.py`). The painted `QColor` constants traced to their draw sites (the atom diagram, the IR and stick spectra, the
histogram, the project table, the periodic table) go through `theme.ink`; the survey shots showed no painted widget unreadable. The vendored Ketcher bundle (1,000-odd literals) is third-party and was excluded by design.

| Class | Count | Example | What decides it |
|---|---|---|---|
| Theme-managed text | 16 literals | `#666666` muted, `#c62828` fault | a `_DARK_FOR_LIGHT` value held to 4.5:1 by `tests/test_theme.py` |
| Painted through `theme.ink` | most painters | histogram, spectra, atom diagram, project-table brushes | lifted only as far as 4.5:1 requires; measured 4.5 to 4.7 after lifting |
| Data colours, intentionally fixed | 8 literals | Okabe-Ito series, contact-kind layers, heat-map ramps | the colour is the data; the 3D viewer paints them on its own background |
| Surfaces | 3 literals | `#1e1e1e`, `#1f1f1f`, `#2d2d2d` | they are the dark, not ink on it |
| **Leak: found and fixed** | **3** | see below | |

The leaks the sweep found:

* The 2D editor's modal dialogs were white boxes (fixed above, `KETCHER_DIALOG_SELECTORS`).
* The macromolecule viewer's three panels were cream in a dark window (fixed above, `setChromeLook`).
* `ir_view_widget` set an imaginary mode's row in `Qt.GlobalColor.red`: pure red is 3.4:1 on the dark field. It goes through `theme.ink`
  now (identical in light; the brush is chosen when the row is built, like the project table's).

**Not changed, on purpose.** Every colour that carries the data kept its value. The only ones that read below 4.5:1 on the dark field are
`#009e73` (4.0:1 on the field, 4.9:1 on the base) and a status chip's `#ef6c00` (4.5:1 on the field, 5.4:1 on the base), listed with their
reasons in `tests/test_colour_literals.py`. **That test is the guard:** it fails on a new hex literal that is neither mapped, readable
(4.5:1 on the field) nor listed with a reason, and on a listed entry that nothing writes any more, so the list only shrinks.

### Rendering systems

| System | How it follows the look | Known exceptions |
|---|---|---|
| Qt widgets | the application palette plus `theme.style` for a colour that means something | a table brush is chosen when the row is built |
| Painted widgets (charts, spectra, atom diagram) | `theme.ink`, `faint`, `panel_fill`, `repaint_on_change` | data series colours (kept, lifted only to 4.5:1) |
| 2D editor (Ketcher) | a stylesheet: toolbars and dialogs filtered, drawing ink recoloured by value | a custom ink colour the editor writes, which reads as well as it did |
| 3D viewer | `setAppearance`: background, overlay chrome, label ink | the structure's own colours |
| Macromolecule viewer (Mol*) | `setAppearance`: canvas, page, and the four layout regions filtered | the structure's own colours; the canvas overlay's own buttons |
| Help | a `QTextBrowser` on the palette | none found |
| Chemical depictions (Lewis, density heat map) | `theme.paper`: white paper in a dark window | by design: ink chosen for white |

## Where the two controls meet

Settings' combo and the View menu both read `Settings.preference(APPEARANCE)`, both write through `Settings.set_preference`, and both
follow a `SettingsChanged` for the key without writing it back (the menu connects `triggered`, not `toggled`; the dialog blocks its
combo's signals while it follows). The checked menu entry is the stored CHOICE, never the look. Combo rows are found by their stored
integer, never by position. The menu entries go through `_document`, so they are rebindable commands like every other menu entry and have
no default shortcut.

## What this does not do

* A hue rotation approximates the coloured buttons inside a filtered web region (the editor's toolbars and dialogs, Mol*'s panels); a
  button's label reads, but its hue is not exactly the original. Nothing a person reads a result from is filtered.
* An ink the editor draws in a value other than black (a custom atom colour, a `#333` annotation) is left as it is, and reads on the
  dark surface only as well as its own colour does.
* Colours that carry the data (element colours, the colour-blind-safe series, periodic-table categories, the structure checker's
  atom highlights, which are drawn on a white depiction) are not changed.
* A table cell's brush is chosen when the row is built, so a project table cell in a non-scalar colour reads correctly after the next
  refresh, not at the instant of a live switch.
* `benchmarks/visual/appearance.json` writes the real stored preference through the real controls and ends by choosing Follow the system.
  A run killed half-way leaves the choice it had reached; Settings ▸ Appearance puts it back.
