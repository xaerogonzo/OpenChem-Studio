"""`solubility` on radicals (the last item of OS4 in docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md).

The rule was committed before ESOL was run on the molecules (`benchmarks/open_shell/solubility_rule.py`): ESOL minus the measured logS of five 4-substituted TEMPO radicals in pure water (Zhou et al. 2020, Table 1),
each compared with ESOL's own usual error of 1.26. Measured: too LOW on all five, by 0.63 to 2.61 log units (mean -1.69), three beyond 1.26, so NOT CONSISTENT, and the calculator says so.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem import solubility as sol

_PATH = Path(__file__).parent.parent / "benchmarks" / "open_shell" / "solubility_rule.py"
_spec = importlib.util.spec_from_file_location("solubility_rule", _PATH)
rule = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rule
_spec.loader.exec_module(rule)

TEMPOL = "CC1(C)CC(O)CC(C)(C)N1[O]"


# --- the rule ---------------------------------------------------------------------------------------------------------------------------------


def _errors(values):
    return {r.name: v for r, v in zip(rule.PANEL, values)}


def test_the_verdict_counts_how_many_exceed_the_usual_error_and_the_boundary_is_not_exceeded():
    assert rule.verdict(_errors([0.1, -0.5, 1.26, -1.0, 0.2]))[:2] == (rule.CONSISTENT, 0), "exactly 1.26 does not exceed it"
    assert rule.verdict(_errors([0.1, -0.5, 1.27, -1.0, 0.2]))[:2] == (rule.MIXED, 1)
    assert rule.verdict(_errors([-2.2, -2.1, 0.1, -1.0, 0.2]))[:2] == (rule.NOT_CONSISTENT, 2)


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_a_missing_or_non_finite_error_is_inconclusive_never_consistent(bad):
    assert rule.verdict(_errors([0.1, 0.1, 0.1, 0.1, bad])) == ("INCONCLUSIVE", 0, None)
    assert rule.verdict({"only one": 0.1}) == ("INCONCLUSIVE", 0, None)


def test_the_reference_values_are_the_five_of_zhou_table_1():
    assert {r.name: r.molar for r in rule.PANEL} == {
        "4-hydroxy-TEMPO": 2.11, "4-oxo-TEMPO": 1.22, "4-amino-TEMPO": 5.79, "4-cyano-TEMPO": 0.026, "4-carboxy-TEMPO": 0.021,
    }
    for radical in rule.PANEL:
        assert Chem.MolFromSmiles(radical.smiles).GetNumHeavyAtoms() > 10


def test_the_note_states_the_numbers_this_application_measures_against_those_references():
    """Every figure in the warning is recomputed here from the rule's data and the shipped ESOL, so it cannot drift from the measurement."""
    predicted = {r.name: sol.esol_logs(Chem.MolFromSmiles(r.smiles)) for r in rule.PANEL}
    errors = rule.errors(predicted)
    verdict, exceeding, mean = rule.verdict(errors)
    assert verdict == rule.NOT_CONSISTENT and exceeding == 3
    assert all(e < 0 for e in errors.values()), "too LOW on every one"
    assert f"{min(abs(e) for e in errors.values()):.1f}" == "0.6" and f"{max(abs(e) for e in errors.values()):.1f}" == "2.6" and f"{abs(mean):.1f}" == "1.7"
    assert "by 0.6 to 2.6 log units (mean 1.7)" in sol.OPEN_SHELL_ESOL_NOTE and "three of the five" in sol.OPEN_SHELL_ESOL_NOTE and "1.26" in sol.OPEN_SHELL_ESOL_NOTE
    assert sol.OPEN_SHELL_ESOL_NOTE.count("doi") == 0 and "Zhou et al. 2020" in sol.OPEN_SHELL_ESOL_NOTE


# --- the consumers ----------------------------------------------------------------------------------------------------------------------------


def test_a_radical_gets_the_warning_and_a_closed_shell_molecule_does_not():
    assert sol.open_shell_warning(Chem.MolFromSmiles(TEMPOL)) == sol.OPEN_SHELL_ESOL_NOTE
    assert sol.open_shell_warning(Chem.MolFromSmiles("O=O")) == sol.OPEN_SHELL_ESOL_NOTE, "triplet O2 drawn closed-shell is open-shell"
    assert sol.open_shell_warning(Chem.MolFromSmiles(TEMPOL), sol.AQSOLDB) == sol.OPEN_SHELL_UNCHECKED_NOTE
    for closed in ("CCO", "CC1(C)CC(O)CC(C)(C)N1O", "c1ccccc1"):
        assert sol.open_shell_warning(Chem.MolFromSmiles(closed)) == ""


def test_the_report_leads_with_a_baseline_row_carries_the_limitation_and_records_it_in_provenance():
    report = sol.compute_solubility(Chem.MolFromSmiles(TEMPOL), "u", {"model": "esol"})
    assert report.facts[0].label == "Baseline reliability" and report.facts[0].value == "ESOL runs low on radicals"
    assert sol.OPEN_SHELL_ESOL_NOTE in report.facts[0].evidence and sol.OPEN_SHELL_ESOL_NOTE in report.limitations
    assert report.provenance.parameters["open_shell_note"] == sol.OPEN_SHELL_RECORD_CODE
    assert any(f.label == "Predicted intrinsic solubility (log mol/L)" for f in report.facts), "the number is still given, with its warning"


def test_the_ich_m9_screen_is_withheld_for_the_open_shell_reason():
    report = sol.compute_solubility(Chem.MolFromSmiles(TEMPOL), "u", {"model": "esol", "dose_mg": 100})
    screen = next(f for f in report.facts if f.label.startswith("BCS high-solubility"))
    assert screen.value == "UNDETERMINED" and sol.BcsReason.OPEN_SHELL.value in repr(screen)


def test_a_closed_shell_molecule_is_unchanged():
    report = sol.compute_solubility(Chem.MolFromSmiles("CC1(C)CC(O)CC(C)(C)N1O"), "u", {"model": "esol"})
    assert all(f.label != "Baseline reliability" for f in report.facts)
    assert report.provenance.parameters["open_shell_note"] == ""
    assert sol.OPEN_SHELL_ESOL_NOTE not in report.limitations


def test_the_note_reaches_the_analysis_in_every_branch_including_a_solvent_that_is_not_covered_and_the_unchecked_model():
    mol = Chem.MolFromSmiles(TEMPOL)
    assert sol.analyse_solubility(mol, {"model": "esol", "solvent": "1,4-dioxane"}).open_shell_note == sol.OPEN_SHELL_ESOL_NOTE
    assert sol.analyse_solubility(mol, {"model": "aqsoldb"}).open_shell_note == sol.OPEN_SHELL_UNCHECKED_NOTE


def test_the_note_survives_the_non_aqueous_branch_that_computes(monkeypatch):
    """A radical is never in the measured-solute table, so this branch is only reached by a solvent shift standing in for a covered one."""
    monkeypatch.setattr("openchem.chem.abraham.solvent_shift", lambda mol, label: object())
    analysis = sol.analyse_solubility(Chem.MolFromSmiles(TEMPOL), {"model": "esol", "solvent": "1,4-dioxane"})
    assert not analysis.refusal_code and analysis.open_shell_note == sol.OPEN_SHELL_ESOL_NOTE
