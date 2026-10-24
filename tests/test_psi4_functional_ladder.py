"""The functional ladder (`benchmarks/psi4_agreement/run_functional_ladder.py`, `PLAN_FUNCTIONAL_LADDER.md`): the fixed cell list, the input each cell gets, and the reading rule, on synthetic records. Nothing here runs an engine."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from openchem.chem.orca_engine import OrcaQuantumEngineProvider
from openchem.chem.psi4_engine import Psi4QuantumEngineProvider

_DIRECTORY = Path(__file__).parent.parent / "benchmarks" / "psi4_agreement"
sys.path.insert(0, str(_DIRECTORY))
_spec = importlib.util.spec_from_file_location("psi4_functional_ladder_runner", _DIRECTORY / "run_functional_ladder.py")
ladder = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ladder
_spec.loader.exec_module(ladder)
ra = ladder.ra


# --- the cells and the inputs ---------------------------------------------------------------------------------------------


def test_the_cells_are_the_plans():
    assert ladder.MOLECULES == ["water", "ethanol", "acetic acid", "benzene", "pyridine", "dimethyl sulfoxide"]
    assert list(ladder.FUNCTIONALS) == ["HF", "PBE", "BLYP", "B3LYP", "PBE0"] and ladder.DFT == ("PBE", "BLYP", "B3LYP", "PBE0") and ladder.BASIS == "def2-SVP"
    for engine in ("orca", "psi4"):
        listed = ladder.jobs(engine)
        assert len(listed) == 6 * 5 == 30 and len({job.key for job in listed}) == 30
        assert all(job.stage == "ladder" and job.calc_type == "sp" and job.basis == "def2-SVP" for job in listed)


def _inputs(functional: str):
    mol = ra.molecule("water")
    base, variant = ladder.FUNCTIONALS[functional]
    orca = ra.orca_variant(OrcaQuantumEngineProvider().build_input(mol, 0, 1, f"{base} def2-SVP", "sp"), variant, "sp")
    psi4 = ra.psi4_variant(Psi4QuantumEngineProvider().build_input(mol, 0, 1, f"{base} def2-SVP", "sp"), variant, "sp")
    return orca, psi4


@pytest.mark.parametrize("functional", ["HF", "B3LYP", "PBE0"])
def test_the_shipped_functionals_are_the_applications_own_input_untouched(functional):
    """Byte for byte what version 3 ran, so a cell here and a cell there are the same calculation."""
    mol = ra.molecule("water")
    orca, psi4 = _inputs(functional)

    assert orca == OrcaQuantumEngineProvider().build_input(mol, 0, 1, f"{functional} def2-SVP", "sp")
    assert psi4 == Psi4QuantumEngineProvider().build_input(mol, 0, 1, f"{functional} def2-SVP", "sp")


@pytest.mark.parametrize("functional, orca_name, psi4_name", [("PBE", "PBE", "pbe"), ("BLYP", "BLYP", "blyp")])
def test_the_added_functionals_change_only_the_functionals_name(functional, orca_name, psi4_name):
    shipped_orca, shipped_psi4 = _inputs("B3LYP")
    orca, psi4 = _inputs(functional)

    assert orca.splitlines()[0] == f"! {orca_name} def2-SVP"
    assert orca.splitlines()[1:] == shipped_orca.splitlines()[1:]
    assert psi4.rstrip().endswith(f"energy('{psi4_name}')")
    assert psi4.splitlines()[:-2] == shipped_psi4.splitlines()[:-2]  # everything before the call is the shipped input, scf_type pk and the molecule block included


def test_a_swap_refuses_an_input_it_does_not_recognise():
    with pytest.raises(ValueError):
        ra.psi4_variant("memory 2 GB\nenergy('pbe0')\n", f"{ra.FUNCTIONAL_VARIANT}PBE", "sp")
    with pytest.raises(ValueError):
        ra.orca_variant("! PBE0 def2-SVP\n* xyz 0 1\n*\n", f"{ra.FUNCTIONAL_VARIANT}PBE", "sp")
    with pytest.raises(ValueError):
        ra.psi4_variant("memory 2 GB\nenergy('b3lyp5')\n", f"{ra.FUNCTIONAL_VARIANT}TPSS", "sp")


def test_records_map_back_to_their_functional_label():
    """PBE and BLYP are recorded as the B3LYP functional with a swap variant; B3LYP is the same functional with the default one. They must not be mixed up."""
    rows = {}
    for label, (functional, variant) in ladder.FUNCTIONALS.items():
        rows[label] = {"molecule": "water", "functional": functional, "variant": variant, "completed": True, "energy_hartree": -1.0 - len(rows)}
    mapped = ladder._energies(list(rows.values()))

    assert {label for (_m, label) in mapped} == set(ladder.FUNCTIONALS) and len(mapped) == 5


# --- the reading rule ----------------------------------------------------------------------------------------------------


def _records(offsets: dict[str, float], hf_move: float = 0.0, skip=()):
    """Synthetic records (Hartree) for every cell: ORCA at -100, Psi4 offset by the functional's number (mEh)."""
    orca, psi4 = [], []
    for m in ladder.MOLECULES:
        for label, (functional, variant) in ladder.FUNCTIONALS.items():
            offset = hf_move if label == "HF" else offsets[label]
            for records, energy, engine in ((orca, -100.0, "orca"), (psi4, -100.0 + offset / 1000.0, "psi4")):
                if (m, label, engine) in skip:
                    continue
                records.append({"molecule": m, "functional": functional, "variant": variant, "completed": True, "energy_hartree": energy})
    return orca, psi4


def _verdict(offsets, **kwargs):
    orca, psi4 = _records(offsets, **kwargs)
    return ladder.judge_ladder(ladder.rows_from(orca, psi4))


def test_the_same_offset_in_every_functional_is_common_to_dft():
    verdict, _ = _verdict({"PBE": 0.25, "BLYP": 0.30, "B3LYP": 0.26, "PBE0": 0.22})

    assert verdict == "COMMON TO DFT"


def test_an_offset_only_in_the_functionals_with_one_ingredient_is_functional_specific_and_names_them():
    verdict, why = _verdict({"PBE": 0.01, "BLYP": 0.30, "B3LYP": 0.26, "PBE0": 0.02})

    assert verdict == "FUNCTIONAL-SPECIFIC"
    assert "carry the offset: BLYP, B3LYP" in why[-1] and "free of it: PBE, PBE0" in why[-1]


def test_offsets_that_differ_by_more_than_the_ratio_without_any_being_absent_are_mixed():
    # 0.12 and 0.40 are both present (>= 0.1) but 0.40 / 0.12 > 2, and none is below 0.05
    verdict, _ = _verdict({"PBE": 0.12, "BLYP": 0.40, "B3LYP": 0.26, "PBE0": 0.22})

    assert verdict == "MIXED"


def _rows_with_exact_medians(medians: dict[str, float]) -> list[dict]:
    """Rows built straight at the judge, with exactly representable numbers, so a boundary is tested AT the boundary and not at the mercy of an energy difference's rounding."""
    return [{"molecule": m, "functional": f, "d": 0.0 if f == "HF" else medians[f]} for m in ladder.MOLECULES for f in ladder.FUNCTIONALS]


def test_the_ratio_boundary_is_inclusive():
    exactly_twice = {"PBE": 0.125, "BLYP": 0.25, "B3LYP": 0.125, "PBE0": 0.125}
    just_over = {"PBE": 0.125, "BLYP": 0.2500001, "B3LYP": 0.125, "PBE0": 0.125}

    assert ladder.judge_ladder(_rows_with_exact_medians(exactly_twice))[0] == "COMMON TO DFT"
    assert ladder.judge_ladder(_rows_with_exact_medians(just_over))[0] == "MIXED"


def test_the_present_and_absent_boundaries_are_where_the_plan_puts_them():
    present = {"PBE": 0.1, "BLYP": 0.1, "B3LYP": 0.1, "PBE0": 0.1}  # exactly PRESENT_MEH counts as present
    assert ladder.judge_ladder(_rows_with_exact_medians(present))[0] == "COMMON TO DFT"
    # 0.05 is not below ABSENT_MEH, so PBE is neither present nor absent: MIXED, not FUNCTIONAL-SPECIFIC
    assert ladder.judge_ladder(_rows_with_exact_medians({"PBE": 0.05, "BLYP": 0.25, "B3LYP": 0.25, "PBE0": 0.25}))[0] == "MIXED"
    assert ladder.judge_ladder(_rows_with_exact_medians({"PBE": 0.0499, "BLYP": 0.25, "B3LYP": 0.25, "PBE0": 0.25}))[0] == "FUNCTIONAL-SPECIFIC"


def test_a_hartree_fock_control_that_moves_invalidates_the_run():
    verdict, why = _verdict({"PBE": 0.25, "BLYP": 0.30, "B3LYP": 0.26, "PBE0": 0.22}, hf_move=0.05)

    assert verdict == "NOT VALID" and any("Hartree-Fock" in line for line in why)


def test_a_b3lyp_offset_that_does_not_reproduce_invalidates_the_run():
    verdict, why = _verdict({"PBE": 0.01, "BLYP": 0.01, "B3LYP": 0.05, "PBE0": 0.01})

    assert verdict == "NOT VALID" and any("did not reproduce" in line for line in why)


def test_one_missing_molecule_is_tolerated_and_two_are_not():
    offsets = {"PBE": 0.25, "BLYP": 0.30, "B3LYP": 0.26, "PBE0": 0.22}
    assert _verdict(offsets, skip={("benzene", "PBE", "psi4")})[0] == "COMMON TO DFT"
    verdict, why = _verdict(offsets, skip={("benzene", "PBE", "psi4"), ("water", "PBE", "orca")})
    assert verdict == "NOT EVALUABLE" and "PBE" in why[0]
    # the Hartree-Fock control cannot be waived
    assert _verdict(offsets, skip={("water", "HF", "psi4")})[0] == "NOT EVALUABLE"


def test_the_thresholds_are_the_plans():
    assert (ladder.PRESENT_MEH, ladder.ABSENT_MEH, ladder.COMMON_RATIO, ladder.HF_CONTROL_MEH, ladder.MIN_MOLECULES) == (0.1, 0.05, 2.0, 0.01, 5)


def test_the_electron_counts_are_right():
    assert ladder.electrons("water") == 10 and ladder.electrons("benzene") == 42 and ladder.electrons("dimethyl sulfoxide") == 42 and ladder.electrons("pyridine") == 42
    assert ladder.electrons("ethanol") == 26 and ladder.electrons("acetic acid") == 32
