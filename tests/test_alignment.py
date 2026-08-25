"""3D alignment, both methods."""

from __future__ import annotations

import pytest
from rdkit import Chem

from rdkit.Chem import AllChem

from openchem.chem.alignment import (
    ACCURACY_LEVELS,
    ALIGNMENT_METHODS,
    CONSTRAINED_EMBED,
    DEFAULT_FLEXIBILITY,
    EMBEDDED,
    FLEXIBILITY_MODES,
    GEOMETRY_SOURCE_LABELS,
    PROJECT_CONFORMERS,
    AlignmentError,
    _ensure_conformer,
    align,
    align_ensemble,
    compute_3d_alignment,
    mcs_partition,
    paired_rmsd,
)
from openchem.domain.common import CacheState

#: Coordinates in this project travel through a four-decimal molblock,
#: so nothing measured across one can be trusted below this. CLAUDE.md
#: records the same floor for the conformer display alignment.
MOLBLOCK_PRECISION = 5e-4

IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
NAPROXEN = "COc1ccc2cc(ccc2c1)C(C)C(=O)O"


def test_aligning_a_molecule_onto_itself_gives_zero_rmsd():
    """The strongest available sanity check: identical structures must
    superimpose exactly.

    **THE TOLERANCE IS THE MOLBLOCK FLOOR, NOT 1e-6.** It was 1e-6 and
    passed for a reason that was never the claim: rigid mode embedded the
    probe from the same seed as the reference, so the two were the same
    object and the RMSD was bitwise zero. Flexible mode builds a
    constrained conformer and minimises it against a 0.05 A restraint, so
    it lands 4.9e-05 A away -- which is an order of magnitude BELOW the
    5e-4 floor this project already records for coordinates that travel
    through a four-decimal molblock. A tolerance tighter than the data
    format can represent is not a stronger test, it is one that can only
    pass by accident.

    Both partitioned RMSDs are asserted too, which is a stronger statement
    than the old single number: a self-alignment must superimpose the
    flexible substituent as exactly as it superimposes the rigid core.
    """
    result = align(
        Chem.MolFromSmiles(IBUPROFEN), Chem.MolFromSmiles(IBUPROFEN), method="mcs", accuracy="Fast"
    )
    assert result.rmsd == pytest.approx(0.0, abs=MOLBLOCK_PRECISION)
    assert result.matched_atoms > 0
    for measured in (result.core_rmsd, result.flexible_rmsd):
        if measured is not None:
            assert measured == pytest.approx(0.0, abs=MOLBLOCK_PRECISION)


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


# --- The reported defect: a rigid core that lands, and a tail that does not ---
#
# MPMI and 4-HO-MPMI, from the project the defect was reported against. They
# differ by one hydroxyl on the indole and share everything else, including
# the pyrrolidine -- so the MCS covers the tail and the correspondence needed
# to measure it EXISTS, which is the whole reason the metric below is possible.
MPMI = "CN1CCC[C@@H]1Cc1c[nH]c2ccccc12"
HYDROXY_MPMI = "CN1CCC[C@@H]1Cc1c[nH]c2cccc(O)c12"


def _internal_distances(molblock):
    """Every pairwise heavy-atom distance. A rigid transform preserves all
    of them, so a change here means a torsion moved."""
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    conformer = mol.GetConformer()
    heavy = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() > 1]
    out = {}
    for i, a in enumerate(heavy):
        for b in heavy[i + 1:]:
            pa, pb = conformer.GetAtomPosition(a), conformer.GetAtomPosition(b)
            out[(a, b)] = (
                (pa.x - pb.x) ** 2 + (pa.y - pb.y) ** 2 + (pa.z - pb.z) ** 2
            ) ** 0.5
    return out


def test_the_partition_is_not_degenerate_on_the_reported_pair():
    """ASSERTS ITS OWN SETUP. Every claim below rests on the MCS covering
    BOTH a rigid core and a flexible substituent; if a future RDKit returns
    a different MCS and everything lands in one bucket, the guards that
    follow would pass while measuring nothing."""
    reference, _ = _ensure_conformer(Chem.MolFromSmiles(MPMI))
    partition = mcs_partition(
        Chem.AddHs(Chem.Mol(Chem.MolFromSmiles(HYDROXY_MPMI))), reference, 15
    )
    assert not partition.degenerate
    assert len(partition.core) >= 6, "the indole should be the rigid core"
    assert len(partition.flexible) >= 4, "the pyrrolidine should be flexible"


def test_flexible_superimposes_the_tail_that_rigid_leaves_behind():
    """THE REPORTED DEFECT.

    Aligned on the common scaffold, the indole overlaid perfectly and the
    pyrrolidine did not -- and every number the panel showed looked
    healthy, because the reported RMSD is over O3A's own matches and is
    dominated by the rigid core.

    Measured through this path on the reported molecules: rigid leaves the
    flexible partition at ~1.6 A while the core sits at ~0.65; flexible
    brings BOTH to ~0.04. The assertion is on the ratio rather than an
    absolute, because the point is that one mode fixes what the other
    cannot, not that any particular number was hit.
    """
    probe, reference = Chem.MolFromSmiles(HYDROXY_MPMI), Chem.MolFromSmiles(MPMI)
    rigid = align(probe, reference, method="mcs", accuracy="Fast", flexibility="rigid")
    flexible = align(probe, reference, method="mcs", accuracy="Fast", flexibility="flexible")

    assert flexible.geometry_source == "constrained_embed"
    assert flexible.flexible_rmsd < rigid.flexible_rmsd / 4
    assert flexible.flexible_rmsd < 0.5


def test_rigid_lands_the_core_far_better_than_the_tail():
    """Why this needed a new metric at all: the two halves of one
    correspondence can disagree, and a single number cannot show it.

    **THE SHARPER CLAIM IS DELIBERATELY NOT ASSERTED HERE.** On the
    reported instance the panel showed RMSD 0.116 while the flexible
    partition sat at 0.931 -- an eightfold gap, entirely hidden. That
    depends on the drawn coordinates the report came from, and rebuilding
    the pair from SMILES gives a different pose where the headline is 1.157
    and the gap is only 1.4x. Asserting the eightfold version here would be
    fitting a threshold to one instance, so the measurement lives in
    CLAUDE.md and this asserts the part that reproduces.

    Also measured while writing this: at "Accurate" (20 starting
    conformers) rigid mode stumbles onto a good rotamer for this molecule
    anyway. More starting poses is not a fix, it is a lottery with better
    odds -- which is the argument for constraining rather than sampling.
    """
    probe, reference = Chem.MolFromSmiles(HYDROXY_MPMI), Chem.MolFromSmiles(MPMI)
    rigid = align(probe, reference, method="mcs", accuracy="Fast", flexibility="rigid")

    assert rigid.core_rmsd is not None and rigid.flexible_rmsd is not None
    assert rigid.flexible_rmsd > 2 * rigid.core_rmsd, (
        "the rigid core lands and the flexible tail does not -- the signature of the defect"
    )


def test_flexible_holds_the_constraint_and_lets_the_rest_move():
    """THE MEANING OF FLEXIBLE, IN ITS TWO HALVES.

    "The flexible RMSD differs between the modes" is satisfied by two
    DIFFERENT WRONG geometries, so it is not the claim. Flexible promises
    two things and each is asserted:

      the constraint HELD          MCS pairs sit on the reference's own
                                   coordinates, which is what makes them
                                   positional constraints rather than
                                   merely a correspondence
      something outside it MOVED   an internal distance changed, which a
                                   rigid transform cannot do
    """
    probe, reference = Chem.MolFromSmiles(HYDROXY_MPMI), Chem.MolFromSmiles(MPMI)
    flexible = align(probe, reference, method="mcs", accuracy="Fast", flexibility="flexible")
    rigid = align(probe, reference, method="mcs", accuracy="Fast", flexibility="rigid")

    # arm 1 -- the constraint held
    aligned = Chem.MolFromMolBlock(flexible.aligned_molblock, removeHs=False)
    reference_3d = Chem.MolFromMolBlock(flexible.reference_molblock, removeHs=False)
    measured = mcs_partition(aligned, reference_3d, 15)
    assert paired_rmsd(aligned, reference_3d, measured.pairs) < 0.5

    # arm 2 -- something outside the constraint really moved
    before = _internal_distances(rigid.aligned_molblock)
    after = _internal_distances(flexible.aligned_molblock)
    shared = set(before) & set(after)
    assert shared, "the two runs should describe the same atoms"
    assert max(abs(before[k] - after[k]) for k in shared) > 0.1, (
        "flexible re-embedded nothing -- no internal geometry changed"
    )


def test_rigid_preserves_the_supplied_geometry():
    """The mirror of the above. Rigid promises no re-embedding and no
    torsion moves, so every internal distance of a supplied conformer must
    survive -- a rigid transform preserves all of them by definition."""
    probe = Chem.MolFromSmiles(HYDROXY_MPMI)
    supplied, _ = _ensure_conformer(probe)
    molblock = Chem.MolToMolBlock(supplied)

    result = align(
        probe, Chem.MolFromSmiles(MPMI), method="mcs", accuracy="Fast",
        flexibility="rigid", conformers=[molblock],
    )
    assert result.geometry_source == "project_conformers"

    before = _internal_distances(molblock)
    after = _internal_distances(result.aligned_molblock)
    shared = set(before) & set(after)
    assert len(shared) > 10
    assert max(abs(before[k] - after[k]) for k in shared) < MOLBLOCK_PRECISION


def test_a_stored_conformer_is_used_rather_than_a_fresh_embed():
    """The alignment used to read `model.molblock` -- the 2D drawing -- and
    discard every conformer the project held. On the reported pair the
    reference had SEVENTEEN of them."""
    probe = Chem.MolFromSmiles(HYDROXY_MPMI)
    supplied, source = _ensure_conformer(probe)
    assert source == "embedded"

    reused, source = _ensure_conformer(probe, conformers=[Chem.MolToMolBlock(supplied)])
    assert source == "project_conformers"
    assert reused.GetNumAtoms() == supplied.GetNumAtoms()


def test_a_two_dimensional_conformer_is_not_mistaken_for_a_stored_one():
    """A 2D molblock parses into a conformer with flat z, so
    `GetNumConformers() > 0` is true and useless as a check."""
    flat = Chem.MolFromSmiles(HYDROXY_MPMI)
    AllChem.Compute2DCoords(flat)
    _, source = _ensure_conformer(
        Chem.MolFromSmiles(HYDROXY_MPMI), conformers=[Chem.MolToMolBlock(flat)]
    )
    assert source == "embedded", "a flat conformer is not a 3D one"


def _heavy_atom_only_conformer(smiles):
    """A 3D conformer molblock carrying IMPLICIT hydrogens.

    **THIS SHAPE IS THE WHOLE FIXTURE.** The first version of the guard
    below stored a conformer that already had explicit hydrogens, so
    `AddHs` had nothing to add and reverting `addCoords=True` changed
    nothing -- the mutation SURVIVED against a test named for it. The bug
    needs a molecule that is 3D and still has hydrogens to place.
    """
    embedded, _ = _ensure_conformer(Chem.MolFromSmiles(smiles))
    return Chem.MolToMolBlock(Chem.RemoveHs(embedded))


def test_added_hydrogens_are_nearer_their_own_heavy_atom_than_any_other():
    """`AddHs` WITHOUT `addCoords=True` PUTS EVERY HYDROGEN AT THE ORIGIN
    when the molecule already carries a 3D conformer -- measured on this
    fixture, all EIGHTEEN of them -- and `Is3D()` stays True throughout,
    because a conformer does exist and is three-dimensional. So the obvious
    assertions cannot see it: `Is3D()` passes, and so does "the coordinates
    are finite".

    This invariant needs no table and no tolerance, and fails on the origin
    case and on any other collapsed placement.
    """
    stored = _heavy_atom_only_conformer(HYDROXY_MPMI)
    prepared, source = _ensure_conformer(
        Chem.MolFromSmiles(HYDROXY_MPMI), conformers=[stored]
    )
    assert source == "project_conformers"

    conformer = prepared.GetConformer()
    heavy = [a.GetIdx() for a in prepared.GetAtoms() if a.GetAtomicNum() > 1]
    assert heavy, "the fixture has no heavy atoms to be near"

    checked = 0
    for atom in prepared.GetAtoms():
        if atom.GetAtomicNum() != 1:
            continue
        neighbours = atom.GetNeighbors()
        if not neighbours:
            continue
        own = neighbours[0].GetIdx()
        position = conformer.GetAtomPosition(atom.GetIdx())

        def distance_to(index, position=position):
            other = conformer.GetAtomPosition(index)
            return (
                (position.x - other.x) ** 2
                + (position.y - other.y) ** 2
                + (position.z - other.z) ** 2
            ) ** 0.5

        nearest = min(heavy, key=distance_to)
        assert nearest == own, (
            f"hydrogen {atom.GetIdx()} is nearer heavy atom {nearest} than its own {own}"
        )
        checked += 1
    assert checked > 5, "no hydrogens were checked -- the fixture proves nothing"


def test_the_hydrogen_fixture_really_has_hydrogens_to_place():
    """ASSERTS THE SETUP OF THE GUARD ABOVE.

    If a future RDKit started writing explicit hydrogens through
    `RemoveHs` + `MolToMolBlock`, the fixture would silently stop being
    able to reproduce the bug and the guard would pass vacuously -- which
    is exactly how the first version of it scored a SURVIVED.
    """
    stored = _heavy_atom_only_conformer(HYDROXY_MPMI)
    parsed = Chem.MolFromMolBlock(stored, removeHs=False)
    assert parsed.GetConformer().Is3D()
    assert sum(a.GetTotalNumHs() for a in parsed.GetAtoms()) > 5, (
        "the stored conformer must carry IMPLICIT hydrogens, or AddHs adds nothing"
    )
    assert not any(a.GetAtomicNum() == 1 for a in parsed.GetAtoms())


def test_a_flexible_request_that_cannot_embed_degrades_and_says_so():
    """Pinning the shared atoms onto the reference is not always
    geometrically possible, and that is chemistry rather than a bug:
    ibuprofen's MCS with naproxen spans BOTH rings of the naphthalene, so
    no conformer of a single benzene can put its shared ring atoms there.

    The alignment still returns -- it degrades to an ordinary embed and
    reports EMBEDDED rather than CONSTRAINED_EMBED, so "flexible did not
    take on this pair" is visible instead of silent.
    """
    result = align(
        Chem.MolFromSmiles(IBUPROFEN), Chem.MolFromSmiles(NAPROXEN),
        method="mcs", accuracy="Fast", flexibility="flexible",
    )
    assert result.geometry_source == "embedded"
    assert result.score > 0


def test_the_mcs_size_and_the_o3a_match_count_are_separate_fields():
    """THE PANEL SAID "14 paired atoms" FOR AN MCS OF 33.

    `matched_atoms` is O3A's own match count. For an MCS-method result a
    reader takes it to mean the MCS, and the two are not the same number.
    One field with a method-dependent meaning is how that ambiguity comes
    back under a new label.
    """
    result = align(
        Chem.MolFromSmiles(HYDROXY_MPMI), Chem.MolFromSmiles(MPMI),
        method="mcs", accuracy="Fast",
    )
    assert result.mcs_atom_count > result.o3a_match_count
    assert result.o3a_match_count == result.matched_atoms


def test_every_geometry_source_carries_a_label():
    """The UI renders these rather than paraphrasing -- "Generated
    geometry" for `embedded` reintroduces exactly the rediscovered meaning
    the field exists to prevent. Derived from the constants, so a new
    member cannot ship unlabelled."""
    for source in (PROJECT_CONFORMERS, EMBEDDED, CONSTRAINED_EMBED):
        assert GEOMETRY_SOURCE_LABELS[source]
    assert set(GEOMETRY_SOURCE_LABELS) == {PROJECT_CONFORMERS, EMBEDDED, CONSTRAINED_EMBED}


def test_both_flexibility_modes_are_offered():
    assert set(FLEXIBILITY_MODES) == {"Flexible", "Rigid"}
    assert FLEXIBILITY_MODES["Flexible"] == DEFAULT_FLEXIBILITY
