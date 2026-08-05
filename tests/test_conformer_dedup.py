"""Asking for ten conformers of a molecule that has one must not return ten.

Embedding is random and nothing pruned the results, so a rigid structure
came back as N copies of one shape and the viewer reported "Conformer
1/10" for every one of them. Beyond being wrong on its face, that invites
Boltzmann-weighting a population that is really a single state counted ten
times.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import rdMolAlign

from openchem.chem.conformer_providers import (
    DEFAULT_RMS_THRESHOLD,
    RDKitConformerProvider,
    comparison_skeleton,
    distinct_conformers,
)


def _generate(smiles: str, count: int = 10):
    return RDKitConformerProvider().generate_conformers(
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
