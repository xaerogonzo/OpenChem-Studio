# Dock layout menu and panel buttons: design and measurements

What each panel's title bar offers, why it is built the way it is, and what was measured before the one part that
could not be assumed (Expand panel). The user-facing description is in `docs/USER_GUIDE.md` under "The … menu on every
panel"; this is for the person changing the code.

## Where things live

| Piece | File |
|---|---|
| The title bar: stable names, deliberate title elision, the layout button, `add_button` / `add_menu_button` | `src/openchem/ui/widgets/dock_title_bar.py` |
| The layout menu, built from a plain `DockMenuState` and returned with its actions by name, never executed | `src/openchem/ui/widgets/dock_layout_menu.py` |
| A panel's own button as data (`PanelButton`, `PanelMenuButton`) and the handle that keeps it current | `src/openchem/ui/widgets/dock_panel_actions.py` |
| Expand / Restore: capture, grow, re-apply, restore | `src/openchem/app/dock_expansion.py` |
| The window's side: state, the one menu handler, Move, Return to default side, the expansion lifecycle, `_register_panel_buttons` | `src/openchem/app/main_window.py` |
| Tests | `tests/test_dock_layout_menu.py`, `tests/test_dock_panel_buttons.py`, `tests/test_dock_title_bar.py` |
| Driven check on the real window | `benchmarks/visual/dock_layout_menu.json` (steps `dock_menu`, `dock_state`, `dock_button`) |

## Decisions, and the reason for each

* **Every dock gets the title bar**, with no "?" when nothing is written about it. Only docks with a help topic used to
  have one, so the layout menu would have been missing from Console and Jobs.
* **The float icon folds into the menu**, so the fixed buttons stay at three (menu, "?", close) and the narrow
  right-hand column pays no extra width.
* **The layout button is a text ellipsis, not a standard icon.** `SP_TitleBarMenuButton` is the window's own icon on
  Windows: in the real window it drew the Qt logo. Only the driven run on the real platform showed it; offscreen draws
  something else. A test pins that the button has no icon.
* **One bound method handles the whole menu**, each action carrying `(kind, dock, argument)`. A lambda over the window
  would root it (PySide6 holds a connected plain callable strongly). The menu is refilled on every opening and the
  submenus of the last filling are deleted, so nothing accumulates.
* **Move** runs outside `_arranging` so the window sees it as the user's own placement, captures visibility first
  (`removeDockWidget` hides the dock) and queues the placement classification itself instead of relying on the
  signals `addDockWidget` happens to emit. It respects `Movable` and `allowedAreas`. A floating panel always has
  **Dock panel back**, whatever its features say.
* **Return to default side** is named for what `_default_dock_areas` records: a side, not a split, a size or the
  neighbours. The placed flag is cleared and the classifier decides it again, as for a drag.
* **Reset Panel Layout now clears the pending classification** (the set and the timer) before it begins. It did not,
  so a move followed at once by a reset could be marked placed again after the reset. Found while writing the menu and
  pinned by a sequence test.
* **Cancel all reports a request, never a completion**, counts only jobs with a cancel callback, asks first for more
  than one, logs a callback that raises and still runs the rest. `JobManager.cancel` only calls the callback.

## Expand panel: what was measured

A dock grows along the side it docks on. Measured on the real Windows platform at 1366 x 768 with the default layout
(a throwaway spike, deleted once these numbers were recorded):

| Measurement | Result |
|---|---|
| Right dock before / after `resizeDocks([dock], [large])` | 420 -> 563 px (+143, +34%) |
| The centre area | stays at 400 px, never below, though its own `minimumSizeHint` says 149 |
| The Project Explorer, which was not asked to move | 264 -> 161 px (its minimum) |
| After restoring only the expanded dock | explorer left at 161 (the defect a one-dock restore has) |
| After restoring every docked dock together, absolute sizes | explorer 264, dock 420, centre 440: exact |
| Window shrunk to 1100 px while expanded, then grown back to 1366 | dock 297 and stays 297: **Qt does not keep an expansion through a resize** |
| The same call re-applied after each resize | 563 again |
| Restore by fractions into a 1100 px window | 166 and 292 where 264 and 420 scaled: clamped by the minimums |
| A bottom dock grown vertically (90 -> 429 px) | left/right docks' heights fall to the area between (281, the Properties minimum) |
| Two panels stacked in the right column, one expanded | both take the new width |

The rail takes 234 px, which is why 1366 px leaves 1132 for the docks and the centre. On a 1920 px screen the same
call took Properties from 420 to 1377 px in the driven run.

What follows from it:

* The snapshot holds every docked dock's size along its axis (widths for left/right docks, heights for top/bottom),
  and a restore puts them all back in one `resizeDocks` call per orientation. Exact for the window size it was taken
  at; scaled by the change in window size, within Qt's minimums, for any other.
* The window re-applies the expansion (after a short pause) when it is resized, so the menu, the state and the
  geometry agree. It is never left expanded without a usable Restore size.
* Any other change to the layout ends it first (a move, a float, Return to default side, Show alongside, a rail click,
  any dock shown or hidden). `closeEvent` resolves it before the window state is saved. Reset Panel Layout drops it.
* A growth under 24 px is undone and reported in the status bar. A panel sharing a tab group with a visible dock is
  refused with its reason.
* It is a resize, not a full-window mode. A mode that hid the centre and the other docks would be a different, explicitly
  restored feature with its own state and tests.

## Known limits

* At its minimum width a dock's title elides to nothing (the full title stays in the tooltip and the accessible
  name). Expanding another panel can put the Project Explorer there.
* The dock title bar's controls were checked at the real narrowest dock only through the driven run's shots; there is
  no automated overlap check at every width.
* The new buttons use text and palette colours, so they follow a dark window; the screenshots in this branch are light.
