"""3D alignment, both methods."""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.alignment import (
    ACCURACY_LEVELS,
    ALIGNMENT_METHODS,
    AlignmentError,
    align,
    align_ensemble,
    compute_3d_alignment,
)
from openchem.domain.common import CacheState

IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
NAPROXEN = "COc1ccc2cc(ccc2c1)C(C)C(=O)O"


def test_aligning_a_molecule_onto_itself_gives_zero_rmsd():
    """The strongest available sanity check: identical structures must
    superimpose exactly."""
    result = align(
        Chem.MolFromSmiles(IBUPROFEN), Chem.MolFromSmiles(IBUPROFEN), method="mcs", accuracy="Fast"
    )
    assert result.rmsd == pytest.approx(0.0, abs=1e-6)
    assert result.matched_atoms > 0


@pytest.mark.parametrize("method", list(ALIGNMENT_METHODS.values()))
def test_both_methods_align_two_related_drugs(method):
    """Ibuprofen and naproxen share the profen scaffold, so both methods
    should find a real overlay."""
    result = align(
        Chem.MolFromSmiles(IBUPROFEN), Chem.MolFromSmiles(NAPROXEN), method=method, accuracy="Fast"
    )
    assert result.score > 0
    assert result.rmsd < 3.0
    assert result.matched_atoms >= 4


def test_both_of_chemaxons_methods_are_offered():
    assert set(ALIGNMENT_METHODS) == {"Extended atom types", "Common scaffold (MCS)"}


def test_the_two_methods_produce_different_pairings():
    """MCS constrains to the shared scaffold; atom-type alignment is free
    to pair anything of matching type. Identical results would mean the
    method option is not doing anything."""
    by_types = align(
        Chem.MolFromSmiles(IBUPROFEN), Chem.MolFromSmiles(NAPROXEN),
        method="atom_types", accuracy="Fast",
    )
    by_scaffold = align(
        Chem.MolFromSmiles(IBUPROFEN), Chem.MolFromSmiles(NAPROXEN),
        method="mcs", accuracy="Fast",
    )
    assert by_types.score != by_scaffold.score


def test_accuracy_controls_how_many_conformers_are_tried():
    """ChemAxon's 'initial conformation count' -- a flexible molecule's
    alignment depends heavily on its starting geometry."""
    fast = align(Chem.MolFromSmiles(IBUPROFEN), Chem.MolFromSmiles(NAPROXEN), accuracy="Fast")
    accurate = align(Chem.MolFromSmiles(IBUPROFEN), Chem.MolFromSmiles(NAPROXEN), accuracy="Accurate")

    assert fast.conformers_tried < accurate.conformers_tried
    # More starting points can only improve the best score, never worsen it.
    assert accurate.score >= fast.score


def test_more_conformers_really_does_find_a_better_pose():
    fast = align(Chem.MolFromSmiles(IBUPROFEN), Chem.MolFromSmiles(NAPROXEN), accuracy="Fast")
    normal = align(Chem.MolFromSmiles(IBUPROFEN), Chem.MolFromSmiles(NAPROXEN), accuracy="Normal")
    assert normal.score > fast.score


def test_mcs_refuses_when_there_is_no_common_substructure():
    """Returning an arbitrary superposition would be worse than refusing."""
    with pytest.raises(AlignmentError, match="no common substructure"):
        align(
            Chem.MolFromSmiles("CCCCCC"), Chem.MolFromSmiles("[Na+].[Cl-]"),
            method="mcs", accuracy="Fast",
        )


def test_the_constraint_map_never_contains_hydrogens():
    """O3A rejects a constraint map with hydrogens outright. The MCS runs
    against H-added molecules, so they have to be filtered -- this failed
    with 'Constrained atoms must be heavy atoms' before the filter."""
    result = align(
        Chem.MolFromSmiles("c1ccccc1C(=O)O"), Chem.MolFromSmiles("c1ccccc1C(=O)OC"),
        method="mcs", accuracy="Fast",
    )
    assert result.matched_atoms > 0


def test_the_typing_used_is_reported():
    """MMFF and Crippen scores are on different scales, so which one ran
    has to be visible or two results could be wrongly compared."""
    result = align(Chem.MolFromSmiles(IBUPROFEN), Chem.MolFromSmiles(NAPROXEN), accuracy="Fast")
    assert result.typing in ("MMFF", "Crippen")


# --- The calculator -----------------------------------------------------


def test_calculator_returns_the_reference_and_the_aligned_structure():
    result = compute_3d_alignment(
        Chem.MolFromSmiles(IBUPROFEN), "mol-1",
        {"reference_smiles": NAPROXEN, "accuracy": "Fast"},
    )
    roles = [entry.metadata["role"] for entry in result.entries]
    assert roles == ["reference", "aligned"]
    for entry in result.entries:
        assert Chem.MolFromMolBlock(entry.molblock) is not None


def test_calculator_needs_a_reference():
    result = compute_3d_alignment(Chem.MolFromSmiles(IBUPROFEN), "mol-1", {})
    assert result.cache_state == CacheState.FAILED
    assert "reference" in result.error.lower()


def test_calculator_reports_an_unparseable_reference():
    result = compute_3d_alignment(
        Chem.MolFromSmiles(IBUPROFEN), "mol-1", {"reference_smiles": "not a smiles"}
    )
    assert result.cache_state == CacheState.FAILED
    assert "parse" in result.error.lower()


def test_score_and_rmsd_are_labelled_with_their_direction():
    """Score is higher-is-better, RMSD is lower-is-better. Conflating them
    would invert the meaning of a result."""
    result = compute_3d_alignment(
        Chem.MolFromSmiles(IBUPROFEN), "mol-1",
        {"reference_smiles": NAPROXEN, "accuracy": "Fast"},
    )
    aligned = result.entries[1].label
    assert "higher is better" in aligned
    assert "RMSD" in aligned


def test_decimal_places_reaches_the_alignment_summary():
    one = compute_3d_alignment(
        Chem.MolFromSmiles(IBUPROFEN), "m",
        {"reference_smiles": NAPROXEN, "accuracy": "Fast", "decimal_places": 1},
    )
    four = compute_3d_alignment(
        Chem.MolFromSmiles(IBUPROFEN), "m",
        {"reference_smiles": NAPROXEN, "accuracy": "Fast", "decimal_places": 4},
    )
    assert one.name != four.name


# --- Ensemble alignment ---------------------------------------------------


def test_ensemble_returns_the_reference_first_then_each_probe_in_order():
    entries = align_ensemble(
        [("ibuprofen", Chem.MolFromSmiles(IBUPROFEN)), ("naproxen", Chem.MolFromSmiles(NAPROXEN))],
        Chem.MolFromSmiles(IBUPROFEN),
        reference_label="ref",
        accuracy="Fast",
    )

    assert [entry.label for entry in entries] == ["ref", "ibuprofen", "naproxen"]
    # The reference defines the frame, so it has no score against anything.
    assert entries[0].score is None
    assert entries[0].molblock
    assert all(entry.aligned for entry in entries)


def test_every_probe_lands_in_the_references_coordinate_frame():
    """The point of an ensemble: aligning each molecule onto the SAME
    reference is what makes their coordinates comparable to each other.
    Checked by centroid proximity -- two independently embedded molecules
    would be centred wherever their own embedding happened to put them."""
    reference = Chem.MolFromSmiles(IBUPROFEN)
    entries = align_ensemble(
        [("naproxen", Chem.MolFromSmiles(NAPROXEN)), ("ibuprofen", Chem.MolFromSmiles(IBUPROFEN))],
        reference,
        accuracy="Fast",
    )

    centroids = []
    for entry in entries:
        conformer = Chem.MolFromMolBlock(entry.molblock, removeHs=False).GetConformer()
        positions = conformer.GetPositions()
        centroids.append(positions.mean(axis=0))
    for centroid in centroids[1:]:
        assert float(((centroid - centroids[0]) ** 2).sum() ** 0.5) < 3.0


def test_one_unalignable_molecule_does_not_discard_the_others():
    """A ten-molecule run where one structure fails should return nine
    alignments and one explanation, not nothing."""
    entries = align_ensemble(
        [
            ("good", Chem.MolFromSmiles(NAPROXEN)),
            ("empty", Chem.MolFromSmiles("")),
        ],
        Chem.MolFromSmiles(IBUPROFEN),
        accuracy="Fast",
    )

    by_label = {entry.label: entry for entry in entries}
    assert by_label["good"].aligned
    assert by_label["good"].score is not None
    assert not by_label["empty"].aligned
    assert by_label["empty"].error


def test_ensemble_reports_progress_per_molecule():
    seen: list[tuple[int, int, str]] = []
    align_ensemble(
        [("ibuprofen", Chem.MolFromSmiles(IBUPROFEN)), ("naproxen", Chem.MolFromSmiles(NAPROXEN))],
        Chem.MolFromSmiles(IBUPROFEN),
        accuracy="Fast",
        on_progress=lambda done, total, label: seen.append((done, total, label)),
    )

    assert seen == [(0, 2, "ibuprofen"), (1, 2, "naproxen")]
