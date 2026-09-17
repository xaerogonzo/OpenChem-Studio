"""The clean-room QTPIE instrument (qtpie_cleanroom_preregistration.md, section 3).

The expected values are re-derived by hand here rather than taken from the module under test.
"""

from __future__ import annotations

import importlib.util
import math
import pathlib
import sys

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("qtpie_cleanroom_check", ROOT / "benchmarks" / "charges" / "models" / "qtpie_cleanroom_check.py")
qc = importlib.util.module_from_spec(_spec)
sys.modules["qtpie_cleanroom_check"] = qc
_spec.loader.exec_module(qc)

EXP = qc.EXPONENTS["E_app"]


def _diatomic_by_hand(r_angstrom: float, model: str, kernel: str) -> float:
    ev = 3.67493245e-2
    r = r_angstrom / 0.529177249
    a, b = EXP["Na"], EXP["Cl"]
    chi_na, j_na = 2.843 * ev, 4.592 * ev
    chi_cl, j_cl = 8.564 * ev, 9.892 * ev
    p = math.sqrt(a * b / (a + b)) if kernel == "K_code" else math.sqrt(2 * a * b / (a + b))
    j12 = math.erf(p * r) / r
    if model == "QEq":
        v_na, v_cl = chi_na, chi_cl
    else:
        s = (4 * a * b / (a + b) ** 2) ** 0.75 * math.exp(-a * b / (a + b) * r * r)
        v_na = (chi_na - chi_cl) * s / (1 + s)
        v_cl = (chi_cl - chi_na) * s / (1 + s)
    return (v_cl - v_na) / (j_na + j_cl - 2 * j12)


@pytest.mark.parametrize("model", ["QEq", "QTPIE"])
@pytest.mark.parametrize("kernel", qc.KERNELS)
def test_a_diatomic_matches_the_closed_form(model, kernel):
    assert qc.nacl(2.36, model, EXP, kernel) == pytest.approx(_diatomic_by_hand(2.36, model, kernel), abs=1e-13)


def test_qtpie_charge_transfer_vanishes_at_dissociation_and_qeq_does_not():
    assert abs(qc.nacl(40.0, "QTPIE", EXP, "K_code")) < 1e-8
    assert abs(qc.nacl(40.0, "QEq", EXP, "K_code")) > 0.1


def test_qtpie_equals_qeq_when_every_overlap_is_one(monkeypatch):
    coords = qc.water_coords(0.96, 0.97, 104.0)
    monkeypatch.setattr(qc, "overlap", lambda a, b, r: 1.0)
    qtpie = qc.charges(["O", "H", "H"], coords, "QTPIE", EXP, "K_code")
    # with S = 1 everywhere, v_i = chi_i - mean(chi): the constant shift is absorbed by mu
    monkeypatch.undo()
    qeq = qc.charges(["O", "H", "H"], coords, "QEq", EXP, "K_code")
    assert np.allclose(qtpie, qeq, atol=1e-12)


@pytest.mark.parametrize("model", ["QEq", "QTPIE"])
def test_charges_sum_to_zero(model):
    q = qc.charges(["O", "H", "H"], qc.water_coords(0.96, 0.97, 104.0), model, EXP, "K_print")
    assert abs(q.sum()) < 1e-12


def test_overlap_is_symmetric_bounded_and_one_on_the_diagonal():
    assert qc.overlap(0.3, 0.3, 0.0) == pytest.approx(1.0, abs=1e-15)
    assert qc.overlap(0.1, 0.5, 1.7) == pytest.approx(qc.overlap(0.5, 0.1, 1.7), abs=1e-15)
    assert 0 < qc.overlap(0.1, 0.5, 1.7) < 1 and qc.overlap(0.1, 0.5, 0.0) < 1


@pytest.mark.parametrize("kernel", qc.KERNELS)
def test_both_kernels_tend_to_one_over_r(kernel):
    assert qc.coulomb_kernel(0.2, 0.5, 60.0, kernel) == pytest.approx(1.0 / 60.0, rel=1e-12)
    assert qc.coulomb_kernel(0.2, 0.5, 1.0, "K_print") > qc.coulomb_kernel(0.2, 0.5, 1.0, "K_code")
