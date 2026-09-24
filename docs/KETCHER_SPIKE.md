# Ketcher drawing spike (2026-09-24, corrected the same day)

A research note, not a specification: what was measured about driving the embedded Ketcher
page, so the drawing work (bond gestures, the atom menu, keyboard shortcuts) starts from what
is true. Everything here was read from the vendored bundle
(`src/openchem/resources/ketcher/dist/assets/index-*.js`) or measured on the running application
with the `OPENCHEM_DRIVE` steps `ketcher_eval`, `ketcher_hover`, `atom_editor` and `key`.

**The first version of this note was wrong in two places, and the corrections are why it says so.**
It reported that a number key over a hovered bond changes the bond, and that a hover cannot be produced
from automation. Neither is true; both were settled the same day by reading the hotkey table and by a
positive control (below).

## What Ketcher does with a hover and a key

Ketcher's `keydown` listener (`initKeydownListener`, on the editor's DOM, not on `document`) applies a
hotkey to the item under the pointer -- the item whose `hover` flag is set in the render's ctab
(`getHoveredItem`). Measured on the running app (`benchmarks/visual/ketcher_hover_keys.json`):

| hover | key | result |
|---|---|---|
| an **atom** | `n` | the atom becomes nitrogen (`CC` -> `NC`) -- the control that shows the machinery works |
| a **bond** | `/` | Ketcher's bond properties dialog opens (`bondProps-dialog`) |
| a **bond** | `2` | **nothing changes.** The key is handled (`preventDefault`) and the bond stays single |

The last row is the correction. `handleHotkeyGroup` does reach `handleTool` for a hovered bond, but
`getToolHandler` has handlers for atoms and s-groups and none for bonds, so the action falls through to
nothing. In this bundle "hover a bond and press 2" is **not** a native feature, so the gestures the plan
proposed (hover + number, click-to-cycle) are new work, not a hint and a Help entry.

## A hover CAN be produced from automation

A synthetic DOM `mousemove` and a real Qt `QMouseEvent` sent with `QTest.mouseMove` to the web view's focus
proxy both left every `hover` flag false, which is what the first version of this note reported. It was a
statement about those two routes only. Ketcher's own tools set the flag with

    editor.hover(editor.findItem(event, null), null, event)

and `findItem` needs only the event's client position, so calling it with a position computed by inverting
`render.page2obj` (as the overlay and the atom Edit path do) puts the page in the state a real hover
produces. The key is then dispatched inside the editor's DOM (`render.clientArea.firstChild`); dispatched on
`document` it is never seen. What this does not exercise is the browser's own mouse-move plumbing, which
Ketcher's hotkeys do not read. The `ketcher_hover` step does exactly this and asserts the result, so a
hover-dependent gesture can now be regression-tested.

## What else Ketcher already does

- **The atom Edit dialog is `elementEdit`, and it needs the selection.** Ketcher's select tool,
  on a double-click over an atom, hands `elementEdit` an ARRAY OF ATOM OBJECTS from the current
  selection and feeds the returned promise to an internal `updateSelectedAtoms`, which writes the
  dialog's answer back as one edit. Dispatching the event with a bare object (what the atom
  right-click menu did) opens nothing and cannot apply an answer. Fixed by selecting the atom and
  dispatching a `dblclick` at its position (`KetcherEditorBackend.open_atom_editor`), driven and
  asserted in `benchmarks/visual/atom_edit_menu.json`.
- **Ketcher's atom and charge tools cannot be armed by a synthetic click** -- the tool arms and nothing
  changes. The atom menu's Change X / charge / delete are therefore edits the application makes itself
  (`ChemistryEngine.edit_atom` through an `EditStructureCommand`), which is also what the project's rule
  for structure-modifying actions asks for. (The hover route above was found afterwards and was not tried
  on those tools; it may well have been the missing state.)

## Consequences for the drawing work

1. Bond gestures are new work. **Hover + 1/2/3 is built** (`interceptBondOrderKeys`, `edit_bond`); click-to-cycle is not. The route that fits is the atom menu's: the page reports the hovered bond
   and the key, and the application changes the bond through a `ChemistryEngine` method and an
   `EditStructureCommand`, so it is one undo entry and recomputes like any deliberate change.
2. **Click-to-cycle is the contested half.** In the select tool a click on a bond SELECTS it; cycling on
   click would take that away, so it needs its own switch, off by default. Aromatic, query and wedge bonds
   are left untouched with a hint.
3. The atom menu's replacement of Ketcher's own menu keeps delegating to Ketcher for anything Ketcher does
   natively; `Edit...` does.
4. A guard, not only a note: if a Ketcher upgrade makes a number over a bond native, the first row of the
   script fails, which is the signal to drop our own implementation rather than fight the editor's.
