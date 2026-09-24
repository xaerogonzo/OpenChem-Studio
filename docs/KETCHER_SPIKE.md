# Ketcher drawing spike (2026-09-24)

A research note, not a specification: what was measured about driving the embedded Ketcher
page, so the drawing work (bond gestures, the atom menu, keyboard shortcuts) starts from what
is true. Everything here was read from the vendored bundle
(`src/openchem/resources/ketcher/dist/assets/index-*.js`) or measured on the running application
with the `OPENCHEM_DRIVE` steps `ketcher_eval`, `ketcher_hover`, `atom_editor` and `key`.

## What Ketcher already does

- **Hover-aware hotkeys are native.** `handleHotkeyGroup` and `handleHotkeyOverItem` in the
  bundle apply a hotkey to the item under the pointer: a bond-group key (`1`, `2`, `3`) over a
  bond changes that bond, an element key over an atom replaces its label, and `/` opens the
  properties dialog of the hovered atom or bond (`handleSlashKey`). So "hover a bond and press a
  number" is very likely something the editor does **without any code of ours** -- which is the
  shape of the earlier lesson about a feature that existed under a name nobody would look for.
  It has **not** been confirmed with a real pointer (see below), so the gesture the plan proposed
  ("click a bond to cycle") should not be built until somebody checks what is already there.
- **The atom Edit dialog is `elementEdit`, and it needs the selection.** Ketcher's select tool,
  on a double-click over an atom, hands `elementEdit` an ARRAY OF ATOM OBJECTS from the current
  selection and feeds the returned promise to an internal `updateSelectedAtoms`, which writes the
  dialog's answer back as one edit. Dispatching the event with a bare object (what the atom
  right-click menu did) opens nothing and cannot apply an answer. Fixed by selecting the atom and
  dispatching a `dblclick` at its position (`KetcherEditorBackend.open_atom_editor`), driven and
  asserted in `benchmarks/visual/atom_edit_menu.json`.

## What could not be produced from automation

A hover. A synthetic DOM `mousemove` dispatched on the canvas or the document, and a real Qt
`QMouseEvent` sent with `QTest.mouseMove` to the web view's focus proxy, both left every
atom's and bond's `hover` flag false, so a following key press had nothing to act on and the bond
stayed single. That is a statement about the automation route, not about Ketcher: a person with a
real mouse produces the hover the bundle expects. What would settle it is one manual check --
hover a bond, press `2`, watch it become double -- or an input route that reaches Chromium as a
real pointer, which the project's rule against driving the machine's cursor rules out here.

## Consequences for the drawing work

1. Before building bond gestures, check the native hover hotkeys by hand (above). If they work, the
   work is a hint in the UI and a Help entry, not a gesture.
2. The atom menu's replacement of Ketcher's own menu should keep delegating to Ketcher for
   anything Ketcher does natively; the `Edit...` item now does.
3. A gesture that needs a hover cannot be regression-tested through `OPENCHEM_DRIVE` as it stands.
   The alternative that can be -- an application-owned gesture on the canvas that calls Ketcher's
   own editor API -- is what to spend effort on only if the native route is found lacking.
