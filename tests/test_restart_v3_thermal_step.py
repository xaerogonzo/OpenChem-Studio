"""The 0 K to 298 K step of Arm D's S-H references (`benchmarks/restart_v3/thermal_step.py`): the reading of ORCA's thermochemistry block, held to a real water job whose answer is known in closed form, and the arithmetic that combines the species."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).parent
_PATH = _HERE.parent / "benchmarks" / "restart_v3" / "thermal_step.py"
_spec = importlib.util.spec_from_file_location("thermal_step_under_test", _PATH)
ts = importlib.util.module_from_spec(_spec)
sys.modules["thermal_step_under_test"] = ts
_spec.loader.exec_module(ts)

WATER = (_HERE / "fixtures" / "orca" / "water_b3lyp_thermochemistry_excerpt.out").read_text(encoding="utf-8")


def test_the_hydrogen_atom_is_translation_only():
    # 3/2 RT of translation + RT of pV = 5/2 RT; no rotation, vibration or electronic part
    assert ts.H_ATOM_KJ == pytest.approx(2.5 * 8.314462618e-3 * 298.15)
    assert ts.H_ATOM_KJ == pytest.approx(6.197, abs=0.001)


def test_water_thermal_enthalpy_is_four_rt_plus_a_little_vibration():
    # real ORCA job: a nonlinear molecule has 3/2 RT translation + 3/2 RT rotation + RT (pV) = 4 RT = 9.91 kJ/mol; the three vibrations at 1638, 3787 and 3882 cm-1 add well under 0.1
    out = ts.thermal_from_output(WATER)
    assert out["h_thermal_kj"] == pytest.approx(4 * 8.314462618e-3 * 298.15, abs=0.05)
    assert out["h_thermal_kj"] > 4 * 8.314462618e-3 * 298.15  # the vibrational part is positive
    assert out["n_frequencies"] == 3 and out["lowest_frequency"] == pytest.approx(1637.67)
    assert out["zpe"] == pytest.approx(0.02120237)


def test_a_job_that_did_not_finish_is_never_a_number():
    with pytest.raises(ValueError, match="terminate normally"):
        ts.thermal_from_output(WATER.replace("ORCA TERMINATED NORMALLY", ""))
    with pytest.raises(ValueError, match="zpe"):
        ts.thermal_from_output(WATER.replace("Zero point energy", "Nothing"))


def test_the_step_is_the_radical_plus_the_atom_minus_the_parent():
    assert ts.step_kj(10.0, 12.0) == pytest.approx(10.0 + ts.H_ATOM_KJ - 12.0)


def _species(parent_h, parent_thermal, radical_h, radical_thermal, parent_freq=100.0, radical_freq=80.0):
    return {"parent": {"enthalpy": parent_h, "h_thermal_kj": parent_thermal, "lowest_frequency": parent_freq},
            "radical": {"enthalpy": radical_h, "h_thermal_kj": radical_thermal, "lowest_frequency": radical_freq}}


def test_the_step_comes_from_the_lowest_enthalpy_conformers_and_the_spread_from_every_pair():
    # conformer 1 is lowest for both the parent and the radical; the other pair is what the spread is made of
    species = [_species(-100.0, 50.0, -99.5, 48.0), _species(-99.9, 51.0, -99.4, 47.0)]
    out = ts.summarise(species)
    assert out["step_kj"] == pytest.approx(48.0 + ts.H_ATOM_KJ - 50.0)
    steps = [48.0 + ts.H_ATOM_KJ - 50.0, 48.0 + ts.H_ATOM_KJ - 51.0, 47.0 + ts.H_ATOM_KJ - 50.0, 47.0 + ts.H_ATOM_KJ - 51.0]
    assert out["spread_kj"] == pytest.approx(max(steps) - min(steps))
    assert out["rejected"] == []


def test_a_species_with_an_imaginary_mode_is_not_used_and_is_reported():
    # the imaginary radical is LOWER in enthalpy (as a saddle point near a rearranged structure can be): it must not be the one the step is taken from
    species = [_species(-100.0, 50.0, -99.5, 48.0), _species(-100.0, 50.0, -99.9, 40.0, radical_freq=-150.0)]
    out = ts.summarise(species)
    assert out["step_kj"] == pytest.approx(48.0 + ts.H_ATOM_KJ - 50.0)
    assert out["rejected"] == [{"role": "radical", "lowest_frequency": -150.0, "skeleton_kept": True}]


def test_a_species_whose_skeleton_changed_is_not_used_either():
    species = [_species(-100.0, 50.0, -99.5, 48.0)]
    species.append(_species(-100.0, 50.0, -99.9, 40.0))
    species[1]["radical"]["skeleton_kept"] = False
    out = ts.summarise(species)
    assert out["step_kj"] == pytest.approx(48.0 + ts.H_ATOM_KJ - 50.0)
    assert out["rejected"][0]["skeleton_kept"] is False


def test_nothing_usable_is_an_error_not_a_number():
    with pytest.raises(ValueError, match="no usable"):
        ts.summarise([_species(-100.0, 50.0, -99.5, 48.0, radical_freq=-300.0)])


def test_the_report_names_a_thiol_with_no_finished_pair():
    text, result = ts.report([])
    assert result == {} and "no finished conformer pair" in text and math.isfinite(ts.H_ATOM_KJ)
