"""Asking for ten conformers of a molecule that has one must not return ten.

Embedding is random and nothing pruned the results, so a rigid structure
came back as N copies of one shape and the viewer reported "Conformer
1/10" for every one of them. Beyond being wrong on its face, that invites
Boltzmann-weighting a population that is really a single state counted ten
times.
"""

from __future__ import annotations

import random

import pytest
from rdkit import Chem
from rdkit.Chem import rdMolAlign

from openchem.chem.conformer_providers import (
    _IDENTICAL_SHAPE_RMSD,
    DEFAULT_ENERGY_WINDOW,
    DEFAULT_RMS_THRESHOLD,
    RDKitConformerProvider,
    comparison_skeleton,
    distinct_conformers,
    merge_candidates,
)

#: Vetoes nothing: every pair "agrees" on energy, so geometry alone
#: decides. The control arm for showing what RMSD does by itself.
#: Zero would be the WRONG control -- it vetoes every merge instead of
#: none, and reading it the other way round silently inverts the test.
NO_VETO = float("inf")


def _generate(smiles: str, count: int = 10, seed: int | None = None):
    return RDKitConformerProvider(random_seed=seed).generate_conformers(
        Chem.MolFromSmiles(smiles), num_conformers=count, optimize=True
    )


@pytest.mark.parametrize(
    ("label", "smiles", "expected"),
    [
        # Three-membered rings have exactly one shape. This is the case
        # from the bug report.
        ("aziridine", "C1CN1", 1),
        ("2H-azirine", "C1=NC1", 1),
        ("benzene", "c1ccccc1", 1),
    ],
)
def test_a_rigid_molecule_yields_one_conformer(label, smiles, expected):
    results = _generate(smiles)
    assert len(distinct_conformers(results)) == expected, label


def test_a_flexible_molecule_keeps_more_than_one():
    """The complement, and the test that stops "always return 1" passing.

    Butane's anti and gauche forms are a real distinction: measured over
    40 embeddings, every pair was either below 0.5 A or at 0.66 A -- two
    clean clusters and nothing between them.
    """
    assert len(distinct_conformers(_generate("CCCC"))) >= 2


def test_survivors_are_genuinely_different_from_each_other():
    """Whatever comes back must be pairwise distinct, not merely fewer.

    A dedup that dropped an arbitrary number of results would satisfy a
    count assertion; this is the property that actually matters.
    """
    kept = distinct_conformers(_generate("CC(C)Cc1ccc(cc1)C(C)C(=O)O"))
    # `comparison_skeleton`, not `RemoveHs`: the pruner keeps polar
    # hydrogens, so comparing survivors without them reports two genuinely
    # different O-H orientations as the same shape and fails a correct
    # implementation.
    heavy = [comparison_skeleton(mol) for mol, _energy in kept]
    for i, first in enumerate(heavy):
        for second in heavy[i + 1 :]:
            assert rdMolAlign.GetBestRMS(first, second) >= DEFAULT_RMS_THRESHOLD


def test_the_lowest_energy_member_of_each_cluster_survives():
    """The provider sorts by energy before the service prunes, so the
    conformer kept from a cluster is its lowest-energy one -- not whichever
    embedding happened to come out of the loop first."""
    results = _generate("CCCC")
    energies = [energy for _mol, energy in results]
    assert energies == sorted(energies)
    kept = distinct_conformers(results)
    assert kept[0][1] == min(energies)


def test_nothing_is_dropped_when_every_shape_is_different():
    """Two deliberately different geometries must both survive."""
    results = _generate("CCCCCC", count=12)
    kept = distinct_conformers(results, rms_threshold=0.0)
    assert len(kept) == len(results)


# --------------------------------------------------------------------------
# The energy veto. Read DEFAULT_ENERGY_WINDOW's comment before changing any
# of this: the criterion is deliberately asymmetric, and the pair of tests
# below is what stops it collapsing into a symmetric one.
# --------------------------------------------------------------------------


def test_cyclohexanes_twist_boat_survives():
    """The case RMSD alone gets wrong, and the reason the veto exists.

    Chair and twist-boat are a textbook two-conformer set. At 0.5 A the
    geometric criterion merges them and reports cyclohexane as rigid --
    measured across five seeds of 50 embeddings, 1.0 without the veto
    against 2.0 with it.
    """
    results = _generate("C1CCCCC1", count=40, seed=0)
    assert len(distinct_conformers(results, DEFAULT_RMS_THRESHOLD, NO_VETO)) == 1
    assert len(distinct_conformers(results, DEFAULT_RMS_THRESHOLD, DEFAULT_ENERGY_WINDOW)) >= 2


def test_close_in_shape_but_far_in_energy_is_kept_apart():
    """The veto fires.

    ASSERTS THE PROPERTY, NOT THE MEASURED NUMBERS. The real pair that
    motivated this reads RMSD 0.437 / dE 15.79 kcal/mol, but pinning
    those literals would make the test a transcription of one run rather
    than a statement about the rule -- and this project has already paid
    once for a fixture whose numbers were typed from memory and hidden
    behind a loose tolerance.
    """
    results = _generate(
        "CN1CC[C@]23[C@@H]4[C@H]1CC5=C2C(=C(C=C5)OCC)O[C@H]3[C@H](C=C4)O", count=24, seed=0
    )
    vetoed = [c for c in merge_candidates(results, with_torsions=False) if not c.merged]
    assert vetoed, "no pair was close in shape and far in energy -- the fixture is not exercising the veto"
    for candidate in vetoed:
        assert candidate.rmsd < DEFAULT_RMS_THRESHOLD
        assert candidate.energy_difference >= DEFAULT_ENERGY_WINDOW


def test_far_in_shape_but_close_in_energy_is_also_kept_apart():
    """The INVERSE, and the test that proves energy is a veto.

    Without this, energy agreement could quietly become a second identity
    criterion -- "same energy therefore same conformer" -- and every
    other test in this file would still pass. Two shapes beyond the RMSD
    threshold must stay separate however close their energies are, up to
    and including exactly equal.

    Butane's anti and gauche are far apart geometrically; their energies
    are forced equal here so that agreement is total.
    """
    results = _generate("CCCC", count=20, seed=0)
    geometric_only = distinct_conformers(results, DEFAULT_RMS_THRESHOLD, NO_VETO)
    assert len(geometric_only) >= 2
    forced = [(mol, 0.0) for mol, _energy in geometric_only]
    assert len(distinct_conformers(forced, DEFAULT_RMS_THRESHOLD, DEFAULT_ENERGY_WINDOW)) == len(
        geometric_only
    )


def test_energy_agreement_permits_a_merge_it_never_asserts_one():
    """The contract from DEFAULT_ENERGY_WINDOW, made executable.

    Stated there as: passing both criteria PERMITS merging; it does not
    prove equivalence. Operationally that means the veto can only ever
    RETAIN more than geometry alone, never fewer -- if some threshold
    combination ever returned fewer conformers with the veto than
    without, energy would be doing classification rather than declining
    to merge.
    """
    for smiles in ("CCO", "CCCC", "C1CCCCC1", "OCCO"):
        results = _generate(smiles, count=16, seed=0)
        for threshold in (0.25, 0.5, 1.0):
            with_veto = len(distinct_conformers(results, threshold, DEFAULT_ENERGY_WINDOW))
            geometry_alone = len(distinct_conformers(results, threshold, NO_VETO))
            assert with_veto >= geometry_alone, (smiles, threshold)


def test_a_missing_energy_falls_back_for_that_pair_only():
    """Mixed None is per pair, not per batch.

    A real pipeline accumulates partial metadata -- a project saved
    before energies were recorded, a provider that does not optimise --
    and an all-or-nothing rule would silently change how an entire batch
    is compared because one member lacked a number.
    """
    results = _generate("C1CCCCC1", count=24, seed=0)
    both_energies = distinct_conformers(results, DEFAULT_RMS_THRESHOLD, DEFAULT_ENERGY_WINDOW)
    assert len(both_energies) >= 2

    # Strip the energy from the LAST conformer only. Pairs involving it
    # lose the veto; every other pair keeps it.
    partial = [(mol, energy) for mol, energy in results[:-1]]
    partial.append((results[-1][0], None))
    assert any(energy is None for _mol, energy in partial)
    assert any(energy is not None for _mol, energy in partial)
    # The energised pairs still separate, so the batch was not degraded
    # to RMSD-only wholesale.
    assert len(distinct_conformers(partial, DEFAULT_RMS_THRESHOLD, DEFAULT_ENERGY_WINDOW)) >= 2


def test_the_retained_set_does_not_depend_on_input_order():
    """Greedy leader clustering is order-dependent, so the order is part
    of the contract rather than whatever the caller happened to pass.

    `_in_comparison_order` sorts by energy precisely so that shuffling
    the input cannot change the answer.
    """
    results = _generate("OCCO", count=20, seed=0)
    baseline = distinct_conformers(results)
    shuffler = random.Random(20260808)
    for _ in range(5):
        shuffled = list(results)
        shuffler.shuffle(shuffled)
        assert len(distinct_conformers(shuffled)) == len(baseline)


def test_conformers_are_not_mutated_by_de_duplication():
    """`GetBestRMS` TRANSFORMS its probe argument.

    Today it is handed a throwaway skeleton so nothing leaks back, but
    that is incidental: an edit that compared the stored mols directly
    would silently rotate saved conformers and nothing else would
    notice. Compares more than coordinates, because "did not mutate" is
    a much stronger invariant than "the coordinates are unchanged".
    """
    results = _generate("OCCO", count=12, seed=0)
    before = [_snapshot(mol) for mol, _energy in results]
    distinct_conformers(results)
    merge_candidates(results)
    assert [_snapshot(mol) for mol, _energy in results] == before


def _snapshot(mol: Chem.Mol) -> tuple:
    """Everything a consumer could observe about a conformer."""
    conformer = mol.GetConformer()
    return (
        mol.GetNumAtoms(),
        tuple(atom.GetAtomicNum() for atom in mol.GetAtoms()),
        tuple(atom.GetFormalCharge() for atom in mol.GetAtoms()),
        tuple(sorted((b.GetBeginAtomIdx(), b.GetEndAtomIdx()) for b in mol.GetBonds())),
        Chem.MolToSmiles(mol),
        tuple(
            (round(p.x, 9), round(p.y, 9), round(p.z, 9))
            for p in (conformer.GetAtomPosition(i) for i in range(mol.GetNumAtoms()))
        ),
    )


def test_the_torsion_diagnostic_can_see_ring_pucker():
    """Guards a bug that shipped silently in the diagnostic itself.

    `TorsionFingerprints.CalculateTorsionLists` returns (non-ring, ring)
    and the first version of `_torsion_deviation` read only the first.
    Cyclohexane has ZERO non-ring torsions, so a chair/twist-boat pair
    reported "max dihedral 0.0 degrees" against a TFD of 0.407 -- and on
    ethylmorphine, whose flexibility is ring pucker, it measured the
    ethyl ether and reported 1.6 degrees where the real answer is 104.

    A diagnostic that silently reports zero is worse than none, because
    it gets quoted as evidence. This is the test that would have caught
    it.
    """
    results = _generate("C1CCCCC1", count=24, seed=0)
    candidates = merge_candidates(results, with_torsions=True)
    assert candidates, "cyclohexane produced no merge candidates to diagnose"
    assert max(c.max_dihedral_change for c in candidates) > 60.0


def test_a_rigid_ring_is_not_split_by_a_force_field_artefact():
    """The veto's false-positive mode, and the original bug in reverse.

    About 2% of 2H-azirine embeddings converge to a distorted minimum
    10.7 kcal/mol up -- same connectivity, same torsions, C=N stretched
    to 1.339 A from 1.246. A three-membered ring has no conformational
    freedom, so that is a force-field artefact and must not be promoted
    to a second conformer just because its energy differs.

    Unseeded and repeated, because the artefact is rare: a single seeded
    run does not produce it and would pass against a broken floor.
    """
    for _ in range(8):
        results = _generate("C1=NC1", count=20)
        assert len(distinct_conformers(results)) == 1


def test_the_same_shape_floor_stays_between_its_measured_bounds():
    """A guard on the constant, derived rather than written down.

    The floor has to sit above the largest artefact RMSD and below the
    smallest genuine one. Both ends are recomputed here, so moving
    `_IDENTICAL_SHAPE_RMSD` fails naming which side it broke rather than
    silently changing counts.
    """
    artefacts = []
    for _ in range(8):
        results = _generate("C1=NC1", count=20)
        artefacts += [
            c.rmsd
            for c in merge_candidates(results, with_torsions=False)
            if c.rmsd > 0.0 and (c.energy_difference or 0) >= DEFAULT_ENERGY_WINDOW
        ]
    genuine = [
        c.rmsd
        for c in merge_candidates(
            _generate(
                "CN1CC[C@]23[C@@H]4[C@H]1CC5=C2C(=C(C=C5)OCC)O[C@H]3[C@H](C=C4)O",
                count=30,
                seed=0,
            ),
            with_torsions=False,
        )
        if not c.merged
    ]
    assert genuine, "the ethylmorphine fixture stopped exercising the veto"
    assert min(genuine) > _IDENTICAL_SHAPE_RMSD, (
        f"the floor {_IDENTICAL_SHAPE_RMSD} has risen into genuine conformers "
        f"(smallest vetoed RMSD {min(genuine):.4f}) -- lowering counts silently"
    )
    if artefacts:
        assert max(artefacts) < _IDENTICAL_SHAPE_RMSD, (
            f"the floor {_IDENTICAL_SHAPE_RMSD} no longer covers the azirine "
            f"artefact at {max(artefacts):.4f} -- rigid rings will split again"
        )


def test_the_diagnostic_and_the_decision_come_from_the_same_scan():
    """`merge_candidates` must describe the run `distinct_conformers` did.

    They were two copies of one loop -- same ordering, same skeleton, same
    GetBestRMS, same threshold, same `_permits_merge` -- one returning the
    survivors and one the reasons, with nothing tying them together. The
    day the merge rule changed in one, the other would have gone on
    describing an algorithm that no longer ran, and a diagnostic that
    describes the wrong algorithm is worse than none: this module's own
    history has a conclusion reached and written down from a torsion
    number that was measuring the wrong thing.

    The invariant that ties them: every pair `merge_candidates` reports as
    merged is one conformer `distinct_conformers` dropped, so the counts
    have to agree exactly.
    """
    from openchem.chem.conformer_providers import distinct_conformers, merge_candidates

    mol = Chem.AddHs(Chem.MolFromSmiles("CCCCO"))
    batch = RDKitConformerProvider(random_seed=11).generate_conformer_batch(
        mol, 12, optimize=True
    )
    kept = distinct_conformers(batch.results)
    candidates = merge_candidates(batch.results, with_torsions=False)

    merged = [c for c in candidates if c.merged]
    assert len(batch.results) - len(merged) == len(kept), (
        f"{len(merged)} merges reported against {len(batch.results) - len(kept)} conformers "
        f"actually dropped -- the diagnostic is describing a different run"
    )


# --- the torsion diagnostic, and the symmetry it used to be blind to ---


#: (S)-ibuprofen. Its para-substituted ring makes a 180-degree flip an
#: AUTOMORPHISM, so two embeddings can superimpose exactly while a raw
#: fixed-index dihedral reads half a turn. Measured at seed 0 over 12
#: embeddings: 10 such pairs, `GetBestRMS` ~1e-5 against a naive reading
#: of 179.8 degrees.
_RING_FLIP_SMILES = "CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O"

#: Below this the two structures are the same shape by any reading, so a
#: large dihedral between them can only be a labelling artefact.
_SUPERIMPOSED = 0.05


def _naive_max_dihedral(first: Chem.Mol, second: Chem.Mol) -> float:
    """The metric this module USED to ship: fixed indices, no correspondence.

    Written out here rather than imported, so the guard does not require
    production to keep a "raw" helper alive purely to be tested against. It
    is the whole of the old implementation, periodic wrap included, so the
    only thing separating it from the current one is the symmetry
    correction.
    """
    from rdkit.Chem import TorsionFingerprints, rdMolTransforms

    nonring, rings = TorsionFingerprints.CalculateTorsionLists(first)
    worst = 0.0
    for atom_groups, _method in list(nonring) + list(rings):
        for atoms in atom_groups:
            a = rdMolTransforms.GetDihedralDeg(first.GetConformer(), *atoms)
            b = rdMolTransforms.GetDihedralDeg(second.GetConformer(), *atoms)
            worst = max(worst, abs((a - b + 180.0) % 360.0 - 180.0))
    return worst


def test_a_symmetry_equivalent_pair_is_not_reported_as_a_half_turn():
    """The defect that would have made a funnel report a fake over-merge.

    `GetBestRMS` is symmetry-aware and the old dihedral reading was not, so
    a pair of structures that superimpose EXACTLY reported a 180-degree
    torsion change. Measured on ibuprofen at 50 embeddings, 33 of 40 merged
    pairs flagged a torsion moving more than 90 degrees -- so anything
    asking "did de-duplication discard a real conformational difference"
    answered yes on the first molecule tried.

    **The naive arm is asserted too**, so this fails if somebody removes
    the correction: without it the two numbers agree and the test would be
    testing nothing.

    A structure against an exact `Chem.Mol` copy of itself will NOT show
    this -- same atom ordering, so both metrics read zero. It takes two
    genuinely different embeddings that happen to superimpose, which is why
    the pair is SEARCHED FOR rather than named by index: the batch is
    sorted by energy, so a positional fixture silently points somewhere
    else the moment an energy moves.
    """
    from openchem.chem.conformer_providers import _torsion_deviation

    results = _generate(_RING_FLIP_SMILES, count=12, seed=0)
    superimposed = [
        (first, second, rmsd)
        for i, (first, _e1) in enumerate(results)
        for second, _e2 in results[i + 1:]
        if (rmsd := rdMolAlign.GetBestRMS(comparison_skeleton(first), comparison_skeleton(second)))
        < _SUPERIMPOSED
    ]
    assert superimposed, "no pair superimposes, so this fixture cannot show the artefact"

    # ASSERT THE SETUP. Without a pair the naive metric gets wrong, the
    # correction has nothing to demonstrate and this test passes vacuously.
    artefacts = [
        (first, second, rmsd)
        for first, second, rmsd in superimposed
        if _naive_max_dihedral(first, second) > 90.0
    ]
    assert artefacts, (
        "the naive metric no longer reads a half turn on any superimposed pair, "
        "so this fixture no longer demonstrates the defect being guarded against"
    )

    for first, second, rmsd in artefacts:
        _tfd, corrected, _atoms = _torsion_deviation(first, second)
        assert corrected is not None
        assert corrected < 5.0, (
            f"structures that superimpose to {rmsd:.5f} A reported a {corrected:.1f} deg "
            f"torsion change -- the dihedral is being read under a different atom "
            f"correspondence than the merge decision used"
        )


def test_the_dihedral_is_periodic_in_both_directions():
    """+179 against -179 is 2 degrees, not 358.

    A quadruple traversed the other way round has the opposite SIGN, so a
    plain subtraction turns a two-degree wobble into most of a full turn.
    Asserted on the arithmetic directly: a molecular fixture exercising it
    would also be exercising the symmetry correction, and the two effects
    would be impossible to tell apart.
    """
    def delta(a: float, b: float) -> float:
        return abs((a - b + 180.0) % 360.0 - 180.0)

    assert delta(179.0, -179.0) == pytest.approx(2.0)
    assert delta(-179.0, 179.0) == pytest.approx(2.0)
    assert delta(350.0, 10.0) == pytest.approx(20.0)
    assert delta(0.0, 180.0) == pytest.approx(180.0)


def test_the_diagnostic_uses_the_same_alignment_the_merge_used():
    """A correspondence that is not the merge's describes a different pairing.

    `_torsion_deviation` takes its atom mapping from
    `GetBestAlignmentTransform` while `_merge_scan` decides on
    `GetBestRMS`. They agree to ~1e-6, which is what makes the diagnostic a
    statement about the merge that actually happened -- so it is checked
    rather than believed, and production declines to answer when the check
    fails.
    """
    from openchem.chem.conformer_providers import _ALIGNMENT_AGREEMENT

    results = _generate(_RING_FLIP_SMILES, count=8, seed=0)
    worst = 0.0
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            probe = comparison_skeleton(results[i][0])
            reference = comparison_skeleton(results[j][0])
            best = rdMolAlign.GetBestRMS(probe, reference)
            aligned, _transform, _map = rdMolAlign.GetBestAlignmentTransform(probe, reference)
            worst = max(worst, abs(best - aligned))
    assert worst < _ALIGNMENT_AGREEMENT, (
        f"the two alignments disagree by {worst:.2e}, so the tolerance no longer "
        f"has the headroom it was measured with"
    )


def test_a_diagnostic_that_cannot_answer_reports_None_rather_than_zero():
    """Could-not-measure is not nothing-moved.

    The whole lesson of the 180-degree reading is that a wrong number is
    worse than no number, so a failure has to stay distinguishable from a
    zero. Generation must survive it -- the diagnostic is never
    load-bearing -- and the MERGE OUTCOME must be untouched, which is the
    half that would matter if this ever fired in production.
    """
    from openchem.chem import conformer_providers
    from openchem.chem.conformer_providers import _merge_scan

    results = _generate("OCCO", count=10, seed=0)
    before_kept, before_candidates = _merge_scan(
        results, DEFAULT_RMS_THRESHOLD, DEFAULT_ENERGY_WINDOW, True
    )

    original = conformer_providers.rdMolAlign.GetBestAlignmentTransform

    def refuse(*_args, **_kwargs):
        raise RuntimeError("alignment declined")

    conformer_providers.rdMolAlign.GetBestAlignmentTransform = refuse
    try:
        kept, candidates = _merge_scan(
            results, DEFAULT_RMS_THRESHOLD, DEFAULT_ENERGY_WINDOW, True
        )
    finally:
        conformer_providers.rdMolAlign.GetBestAlignmentTransform = original

    assert candidates, "the fixture must produce merge candidates or this asserts nothing"
    assert all(c.max_dihedral_change is None for c in candidates)
    assert all(c.tfd is None for c in candidates)
    assert len(kept) == len(before_kept)
    assert [c.merged for c in candidates] == [c.merged for c in before_candidates]


def test_origin_tags_cannot_reach_the_merge_decision():
    """Diagnostic metadata must not be readable from any comparison.

    `ORIGIN_PROPERTY` rides along on the molecules the merge scan walks, so
    a stray equality on the mol -- or a future criterion that hashed
    properties -- could make two structures compare differently for a
    reason that has nothing to do with their shape. Tagged and untagged
    runs must decide identically.
    """
    from openchem.chem.conformer_providers import ORIGIN_PROPERTY, _merge_scan

    # PRODUCTION TAGS UNCONDITIONALLY -- `_embed_one` stamps every
    # embedding -- so the tagged arm is simply the results as generated,
    # and the UNtagged arm is the one that has to be constructed. The
    # first version of this test had that backwards: it assumed
    # `_generate` returned bare molecules, and the "untagged" control was
    # tagged all along.
    results = _generate("CCCCO", count=10, seed=3)
    tagged_kept, tagged = _merge_scan(
        results, DEFAULT_RMS_THRESHOLD, DEFAULT_ENERGY_WINDOW, False
    )

    for mol, _energy in results:
        mol.ClearProp(ORIGIN_PROPERTY)
    untagged_kept, untagged = _merge_scan(
        results, DEFAULT_RMS_THRESHOLD, DEFAULT_ENERGY_WINDOW, False
    )

    assert len(tagged_kept) == len(untagged_kept)
    assert [c.merged for c in tagged] == [c.merged for c in untagged]
    assert [round(c.rmsd, 9) for c in tagged] == [round(c.rmsd, 9) for c in untagged]
    # And the arms really differ in what this test varies, or they agreed
    # for a boring reason.
    assert all(c.candidate_origin is not None for c in tagged)
    assert all(c.candidate_origin is None for c in untagged)
