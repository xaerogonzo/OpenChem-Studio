"""TRIAGE.md 2.8: the Ionescu EEM instrument.

The synthetic tests transcribe the paper's equations again by hand rather than call the module's own
system builder, so a sign or unit error shared by both would not pass. The corpus tests need the
supporting information, which is not in the repository (the structures and charge CSVs are ACS
accompanying files); they skip with a named reason when it is absent, and the result pins below say
what they measured on the machine that ran them.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import math
import pathlib
import sys

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("ionescu_eem_check", ROOT / "benchmarks" / "charges" / "models" / "ionescu_eem_check.py")
ie = importlib.util.module_from_spec(_spec)
sys.modules["ionescu_eem_check"] = ie
_spec.loader.exec_module(ie)

FIXTURES = ROOT / "tests" / "fixtures" / "charges" / "ionescu2013"
needs_si = pytest.mark.skipif(not ie.SI.exists(), reason="the Ionescu 2013 supporting information is not on this machine")

#: A toy: two atoms of different types, 2 A apart, with hand-chosen parameters.
TOY = {"kappa": 0.01, "types": {"H": (2.5, 0.02), "O": (2.4, 0.03)}}


def test_two_atoms_match_the_equations_solved_by_hand():
    """X = A_i + B_i q_i + k q_j / r for both atoms, with q_1 + q_2 = 0, solved on paper:
    q_1 = (A_2 - A_1) / (B_1 + B_2 - 2k/r)."""
    r = 2.0
    a1, b1 = TOY["types"]["H"]
    a2, b2 = TOY["types"]["O"]
    expected = (a2 - a1) / (b1 + b2 - 2 * TOY["kappa"] / r)
    q = ie.eem_charges(["H", "O"], [(0.0, 0.0, 0.0), (r, 0.0, 0.0)], 0.0, TOY)
    assert q == pytest.approx([expected, -expected], abs=1e-12)


@pytest.mark.parametrize("total", [0.0, -3.0, 2.0])
def test_the_total_charge_is_conserved_exactly(total):
    coords = [(0.0, 0.0, 0.0), (1.1, 0.0, 0.0), (0.0, 1.2, 0.3), (2.0, 1.0, 1.0)]
    q = ie.eem_charges(["H", "O", "H", "O"], coords, total, TOY)
    assert float(np.sum(q)) == pytest.approx(total, abs=1e-9)


def test_exact_sensitivities_agree_with_central_differences():
    elements = ["H", "O", "H", "O"]
    coords = [(0.0, 0.0, 0.0), (1.1, 0.0, 0.0), (0.0, 1.2, 0.3), (2.0, 1.0, 1.0)]
    exact = ie.sensitivities(elements, coords, -1.0, TOY, "R_angstrom")
    step = 1e-6
    for (kind, atom_type), derivative in exact.items():
        def moved(delta):
            types = {t: list(v) for t, v in TOY["types"].items()}
            parameters = {"kappa": TOY["kappa"], "types": types}
            if kind == "kappa":
                parameters["kappa"] += delta
            else:
                types[atom_type][0 if kind == "A" else 1] += delta
            parameters["types"] = {t: tuple(v) for t, v in types.items()}
            return ie.eem_charges(elements, coords, -1.0, parameters, "R_angstrom")
        finite = (moved(step) - moved(-step)) / (2 * step)
        assert derivative == pytest.approx(finite, abs=1e-6), (kind, atom_type)


def test_charges_follow_a_permuted_atom_order():
    elements = ["H", "O", "H", "O"]
    coords = [(0.0, 0.0, 0.0), (1.1, 0.0, 0.0), (0.0, 1.2, 0.3), (2.0, 1.0, 1.0)]
    order = [2, 0, 3, 1]
    straight = ie.eem_charges(elements, coords, 0.0, TOY)
    permuted = ie.eem_charges([elements[i] for i in order], [coords[i] for i in order], 0.0, TOY)
    assert permuted == pytest.approx([straight[i] for i in order], abs=1e-12)


def test_the_two_readings_differ_by_the_bohr_conversion_in_the_kernel_only():
    elements, coords = ["H", "O"], [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0)]
    bohr = ie.eem_charges(elements, coords, 0.0, TOY, "R_bohr")
    # r in bohr is 1.889 x r in angstrom, so k / r_bohr is (k / 1.889) / r_angstrom.
    scaled = {"kappa": TOY["kappa"] / ie.BOHR_PER_ANGSTROM, "types": TOY["types"]}
    assert bohr == pytest.approx(ie.eem_charges(elements, coords, 0.0, scaled, "R_angstrom"), abs=1e-12)


def test_the_metric_set_reproduces_hand_values():
    reference = np.array([0.5, -0.5, 0.25, -0.25])
    model = np.array([0.4, -0.45, 0.30, -0.25])
    metrics = ie.metric_set([(reference, model)])
    difference = reference - model
    assert metrics["RMSD_avg"] == pytest.approx(math.sqrt(float(difference @ difference) / 4))
    assert metrics["D_avg"] == pytest.approx(float(np.abs(difference).mean()))
    assert metrics["R_sample"] == pytest.approx(float(np.corrcoef(reference, model)[0, 1]))
    assert metrics["R2_sample"] == pytest.approx(metrics["R_sample"] ** 2)
    # Pearson's r does not depend on ddof; both conventions must agree, which is why the identification
    # in 2.8 turns on r against r squared, not on the sigma convention.
    assert metrics["R_population"] == pytest.approx(metrics["R_sample"])


def test_the_pdb_element_rule_separates_calcium_from_an_alpha_carbon(tmp_path):
    text = "\n".join([
        "MODEL        1",
        "ATOM      1  CA  ALA A   1      -4.239   3.079  10.081",
        "ATOM      2 2HB  ALA A   1      -3.285   3.042  10.519",
        "ATOM      3  OD1 ASP A   2      -4.986   3.045  10.818",
        "HETATM    4 CA    CA A 100      -1.000   2.000   3.000",
        "ENDMDL",
    ])
    path = tmp_path / "toy.pdb"
    path.write_text(text, encoding="utf-8")
    atoms = ie.pdb_models(path)[0]
    assert [a[0] for a in atoms] == ["C", "H", "O", "Ca"]
    assert atoms[3][1:] == (-1.0, 2.0, 3.0)


# --- the frozen tables ----------------------------------------------------------------------------


def test_table_s1_has_every_model_with_calcium_parameterised():
    models = ie.table_s1()
    assert len(models) == 24
    e_models = {m for m in models if m.startswith("E-")}
    ex_models = set(models) - e_models
    assert len(e_models) == 12 and len(ex_models) == 12
    for name, model in models.items():
        expected = {"H", "C", "N", "O", "S", "Ca"} if name.startswith("E-") else {"H1", "C1", "C2", "N1", "N2", "O1", "O2", "S1", "Ca0"}
        assert set(model["types"]) == expected, name
        assert 0.004 <= model["kappa"] <= 0.011, name
        # The Ca decision in 2.8 rests on these rows existing, so it is asserted, not assumed.
        assert any(t.startswith("Ca") for t in model["types"]), name


def test_table_s2_holds_every_cell_and_its_internal_validation_diagonal():
    printed = ie.table_s2()
    assert len(printed) == 24 * 12 * 3 * 3
    assert printed[("E-MPA/6-31G*/gas", "MPA/6-31G*/gas", "training_set", "R_avg")] == 0.975
    assert printed[("E-HiI/6-31G**/PCM", "HiI/6-31G**/PCM", "ubiquitin", "RMSD_avg")] == 0.116


# --- result pins (section 3.8) --------------------------------------------------------------------


@needs_si
def test_result_pin_ubiquitin_reproduces_under_the_angstrom_reading_and_not_the_bohr_one():
    molecule = ie.dataset("ubiquitin")[0]
    model = "E-HiI/6-31G**/PCM"
    parameters = ie.table_s1()[model]
    total = round(sum(molecule["qm"]["HiI/6-31G**/PCM"]))
    printed = np.array(molecule["eem"][model])
    angstrom = ie.eem_charges(molecule["elements"], molecule["coords"], total, parameters, "R_angstrom")
    bohr = ie.eem_charges(molecule["elements"], molecule["coords"], total, parameters, "R_bohr")
    assert np.max(np.abs(angstrom - printed)) < 1e-5
    assert np.max(np.abs(bohr - printed)) > 0.1


@needs_si
def test_result_pin_the_printed_r_avg_is_the_squared_pearson_coefficient():
    """The paper's prose calls R_avg the squared Pearson coefficient; its eq 7 prints the unsquared form.
    2.8 identifies which one Table S2 holds, from a closed list, rather than assuming either."""
    molecule = ie.dataset("ubiquitin")[0]
    model, scheme = "E-HiI/6-31G**/PCM", "HiI/6-31G**/PCM"
    parameters = ie.table_s1()[model]
    total = round(sum(molecule["qm"][scheme]))
    q = ie.eem_charges(molecule["elements"], molecule["coords"], total, parameters, "R_angstrom")
    metrics = ie.metric_set([(np.array(molecule["qm"][scheme]), q)])
    printed = ie.table_s2()
    assert metrics["R2_sample"] == pytest.approx(printed[(model, scheme, "ubiquitin", "R_avg")], abs=5e-4)
    assert metrics["R_sample"] != pytest.approx(printed[(model, scheme, "ubiquitin", "R_avg")], abs=5e-4)
    assert metrics["RMSD_avg"] == pytest.approx(printed[(model, scheme, "ubiquitin", "RMSD_avg")], abs=5e-4)
    assert metrics["D_avg"] == pytest.approx(printed[(model, scheme, "ubiquitin", "D_avg")], abs=5e-4)


@needs_si
def test_result_pin_the_pdb_element_rule_reproduces_the_papers_table_1_counts():
    counts: dict[str, int] = {}
    for atoms in ie.pdb_models(ie.SI / "ci400448n_si_005" / ie.STRUCTURES["training_set"]):
        for element, *_ in atoms:
            counts[element] = counts.get(element, 0) + 1
    assert counts == {"H": 19879, "C": 11912, "N": 3188, "O": 4954, "S": 148, "Ca": 61}


def test_the_gate_uses_the_envelope_where_it_was_sampled_and_the_ratio_elsewhere():
    linear = np.array([1e-6, 2e-6])
    envelope = np.array([1e-5, 1e-7])
    combined = ie.combined_tolerance(linear, envelope, 1.0)
    assert combined == pytest.approx([1.1e-5, 2e-6])  # the envelope wins on the first atom, the linear term on the second
    assert ie.combined_tolerance(linear, None, 50.0) == pytest.approx(linear * 55.0)


def test_the_total_charge_comes_from_the_sources_own_column():
    molecule = {"qm": {"MPA/6-31G*/gas": [-0.5, -0.5, -1.0, -0.999999]}}
    assert ie.total_charge(molecule, "MPA/6-31G*/gas") == -3.0
    parameters = ie.table_s1()["E-MPA/6-31G*/gas"]
    not_integer = {"id": "x", "elements": ["H"], "geometry_elements": ["H"], "coords": np.zeros((1, 3)),
                   "qm": {"MPA/6-31G*/gas": [0.4]}, "eem": {"E-MPA/6-31G*/gas": [0.4]}}
    assert "not an integer" in ie.applicable(not_integer, parameters, "MPA/6-31G*/gas", "E-MPA/6-31G*/gas")


def test_the_rounding_envelope_exceeds_the_linear_estimate_on_the_toy():
    """The envelope is the gate because q depends on the parameters through an inverse, so the linear
    term understates the rounding box's effect. On the toy it is larger, which is why 2.8 samples."""
    elements, coords = ["H", "O", "H"], [(0.0, 0.0, 0.0), (1.1, 0.0, 0.0), (0.0, 1.2, 0.3)]
    linear = ie.linearized_tolerance(ie.sensitivities(elements, coords, 0.0, TOY, "R_angstrom"))
    envelope = ie.rounding_envelope(elements, coords, 0.0, TOY, "R_angstrom", samples=40)
    assert np.all(envelope > 0)
    assert np.max(envelope / linear) > 1.0


def test_calcium_uses_its_own_table_s1_row_and_not_carbons():
    """Ca is parameterised in every model (2.8 decided it INCLUDED on that measurement), so a calcium
    atom must never be given carbon's A and B. Without this, typing Ca as C changes nothing any other
    test looks at: the corpus pins below run on ubiquitin, which has no calcium."""
    parameters = ie.table_s1()["E-MPA/6-31G*/gas"]
    elements, coords = ["Ca", "O", "H"], [(0.0, 0.0, 0.0), (2.4, 0.0, 0.0), (3.0, 0.9, 0.0)]
    as_calcium = ie.eem_charges(elements, coords, 2.0, parameters)
    as_carbon = ie.eem_charges(["C", "O", "H"], coords, 2.0, parameters)
    assert parameters["types"]["Ca"] != parameters["types"]["C"]
    assert abs(as_calcium[0] - as_carbon[0]) > 1e-4
