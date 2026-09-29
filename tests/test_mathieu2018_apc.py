"""Mathieu (2018) APC gas-phase DfH model -- checked against three real primary-source experimental
values (Lange's Handbook Table 6.1), not the paper's own claimed statistics (its training/test sets,
Tables S4/S5, are Supporting Information -- not held). See the module docstring in
`benchmarks/thermophysical/mathieu2018_apc.py` for the nitro-group bond-order finding these checks
established.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def apc():
    path = ROOT / "benchmarks" / "thermophysical" / "mathieu2018_apc.py"
    spec = importlib.util.spec_from_file_location("mathieu2018_apc", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_benzene_matches_lange_within_2_kjmol(apc):
    """No nitro-group interpretation needed here -- isolates the bond/geminal/atomic-reference
    transcription itself, independent of the nitro-group finding checked below."""
    value = apc.compute_hf("c1ccccc1")
    assert value == pytest.approx(82.6, abs=2.0)


def test_nitromethane_matches_lange_within_35_kjmol(apc):
    """The check that found the nitro-group bond-order convention: a naive charge-separated
    single/double assignment misses by 300+ kJ/mol; both N-O bonds as N=O (double) gets to 33.2."""
    value = apc.compute_hf("C[N+](=O)[O-]")
    assert value == pytest.approx(-74.3, abs=35.0)


def test_methyl_nitrate_matches_lange_within_15_kjmol(apc):
    """A nitrate ester (O-NO2, not C-NO2) -- confirms the same nitro-group convention generalizes to
    a different attachment point, and exercises the geminal O..O/C..N pairs at the bridging ester O."""
    value = apc.compute_hf("CO[N+](=O)[O-]")
    assert value == pytest.approx(-124.4, abs=15.0)


def test_naive_charge_separated_nitro_bonds_would_fail_nitromethane_by_300_kjmol(apc):
    """Locks in the magnitude of the wrong-convention error so it is not silently rediscovered: the
    charge-separated Lewis structure (one N=O double, one N-O(-) single) is what RDKit's own
    sanitizer would assign by default, and it is NOT what this model's own tables reproduce against."""
    naive = (
        apc.ATOM_HF["C"] + 3 * apc.ATOM_HF["H"] + apc.ATOM_HF["N"] + 2 * apc.ATOM_HF["O"]
        + 3 * apc.BOND_HF[(("C", "H"), apc.BondType.SINGLE)]
        + apc.BOND_HF[(("C", "N"), apc.BondType.SINGLE)]
        + apc.BOND_HF[(("N", "O"), apc.BondType.DOUBLE)]
        + apc.BOND_HF[(("N", "O"), apc.BondType.SINGLE)]
        + 3 * apc.GEMINAL_HF[("H", "N")]
        + 2 * apc.GEMINAL_HF[("C", "O")]
        + apc.GEMINAL_HF[("O", "O")]
        + apc.NO2_CORRECTION
    )
    assert naive == pytest.approx(250.08, abs=0.5)
    assert abs(naive - (-74.3)) > 300


@pytest.mark.parametrize(
    ("name", "smiles"),
    [
        ("RDX", "O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]"),
        ("HMX", "O=[N+]([O-])N1CN(CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]"),
        ("PETN", "C(C(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-])O[N+](=O)[O-]"),
    ],
)
def test_corpus_gas_phase_predictions_are_recorded_not_yet_independently_verified(apc, name, smiles):
    """Locks in this survey's own computed gas-phase DfH so a future change to the module is visible.
    No experimental gas-phase DfH for RDX/HMX/PETN has been verified against a primary source in this
    session (rarely measured directly -- these compounds decompose before vaporizing) -- these values
    feed the combined route in docs/research/literature.toml's mathieu2018_apc entry, not a validated
    claim about RDX/HMX/PETN's true gas-phase enthalpy."""
    expected = {"RDX": 180.50, "HMX": 240.66, "PETN": -344.00}[name]
    value = apc.compute_hf(smiles)
    assert value == pytest.approx(expected, abs=0.2)


def test_rdx_ring_gets_no_structural_correction(apc):
    """RDX's 6-membered ring and HMX's 8-membered ring both fall outside the R3/R4/R5 corrections this
    module implements (only 3-, 4-, and 5-membered rings get one) -- a real, checked feature of the
    model (6-membered rings are its strain-free reference size), not a gap in this module."""
    rdx = apc.compute_hf("O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]")
    # Recompute with the ring-correction step forced off by using an acyclic proxy is not meaningful
    # here (would change the bond graph); instead assert RDX's value is unaffected by R3/R4/R5 by
    # construction -- there is no 3/4/5-membered ring in this molecule's RDKit ring info.
    from rdkit import Chem

    mol = Chem.AddHs(Chem.MolFromSmiles("O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]"))
    ring_sizes = {len(r) for r in mol.GetRingInfo().BondRings()}
    assert ring_sizes == {6}
    assert rdx == pytest.approx(180.50, abs=0.2)
