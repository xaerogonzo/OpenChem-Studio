"""The S-H and bromine reference inputs of `benchmarks/restart_v3/PREREGISTRATION.md` (`benchmarks/restart_v3/references.json`).

Like the halogen arm's test, this recomputes every derived number from the inputs the papers print instead of restating it, so a number in the preregistration cannot drift from its arithmetic. What it adds: the one derived value that a paper
ALSO publishes (ethanethiol's S-H) is held to the published figure, which is the check that the cycle used for the propanethiols is the paper's own cycle.
"""
from __future__ import annotations

import json
import math
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


@pytest.mark.parametrize("bond", SH[1:], ids=lambda b: b["name"])
def test_each_derived_sh_reference_is_its_inputs_combined_as_the_definition_says(bond):
    d0 = _d0_kj(bond)
    assert d0 == pytest.approx(bond["stated_d0_kj"], abs=0.01)
    d298_kcal = (d0 + C["d0_to_d298_ethanethiol_kj"]) / C["kj_per_kcal"]
    assert d298_kcal == pytest.approx(bond["stated_d298_kcal"], abs=0.01)
    unc_kj = math.hypot(_d0_unc_kj(bond), C["borrowed_thermal_uncertainty_kj"])
    assert unc_kj / C["kj_per_kcal"] == pytest.approx(bond["stated_d298_uncertainty_kcal"], abs=0.01)
    assert "not a published number" in bond["d298_status"], "a derived value must say that it is"


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
