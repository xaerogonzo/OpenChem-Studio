"""The four physical checks on a docked pose, on poses built atom by atom so each distance is known."""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Geometry import Point3D

from openchem.chem import pose_plausibility as pp
from openchem.chem.pose_analysis import ReceptorAtom
from openchem.domain.docking import DockingBox


def _chain(coords: list[tuple[float, float, float]]) -> str:
    """A bonded chain of carbons at exactly these positions, as a molblock."""
    mol = Chem.RWMol()
    for _ in coords:
        mol.AddAtom(Chem.Atom(6))
    for i in range(len(coords) - 1):
        mol.AddBond(i, i + 1, Chem.BondType.SINGLE)
    conformer = Chem.Conformer(len(coords))
    for i, (x, y, z) in enumerate(coords):
        conformer.SetAtomPosition(i, Point3D(x, y, z))
    mol.AddConformer(conformer)
    return Chem.MolToMolBlock(mol)


#: Six carbons in a zig-zag, 1.5 A bonds: nothing close that is not bonded.
_EXTENDED = [(1.25 * i, 0.8 * (i % 2), 0.0) for i in range(6)]
#: The same chain curled so atom 0 sits 1.2 A from atom 5, five bonds away.
_FOLDED = [(0.0, 0.0, 0.0), (1.5, 0.0, 0.0), (2.2, 1.3, 0.0), (1.5, 2.5, 0.0), (0.5, 2.0, 0.0), (0.0, 1.2, 0.0)]
_BOX = DockingBox(center=(2.0, 0.0, 0.0), size=(20.0, 20.0, 20.0))


def _receptor(*positions: tuple[float, float, float], element: str = "C") -> list[ReceptorAtom]:
    return [ReceptorAtom(element, p, "LEU", 10 + i) for i, p in enumerate(positions)]


def _check(molblock: str, receptor, box=_BOX) -> dict:
    return pp.check_pose(molblock, receptor, box)


def _passed(result: dict, check_id: str):
    return result["checks"][check_id]["passed"]


def test_a_clean_extended_pose_passes_every_check():
    result = _check(_chain(_EXTENDED), _receptor((2.5, 4.0, 0.0)))
    assert result["failed"] == []
    assert all(_passed(result, c) is True for c in pp.CHECK_LABELS)


def test_a_receptor_atom_inside_the_clash_limit_fails_and_one_outside_it_does_not():
    # C...C vdW sum is 3.40 A, so the limit is 2.55 A.
    assert "receptor_clash" in _check(_chain(_EXTENDED), _receptor((2.5, 2.4, 0.0)))["failed"]
    assert _passed(_check(_chain(_EXTENDED), _receptor((2.5, -2.7, 0.0))), "receptor_clash") is True


def test_a_receptor_hydrogen_is_not_a_clash_partner():
    # A hydrogen sitting on the chain is ignored; the one heavy atom, 4 A away, is what is judged.
    receptor = _receptor((2.5, 1.0, 0.0), element="H") + _receptor((2.5, -4.0, 0.0))
    assert _passed(_check(_chain(_EXTENDED), receptor), "receptor_clash") is True


def test_a_chain_folded_back_through_itself_fails_the_internal_check():
    assert "internal_clash" in _check(_chain(_FOLDED), _receptor((0.5, 4.0, 0.0)))["failed"]


def test_close_atoms_four_bonds_apart_are_geometry_not_a_clash():
    four_apart = [(0.0, 0.0, 0.0), (1.5, 0.0, 0.0), (2.2, 1.3, 0.0), (1.5, 2.5, 0.0), (0.3, 2.0, 0.0)]
    assert _passed(_check(_chain(four_apart), _receptor((0.5, 4.0, 0.0))), "internal_clash") is True


def test_two_unbonded_fragments_are_not_one_molecule_folded():
    mol = Chem.RWMol()
    mol.AddAtom(Chem.Atom(11))
    mol.AddAtom(Chem.Atom(17))
    conformer = Chem.Conformer(2)
    conformer.SetAtomPosition(0, Point3D(0, 0, 0))
    conformer.SetAtomPosition(1, Point3D(1.0, 0, 0))
    mol.AddConformer(conformer)
    result = _check(Chem.MolToMolBlock(mol), _receptor((0.0, 3.5, 0.0)))
    assert _passed(result, "internal_clash") is True


def test_a_pose_past_the_box_edge_fails_unless_within_the_slack():
    far = [(x + 30.0, y, z) for x, y, z in _EXTENDED]
    assert "in_search_box" in _check(_chain(far), _receptor((31.0, 4.0, 0.0)))["failed"]
    edge = [(x + 11.5, y, z) for x, y, z in _EXTENDED]  # furthest atom 0.5 A beyond the face at x = 12
    assert _passed(_check(_chain([(12.5, 0.0, 0.0), (12.0, 1.4, 0.0)]), _receptor((12.0, 4.0, 0.0))), "in_search_box") is True
    assert edge  # keep the literal above documented


def test_a_pose_far_from_every_receptor_atom_touches_nothing():
    result = _check(_chain(_EXTENDED), _receptor((2.5, 30.0, 0.0)))
    assert "touches_receptor" in result["failed"]


def test_checks_that_cannot_be_made_are_none_and_never_listed_as_failed():
    result = _check(_chain(_EXTENDED), [], box=None)
    assert _passed(result, "receptor_clash") is None
    assert _passed(result, "touches_receptor") is None
    assert _passed(result, "in_search_box") is None
    assert result["failed"] == []


def test_an_unreadable_pose_checks_nothing_rather_than_passing():
    result = _check("not a molblock", _receptor((0.0, 0.0, 0.0)))
    assert {c["passed"] for c in result["checks"].values()} == {None}
    assert result["failed"] == []


def test_a_bond_to_a_receptor_metal_is_not_a_clash():
    mol = Chem.RWMol()
    mol.AddAtom(Chem.Atom(7))
    conformer = Chem.Conformer(1)
    conformer.SetAtomPosition(0, Point3D(0, 0, 0))
    mol.AddConformer(conformer)
    zinc = [ReceptorAtom("ZN", (2.0, 0.0, 0.0), "ZN", 300)]
    assert _passed(_check(Chem.MolToMolBlock(mol), zinc), "receptor_clash") is True


def test_the_summary_says_what_a_pass_is_worth_and_names_the_failing_poses():
    good = {pp.METADATA_KEY: {"checks": {}, "failed": []}}
    bad = {pp.METADATA_KEY: {"checks": {}, "failed": ["receptor_clash", "in_search_box"]}}
    assert pp.summarize([{}, {}]) == ""
    passed = pp.summarize([good, good])
    assert "all 2 pose(s) passed" in passed and "does not mean the pose is where" in passed
    failed = pp.summarize([good, bad])
    assert "1 of 2 pose(s) failed" in failed
    assert "pose 2 clashes with the receptor, leaves the search box" in failed


def test_a_summary_lists_three_failures_and_counts_the_rest():
    bad = {pp.METADATA_KEY: {"checks": {}, "failed": ["internal_clash"]}}
    text = pp.summarize([bad] * 5)
    assert "5 of 5" in text and "(and 2 more)" in text


def test_a_row_tooltip_lists_every_check_with_its_outcome():
    metadata = {
        pp.METADATA_KEY: {
            "checks": {
                "receptor_clash": {"passed": False, "detail": "2 pairs"},
                "internal_clash": {"passed": True, "detail": "fine"},
                "in_search_box": {"passed": None, "detail": "box unknown"},
            },
            "failed": ["receptor_clash"],
        }
    }
    tip = pp.pose_tooltip(metadata)
    assert "clashes with the receptor: FAILED -- 2 pairs" in tip
    assert "folds through itself: passed" in tip
    assert "leaves the search box: not checked" in tip
    assert pp.pose_tooltip({}) == ""


@pytest.mark.parametrize("junk", [None, 5, {"checks": {}}, {"failed": "x"}])
def test_a_metadata_value_that_is_not_ours_reads_as_never_checked(junk):
    assert pp.failed_checks({pp.METADATA_KEY: junk}) is None or junk == {"failed": "x"}
