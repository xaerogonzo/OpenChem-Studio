"""The overlay's lifecycle and its work tiers, against the real bundle.

`test_electron_overlay_canvas.py` asks whether the dots are in the right
PLACE. This asks whether the layer behaves itself: one of it, forever;
nothing done outside its tier; the pointer and the selection untouched;
and Ketcher's own history never grown.

**Lifecycle bugs are likelier here than placement bugs**, and quieter. A
placement bug is visible the moment you look at a molecule. A second layer,
a second rAF loop, or a label re-measured sixty times a second shows up
months later as an editor that has gone sticky, with nothing to point at.
"""

from __future__ import annotations

import json

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.electron_layout import Box, violations
from openchem.chem.electron_overlay import build
from tests.test_ketcher_editor_backend import _ready_backend, _run_js_json, _wait_until

BOND = 1.0

#: One drag of the rotation overlay, as real DOM events.
_DRAG = """
  var o = document.querySelector('.openchem-rotate');
  if (!o) return 'no overlay';
  o.dispatchEvent(new MouseEvent('mousedown', {clientX: 200, clientY: 200, bubbles: true}));
  for (var i = 1; i <= %d; i++) {
    window.dispatchEvent(new MouseEvent('mousemove',
      {clientX: 200 + i * 2, clientY: 200 + i, bubbles: true}));
  }
  window.dispatchEvent(new MouseEvent('mouseup',
    {clientX: 200 + %d * 2, clientY: 200 + %d, bubbles: true}));
  return 'dragged';
"""


def _molblock(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


def _overlaid(qapp, smiles: str, atom_count: int, mode: str = "pairs"):
    backend = _ready_backend(qapp, shown=True)
    backend.load_molblock(_molblock(smiles))
    assert _wait_until(
        qapp,
        lambda: _run_js_json(qapp, backend, "return window.ketcher.editor.struct().atoms.size;")
        == atom_count,
        timeout_seconds=25,
    )
    payload = build(Chem.MolFromSmiles(smiles)).to_payload()
    payload["mode"] = mode
    _run_js_json(qapp, backend, "window.openchemElectrons.set(%s); return 1;" % json.dumps(payload))
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)
    return backend, payload


def _work(qapp, backend) -> dict:
    return json.loads(_run_js_json(qapp, backend, "return window.openchemElectrons.work();"))


def _state(qapp, backend) -> dict:
    return json.loads(_run_js_json(qapp, backend, "return window.openchemElectrons.state();"))


def _settle(qapp, seconds: float = 0.5) -> None:
    _wait_until(qapp, lambda: False, timeout_seconds=seconds)


# --- invariant 5: nothing does more than its tier ----------------------------


def test_a_zoom_recomputes_NOTHING_but_the_transform(qapp):
    """**The performance boundary, which is invisible until it is not.**

    A viewport change must rewrite one transform attribute. Recomputing
    placement there is wasted work sixty times a second; re-measuring a
    label through the DOM is worse. Neither ever reports itself.
    """
    backend, _ = _overlaid(qapp, "COC", 3)
    _run_js_json(qapp, backend, "window.openchemElectrons.resetWork(); return 1;")

    for zoom in (1.6, 0.7, 1.0):
        _run_js_json(qapp, backend, "window.ketcher.editor.zoom(%s); return 1;" % zoom)
        _settle(qapp)

    work = _work(qapp, backend)
    assert work["placements"] == 0, work
    assert work["labelMeasurements"] == 0, work
    assert work["transforms"] > 0, "the transform never moved, so nothing was really zoomed"


def test_sixty_rotation_frames_never_re_measure_a_label(qapp):
    """Turning the molecule moves atoms, so placement legitimately
    recomputes -- a different geometry, not instability. Label metrics are
    not: `NH2` is the same width whichever way the molecule faces."""
    backend, _ = _overlaid(qapp, "CO", 2)
    _run_js_json(qapp, backend, "window.openchemRotation.enter(); return 1;")
    _settle(qapp, 0.8)
    _run_js_json(qapp, backend, "window.openchemElectrons.resetWork(); return 1;")

    assert _run_js_json(qapp, backend, _DRAG % (60, 60, 60)) == "dragged"
    _settle(qapp, 1.5)

    work = _work(qapp, backend)
    assert work["labelMeasurements"] == 0, work
    _run_js_json(qapp, backend, "window.openchemRotation.leave(true); return 1;")


def test_only_one_viewport_watcher_is_ever_started(qapp):
    """One rAF loop for the life of the page. A loop per toggle would run
    twenty of them after twenty toggles, all doing the same work -- the
    shape of leak the rotation overlay had once, and just as inert-looking.
    """
    backend, payload = _overlaid(qapp, "CO", 2)

    _run_js_json(qapp, backend, """
      for (var i = 0; i < 20; i++) {
        window.openchemElectrons.set(null);
        window.openchemElectrons.set(%s);
      }
      return 1;
    """ % json.dumps(payload))
    _settle(qapp, 0.8)

    assert _work(qapp, backend)["watchers"] == 1


# --- invariant 3: the pointer and the selection ------------------------------


def test_a_selection_survives_the_overlay_going_on_moving_and_going_off(qapp):
    """The layer sits on top of the canvas, so the ways it could disturb a
    selection are many and every one of them silent."""
    backend, payload = _overlaid(qapp, "CO", 2, mode="off")
    _run_js_json(qapp, backend, "window.ketcher.editor.selection({atoms: [0]}); return 1;")
    before = _run_js_json(
        qapp, backend, "return JSON.stringify(window.ketcher.editor.selection());"
    )
    assert before and before != "null", before

    _run_js_json(qapp, backend, "window.openchemElectrons.set(%s); return 1;" % json.dumps(payload))
    _run_js_json(qapp, backend, "window.ketcher.editor.zoom(1.5); return 1;")
    _settle(qapp, 0.8)
    _run_js_json(qapp, backend, "window.openchemElectrons.set(null); return 1;")
    _settle(qapp)

    assert (
        _run_js_json(qapp, backend, "return JSON.stringify(window.ketcher.editor.selection());")
        == before
    )


def test_a_click_where_a_dot_is_reaches_the_canvas_underneath(qapp):
    """`pointer-events: none` asserted through BEHAVIOUR rather than
    through the style property: `elementFromPoint` answers what a real
    click would hit, and a dot that swallowed one would make an atom
    unselectable for no visible reason."""
    backend, _ = _overlaid(qapp, "CO", 2)

    hit = _run_js_json(qapp, backend, """
      var dot = document.querySelector('.openchem-electrons circle');
      if (!dot) return '<no dot>';
      var b = dot.getBoundingClientRect();
      var el = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
      if (!el) return '<nothing>';
      return el.closest('.openchem-electrons') ? 'the overlay' : 'the canvas';
    """)

    assert hit == "the canvas", hit


# --- invariant 12: off is off ------------------------------------------------


def test_off_leaves_no_dots_and_no_note(qapp):
    backend, _ = _overlaid(qapp, "COC", 3)
    assert (
        _run_js_json(
            qapp, backend, "return document.querySelectorAll('.openchem-electrons circle').length;"
        )
        == 4
    )

    _run_js_json(qapp, backend, "window.openchemElectrons.set(null); return 1;")
    _settle(qapp, 0.6)

    counted = json.loads(_run_js_json(qapp, backend, """
      var layer = document.querySelector('.openchem-electrons');
      return JSON.stringify({
        dots: document.querySelectorAll('.openchem-electrons circle').length,
        hidden: layer ? getComputedStyle(layer).display === 'none' : true,
        note: layer ? layer.querySelector('.el-note').textContent : ''
      });
    """))

    assert counted == {"dots": 0, "hidden": True, "note": ""}


# --- invariant 8: still legal after the molecule turns -----------------------


def test_after_a_rotation_drag_the_dots_still_obey_every_rule(qapp):
    """Turning the molecule changes the bond directions, so the slots move
    with them. What must not happen is a placement that was legal before
    the turn becoming a smudge after it."""
    from tests.test_electron_overlay_canvas import (
        _atom_geometry,
        _composed_label,
        _label_box,
    )

    backend, _ = _overlaid(qapp, "COC", 3)
    _run_js_json(qapp, backend, "window.openchemRotation.enter(); return 1;")
    _settle(qapp, 0.6)
    assert _run_js_json(qapp, backend, _DRAG % (30, 30, 30)) == "dragged"
    _settle(qapp, 1.2)

    state = _state(qapp, backend)
    geometry = _atom_geometry(qapp, backend)
    assert state["placement"], "the dots vanished when the molecule turned"
    for entry in state["placement"]:
        atom = geometry[str(entry["position"])]
        measured = _label_box(qapp, backend, _composed_label(atom))
        label_box = (
            Box(
                atom["centre"][0] - measured["hw"],
                atom["centre"][1] - measured["hh"],
                atom["centre"][0] + measured["hw"],
                atom["centre"][1] + measured["hh"],
            )
            if measured
            else None
        )
        breaches = violations(
            [tuple(dot) for dot in entry["dots"]],
            tuple(atom["centre"]),
            atom["bonds"],
            label_box,
            BOND,
            expected_pairs=entry["pairs"],
        )
        assert breaches == [], breaches
    _run_js_json(qapp, backend, "window.openchemRotation.leave(true); return 1;")


# --- invariant 14: THE UGLY ONE ----------------------------------------------


def test_the_whole_miserable_sequence(qapp):
    """Enable, zoom, disable, zoom, enable, rotate, leave, zoom, then
    toggle ten more times.

    Every one of those is fine on its own; the failures live in the joins.
    One layer at the end, no stale dots, one watcher, the right atom, and
    Ketcher's history untouched by any of it.
    """
    backend, payload = _overlaid(qapp, "CCO", 3)
    on = json.dumps(payload)
    history_before = _run_js_json(
        qapp, backend, "return JSON.stringify(window.ketcher.editor.historySize());"
    )

    def step(script: str):
        result = _run_js_json(qapp, backend, script)
        _settle(qapp, 0.35)
        return result

    step("window.openchemElectrons.set(%s); return 1;" % on)
    step("window.ketcher.editor.zoom(1.7); return 1;")
    step("window.openchemElectrons.set(null); return 1;")
    step("window.ketcher.editor.zoom(0.8); return 1;")
    step("window.openchemElectrons.set(%s); return 1;" % on)
    step("window.openchemRotation.enter(); return 1;")
    step(_DRAG % (20, 20, 20))
    step("window.openchemRotation.leave(true); return 1;")
    step("window.ketcher.editor.zoom(1.0); return 1;")
    for _ in range(10):
        step("window.openchemElectrons.set(null); return 1;")
        step("window.openchemElectrons.set(%s); return 1;" % on)

    final = json.loads(_run_js_json(qapp, backend, """
      return JSON.stringify({
        layers: document.querySelectorAll('.openchem-electrons').length,
        dots: document.querySelectorAll('.openchem-electrons circle').length,
        watchers: JSON.parse(window.openchemElectrons.work()).watchers,
        history: JSON.stringify(window.ketcher.editor.historySize())
      });
    """))

    assert final["layers"] == 1, final
    # Ethanol: the oxygen's two pairs, four dots. Not forty.
    assert final["dots"] == 4, final
    assert final["watchers"] == 1, final
    assert final["history"] == history_before, final

    # And they are still on the RIGHT atom after all of that.
    state = _state(qapp, backend)
    assert [(e["position"], e["pairs"]) for e in state["placement"]] == [(2, 2)]
