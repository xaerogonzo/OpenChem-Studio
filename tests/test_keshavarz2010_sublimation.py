"""Keshavarz (2010) sublimation-enthalpy model (Eq. 3), checked against a strongly-identified row from
the paper's own Table 1 and computed for the rest of this survey's corpus. See the module docstring in
`benchmarks/thermophysical/keshavarz2010_sublimation.py` for the identification confidence caveat.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ks():
    path = ROOT / "benchmarks" / "thermophysical" / "keshavarz2010_sublimation.py"
    spec = importlib.util.spec_from_file_location("keshavarz2010_sublimation", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _mw(c, h, n, o):
    return c * 12.011 + h * 1.008 + n * 14.007 + o * 16.00


def test_hmx_matches_the_papers_own_printed_calculated_value(ks):
    """Table 1's first 'cyclic and acyclic nitramines' row: Hsub(exp)=175.3, Hsub(cal)=174.6 -- almost
    certainly HMX by magnitude (the largest, best-known cyclic nitramine in this class). HMX has 4
    N-NO2 groups: C = 1.75*4 - 4 = 3, so CIn=3 (C >= 0)."""
    c_in, c_de = ks.nitramine_correction(4)
    assert (c_in, c_de) == (3.0, 0.0)
    value = ks.compute_hsub(_mw(4, 8, 8, 8), c_in=c_in, c_de=c_de)
    assert value == pytest.approx(174.6, abs=0.2)


def test_nitramine_correction_sign_rule(ks):
    """A nitramine with few enough N-NO2 groups gives a NEGATIVE C, which becomes CDe (positive
    magnitude), not a negative CIn -- e.g. a single acyclic N-NO2 (n=1): C = 1.75-4 = -2.25."""
    c_in, c_de = ks.nitramine_correction(1)
    assert c_in == 0.0
    assert c_de == pytest.approx(2.25)


def test_tnt_alkyl_ratio_does_not_meet_the_cde_threshold(ks):
    """TNT: 1 methyl / 3 nitro = 0.33, below the Sec. 3.1.2 threshold of n_R/n_NO2 >= 1 -- CDe stays 0
    despite the alkyl group being present. A real, checked feature of the rule, not an oversight."""
    c_in, c_de = ks.nitroaromatic_correction(n_r_over_no2=1 / 3)
    assert (c_in, c_de) == (0.0, 0.0)


def test_tatb_amino_correction(ks):
    """TATB: 3 amino groups, Sec. 3.1.1(ii) CIn = n_NH2 -- the paper names TATB explicitly as the
    motivating example for this rule."""
    c_in, c_de = ks.nitroaromatic_correction(n_nh2=3)
    assert (c_in, c_de) == (3.0, 0.0)


@pytest.mark.parametrize(
    ("name", "formula", "corr"),
    [
        ("RDX", (3, 6, 6, 6), {"n_n_no2": 3}),
        ("PETN", (5, 8, 4, 12), None),
        ("TNT", (7, 5, 3, 6), {"n_r_over_no2": 1 / 3}),
        ("TATB", (6, 6, 6, 6), {"n_nh2": 3}),
    ],
)
def test_corpus_predictions_are_recorded_not_yet_all_independently_checked(ks, name, formula, corr):
    """Locks in this survey's own computed sublimation enthalpies so a future code change is visible.
    Only HMX (above) has been checked against the paper's own table; RDX/PETN/TNT/TATB are computed,
    not yet verified against an independent measured value -- do not treat these numbers as validated
    without that check."""
    c, h, n, o = formula
    if corr is None:
        c_in = c_de = 0.0
    elif "n_n_no2" in corr:
        c_in, c_de = ks.nitramine_correction(corr["n_n_no2"])
    else:
        c_in, c_de = ks.nitroaromatic_correction(**corr)
    value = ks.compute_hsub(_mw(c, h, n, o), c_in=c_in, c_de=c_de)
    expected = {"RDX": 130.4, "PETN": 138.0, "TNT": 114.3, "TATB": 164.5}[name]
    assert value == pytest.approx(expected, abs=0.2)
