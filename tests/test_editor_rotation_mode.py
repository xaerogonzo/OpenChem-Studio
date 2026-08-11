"""Turning a structure in the 2D editor, against the real Ketcher bundle.

*"we need the rotation rulers and live angle readouts too inside the 2d
editor definitely"*, against a MarvinSketch screenshot.

**The engineering was never the maths.** Getting a molecule to move on
screen is easy; keeping Ketcher's model coherent is the part that can go
wrong, and the gate measured all of it before any of this was written:

    an atom's `pp` really carries a z, populated from a 3D molfile
    mutating positions + render.update fires NO `change` event
    Ketcher's own undo history is unchanged by the preview
    selection survives, and atom 3 is still atom 3
    getMolfile afterwards reports the NEW coordinates
    ~32 ms per redraw at 20 atoms

Those are asserted here rather than left in a scratch probe, because each
is a way for the preview to look right while the model rots underneath.
"""

from __future__ import annotations

import json
import math

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from tests.test_ketcher_editor_backend import _ready_backend, _run_js_json, _wait_until

#: Non-planar and rigid, so a rotation is unmistakable in the coordinates.
CYCLOHEXANE = "C1CCCCC1"


def _embedded(smiles: str) -> str:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    AllChem.MMFFOptimizeMolecule(mol)
    return Chem.MolToMolBlock(Chem.RemoveHs(mol))


def _rotating_backend(qapp):
    backend = _ready_backend(qapp, shown=True)
    backend.load_molblock(_embedded(CYCLOHEXANE))
    assert _wait_until(
        qapp,
        lambda: _run_js_json(qapp, backend, "return window.ketcher.editor.struct().atoms.size;")
        == 6,
        timeout_seconds=20,
    )
    return backend


def _positions(qapp, backend):
    return _run_js_json(qapp, backend, """
      var s = window.ketcher.editor.struct(), out = [];
      s.atoms.forEach(function(a){ out.push([a.pp.x, a.pp.y, a.pp.z || 0]); });
      return out;
    """)


def _drag(qapp, backend, dx: int, dy: int) -> None:
    """A real drag over the overlay: down, move, up."""
    _run_js_json(qapp, backend, """
      var o = document.querySelector('.openchem-rotate');
      if (!o) return {__error: 'no overlay'};
      function at(type, target, x, y) {
        target.dispatchEvent(new MouseEvent(type, {clientX: x, clientY: y, bubbles: true}));
      }
      at('mousedown', o, 200, 200);
      at('mousemove', window, %d, %d);
      at('mouseup', window, %d, %d);
      return 1;
    """ % (200 + dx, 200 + dy, 200 + dx, 200 + dy))
    _wait_until(qapp, lambda: False, timeout_seconds=1.5)


# --- the mode ----------------------------------------------------------------


def test_entering_the_mode_changes_nothing(qapp):
    """**A mode you tried out of curiosity must be free.** Entering
    snapshots the geometry and rotates a copy; the structure is untouched
    until a drag happens."""
    backend = _rotating_backend(qapp)
    before = _positions(qapp, backend)

    _run_js_json(qapp, backend, "window.openchemRotation.enter(); return 1;")
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)

    assert _positions(qapp, backend) == before


def test_the_overlay_shows_the_mode_and_a_live_readout(qapp):
    """It steals the drag gesture, so the user must never be in doubt
    which mode they are in. Rulers, a banner and the angles."""
    backend = _rotating_backend(qapp)
    _run_js_json(qapp, backend, "window.openchemRotation.enter(); return 1;")
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)

    seen = _run_js_json(qapp, backend, """
      var o = document.querySelector('.openchem-rotate');
      return {
        banner: !!o.querySelector('.rot-banner'),
        readout: o.querySelector('.rot-readout').textContent,
        ticks: o.querySelectorAll('.rot-tick').length
      };
    """)

    assert seen["banner"]
    assert "0" in seen["readout"]
    assert seen["ticks"] >= 20, seen


def test_a_drag_rotates_the_structure_rigidly(qapp):
    """The coordinates move and every interatomic distance survives --
    which is what makes it a rotation rather than a distortion."""
    backend = _rotating_backend(qapp)
    _run_js_json(qapp, backend, "window.openchemRotation.enter(); return 1;")
    before = _positions(qapp, backend)

    _drag(qapp, backend, dx=120, dy=0)
    after = _positions(qapp, backend)

    assert after != before, "the drag did not move anything"
    for i in range(len(before)):
        for j in range(i + 1, len(before)):
            assert math.dist(after[i], after[j]) == pytest.approx(
                math.dist(before[i], before[j]), abs=1e-6
            )


def test_the_readout_matches_the_drag(qapp):
    """A readout fed by its own input is the classic circular guard, so
    this checks the angle against the DRAG that produced it: half a degree
    per pixel, horizontal drag on the y axis."""
    backend = _rotating_backend(qapp)
    _run_js_json(qapp, backend, "window.openchemRotation.enter(); return 1;")

    _drag(qapp, backend, dx=120, dy=-40)

    angles = json.loads(_run_js_json(qapp, backend, "return window.openchemRotation.angles();"))
    assert angles["y"] == pytest.approx(60.0, abs=0.5)
    assert angles["x"] == pytest.approx(-20.0, abs=0.5)


def test_re_entering_the_mode_reads_zero(qapp):
    """The reference is where you entered, not where the molecule happens
    to sit -- otherwise the readout drifts a little further every time."""
    backend = _rotating_backend(qapp)
    _run_js_json(qapp, backend, "window.openchemRotation.enter(); return 1;")
    _drag(qapp, backend, dx=80, dy=40)

    _run_js_json(qapp, backend, "window.openchemRotation.leave(false); return 1;")
    _run_js_json(qapp, backend, "window.openchemRotation.enter(); return 1;")

    angles = json.loads(_run_js_json(qapp, backend, "return window.openchemRotation.angles();"))
    assert angles == {"x": 0, "y": 0}


def test_leaving_with_restore_puts_the_geometry_back(qapp):
    """Cancelling is zero undo steps AND the entry geometry -- the preview
    was never an edit, so there is nothing to undo and nothing to keep."""
    backend = _rotating_backend(qapp)
    before = _positions(qapp, backend)
    _run_js_json(qapp, backend, "window.openchemRotation.enter(); return 1;")
    _drag(qapp, backend, dx=100, dy=60)
    assert _positions(qapp, backend) != before

    _run_js_json(qapp, backend, "window.openchemRotation.leave(true); return 1;")
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)

    after = _positions(qapp, backend)
    for original, restored in zip(before, after):
        assert restored == pytest.approx(original, abs=1e-6)


def test_the_overlay_is_gone_after_leaving(qapp):
    """Or a drag afterwards would still rotate instead of drawing."""
    backend = _rotating_backend(qapp)
    _run_js_json(qapp, backend, "window.openchemRotation.enter(); return 1;")
    _run_js_json(qapp, backend, "window.openchemRotation.leave(true); return 1;")

    assert _run_js_json(
        qapp, backend, "return document.querySelectorAll('.openchem-rotate').length;"
    ) == 0


# --- Ketcher's model stays coherent, which is the whole engineering ----------


def test_the_preview_fires_no_change_event_and_grows_no_history(qapp):
    """**SIXTY FRAMES OF A DRAG MUST COST NOTHING.**

    A `change` per frame would push a command per frame through
    `structureEdited`, and Ketcher recording its own history would make
    its undo stack disagree with the application's. Both are asserted,
    because suppressing Python's response to `change` is not the same as
    Ketcher declining to record anything.
    """
    backend = _rotating_backend(qapp)
    _run_js_json(qapp, backend, """
      window.__changes = 0;
      window.ketcher.editor.subscribe('change', function(){ window.__changes++; });
      window.__historyBefore = JSON.stringify(window.ketcher.editor.historySize());
      window.openchemRotation.enter();
      return 1;
    """)

    _drag(qapp, backend, dx=60, dy=30)
    _drag(qapp, backend, dx=-90, dy=15)

    state = _run_js_json(qapp, backend, """
      return {changes: window.__changes,
              before: window.__historyBefore,
              after: JSON.stringify(window.ketcher.editor.historySize())};
    """)
    assert state["changes"] == 0, state
    assert state["before"] == state["after"], state


def test_the_selection_survives_a_rotation_and_still_means_the_same_atom(qapp):
    """Coordinate mutation is where selection bugs live, and this project
    has already been bitten by a Ketcher index space -- a pool id is not a
    molfile position."""
    backend = _rotating_backend(qapp)
    _run_js_json(qapp, backend, "window.ketcher.editor.selection({atoms: [3]}); return 1;")
    _run_js_json(qapp, backend, "window.openchemRotation.enter(); return 1;")

    _drag(qapp, backend, dx=70, dy=-25)

    assert _run_js_json(
        qapp, backend, "return JSON.stringify(window.ketcher.editor.selection());"
    ) == '{"atoms":[3]}'


def test_a_round_trip_through_ketcher_RESCALES_and_the_commit_path_puts_it_back(qapp):
    """**KETCHER WORKS IN ITS OWN UNITS, AND `getMolfile` WRITES THEM OUT.**

    Asked because `test_getMolfile_reports_the_rotated_coordinates`
    deliberately compares SHAPE up to one factor -- which leaves open
    whether molblock in -> molblock out is scale-neutral. It is not.
    Measured here: cyclohexane goes in with C-C at 1.5301 A and comes back
    at 1.0702, a uniform x0.699 on every bond.

    Harmless for as long as the editor only ever held a LAYOUT, which is
    why nothing noticed. The moment it holds a GEOMETRY it is a 30% error
    in every bond length -- and it is invisible to atom order, to the CIP
    labels and to the oriented volume, because a uniform scale changes
    none of them. Only a length or an energy sees one.

    Three assertions, because each answers a different question: that it
    really is UNIFORM (a per-atom distortion would need a different fix
    entirely), what the FACTOR is (`tests/test_rotation_transaction.py`
    stages its molblocks at it, so a Ketcher that changes it must fail
    here rather than there), and that `ChemistryEngine.rescale_like`
    -- the production repair -- puts it back.
    """
    from openchem.chem.engine import ChemistryEngine
    from tests.test_ketcher_editor_backend import _get_molblock_sync

    backend = _rotating_backend(qapp)
    loaded = _embedded(CYCLOHEXANE)
    _run_js_json(qapp, backend, "window.openchemRotation.enter(); return 1;")
    _drag(qapp, backend, dx=110, dy=45)
    returned = _get_molblock_sync(qapp, backend)

    def lengths(molblock: str) -> list[float]:
        mol = Chem.MolFromMolBlock(molblock, removeHs=False, sanitize=False)
        conformer = mol.GetConformer()
        return [
            math.dist(
                tuple(conformer.GetAtomPosition(bond.GetBeginAtomIdx())),
                tuple(conformer.GetAtomPosition(bond.GetEndAtomIdx())),
            )
            for bond in mol.GetBonds()
        ]

    before, after = lengths(loaded), lengths(returned)
    factors = [b / a for a, b in zip(before, after)]
    assert max(factors) - min(factors) < 1e-3, factors
    assert sum(factors) / len(factors) == pytest.approx(0.6994, abs=1e-3), factors

    repaired, residual = ChemistryEngine().rescale_like(returned, loaded)
    assert residual < 0.01, residual
    assert lengths(repaired) == pytest.approx(before, abs=0.01)


def test_getMolfile_reports_the_rotated_coordinates(qapp):
    """The opposite failure to the one above: a canvas that visually moves
    while Ketcher's model still thinks the atoms are where they were.
    Everything downstream reads this molfile."""
    from tests.test_ketcher_editor_backend import _get_molblock_sync

    backend = _rotating_backend(qapp)
    _run_js_json(qapp, backend, "window.openchemRotation.enter(); return 1;")
    before = _get_molblock_sync(qapp, backend)
    _drag(qapp, backend, dx=140, dy=60)

    after = _get_molblock_sync(qapp, backend)

    assert after and after != before
    positions = _positions(qapp, backend)
    mol = Chem.MolFromMolBlock(after, removeHs=False, sanitize=False)
    conformer = mol.GetConformer()
    # The molfile is Ketcher's own scaled copy of the struct, so the
    # comparison is on SHAPE: same pairwise distances, up to one factor.
    ratios = [
        math.dist(
            (conformer.GetAtomPosition(i).x, conformer.GetAtomPosition(i).y,
             conformer.GetAtomPosition(i).z),
            (conformer.GetAtomPosition(j).x, conformer.GetAtomPosition(j).y,
             conformer.GetAtomPosition(j).z),
        )
        / math.dist(positions[i], positions[j])
        for i in range(len(positions))
        for j in range(i + 1, len(positions))
    ]
    assert max(ratios) / min(ratios) == pytest.approx(1.0, abs=0.01)
