"""Lone-pair dots on the real canvas, judged by the rules.

The placement lives in the page, because only the page knows the
viewport. This runs it against the real vendored bundle and hands what it
produced to `chem/electron_layout.violations()` — one implementation, one
independent judge, so a failure names the geometric rule that broke
rather than reporting that two implementations disagree.

**Everything the overlay computes is in MODEL UNITS**, which is what makes
the pan/zoom tier free: Ketcher's viewport transform is scale + translate
with no rotation, so nothing a viewport change does can move a slot. The
tests below check that by construction rather than by tolerance.
"""

from __future__ import annotations

import json
import math

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.electron_layout import Box, violations
from openchem.chem.electron_overlay import build
from tests.test_ketcher_editor_backend import _ready_backend, _run_js_json, _wait_until

#: Model units. Ketcher normalises bond lengths to 1 unit, so every model
#: quantity the overlay produces is in these.
BOND = 1.0

FIXTURES = {
    "water": ("O", 1),
    "ammonia": ("N", 1),
    "methanol": ("CO", 2),
    "dimethyl ether": ("COC", 3),
    "pyridine": ("c1ccncc1", 6),
    "sulfoxide": ("CS(=O)C", 4),
    # A BONDED halide, not an isolated [Cl-]: three pairs and six dots is
    # the hardest placement, and a free ion has no bonds at all, so it
    # would exercise none of the bond-obstacle path.
    "chloromethane": ("CCl", 2),
}


def _molblock(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


def _overlaid(qapp, smiles: str, atom_count: int, mode: str = "pairs"):
    """Load a structure, hand over its counts, and switch the mode on."""
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
    _run_js_json(
        qapp, backend, "window.openchemElectrons.set(%s); return 1;" % json.dumps(payload)
    )
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)
    return backend, payload


def _state(qapp, backend) -> dict:
    return json.loads(_run_js_json(qapp, backend, "return window.openchemElectrons.state();"))


def _atom_geometry(qapp, backend) -> dict:
    """Atom centres and bond bearings, in model units, straight from the
    struct -- the same numbers the checker needs."""
    return json.loads(_run_js_json(qapp, backend, """
      var s = window.ketcher.editor.struct();
      var ids = Array.from(s.atoms.keys());
      var out = {};
      s.atoms.forEach(function (a, id) {
        var bearings = [];
        s.bonds.forEach(function (b) {
          var other = null;
          if (b.begin === id) other = b.end;
          else if (b.end === id) other = b.begin;
          if (other === null) return;
          var o = s.atoms.get(other);
          if (!o) return;
          bearings.push(Math.atan2(o.pp.y - a.pp.y, o.pp.x - a.pp.x) * 180 / Math.PI);
        });
        out[ids.indexOf(id)] = {centre: [a.pp.x, a.pp.y], bonds: bearings,
                                label: a.label, implicitH: a.implicitH, charge: a.charge};
      });
      return JSON.stringify(out);
    """))


def _label_box(qapp, backend, text: str):
    if not text:
        return None
    measured = json.loads(_run_js_json(qapp, backend, """
      var o = window.ketcher.editor.render.options;
      var unit = o.microModeScale || o.bondLength || 40;
      var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('style', 'position:absolute;left:-9999px;top:0;width:200px;height:60px');
      document.body.appendChild(svg);
      var t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t.setAttribute('font-size', o.fontsz || 13);
      t.setAttribute('font-family', 'Arial');
      t.textContent = %s;
      svg.appendChild(t);
      var b = t.getBBox();
      document.body.removeChild(svg);
      return JSON.stringify({hw: b.width / 2 / unit, hh: b.height / 2 / unit});
    """ % json.dumps(text)))
    return measured


def _composed_label(atom: dict) -> str:
    if atom["label"] == "C" and not atom["charge"]:
        return ""
    text = atom["label"]
    if atom["implicitH"]:
        text += "H%d" % atom["implicitH"] if atom["implicitH"] > 1 else "H"
    if atom["charge"]:
        text += "+" if atom["charge"] > 0 else "-"
    return text


# --- the judge over what the page really drew --------------------------------


@pytest.mark.parametrize("case", list(FIXTURES), ids=list(FIXTURES))
def test_the_pages_placement_satisfies_every_rule(qapp, case):
    """The whole point of the split: the page places, Python judges.

    A failure here names the rule -- "a dot is inside the label box",
    "pairs 0 and 1 are 20 deg apart" -- rather than saying two
    implementations disagree, which would leave open which one was right.
    """
    smiles, atom_count = FIXTURES[case]
    backend, _ = _overlaid(qapp, smiles, atom_count)

    state = _state(qapp, backend)
    geometry = _atom_geometry(qapp, backend)
    assert state["placement"], f"{case}: nothing was drawn at all"

    for entry in state["placement"]:
        atom = geometry[str(entry["position"])]
        box = _label_box(qapp, backend, _composed_label(atom))
        label_box = (
            Box(
                atom["centre"][0] - box["hw"],
                atom["centre"][1] - box["hh"],
                atom["centre"][0] + box["hw"],
                atom["centre"][1] + box["hh"],
            )
            if box
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
        assert breaches == [], f"{case}, atom {entry['position']}: {breaches}"


def test_the_counts_reaching_the_canvas_are_the_chemistry_s(qapp):
    """Water draws two pairs on its oxygen and none anywhere else."""
    backend, _ = _overlaid(qapp, "O", 1)

    state = _state(qapp, backend)

    assert [(e["position"], e["pairs"]) for e in state["placement"]] == [(0, 2)]
    assert len(state["placement"][0]["dots"]) == 4


def test_an_atom_with_zero_pairs_draws_nothing_but_is_not_an_error(qapp):
    """The middle of the three states. An ammonium nitrogen has no lone
    pair, which is an ANSWER -- so no dots, and no refusal note."""
    backend, payload = _overlaid(qapp, "C[NH3+]", 2)

    state = _state(qapp, backend)

    assert payload["counts"] == {"0": 0, "1": 0}
    assert state["placement"] == []
    assert state["refused"] is False


def test_a_refused_analysis_draws_no_dots_and_shows_the_reason(qapp):
    """The third state, and the one silence would misreport as the
    second. Ferrocene is not "a molecule with no lone pairs"."""
    backend, payload = _overlaid(qapp, "[CH2]", 1)

    state = _state(qapp, backend)
    note = _run_js_json(qapp, backend, """
      var n = document.querySelector('.openchem-electrons .el-note');
      return n ? n.textContent : '<no layer>';
    """)

    assert payload["refused"] is True
    assert state["placement"] == []
    assert "unpaired" in note.lower(), note


def _slot_bearings(qapp, backend) -> dict:
    """Each atom's slot directions, relative to that atom. The quantity a
    viewport change must not touch -- the whole drawing obviously moves,
    so comparing pixels would prove nothing."""
    state = _state(qapp, backend)
    geometry = _atom_geometry(qapp, backend)
    out = {}
    for entry in state["placement"]:
        cx, cy = geometry[str(entry["position"])]["centre"]
        dots = entry["dots"]
        bearings = []
        for index in range(0, len(dots), 2):
            mx = (dots[index][0] + dots[index + 1][0]) / 2
            my = (dots[index][1] + dots[index + 1][1]) / 2
            bearings.append(round(math.degrees(math.atan2(my - cy, mx - cx)), 3))
        out[entry["position"]] = sorted(bearings)
    return out


@pytest.mark.parametrize(
    "case", ["water", "methanol", "dimethyl ether", "pyridine", "chloromethane"]
)
def test_a_viewport_change_cannot_move_a_slot(qapp, case):
    """**G8, and the answer is by construction rather than by tolerance.**

    Everything the overlay computes is in MODEL units: bond bearings, the
    label box, the slot radius. Ketcher's viewport transform is scale +
    translate with NO rotation, so a label box is axis-aligned in model
    space exactly as it is on screen, and a pan or a zoom changes nothing
    the placement reads. The layer's single <g> carries the whole
    viewport.

    Measured across zoom 1 -> 1.8 -> 0.55 -> 1: slot identity unchanged on
    every fixture. Compared as BEARINGS relative to each atom, never as
    pixels.
    """
    smiles, atom_count = FIXTURES[case]
    backend, _ = _overlaid(qapp, smiles, atom_count)
    before = _slot_bearings(qapp, backend)
    assert before, f"{case}: nothing was drawn, so there is nothing to compare"

    for zoom in (1.8, 0.55, 1.0):
        _run_js_json(qapp, backend, "window.ketcher.editor.zoom(%s); return 1;" % zoom)
        _wait_until(qapp, lambda: False, timeout_seconds=0.6)

    assert _slot_bearings(qapp, backend) == before


def test_the_placement_is_chemically_where_it_should_be(qapp):
    """Not just "legal" -- RIGHT, on cases a chemist would check first.

    The checker says a placement breaks no rule, which a placement can
    manage while still looking odd. These are the textbook answers:
    dimethyl ether's oxygen puts its two pairs perpendicular to the two
    C-O bonds, and pyridine's nitrogen points its single pair straight out
    of the ring.
    """
    backend, _ = _overlaid(qapp, "COC", 3)
    ether = _slot_bearings(qapp, backend)
    assert list(ether) == [1], ether
    first, second = ether[1]
    assert abs(abs(first - second) - 180.0) < 1e-6, ether

    backend, _ = _overlaid(qapp, "c1ccncc1", 6)
    pyridine = _slot_bearings(qapp, backend)
    (nitrogen,) = pyridine.values()
    assert len(nitrogen) == 1, pyridine
    geometry = _atom_geometry(qapp, backend)
    position = next(iter(pyridine))
    bonds = geometry[str(position)]["bonds"]
    # Pointing away from BOTH ring bonds, which is the only place it can
    # be right: a lone pair drawn into the ring is simply wrong.
    for bond in bonds:
        gap = abs((nitrogen[0] - bond + 180) % 360 - 180)
        assert gap > 90.0, (nitrogen, bonds)


def test_the_dots_follow_an_edit_onto_the_RIGHT_atoms(qapp):
    """The index trap, on the canvas.

    Python keys the payload by molfile position; Ketcher keys atoms by
    pool id, and the two diverge the moment anything is deleted. Two rings
    with the first erased leaves pool ids 6..11 against positions 0..5, so
    a payload applied without translating would decorate nothing at all --
    or, worse, the wrong atoms if the ids happened to stay in range.
    """
    from tests.test_ketcher_editor_backend import _draw_two_rings_and_erase_the_first

    backend = _ready_backend(qapp, shown=True)
    state = _draw_two_rings_and_erase_the_first(qapp, backend)
    assert state["atoms"] == [6, 7, 8, 9, 10, 11], state

    # Six carbons, and a fabricated payload that says atom 2 (the third by
    # MOLFILE POSITION) carries one pair. Pool id 8 is the atom it means.
    payload = {"counts": {"2": 1}, "refused": False, "reason": "", "mode": "pairs"}
    _run_js_json(qapp, backend, "window.openchemElectrons.set(%s); return 1;" % json.dumps(payload))
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)

    placement = _state(qapp, backend)["placement"]
    assert len(placement) == 1, placement
    assert placement[0]["position"] == 2

    centre = json.loads(_run_js_json(qapp, backend, """
      var a = window.ketcher.editor.struct().atoms.get(8);
      return JSON.stringify([a.pp.x, a.pp.y]);
    """))
    for dot in placement[0]["dots"]:
        assert math.dist(dot, centre) < 0.6, (dot, centre)


def test_the_index_map_is_INSERTION_ORDER_and_a_sorted_one_would_be_wrong(qapp):
    """**The test above is DEGENERATE against the mutation that matters.**

    Deleting the first of two rings leaves pool ids 6..11 -- which are
    already ascending, so sorting them changes nothing and a sorted
    implementation passes. Measured: a mutation replacing the map with
    `.sort()` survived every other test in this file.

    Undo is what makes the two differ. Ketcher re-inserts a deleted atom
    under its ORIGINAL id at the END of the pool, so deleting atom 0 of
    ethanol and undoing gives insertion order [1, 2, 0]:

        molfile position   0        1        2
        pool id            1        2        0
        element            C        O        C
        sorted would give  0        1        2      <- a CARBON at 1

    So a payload naming position 1 -- the oxygen -- decorates the oxygen
    under insertion order and a carbon under sorting. `molfilePosition()`
    documents the same trap for the reverse direction; this is the
    forward one.
    """
    backend = _ready_backend(qapp, shown=True)
    backend.load_molblock(_molblock("CCO"))
    assert _wait_until(
        qapp,
        lambda: _run_js_json(qapp, backend, "return window.ketcher.editor.struct().atoms.size;")
        == 3,
        timeout_seconds=25,
    )
    _run_js_json(qapp, backend, """
      window.ketcher.editor.selection({atoms: [0]});
      var el = document.querySelector('.Ketcher-root') || document.body;
      ['keydown','keyup'].forEach(function (t) {
        el.dispatchEvent(new KeyboardEvent(t, {key:'Delete', code:'Delete',
          bubbles:true, cancelable:true, keyCode:46, which:46}));
      });
      return 1;
    """)
    _wait_until(qapp, lambda: False, timeout_seconds=1.2)
    _run_js_json(qapp, backend, "window.ketcher.editor.undo(); return 1;")
    _wait_until(qapp, lambda: False, timeout_seconds=1.5)

    # **ASSERT THE SETUP.** If undo ever stops re-inserting at the end,
    # the pool is dense again and this test would pass while testing
    # nothing at all.
    order = json.loads(_run_js_json(qapp, backend, """
      var out = [];
      window.ketcher.editor.struct().atoms.forEach(function (a, id) {
        out.push([id, a.label]);
      });
      return JSON.stringify(out);
    """))
    assert order == [[1, "C"], [2, "O"], [0, "C"]], order

    payload = {"counts": {"1": 2}, "refused": False, "reason": "", "mode": "pairs"}
    _run_js_json(qapp, backend, "window.openchemElectrons.set(%s); return 1;" % json.dumps(payload))
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)

    placement = _state(qapp, backend)["placement"]
    assert len(placement) == 1, placement
    oxygen = json.loads(_run_js_json(qapp, backend, """
      var a = window.ketcher.editor.struct().atoms.get(2);
      return JSON.stringify([a.pp.x, a.pp.y, a.label]);
    """))
    assert oxygen[2] == "O"
    for dot in placement[0]["dots"]:
        assert math.dist(dot, oxygen[:2]) < 0.6, (dot, oxygen)


# --- the ownership invariant --------------------------------------------------


def test_the_overlay_never_touches_the_molecular_graph(qapp):
    """Zero `change` events, unchanged history, byte-identical molfile --
    the same three assertions the rotation preview makes, for the same
    reason: an annotation that edits the molecule is not an annotation."""
    from tests.test_ketcher_editor_backend import _get_molblock_sync

    backend = _ready_backend(qapp, shown=True)
    backend.load_molblock(_molblock("CO"))
    assert _wait_until(
        qapp,
        lambda: _run_js_json(qapp, backend, "return window.ketcher.editor.struct().atoms.size;")
        == 2,
        timeout_seconds=25,
    )
    # Let the load settle before reading: asked immediately, `get_molblock`
    # comes back None while Ketcher is still laying the structure out, and
    # a None baseline would make this test pass for the wrong reason.
    _wait_until(qapp, lambda: False, timeout_seconds=1.5)
    before = _get_molblock_sync(qapp, backend)
    assert before, "no baseline molfile, so the comparison below is vacuous"
    _run_js_json(qapp, backend, """
      window.__changes = 0;
      window.ketcher.editor.subscribe('change', function () { window.__changes++; });
      window.__history = JSON.stringify(window.ketcher.editor.historySize());
      return 1;
    """)

    payload = build(Chem.MolFromSmiles("CO")).to_payload()
    payload["mode"] = "pairs"
    _run_js_json(qapp, backend, "window.openchemElectrons.set(%s); return 1;" % json.dumps(payload))
    _wait_until(qapp, lambda: False, timeout_seconds=1.2)

    after = _get_molblock_sync(qapp, backend)
    state = json.loads(_run_js_json(qapp, backend, """
      return JSON.stringify({changes: window.__changes, before: window.__history,
                             after: JSON.stringify(window.ketcher.editor.historySize())});
    """))

    assert after == before
    assert state["changes"] == 0, state
    assert state["before"] == state["after"], state


def test_the_layer_ignores_the_pointer(qapp):
    """It sits on top of the canvas, so a dot must never eat a click
    meant for the atom underneath it."""
    backend, _ = _overlaid(qapp, "O", 1)

    style = _run_js_json(qapp, backend, """
      var l = document.querySelector('.openchem-electrons');
      return getComputedStyle(l).pointerEvents;
    """)

    assert style == "none"


def test_toggling_a_hundred_times_leaves_exactly_one_layer(qapp):
    """A layer per toggle is how a DOM quietly accumulates a hundred of
    them -- and the rotation overlay in this same file already leaked a
    listener pair per entry, invisible because the leak was inert."""
    backend, payload = _overlaid(qapp, "CO", 2)
    off = json.dumps(None)
    on = json.dumps(payload)

    _run_js_json(qapp, backend, """
      for (var i = 0; i < 100; i++) {
        window.openchemElectrons.set(%s);
        window.openchemElectrons.set(%s);
      }
      return 1;
    """ % (off, on))
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)

    counted = json.loads(_run_js_json(qapp, backend, """
      var layers = document.querySelectorAll('.openchem-electrons');
      var dots = document.querySelectorAll('.openchem-electrons circle');
      return JSON.stringify({layers: layers.length, dots: dots.length});
    """))

    assert counted["layers"] == 1, counted
    # Methanol: one oxygen with two pairs, so four dots -- not 400.
    assert counted["dots"] == 4, counted
