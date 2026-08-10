"""Does Ketcher hold 3D coordinates, and hold them through an edit?

**This is a GATE, not a feature test.** "Use in 2D Editor" is meant to hand
the 2D canvas the conformer you are looking at, oriented the way you have it
rotated -- a projection of a real 3D geometry, the way MarvinSketch draws
buckminsterfullerene in perspective inside a 2D editor. That is only
reachable if the molblock's own coordinates survive the round trip through
Ketcher.

**The third question is the one that matters**, and the reason it matters is
a compounding one. `main.jsx` forwards every canvas change as
`structureEdited(ketcher.getMolfile())`, which becomes an
`EditStructureCommand` -- and that command clears the conformer set:

    adopt a 3D structure -> click anything -> structureEdited fires
      -> molblock flattened to z = 0  AND  molecule.conformers = []

So if Ketcher round-trips to 2D, one click destroys both the adopted view and
the geometry that produced it. The answer decides whether an adopted
structure can be an ordinary editable structure at all; it must not be
guessed at.

These tests PRINT their measurements as well as asserting, because the
numbers are what the design decision rests on.
"""

from __future__ import annotations

import math

from rdkit import Chem
from rdkit.Chem import AllChem

from tests.test_ketcher_editor_backend import (
    _get_molblock_sync,
    _ready_backend,
    _run_js_json,
    _wait_until,
)

#: Deliberately non-planar and rigid, so "did z survive" has a loud answer.
#: A chair cyclohexane's carbons sit at +/-0.25 A off the mean plane.
CYCLOHEXANE = "C1CCCCC1"

#: The molecule the whole feature was reported broken on -- a
#: benzobicyclo[2.2.2]octane, whose bridge is the part a projection has to
#: show and a flat depiction cannot.
REPORTED = "COc1cc(C[C@@H](C)N)c2c(c1OC)C1CCC2CC1"


def _embedded_molblock(smiles: str, seed: int = 0xC0FFEE) -> str:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    AllChem.EmbedMolecule(mol, params)
    AllChem.MMFFOptimizeMolecule(mol)
    return Chem.MolToMolBlock(Chem.RemoveHs(mol))


def _coords(molblock: str) -> list[tuple[float, float, float]]:
    """Every atom's x, y, z, from either a V2000 or a V3000 molblock.

    Parsed through RDKit rather than by slicing columns, because Ketcher
    writes V3000 -- measured, a probe that read line 4 as the counts line
    reported "0 atoms" against a perfectly good structure.
    """
    mol = Chem.MolFromMolBlock(molblock, removeHs=False, sanitize=False)
    assert mol is not None, "the molblock did not parse"
    conformer = mol.GetConformer()
    return [
        (p.x, p.y, p.z)
        for p in (conformer.GetAtomPosition(i) for i in range(mol.GetNumAtoms()))
    ]


def _z_spread(coords) -> float:
    zs = [z for _x, _y, z in coords]
    return max(zs) - min(zs)


def _round_tripped(qapp, backend, molblock: str) -> str:
    """What Ketcher gives back -- through `get_molblock`, which is the exact
    call `structureEdited` makes, so this is what an edit would send.

    Polled rather than requested once: `load_molblock` is asynchronous, so a
    single request issued straight after it can be answered from the canvas
    as it was BEFORE the load. Asking repeatedly until the structure has the
    expected atom count is what the existing render-option test does.
    """
    backend.load_molblock(molblock)
    expected = len(_coords(molblock))
    got: dict[str, str] = {}

    def arrived() -> bool:
        current = _get_molblock_sync(qapp, backend) or ""
        if current.strip() and len(_coords(current)) == expected:
            got["value"] = current
            return True
        return False

    assert _wait_until(qapp, arrived, timeout_seconds=25), "Ketcher never returned the structure"
    return got["value"]


# --- the gate ----------------------------------------------------------------


def test_ketcher_reports_whether_it_keeps_z(qapp):
    """GATE C, and the decisive one.

    Load a genuinely non-planar structure and read back exactly what an
    edit would send. Either z survives -- and an adopted 3D structure can
    be edited like any other -- or it does not, and the feature has to keep
    the geometry somewhere Ketcher cannot reach.
    """
    backend = _ready_backend(qapp)
    original = _embedded_molblock(CYCLOHEXANE)
    before = _coords(original)
    assert _z_spread(before) > 0.3, "the fixture is flat; it cannot answer this"

    after = _coords(_round_tripped(qapp, backend, original))

    print(f"\n  atoms in  {len(before)}   out {len(after)}")
    print(f"  z spread in  {_z_spread(before):.4f} A")
    print(f"  z spread out {_z_spread(after):.4f} A")
    print(f"  first three z out: {[round(z, 4) for _x, _y, z in after[:3]]}")

    assert _z_spread(after) > 0.3, (
        "KETCHER FLATTENS Z. An adopted 3D structure cannot be an ordinary "
        "editable structure -- see this module's docstring for what that costs."
    )


def test_ketcher_keeps_the_geometry_undistorted_not_merely_non_flat(qapp):
    """A NON-ZERO Z IS NOT THE SAME AS AN INTACT GEOMETRY.

    The gate above only proves z is not zeroed. It would pass just as
    happily against a Ketcher that scaled x and y by one factor and z by
    another -- which flattens or stretches the molecule along one axis,
    changes every bond length and angle, and is the quiet kind of wrong: the
    structure still looks like itself.

    It looked like a real risk before it was measured: z spread went
    0.9832 -> 0.6828, a factor of 0.695, while another molecule's x and y
    scaled by 0.7993. **Both numbers are right and there is no anisotropy** --
    the 0.7993 belongs to a DIFFERENT molecule, and Ketcher normalises to its
    own bond length per structure, so an aromatic molecule and cyclohexane
    get different factors. 0.9832 x 0.6943 = 0.6826, which is the 0.6828
    observed. Recorded because comparing two scale factors across two
    molecules is an easy way to invent a bug that is not there.

    The question that actually settles it, and the one asserted: are all
    pairwise 3D distances related by ONE ratio?
    """
    backend = _ready_backend(qapp)
    original = _embedded_molblock(CYCLOHEXANE)
    before = _coords(original)

    after = _coords(_round_tripped(qapp, backend, original))

    ratios_3d = []
    ratios_xy = []
    for i in range(len(before)):
        for j in range(i + 1, len(before)):
            d3_before = math.dist(before[i], before[j])
            if d3_before > 0.1:
                ratios_3d.append(math.dist(after[i], after[j]) / d3_before)
            d2_before = math.dist(before[i][:2], before[j][:2])
            if d2_before > 0.1:
                ratios_xy.append(math.dist(after[i][:2], after[j][:2]) / d2_before)

    spread_3d = max(ratios_3d) / min(ratios_3d)
    print(f"\n  3D distance ratio: {min(ratios_3d):.4f} .. {max(ratios_3d):.4f}  "
          f"spread {spread_3d:.4f}")
    print(f"  xy distance ratio: {min(ratios_xy):.4f} .. {max(ratios_xy):.4f}")

    assert spread_3d < 1.02, (
        f"Ketcher distorted the geometry: 3D distances scale by "
        f"{min(ratios_3d):.4f}..{max(ratios_3d):.4f}, so this is not a "
        f"similarity transform and bond lengths and angles have changed."
    )


def test_ketcher_does_not_relayout_the_coordinates(qapp):
    """GATE A. The returned x,y must be the SAME arrangement, not a fresh one.

    Stated as a similarity transform rather than as equality, because
    Ketcher scales a molfile to its own bond length and re-centres it --
    both of which are fine. What is not fine is a per-atom re-layout.

    Checked by ratio of pairwise distances: one uniform scale for the whole
    structure means every ratio is the same number. A re-layout moves atoms
    relative to each other and the ratios scatter.
    """
    backend = _ready_backend(qapp)
    original = _embedded_molblock(REPORTED)
    before = _coords(original)

    after = _coords(_round_tripped(qapp, backend, original))
    assert len(after) == len(before), f"atom count changed: {len(before)} -> {len(after)}"

    ratios = []
    for i in range(len(before)):
        for j in range(i + 1, len(before)):
            d_before = math.dist(before[i][:2], before[j][:2])
            d_after = math.dist(after[i][:2], after[j][:2])
            if d_before > 0.1:
                ratios.append(d_after / d_before)

    spread = max(ratios) / min(ratios)
    print(f"\n  pairwise xy distance ratio: {min(ratios):.4f} .. {max(ratios):.4f}")
    print(f"  spread (1.00 = one uniform scale): {spread:.4f}")

    assert spread < 1.05, (
        "Ketcher re-laid out the structure rather than scaling it, so no "
        "projection can survive the round trip."
    )


def test_an_actual_edit_does_not_flatten_the_canvas(qapp):
    """GATE C in its strict form.

    The round trip above proves `getMolfile()` reports z. It does not prove
    an EDIT keeps it -- the canvas could hold 3D until the moment something
    is changed and flatten then, which is precisely the moment
    `structureEdited` fires and `EditStructureCommand` writes the result
    into the model.

    The edit goes through Ketcher's own Delete hotkey rather than by poking
    the pool, so the state under test is one the real editor produces.

    **The setup is asserted**, because if the Delete stopped working the
    structure would be unchanged and this would pass while testing nothing --
    the same trap the pool-id test in `test_ketcher_editor_backend.py`
    already documents.
    """
    backend = _ready_backend(qapp)
    original = _embedded_molblock(CYCLOHEXANE)
    before = _coords(_round_tripped(qapp, backend, original))
    assert _z_spread(before) > 0.3

    _run_js_json(qapp, backend, """
      var e = window.ketcher.editor, s = e.struct();
      e.selection({atoms: Array.from(s.atoms.keys()).slice(0, 1)});
      return 1;
    """)
    _wait_until(qapp, lambda: False, timeout_seconds=0.5)
    _run_js_json(qapp, backend, """
      var el = document.querySelector('.Ketcher-root') || document.body;
      ['keydown','keyup'].forEach(function(t){
        el.dispatchEvent(new KeyboardEvent(t, {key:'Delete', code:'Delete',
          bubbles:true, cancelable:true, keyCode:46, which:46})); });
      return 1;
    """)
    _wait_until(qapp, lambda: False, timeout_seconds=2.0)

    edited = _get_molblock_sync(qapp, backend, timeout_seconds=10) or ""
    after = _coords(edited)

    print(f"\n  atoms before edit {len(before)}  after {len(after)}")
    print(f"  z spread after the edit: {_z_spread(after):.4f} A")

    assert len(after) == len(before) - 1, (
        "the Delete did not remove an atom, so this test exercised nothing"
    )
    assert _z_spread(after) > 0.3, (
        "AN EDIT FLATTENS THE CANVAS. Adopting a 3D structure and then "
        "touching it would destroy the geometry and clear the conformers."
    )
