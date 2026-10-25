"""`openchem.chem.bond_dissociation`: the chemistry of the X-H bond dissociation enthalpy calculation, held to the two benchmarks that measured it.

The library is a port of `benchmarks/bde/` (PARTIAL, 2026-10-21) as `benchmarks/restart_v2/` used it on bonds it had not seen (PASS, 2026-10-23), so the tests compare it with those runners and with their committed job records instead of restating expected numbers:
the structures it builds, the ORCA input it writes, what it reads from an output and the bond enthalpy it selects from the 140 recorded structures must be the benchmarks', to the digit; and the error it states beside a result is recomputed from the same records.
"""
from __future__ import annotations

import functools
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from openchem.chem import bond_dissociation as bd
from openchem.chem import proton_affinity as pa

_ROOT = Path(__file__).parent.parent
_FIXTURES = Path(__file__).parent / "fixtures" / "orca"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# `run_restart` loads the first run's runner (`bde`), its judge and the proton-affinity runner by path, and holds the held-out arm's bonds
restart = _load("restart_v2_run_for_the_library", _ROOT / "benchmarks" / "restart_v2" / "run_restart.py")
bde = restart.bde

FIRST_RUN = restart.pa.records_of(_ROOT / "benchmarks" / "bde" / "artifacts" / "primary" / "runs.jsonl")
HELD_OUT = restart.pa.records_of(_ROOT / "benchmarks" / "restart_v2" / "artifacts" / "heldout" / "runs.jsonl")
H_ATOM = (_FIXTURES / "bde_h_atom.out").read_text(encoding="utf-8")
CN_RADICAL = (_FIXTURES / "bde_cn_radical_optfreq.out").read_text(encoding="utf-8")
HCN = (_FIXTURES / "bde_hcn_parent_optfreq.out").read_text(encoding="utf-8")
WATER = (_FIXTURES / "pa_water_optfreq.out").read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def _first_run_structures() -> dict[str, dict]:
    return {s["id"]: s for s in json.loads((_ROOT / "benchmarks" / "bde" / "artifacts" / "structures.json").read_text(encoding="utf-8"))}


# --- the same protocol ------------------------------------------------------------------------------------------------------


def test_the_keywords_and_limits_are_the_benchmarks():
    assert bd.HEADER == bde.HEADER and bd.ATOM_HEADER == bde.ATOM_HEADER and bd.IMAGINARY_CM == bde.IMAGINARY_CM and bd.ATOM_ID == bde.ATOM_ID
    for name in ("SEED", "CONFORMERS", "DEDUPE_RMSD", "KEEP", "KEEP_WINDOW_KCAL"):
        assert getattr(pa, name) == getattr(restart.pa, name), name
    assert bd.S2_DOUBLET == bde.core.S2_DOUBLET and bd.S2_FLAG_EXCESS == bde.core.S2_FLAG_EXCESS


def test_the_arithmetic_is_the_benchmarks():
    assert bd.hydrogen_atom_enthalpy(-0.49999) == bde.core.hydrogen_atom_enthalpy(-0.49999)
    assert bd.bond_dissociation_enthalpy(-40.5, -39.8, -0.4978) == bde.core.bond_dissociation_enthalpy(-40.5, -39.8, -0.4978)
    assert bd.HARTREE_TO_KCAL == pytest.approx(bde.core.HARTREE_TO_KCAL, rel=1e-12)
    # the translation term of the atom is (5/2) RT = 1.4812 kcal/mol, the proton's
    assert (bd.hydrogen_atom_enthalpy(0.0)) * bd.HARTREE_TO_KCAL == pytest.approx(1.4812, abs=1e-3)
    assert bd.spin_contaminated(0.81) and not bd.spin_contaminated(0.79)


def test_a_radicals_start_is_the_parents_conformer_with_its_lowest_hydrogen_deleted():
    symbols = ["C", "O", "H", "H", "H", "H"]
    xyz = np.arange(18, dtype=float).reshape(6, 3)
    mine = bd.radical_start(symbols, xyz, 1, [0, 2, 5])
    theirs = bde.core.radical_start(symbols, xyz, 1, [0, 2, 5])
    assert mine[0] == theirs[0] == ["C", "O", "H", "H", "H"] and np.array_equal(mine[1], theirs[1])
    with pytest.raises(ValueError, match="no hydrogen"):
        bd.radical_start(symbols, xyz, 0, [1])


@pytest.mark.parametrize("name", ["methanol O-H", "ethanol O-H", "propane secondary C-H", "toluene benzylic C-H", "acetaldehyde formyl C-H", "hydrogen peroxide O-H"])
def test_the_structures_are_the_benchmarks_for_the_same_bond(name):
    bond = next(b for b in bde.reference_bonds() if b["name"] == name)
    mol = bd.molecule_from_smiles(bond["smiles"])
    mine = bd.build_structures(mol, [bond["atom"]], key="mol")
    theirs = {s["id"]: s for s in _first_run_structures().values() if (s["role"] == "parent" and s["smiles"] == bond["smiles"]) or (s["role"] == "radical" and s["bond"] == name)}
    mine_parents = [s for s in mine if s["role"] == "parent"]
    mine_radicals = [s for s in mine if s["role"] == "radical"]
    their_parents = sorted((s for s in theirs.values() if s["role"] == "parent"), key=lambda s: s["id"])
    their_radicals = sorted((s for s in theirs.values() if s["role"] == "radical"), key=lambda s: s["id"])
    assert len(mine_parents) == len(their_parents) >= 1 and len(mine_radicals) == len(their_radicals)
    for a, b in list(zip(mine_parents, their_parents)) + list(zip(mine_radicals, their_radicals)):
        assert a["symbols"] == b["symbols"] and a["charge"] == b["charge"] and a["mult"] == b["mult"]
        assert np.allclose(a["coordinates"], b["coordinates"], atol=1e-9)


def test_the_orca_input_is_the_benchmarks_for_every_role_with_and_without_the_retry():
    structures = bd.build_structures(bd.molecule_from_smiles("CCO"), [2], key="mol")
    assert {s["role"] for s in structures} == {"atom", "parent", "radical"}
    for structure in structures:
        for retry in (False, True):
            assert bd.orca_input(structure, 4, retry) == bde.orca_input(structure, 4, retry)
    radical = next(s for s in structures if s["role"] == "radical")
    assert "* xyz 0 2" in bd.orca_input(radical, 4) and "Calc_Hess true" in bd.orca_input(radical, 4, True)
    atom = bd.orca_input(structures[0], 4)
    assert "%pal" not in atom and "Opt" not in atom and atom.startswith("! M062X def2-TZVPD TightSCF DefGrid3")


@pytest.mark.parametrize("text", [CN_RADICAL, HCN], ids=["cn radical", "hcn"])
def test_an_output_is_read_as_the_benchmark_reads_it(text):
    assert bd.parse_species(text) == bde.parse_species(text)
    assert bd.parse_atom(H_ATOM) == bde.parse_atom(H_ATOM)
    assert bd.parse_s2(CN_RADICAL) == pytest.approx(0.764932)


# --- the same numbers from the recorded jobs --------------------------------------------------------------------------------


def test_the_records_that_count_are_the_benchmarks_in_both_arms():
    for records in (FIRST_RUN, HELD_OUT):
        assert sorted(r["structure"] for r in bd.accepted(records)) == sorted(r["structure"] for r in bde.accepted(records))


def _selected_kcal(records: list[dict], bond: dict) -> float | None:
    done = bd.accepted(records)
    atoms = [r for r in done if r["role"] == "atom"]
    parents = [r for r in done if r["role"] == "parent" and r["smiles"] == bond["smiles"]]
    radicals = [r for r in done if r["role"] == "radical" and r["bond"] == bond["name"]]
    if not (atoms and parents and radicals):
        return None
    return bd.select(parents, radicals, bd.hydrogen_atom_enthalpy(atoms[-1]["energy"]))["value_eh"] * bd.HARTREE_TO_KCAL


@pytest.mark.parametrize("arm", ["first run", "held out"])
def test_selecting_from_the_recorded_jobs_gives_the_benchmarks_bond_enthalpy_for_every_bond(arm):
    records, bonds = (FIRST_RUN, bde.reference_bonds()) if arm == "first run" else (HELD_OUT, restart.heldout_bonds())
    judged = bde.judge_records(records, bonds)
    assert len(judged) == (33 if arm == "first run" else 30)
    missing = 0
    for bond, row in zip(bonds, judged):
        mine = _selected_kcal(records, bond)
        if row["dh_kcal"] is None:
            missing += 1
            assert mine is None, bond["name"]
        else:
            assert mine == pytest.approx(row["dh_kcal"], abs=1e-9), bond["name"]
    assert missing == (3 if arm == "first run" else 0)  # the first run's three missing bonds, and none held out


def test_the_stated_error_is_recomputed_from_the_committed_records():
    errors = {"ALL": [], "ALL first run": [], "ALL held out": []}
    classes: dict[str, list[float]] = {}
    hold = {b["name"]: b for b in restart.heldout_bonds()}
    for records, bonds, arm in ((FIRST_RUN, bde.reference_bonds(), "first run"), (HELD_OUT, restart.heldout_bonds(), "held out")):
        for row in bde.judge_records(records, bonds):
            if row["dh_kcal"] is None or (arm == "first run" and row["uncertainty"] > 1.0) or (arm == "held out" and hold[row["name"]]["excluded"]):
                continue
            error = row["dh_kcal"] - row["dh_ref"]
            name = row["name"]
            key = "O-H next to O or N" if " O-H" in name and ("peroxide" in name or "hydroxylamine" in name or "oxime" in name) else next((k for k in ("C-H", "N-H", "O-H", "S-H", "Si-H") if k in name), "?")
            errors["ALL"].append(error)
            errors["ALL " + arm].append(error)
            classes.setdefault(key, []).append(error)

    def stats(values: list[float]) -> dict:
        return {"n": len(values), "mae": sum(abs(v) for v in values) / len(values), "mse": sum(values) / len(values), "max": max(abs(v) for v in values)}

    for stated, measured in ((bd.BENCHMARK["all"], errors["ALL"]), (bd.BENCHMARK["first_run"], errors["ALL first run"]), (bd.BENCHMARK["held_out"], errors["ALL held out"])):
        s = stats(measured)
        assert stated["n"] == s["n"] and stated["mae"] == pytest.approx(s["mae"], abs=0.005) and stated["mse"] == pytest.approx(s["mse"], abs=0.005) and stated["max"] == pytest.approx(s["max"], abs=0.005)
    for key in ("C-H", "N-H", "O-H", "O-H next to O or N", "S-H", "Si-H"):
        s = stats(classes[key])
        stated = bd.BENCHMARK[key]
        assert stated["n"] == s["n"] and stated["mae"] == pytest.approx(s["mae"], abs=0.005) and stated["mse"] == pytest.approx(s["mse"], abs=0.005) and stated["max"] == pytest.approx(s["max"], abs=0.005), key
    # the calculation runs low: only HCN's C-H is above its reference, in the first run
    assert sum(1 for v in errors["ALL"] if v > 0) == 1


# --- the bonds and the scope ------------------------------------------------------------------------------------------------


def test_ethanol_has_three_bond_classes_and_the_oxygen_is_not_next_to_a_heteroatom():
    classes = bd.bond_classes(bd.molecule_from_smiles("CCO"))
    assert [(c["element"], c["hydrogens"]) for c in classes] == [("C", 3), ("C", 2), ("O", 1)]
    assert [c["atom"] for c in classes] == [0, 1, 2] and not any(c["next_to_heteroatom"] for c in classes)
    assert [c["label"] for c in classes] == ["CH3-H, bonded to C", "CH2-H, bonded to C, O", "O-H, bonded to C"]


def test_equivalent_atoms_are_one_bond_class_and_aromatic_positions_are_distinct():
    assert len(bd.bond_classes(bd.molecule_from_smiles("C"))) == 1  # methane: four equivalent hydrogens
    toluene = bd.bond_classes(bd.molecule_from_smiles("Cc1ccccc1"))
    assert [(c["hydrogens"], c["aromatic"]) for c in toluene] == [(3, False), (1, True), (1, True), (1, True)]
    assert "aromatic" in toluene[1]["label"]


def test_an_oxygen_bonded_to_another_oxygen_or_a_nitrogen_is_flagged_as_the_class_measured_to_run_lowest():
    for smiles, flagged in (("OO", True), ("COO", True), ("NO", True), ("C=NO", True), ("CO", False), ("O", False)):
        classes = bd.bond_classes(bd.molecule_from_smiles(smiles))
        oxygen = [c for c in classes if c["element"] == "O"]
        assert oxygen and all(c["next_to_heteroatom"] == flagged for c in oxygen), smiles
        assert all(bd.class_key(c) == ("O-H next to O or N" if flagged else "O-H") for c in oxygen)
    assert bd.class_key(bd.bond_classes(bd.molecule_from_smiles("CS"))[1]) == "S-H"


@pytest.mark.parametrize(
    ("smiles", "reason"),
    [
        ("[CH3]", "radical"), ("C[N+](C)(C)C", "charged"), ("[Na+].[Cl-]", "more than one"), ("O=C=O", "no bond between a heavy atom and a hydrogen"),
        ("not a smiles", "could not be read"), ("[UH3]", "basis set has no functions"),
    ],
)
def test_a_molecule_the_protocol_cannot_compute_is_refused_with_its_reason(smiles, reason):
    """The jobs are a neutral singlet parent and a neutral doublet radical: a charged or open-shell input would be computed WRONGLY, not merely without a measured error."""
    with pytest.raises(pa.OutOfScope, match=reason):
        bd.molecule_from_smiles(smiles)


@pytest.mark.parametrize(
    ("smiles", "atoms", "warned"),
    [
        ("CCl", None, ["Cl: the benchmarks measured molecules of only H, C, N, O and S"]),
        ("CC(C)(C)C(C)(C)C(C)(C)C", None, ["11 heavy atoms: the benchmarks measured molecules of at most 9"]),
        ("c1ccccc1P", [6], ["P: the benchmarks measured molecules of only H, C, N, O and S", "P-H bonds: no bond of that kind was measured"]),
        ("c1ccccc1P", [0], ["P: the benchmarks measured molecules of only H, C, N, O and S"]),
        ("[SiH4]", [0], ["Si: the benchmarks measured molecules of only H, C, N, O and S"]),  # silane's Si-H was measured once, the element is outside the deciding set
        ("CO", [0, 1], []),
    ],
)
def test_a_molecule_the_benchmarks_did_not_measure_is_computed_with_its_warnings(smiles, atoms, warned):
    """Alex, 2026-10-23: our benchmarks' edge is a warning, not a refusal."""
    assert bd.scope_warnings(bd.molecule_from_smiles(smiles), atoms) == warned


def test_a_sequence_outside_the_measured_scope_carries_its_warnings_into_the_result():
    sequence = bd.Sequence("c1ccccc1P", [6])
    assert "P-H bonds: no bond of that kind was measured" in sequence.scope_warnings
    sequence.records = [{"structure": "atom|H", "role": "atom", "completed": True, "energy": -0.49982}]
    parameters = bd.descriptors(sequence, "u")[0].provenance.parameters
    assert parameters["within_measured_scope"] is False and "OUTSIDE WHAT WAS MEASURED" in parameters["validation"]


def test_a_run_names_which_bonds_and_refuses_a_choice_that_is_not_a_class_or_is_too_big():
    with pytest.raises(ValueError, match="not the representative"):
        bd.build_structures(bd.molecule_from_smiles("CCO"), [5])
    with pytest.raises(pa.OutOfScope, match="twice"):
        bd.Sequence("CCO", [0, 0])
    with pytest.raises(pa.OutOfScope, match="no bond was chosen"):
        bd.Sequence("CCO", [])
    with pytest.raises(pa.OutOfScope, match="at most"):
        bd.Sequence("Cc1ccc(CC(C)CC)cc1", list(range(8)))


# --- the sequence of jobs ---------------------------------------------------------------------------------------------------


def _run_hcn(*outputs: str) -> bd.Sequence:
    sequence = bd.Sequence("C#N")
    for text in outputs:
        sequence.next_job()
        sequence.finish(text)
    return sequence


def test_the_real_outputs_of_hydrogen_cyanide_give_the_first_runs_bond_enthalpy():
    sequence = bd.Sequence("C#N")
    assert [s["role"] for s in sequence.structures] == ["atom", "parent", "radical"] and sequence.total == 3
    structure, retry = sequence.next_job()
    assert structure["role"] == "atom" and retry is False
    assert sequence.finish(H_ATOM) == "recorded"
    assert sequence.next_job()[0]["role"] == "parent" and sequence.finish(HCN) == "recorded"
    assert sequence.next_job()[0]["role"] == "radical" and sequence.finish(CN_RADICAL) == "recorded" and sequence.done and sequence.settled == 3
    result = sequence.result()
    row = result.bonds[0]
    # the first run's judged value for HCN's C-H: 126.30 + 2.53 = 128.83 kcal/mol (the fixtures are a smoke run and a fresh run of the same jobs)
    judged = next(r for r, b in zip(bde.judge_records(FIRST_RUN, bde.reference_bonds()), bde.reference_bonds()) if b["name"] == "hydrogen cyanide C-H")
    assert row.dh_kcal == pytest.approx(judged["dh_kcal"], abs=0.05) and row.weakest and row.s2 == pytest.approx(0.764932) and not row.spin_contaminated
    assert row.dh_kj == pytest.approx(row.dh_kcal * 4.184) and result.weakest is row and row.element == "C" and row.class_key == "C-H"


def test_an_imaginary_mode_queues_one_retry_from_the_final_geometry_and_a_second_failure_drops_the_radical():
    imaginary = CN_RADICAL
    import re

    imaginary = re.sub(r"(\n\s*5:\s+)(\d+\.\d+)( cm\*\*-1)", r"\g<1>-30.00\g<3>", CN_RADICAL, count=1)
    assert imaginary != CN_RADICAL and bd.parse_species(imaginary)["lowest_frequency"] == -30.0
    sequence = _run_hcn(H_ATOM, HCN)
    sequence.next_job()
    assert sequence.finish(imaginary) == "retrying" and not sequence.done and sequence.settled == 2
    structure, retry = sequence.next_job()
    assert retry is True and structure["role"] == "radical" and "Calc_Hess true" in bd.orca_input(structure, 4, retry)
    assert structure["coordinates"] == [list(c) for c in bd.parse_species(imaginary)["coordinates"]]  # the retry starts where the first attempt ended
    assert sequence.finish(imaginary) == "recorded" and sequence.done  # one retry only
    row = sequence.result().bonds[0]
    assert row.dh_kcal is None and "-30 cm-1 after the one Calc_Hess re-run" in row.reason and "saddle point" in row.reason
    descriptor = bd.descriptors(sequence, "u")[0]
    assert descriptor.value is None and "No bond has a value" in descriptor.error and "mol|radical|0|0" in descriptor.error


def test_a_retry_that_clears_the_imaginary_mode_replaces_the_first_attempt():
    import re

    imaginary = re.sub(r"(\n\s*5:\s+)(\d+\.\d+)( cm\*\*-1)", r"\g<1>-30.00\g<3>", CN_RADICAL, count=1)
    sequence = _run_hcn(H_ATOM, HCN, imaginary)
    sequence.next_job()
    assert sequence.finish(CN_RADICAL) == "recorded"
    assert sequence.result().bonds[0].dh_kcal == pytest.approx(128.83, abs=0.1) and sequence.result().dropped == ()


def test_a_radical_that_rearranged_is_a_failed_structure_not_a_low_one():
    # water's output stands in for a radical whose heavy-atom skeleton is not HCN's
    sequence = _run_hcn(H_ATOM, HCN, WATER)
    row = sequence.result().bonds[0]
    assert row.dh_kcal is None and "rearranged" in row.reason


def test_a_failed_hydrogen_atom_ends_the_run_because_no_bond_can_have_a_value_without_it():
    sequence = bd.Sequence("C#N")
    sequence.next_job()
    assert sequence.finish("ORCA died with nothing to read") == "failed"
    assert sequence.done and sequence.fatal and "hydrogen atom" in sequence.fatal
    descriptor = bd.descriptors(sequence, "u")[0]
    assert descriptor.value is None and "hydrogen atom's single point failed" in descriptor.error


def test_an_output_that_cannot_be_read_fails_that_structure_with_its_reason_and_the_sequence_goes_on():
    sequence = bd.Sequence("C#N")
    sequence.next_job()
    sequence.finish(H_ATOM)
    sequence.next_job()
    assert sequence.finish("garbage") == "failed" and "did not converge" in sequence.failures["mol|parent|0"]
    sequence.next_job()
    assert sequence.finish(CN_RADICAL) == "recorded" and sequence.done
    assert sequence.result().bonds[0].dh_kcal is None and "no accepted parent structure" in sequence.result().bonds[0].reason


def test_a_run_of_several_bonds_marks_the_weakest_and_reports_a_bond_with_no_value_beside_it():
    sequence = bd.Sequence("CO", [0, 1])  # methanol: C-H and O-H
    assert [s["id"] for s in sequence.structures if s["role"] == "radical"] == ["mol|radical|0|0", "mol|radical|1|0"]
    records = [
        {"structure": "atom|H", "role": "atom", "completed": True, "energy": -0.49982},
        {"structure": "mol|parent|0", "role": "parent", "completed": True, "enthalpy": -115.0, "lowest_frequency": 100.0, "skeleton_kept": True},
        {"structure": "mol|radical|0|0", "role": "radical", "atom": 0, "completed": True, "enthalpy": -114.4, "lowest_frequency": 90.0, "skeleton_kept": True, "s2": 0.76},
        {"structure": "mol|radical|1|0", "role": "radical", "atom": 1, "completed": True, "enthalpy": -114.3, "lowest_frequency": -120.0, "skeleton_kept": True, "s2": 0.88},
    ]
    result = bd.resolve(sequence.mol, records, [0, 1])
    carbon, oxygen = result.bonds
    assert carbon.dh_kcal is not None and carbon.weakest and oxygen.dh_kcal is None and "-120 cm-1" in oxygen.reason
    sequence.records = records
    value = bd.descriptors(sequence, "u")[0]
    assert value.value == pytest.approx(carbon.dh_kj) and value.provenance.parameters["bonds_without_value"] == 1 and value.provenance.parameters["weakest_atom"] == 0


def test_the_spin_contaminated_radical_is_flagged_and_decides_nothing():
    records = [
        {"structure": "atom|H", "role": "atom", "completed": True, "energy": -0.49982},
        {"structure": "mol|parent|0", "role": "parent", "completed": True, "enthalpy": -115.0, "lowest_frequency": 100.0, "skeleton_kept": True},
        {"structure": "mol|radical|0|0", "role": "radical", "atom": 0, "completed": True, "enthalpy": -114.4, "lowest_frequency": 90.0, "skeleton_kept": True, "s2": 0.83},
    ]
    row = bd.resolve(bd.molecule_from_smiles("C"), records, [0]).bonds[0]
    assert row.dh_kcal is not None and row.spin_contaminated


# --- the words beside a number -----------------------------------------------------------------------------------------------


def test_the_validation_note_states_the_measured_error_the_direction_and_the_classes_that_run_worse():
    note = bd.validation_note(["C-H", "O-H next to O or N"])
    assert "49 X-H bonds" in note and "1.48" in note and "-1.38" in note and "LOW" in note
    assert "O-H next to O or N: 4 bonds, mean absolute error 3.30, mean signed error -3.30, largest 4.57" in note
    assert "C-H: 32 bonds" in note and "at most 9 heavy atoms" in note and "no Boltzmann averaging" in note
    assert "may have no value" in bd.validation_note(["S-H"]) and "one bond: not an error bar" in bd.validation_note(["S-H"])
    assert "may have no value" not in note


def test_the_typed_output_is_one_enthalpy_in_kilojoules_with_its_table_and_the_measured_error():
    sequence = _run_hcn(H_ATOM, HCN, CN_RADICAL)
    (descriptor,) = bd.descriptors(sequence, "u", run_id="r1", timestamp=5.0)
    assert descriptor.descriptor_id == "orca.bond_dissociation_enthalpy" == bd.DESCRIPTOR_ID and descriptor.units == "kJ/mol" and descriptor.error is None
    assert descriptor.value == pytest.approx(128.83 * 4.184, abs=0.3)
    parameters = descriptor.provenance.parameters
    assert parameters["method"] == "M062X/def2-TZVPD" and parameters["temperature_k"] == 298.15 and parameters["lowest_structure_only"] is True and parameters["run_id"] == "r1"
    assert parameters["bonds"][0]["weakest"] is True and parameters["bonds"][0]["element"] == "C" and "49 X-H bonds" in parameters["validation"]
    assert parameters["hydrogen_atom_translation_kcal"] == pytest.approx(1.4812, abs=1e-3)
