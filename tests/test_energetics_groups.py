"""The scoped Marrero-Gani group counter (`benchmarks/thermophysical/energetics_groups.py`), checked two
ways: against every hand decomposition already published in `compare_energetics.py`, and for
representation invariance (Track 1 step 3 of the research plan -- a group-contribution assignment must
not depend on SMILES atom order or ring-traversal direction).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from rdkit import Chem

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def eg():
    path = ROOT / "benchmarks" / "thermophysical" / "energetics_groups.py"
    spec = importlib.util.spec_from_file_location("energetics_groups", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def compare_module():
    path = ROOT / "benchmarks" / "thermophysical" / "compare_energetics.py"
    spec = importlib.util.spec_from_file_location("compare_energetics", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_reproduces_every_already_published_hand_decomposition(eg, compare_module):
    """A mismatch here means either this counter or `compare_energetics.py`'s hand decomposition is
    wrong -- never a shrug, per the research plan's own standard. Rows with `groups: None` are
    documented refusals (checked separately, below) and have nothing to reproduce."""
    for name, spec in compare_module.MOLECULES.items():
        if spec["groups"] is None:
            continue
        assert eg.count_groups(spec["smiles"]) == spec["groups"], name


def test_reproduces_every_documented_refusal_too(eg, compare_module):
    for name, spec in compare_module.MOLECULES.items():
        if spec["groups"] is not None:
            continue
        with pytest.raises(ValueError):
            eg.count_groups(spec["smiles"])


@pytest.mark.parametrize(
    "smiles",
    [
        "O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]",  # RDX
        "Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",  # TNT
        "CN(c1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",  # tetryl
        "C(C(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-])O[N+](=O)[O-]",  # PETN
    ],
)
def test_group_counts_are_invariant_to_representation(eg, smiles):
    """Rewrite the molecule as several differently-rooted, differently-traversed, differently-kekulized
    SMILES (RDKit's own randomized writer, not hand-picked variants) and require identical group counts
    from every one -- a real check that the assignment is a property of the molecule, not the string."""
    mol = Chem.MolFromSmiles(smiles)
    expected = None
    for seed in range(12):
        variant = Chem.MolToSmiles(mol, canonical=False, doRandom=True)
        counts = eg.count_groups(variant)
        if expected is None:
            expected = counts
        assert counts == expected, f"seed {seed}: {variant!r} gave {counts}, expected {expected}"


def test_new_diagnostic_corpus_molecules_decompose_cleanly(eg):
    """`tests/fixtures/census_panel.toml`'s diagnostic-set rows this track adds: each should decompose
    with no uncovered atom, confirming the by-hand reasoning in the research plan's Track 1 notes."""
    cases = {
        "dinitrodiazetidine": (
            "O=[N+]([O-])N1CN([N+](=O)[O-])C1",
            {"N (cyclic)": 2, "NO2 except as above": 2, "CH2 (cyclic)": 2},
        ),
        "tetryl": (
            "CN(c1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
            {"aC-NO2": 3, "aC-N": 1, "aCH": 2, "NO2 except as above": 1, "CH3": 1},
        ),
        "tatb": (
            "Nc1c(N)c([N+](=O)[O-])c(N)c([N+](=O)[O-])c1[N+](=O)[O-]",
            {"aC-NO2": 3, "aC-NH2": 3},
        ),
        "nitroglycerin": (
            "C(C(CO[N+](=O)[O-])O[N+](=O)[O-])O[N+](=O)[O-]",
            {"ONO2": 3, "CH2": 2, "CH": 1},
        ),
    }
    for name, (smiles, expected) in cases.items():
        assert eg.count_groups(smiles) == expected, name


def test_nitroguanidine_refuses_at_its_guanidine_core(eg):
    """No group in Table 6 covers a C=N in a guanidine context (the CH=N/C=N groups are for
    aldazine/ketazine only). A generic NH2 IS covered (row 65), so only the C=N-NH-NO2 core should be
    uncovered -- confirming this is a genuine gap, not a missing pattern for the whole molecule."""
    with pytest.raises(ValueError) as exc:
        eg.count_groups("NC(=N)N[N+](=O)[O-]")
    assert "[1, 2, 3]" in str(exc.value)


def test_ammonium_nitrate_refuses_as_ionic(eg):
    """Marrero-Gani's groups describe organic molecular structures; an ammonium cation and a nitrate
    anion are neither, and should refuse rather than silently match something they aren't."""
    with pytest.raises(ValueError):
        eg.count_groups("[NH4+].[O-][N+](=O)[O-]")
