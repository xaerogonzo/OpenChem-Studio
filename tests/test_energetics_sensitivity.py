"""The sensitivity tool's arithmetic is checked against the equation it differentiates.

`tools/energetics_sensitivity.py` reports how the Kamlet-Jacobs estimate moves with its two inputs. What is
tested here is that its ANALYTIC elasticities are the derivatives of the module's own equations (a finite
difference through the real function agrees), that its nominal point is the paper's printed row, and that it
says what it is not: it does not compute a realistic input uncertainty, and its default sigmas are labelled
illustrative.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest
from rdkit import Chem

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("energetics_sensitivity", ROOT / "tools" / "energetics_sensitivity.py")
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE it runs: a dataclass in a module using `from __future__ import annotations` looks
    # its own module up in `sys.modules`, and an unregistered one fails with an AttributeError that reads
    # like a bug in the tool.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rdx(tool):
    mol = Chem.MolFromSmiles(tool.RDX_TABLE_III["smiles"])
    return mol, tool.RDX_TABLE_III["rho"], tool.enthalpy_implied_by_q(mol, tool.RDX_TABLE_III["q_cal_per_g"])


def test_the_nominal_point_is_the_papers_printed_row(tool, rdx):
    """Kamlet-Jacobs 1968 Table III, RDX: P 311.9 kbar, D 8.512 mm/us. From the FORMULA (not the printed N and
    M) the module lands within a kbar, which is the rounding of the printed inputs."""
    mol, rho, enthalpy = rdx
    point = tool.evaluate(mol, rho, enthalpy)
    assert point.q == pytest.approx(1496.0, abs=0.5), "the enthalpy is what Eq. (15b) inverts to"
    assert point.p == pytest.approx(tool.RDX_TABLE_III["printed_p_kbar"], abs=1.0)
    assert point.d == pytest.approx(tool.RDX_TABLE_III["printed_d_mm_us"], abs=0.02)


def _log_slope(f, x, step=1e-5):
    return (math.log(f(x * (1 + step))) - math.log(f(x * (1 - step)))) / (math.log(1 + step) - math.log(1 - step))


def test_the_analytic_density_elasticities_are_the_derivatives_of_the_equations(tool, rdx):
    mol, rho, enthalpy = rdx
    slopes = tool.local_sensitivity(mol, rho, enthalpy)
    assert _log_slope(lambda r: tool.evaluate(mol, r, enthalpy).p, rho) == pytest.approx(slopes["dlnP_dlnrho"], rel=1e-4)
    assert _log_slope(lambda r: tool.evaluate(mol, r, enthalpy).d, rho) == pytest.approx(slopes["dlnD_dlnrho"], rel=1e-4)
    assert slopes["dlnP_dlnrho"] == 2.0, "P goes as the square of the loading density"


def test_the_analytic_enthalpy_slopes_are_the_derivatives_of_the_equations(tool, rdx):
    mol, rho, enthalpy = rdx
    slopes = tool.local_sensitivity(mol, rho, enthalpy)
    h = 1e-3
    for name, key in (("p", "dlnP_dH_per_kcal"), ("d", "dlnD_dH_per_kcal"), ("q", "dlnQ_dH_per_kcal")):
        up = getattr(tool.evaluate(mol, rho, enthalpy + h), name)
        down = getattr(tool.evaluate(mol, rho, enthalpy - h), name)
        assert (math.log(up) - math.log(down)) / (2 * h) == pytest.approx(slopes[key], rel=1e-4), key


def test_a_finite_step_is_not_the_slope_because_pressure_goes_as_rho_squared(tool, rdx):
    """The reason step (2) exists beside step (1): +sigma and -sigma in density do not move P equally."""
    mol, rho, enthalpy = rdx
    rows = {r["label"]: r for r in tool.perturb(mol, rho, enthalpy, 0.04, 9.3)}
    assert rows["rho +0.04"]["dP_pct"] > -rows["rho -0.04"]["dP_pct"] > 0


def test_for_rdx_the_density_step_moves_pressure_more_than_the_enthalpy_step(tool, rdx):
    """One compound, at ILLUSTRATIVE sigmas -- a worked example, never a statement about a set."""
    mol, rho, enthalpy = rdx
    rows = {r["label"]: r for r in tool.perturb(mol, rho, enthalpy, 0.04, 9.3)}
    assert abs(rows["rho +0.04"]["dP_pct"]) > 2 * abs(rows["H +9.3"]["dP_pct"])
    assert abs(rows["H +9.3"]["dQ_pct"]) > 2.0, "while the enthalpy step moves Q itself the most"


def test_a_compound_the_method_cannot_use_raises_rather_than_returning_a_number(tool):
    nitroglycerin = Chem.MolFromSmiles("O=[N+]([O-])OCC(O[N+](=O)[O-])CO[N+](=O)[O-]")
    with pytest.raises(ValueError, match="does not apply"):
        tool.evaluate(nitroglycerin, 1.6, -82.7)


def test_the_report_labels_default_sigmas_illustrative_and_says_realistic_uncertainty_is_not_computed(tool, rdx, capsys):
    mol, rho, enthalpy = rdx
    text = tool.report(mol, rho, enthalpy, 0.04, 9.3, sigmas_are_defaults=True)
    assert "ILLUSTRATIVE" in text and "NOT computed here" in text
    assert "ILLUSTRATIVE" not in tool.report(mol, rho, enthalpy, 0.03, 5.0, sigmas_are_defaults=False)


def test_the_command_line_runs_the_worked_example(tool, capsys):
    assert tool.main(["--preset", "rdx-table-iii"]) == 0
    assert "Kamlet-Jacobs 1968 Table III" in capsys.readouterr().out
