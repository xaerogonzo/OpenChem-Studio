"""The S-H and bromine reference inputs of `benchmarks/restart_v3/PREREGISTRATION.md` (`benchmarks/restart_v3/references.json`).

Like the halogen arm's test, this recomputes every derived number from the inputs the papers print instead of restating it, so a number in the preregistration cannot drift from its arithmetic. What it adds: the one derived value that a paper
ALSO publishes (ethanethiol's S-H) is held to the published figure, which is the check that the cycle used for the propanethiols is the paper's own cycle.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest
from rdkit import Chem

_FILE = Path(__file__).parent.parent / "benchmarks" / "restart_v3" / "references.json"
DATA = json.loads(_FILE.read_text(encoding="utf-8"))
C = DATA["constants"]
SH = DATA["sh_bonds"]
BR = DATA["bromine_bonds"]

#: Decision D1 of the preregistration: the numerical frequency job is run on radicals of at most this many atoms.
ATOM_CAP = 12


def _d0_kj(bond: dict) -> float:
    """D0(RS-H) = acidity(0 K) + EA - IE(H), the cycle Ervin 2015 and Moran and Ellison 1988 write as their equation."""
    ie_h = C["ionization_energy_of_hydrogen_ev"] * C["kj_per_mol_per_ev"]
    return bond["acidity_dH0_kj"] + bond["electron_affinity_ev"] * C["kj_per_mol_per_ev"] - ie_h


def _d0_unc_kj(bond: dict) -> float:
    return math.hypot(bond["acidity_dH0_uncertainty_kj"], bond["electron_affinity_uncertainty_ev"] * C["kj_per_mol_per_ev"])


def _radical_atoms(parent_smiles: str) -> int:
    """The radical is the thiol minus one hydrogen."""
    return Chem.AddHs(Chem.MolFromSmiles(parent_smiles)).GetNumAtoms() - 1


def test_ethanethiol_is_the_published_value_and_the_cycle_reproduces_it():
    ethyl = SH[0]
    assert ethyl["name"] == "ethanethiol S-H"
    # the cycle, from the two printed inputs, against the paper's own D0 (rounding only) ...
    assert _d0_kj(ethyl) == pytest.approx(ethyl["published_d0_kj"], abs=0.3)
    # ... and, with the paper's own thermal step, against its D298
    assert _d0_kj(ethyl) + C["d0_to_d298_ethanethiol_kj"] == pytest.approx(ethyl["published_d298_kj"], abs=0.3)
    assert ethyl["published_d298_kj"] / C["kj_per_kcal"] == pytest.approx(ethyl["published_d298_kcal"], abs=0.01)
    assert ethyl["published_d298_uncertainty_kj"] / C["kj_per_kcal"] == pytest.approx(ethyl["published_d298_uncertainty_kcal"], abs=0.01)
    # the thermal step borrowed for the other bonds is exactly the paper's own difference
    assert ethyl["published_d298_kj"] - ethyl["published_d0_kj"] == pytest.approx(C["d0_to_d298_ethanethiol_kj"], abs=0.05)


def _step_kj(bond: dict) -> tuple[float, float]:
    """The 0 K to 298 K step and its uncertainty a derived bond carries: the one COMPUTED in `thermal_step.py` where the bond has one, the borrowed ethyl step (excluded bond only) otherwise."""
    if "thermal_step_kj" in bond:
        return bond["thermal_step_kj"], bond["thermal_step_uncertainty_kj"]
    return C["d0_to_d298_ethanethiol_kj"], C["borrowed_thermal_uncertainty_kj"]


@pytest.mark.parametrize("bond", SH[1:], ids=lambda b: b["name"])
def test_each_derived_sh_reference_is_its_inputs_combined_as_the_definition_says(bond):
    d0 = _d0_kj(bond)
    assert d0 == pytest.approx(bond["stated_d0_kj"], abs=0.01)
    step, step_unc = _step_kj(bond)
    assert (d0 + step) / C["kj_per_kcal"] == pytest.approx(bond["stated_d298_kcal"], abs=0.01)
    assert math.hypot(_d0_unc_kj(bond), step_unc) / C["kj_per_kcal"] == pytest.approx(bond["stated_d298_uncertainty_kcal"], abs=0.01)
    assert "not a published number" in bond["d298_status"], "a derived value must say that it is"


def _thermal_records() -> dict:
    """The committed ORCA records of `thermal_step.py`, summarised by the script's own rule."""
    spec = importlib.util.spec_from_file_location("thermal_step_for_references", Path(__file__).parent.parent / "benchmarks" / "restart_v3" / "thermal_step.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["thermal_step_for_references"] = module
    spec.loader.exec_module(module)
    records = [json.loads(line) for line in (Path(__file__).parent.parent / "benchmarks" / "restart_v3" / "artifacts" / "thermal_step" / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert all("error" not in r for r in records)
    out = {}
    for name in {r["name"] for r in records}:
        species = []
        for k in sorted({r["conformer"] for r in records if r["name"] == name}):
            pair = {r["role"]: r for r in records if r["name"] == name and r["conformer"] == k}
            species.append({"parent": pair["parent"], "radical": pair["radical"]})
        out[name] = module.summarise(species)
    return out


def test_the_computed_thermal_steps_are_the_committed_records_summarised():
    """`references.json` states the step; the records are the evidence. A step edited by hand, or a record replaced, fails here."""
    steps = _thermal_records()
    by_name = {b["name"]: b for b in SH}
    for thiol, key in (("1-propanethiol", "1-propanethiol S-H"), ("2-propanethiol", "2-propanethiol S-H")):
        assert by_name[key]["thermal_step_kj"] == pytest.approx(steps[thiol]["step_kj"], abs=0.006)
        assert by_name[key]["thermal_step_uncertainty_kj"] == pytest.approx(max(0.5, steps[thiol]["spread_kj"]), abs=0.006)
    assert by_name["ethanethiol S-H"]["thermal_step_computed_kj"] == pytest.approx(steps["ethanethiol"]["step_kj"], abs=0.006)


def test_the_method_reproduces_the_one_step_a_paper_publishes():
    """Ervin 2015 computed D298 - D0 for ethanethiol: 364.7 - 359.5 = 5.2 kJ/mol. The same method on the propyl cases is only trusted because it gets this one."""
    ethyl = SH[0]
    computed = _thermal_records()["ethanethiol"]["step_kj"]
    assert computed == pytest.approx(ethyl["published_d298_kj"] - ethyl["published_d0_kj"], abs=0.2)


def test_a_species_rejected_from_the_step_is_a_saddle_point_the_report_names():
    """2-propanethiyl: two of three radical conformers came out with a frequency of -233 cm-1 and a LOWER enthalpy than the third. They are not minima and the step is taken from the one that is; the preregistration says so."""
    rejected = _thermal_records()["2-propanethiol"]["rejected"]
    assert len(rejected) == 2 and all(r["role"] == "radical" and r["lowest_frequency"] < -200 for r in rejected)


def test_every_sh_reference_that_is_deciding_passes_the_one_kcal_rule_and_fits_the_atom_cap():
    deciding = [b for b in SH if b["role"] == "Arm D deciding"]
    assert [b["name"] for b in deciding] == ["ethanethiol S-H", "1-propanethiol S-H", "2-propanethiol S-H"]
    for bond in deciding:
        unc_kcal = bond.get("published_d298_uncertainty_kcal", bond.get("stated_d298_uncertainty_kcal"))
        assert unc_kcal <= 1.0, bond["name"]
        assert _radical_atoms(bond["parent_smiles"]) <= ATOM_CAP, bond["name"]


def test_tert_butanethiol_is_left_out_by_the_atom_cap_and_for_no_other_reason():
    tert = next(b for b in SH if b["parent_smiles"] == "CC(C)(C)S")
    assert _radical_atoms(tert["parent_smiles"]) == 14 > ATOM_CAP
    assert tert["role"].startswith("excluded")
    assert tert["stated_d298_uncertainty_kcal"] <= 1.0, "its reference is as good as the others: only its size excludes it"


def test_atom_counts_quoted_in_the_preregistration():
    counts = {b["name"]: _radical_atoms(b["parent_smiles"]) for b in SH}
    assert counts == {
        "ethanethiol S-H": 8,
        "1-propanethiol S-H": 11,
        "2-propanethiol S-H": 11,
        "2-methyl-2-propanethiol S-H": 14,
    }


def test_the_sh_arm_has_no_bond_that_shares_a_parent_with_the_first_run():
    """Methanethiol is the first run's lost bond (spent); it must not reappear as a held-out S-H bond."""
    assert all(b["parent_smiles"] != "CS" for b in SH)


def test_bromine_bonds_are_the_four_the_preregistration_lists_and_carry_their_sources():
    assert [b["name"] for b in BR] == ["bromomethane C-H", "dibromomethane C-H", "bromochloromethane C-H", "bromoethane alpha C-H"]
    for bond in BR:
        assert bond["arm"] == "C-Br, reported only"
        assert bond["kinetics_source"] in {"seetula2003", "seetula2008"}
    assert [b["name"] for b in DATA["bromine_excluded"]] == ["tribromomethane C-H"]


@pytest.mark.parametrize("bond", [b for b in BR if b["theory_fpd_kj"] is not None], ids=lambda b: b["name"])
def test_the_calculation_sits_below_the_kinetics_value_for_every_bromine_bond_it_covers(bond):
    """The direction the preregistration states (section 6): the coupled-cluster values are lower, by 2 to 7 kJ/mol."""
    gap = bond["theory_fpd_kj"] - bond["kinetics_kj"]
    assert -7.0 <= gap <= -2.0, gap


def test_bromoethane_is_flagged_because_its_kinetics_value_is_the_highest_of_the_determinations():
    ethyl_bromide = BR[3]
    others = [d["value"] for d in ethyl_bromide["other_determinations_kj"]]
    assert ethyl_bromide["kinetics_kj"] > max(others)
    # about two kcal/mol above the best of the others, as the preregistration says
    assert (ethyl_bromide["kinetics_kj"] - max(others)) / C["kj_per_kcal"] == pytest.approx(2.0, abs=0.1)


def test_bromomethane_has_an_independent_determination_that_agrees_with_the_kinetics_value():
    methyl_bromide = BR[0]
    bromination = next(d for d in methyl_bromide["other_determinations_kj"] if d["method"].startswith("bromination"))
    combined = math.hypot(bromination["uncertainty"], methyl_bromide["kinetics_uncertainty_kj"])
    assert abs(bromination["value"] - methyl_bromide["kinetics_kj"]) < combined


def test_following_the_isopropyl_thiyl_saddle_point_found_a_flat_double_well_not_a_deeper_state():
    """The -233 cm-1 mode of two 2-propanethiyl structures (preregistration section 7): displaced and re-optimised, both ends are minima of the same electronic energy as the one already used, and the saddle lies a few hundredths of a kcal/mol above."""
    s = json.loads((Path(__file__).parent.parent / "benchmarks" / "restart_v3" / "artifacts" / "saddle_follow" / "summary.json").read_text(encoding="utf-8"))
    eh = 627.5094740631
    assert s["saddle"]["lowest_frequencies_cm1"][0] == pytest.approx(-233.5, abs=0.1)
    for end in ("followed_plus", "followed_minus"):
        assert s[end]["lowest_frequencies_cm1"][0] > 200.0                                           # a minimum
        assert abs(s[end]["electronic_eh"] - s["conformer0_minimum"]["electronic_eh"]) * eh < 0.02   # the minimum already used
        assert 0.0 < (s["saddle"]["electronic_eh"] - s[end]["electronic_eh"]) * eh < 0.1             # the saddle is barely above
    # the harmonic enthalpy at the saddle is LOWER than at the minimum, by about half a kcal/mol: the artefact the preregistration warns of
    assert -0.7 < s["derived_kcal"]["saddle_enthalpy_minus_conformer0_enthalpy"] < -0.4


def test_the_methanethiol_anchor_block_is_the_two_papers_arithmetic():
    """Ervin 2015 anchors the acidity scale on D0(CH3S-H) = 359.7 +- 1.5 kJ/mol; wu2025 quotes (from Wilson, Ashfold and Dixon 1994) 30 250 +- 100 cm-1 for the same bond. Nothing here says which is right: it is the size of the difference."""
    a = DATA["methanethiol_anchor"]
    wilson = a["wilson1994_d0_cm1"] * a["cm1_to_kj_per_mol"]
    unc = a["wilson1994_d0_uncertainty_cm1"] * a["cm1_to_kj_per_mol"]
    assert wilson == pytest.approx(361.87, abs=0.01) and unc == pytest.approx(1.196, abs=0.001)
    assert wilson - a["ervin2015_combined_kj"] == pytest.approx(2.17, abs=0.01)                      # 0.52 kcal/mol above Ervin's anchor
    combined = math.hypot(a["ervin2015_combined_uncertainty_kj"], unc)                                   # 1.92
    ratio = (wilson - a["ervin2015_combined_kj"]) / combined
    assert 1.0 < ratio < 2.0, ratio                                                                      # 1.13 times the combined uncertainty: OUTSIDE one of them, inside two
    w1, w2 = 1 / a["ervin2015_combined_uncertainty_kj"] ** 2, 1 / unc ** 2
    mean = (a["ervin2015_combined_kj"] * w1 + wilson * w2) / (w1 + w2)
    assert mean == pytest.approx(361.03, abs=0.01) and (w1 + w2) ** -0.5 == pytest.approx(0.94, abs=0.01)
    assert (mean - a["ervin2015_combined_kj"]) / C["kj_per_kcal"] == pytest.approx(0.317, abs=0.002)    # the most the combined anchor could move an Arm D reference
    assert a["ervin2015_combined_kj"] == pytest.approx(359.7)                                           # the figure Ervin prints, as the preregistration quotes it


def test_the_thiophenol_determinations_are_the_papers_arithmetic_and_still_leave_it_out():
    """Devine, Nix, Dixon and Ashfold 2008 print D0(C6H5S-H) <= 28 030 +- 100 cm-1 (335.3 +- 1.2 kJ/mol) and call it an upper limit; Lim 2007 prints 76.8 +- 0.3 kcal/mol; they differ by 3.3 kcal/mol at 0 K, so no thiophenol reference passes the 1.0 kcal/mol rule."""
    t = DATA["thiophenol_context"]
    cm = DATA["methanethiol_anchor"]["cm1_to_kj_per_mol"]
    kj = t["devine2008_d0_cm1"] * cm
    assert kj == pytest.approx(t["devine2008_printed_kj"], abs=0.05)                           # the paper's own conversion
    kcal = kj / C["kj_per_kcal"]
    assert kcal == pytest.approx(80.15, abs=0.01)
    assert kcal - t["lim2007_d0_kcal"] == pytest.approx(3.35, abs=0.02)
    assert "UPPER LIMIT" in t["devine2008_kind"]
    assert t["devine2008_d0_uncertainty_cm1"] * cm / C["kj_per_kcal"] < 1.0 < kcal - t["lim2007_d0_kcal"]   # each is precise on its own; together they are not usable
    anchor = DATA["methanethiol_anchor"]
    assert anchor["nicovich1992_d0_cm1"] * cm == pytest.approx(359.7, abs=0.1)                       # 30 065 cm-1 is the 85.96 kcal/mol that Ervin's anchor rests on
    assert (anchor["wilson1994_d0_cm1"] - anchor["nicovich1992_d0_cm1"]) < (anchor["wilson1994_d0_uncertainty_cm1"] ** 2 + anchor["nicovich1992_d0_uncertainty_cm1"] ** 2) ** 0.5   # Wilson's own 'good agreement': 185 cm-1 against 260
