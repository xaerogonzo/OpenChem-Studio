"""Keshavarz (2009) nitroaromatic condensed-Hf model (Eq. 2), checked against the paper's own Table 1
and Table 3 rows -- the reproduction that `keshavarz_sadeghi2009`'s sister paper FAILED (see that
entry's note in docs/research/literature.toml). This model passes: every row checked here reproduces
the paper's own printed value within rounding.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ka():
    path = ROOT / "benchmarks" / "thermophysical" / "keshavarz_nitroaromatic2009.py"
    spec = importlib.util.spec_from_file_location("keshavarz_nitroaromatic2009", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_1_3_dinitrobenzene_no_corrections(ka):
    """Table 1: C6H4N2O4, MW 168.112, no DFG/IFG groups -- printed New method -49.3."""
    value = ka.compute_hf(n_c=6, n_h=4, n_n=2, n_o=4, molar_mass=168.112, n_aromatic_rings=1)
    assert value == pytest.approx(-49.3, abs=0.1)


def test_1_4_and_1_2_dinitrobenzene_give_the_same_value_as_1_3(ka):
    """The model is elemental-composition-based with zero structural correction for any of these three
    isomers -- Table 1 prints -49.3 for all three, which is itself a real fact about the model's
    resolution (it cannot distinguish ortho/meta/para without a triggered DFG/IFG term), not a bug."""
    value = ka.compute_hf(n_c=6, n_h=4, n_n=2, n_o=4, molar_mass=168.112, n_aromatic_rings=1)
    assert value == pytest.approx(-49.3, abs=0.1)


def test_dinitrophenol_with_the_oh_decreasing_term(ka):
    """Table 1: C6H4N2O5, MW 184.112, one OH with nNO2=2 -> E=0.5. Printed DFG column is 0.5 exactly
    (not 1.0, which a literal (nNO2/nOH)*E reading would give) -- this is the row that caught the bug."""
    term = ka.decreasing_term(2, n_oh=1)
    assert term == pytest.approx(0.5)
    value = ka.compute_hf(n_c=6, n_h=4, n_n=2, n_o=5, molar_mass=184.112, n_aromatic_rings=1, dfg_term=term)
    assert value == pytest.approx(-240.0, abs=0.2)


def test_dinitrotoluene_with_the_alkyl_increasing_term(ka):
    """Table 3: C7H6N2O4, MW 182.139, one methyl with nNO2=2 -> F term (1/2)*2.0=1.0, printed IFG
    column is 1 exactly. This is the row confirming the increasing_term/F branch independently of the
    decreasing_term bug found via dinitrophenol."""
    term = ka.increasing_term(2, n_alkyl_or_alkoxy=1)
    assert term == pytest.approx(1.0)
    value = ka.compute_hf(n_c=7, n_h=6, n_n=2, n_o=4, molar_mass=182.139, n_aromatic_rings=1, ifg_term=term)
    assert value == pytest.approx(-37.6, abs=0.2)


def test_nhx_linked_diphenylamine_decreasing_term(ka):
    """Table 3: an N-H bridging two nitrophenyl rings, one NHx group, nNO2=2 (one per ring) -> E=0.75
    per Sec. 3.2(b). Printed DFG column is 0.75 exactly, confirming the term equals E directly for the
    NHx rule too, not just for OH."""
    assert ka.decreasing_term(2, n_nhx=1) == pytest.approx(0.75)


def test_dinitronaphthalene_decreasing_term_is_the_fixed_constant(ka):
    """Table 3: Sec. 3.2(d) gives BOTH n_DFG/SP and E as fixed constants (2.0, 1.0) for polynitro
    naphthalene -- the printed DFG column is 2.0 (= n_DFG/SP itself), not 1.0 (= E alone) and not any
    ratio combining them. A distinct code path from the OH/NHx/COOH rules for exactly this reason."""
    assert ka.decreasing_term(2, n_naphthalene=1) == pytest.approx(2.0)


def test_tnt_matches_an_independent_primary_source(ka):
    """TNT (C7H5N3O6, MW 227.13, one methyl -> IFG term (1/3)*2.0): this model predicts -68.8 kJ/mol.
    Klapoetke (klapotke2017, p. 243, already cited in docs/sources.toml) states TNT's DfH = -295.5
    kJ/kg, which for TNT's own molar mass converts to -295.5 * 0.22713 = -67.1 kJ/mol -- independent
    agreement within 1.7 kJ/mol, far inside SENSITIVITY.md's ~21 kJ/mol screening bar."""
    term = ka.increasing_term(3, n_alkyl_or_alkoxy=1)
    value = ka.compute_hf(n_c=7, n_h=5, n_n=3, n_o=6, molar_mass=227.13, n_aromatic_rings=1, ifg_term=term)
    klapotke_value = -295.5 * (227.13 / 1000)
    assert value == pytest.approx(klapotke_value, abs=2.0)


def test_tatb_prediction_is_recorded_but_not_yet_checked_against_a_measured_value(ka):
    """TATB (C6H6N6O6, MW 258.156, three NH2 -> DFG term via nNHx=3>1, E=0.67): this model gives
    -68.2 kJ/mol. No measured condensed Hf for TATB has been verified against a primary source in this
    session -- this test locks the COMPUTED value so a future change is visible, not a claim that
    -68.2 kJ/mol is correct."""
    term = ka.decreasing_term(3, n_nhx=3)
    value = ka.compute_hf(n_c=6, n_h=6, n_n=6, n_o=6, molar_mass=258.156, n_aromatic_rings=1, dfg_term=term)
    assert value == pytest.approx(-68.2, abs=0.1)
