"""The ORCA optimization progress parser, held to a real ORCA 6.1.1 transcript and to hand-written edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from openchem.chem.orca_progress import CRITERIA_NAMES, OrcaProgressParser

REAL = Path(__file__).parent / "fixtures" / "orca" / "bde_hcn_parent_optfreq.out"


def _read(text: str, size: int | None = None):
    parser = OrcaProgressParser()
    if size is None:
        parser.feed(text)
    else:
        for start in range(0, len(text), size):
            parser.feed(text[start:start + size])
    return parser.finish()


@pytest.fixture(scope="module")
def real_text() -> str:
    return REAL.read_text(encoding="utf-8", errors="replace")


def test_a_real_optimization_is_read_to_convergence(real_text):
    progress = _read(real_text)
    assert progress.cycle == 3
    assert progress.max_cycles == 50
    assert progress.converged is True
    assert progress.energy_history[:3] == pytest.approx((-93.423897153316, -93.424651879504, -93.424676334015))
    assert progress.energy_change is not None  # the later frequency job prints one more energy


def test_the_last_table_has_five_named_rows_and_ORCA_converged_with_one_unmet(real_text):
    # Real behaviour: "Everything but the energy has converged ... Convergence will therefore be signaled now".
    # So `converged` comes from ORCA's own statement, never from counting rows.
    progress = _read(real_text)
    assert tuple(item.name for item in progress.criteria) == CRITERIA_NAMES
    assert progress.criteria_met == (4, 5)
    assert [item.name for item in progress.unmet()] == ["Energy change"]
    assert progress.converged is True


def test_a_cycle_mid_run_names_the_criteria_that_hold_it_up(real_text):
    # Stop the stream at the end of cycle 2's table (the line before cycle 3's header).
    cut = real_text.index("GEOMETRY OPTIMIZATION CYCLE   3")
    progress = _read(real_text[:cut])
    assert progress.cycle == 2
    assert progress.converged is False
    assert progress.criteria_met == (0, 5)
    assert {item.name for item in progress.unmet()} == set(CRITERIA_NAMES)
    assert progress.criteria[0].name == "Energy change"
    assert progress.criteria[0].value == pytest.approx(-0.0007547262)
    assert progress.criteria[0].tolerance == pytest.approx(1e-6)


def test_the_first_cycle_table_has_four_rows_because_there_is_no_previous_energy(real_text):
    cut = real_text.index("GEOMETRY OPTIMIZATION CYCLE   2")
    progress = _read(real_text[:cut])
    assert progress.cycle == 1
    assert [item.name for item in progress.criteria] == list(CRITERIA_NAMES[1:])
    assert progress.energy_change is None  # one energy so far: not 0, unknown


@pytest.mark.parametrize("size", [1, 7, 61, 1000])
def test_any_chunking_gives_the_same_result_as_one_read(real_text, size):
    assert _read(real_text, size) == _read(real_text)


def test_crlf_output_reads_like_lf(real_text):
    assert _read(real_text.replace("\n", "\r\n"), 53) == _read(real_text)


def test_a_partial_last_line_is_not_read_early():
    parser = OrcaProgressParser()
    parser.feed("         *                GEOMETRY OPTIMIZATION CYCLE   1            *\nFINAL SINGLE POINT ENERGY       -93.4238")
    assert parser.snapshot().energy is None  # half a number is not an energy
    assert parser.feed("97153316\n").energy == pytest.approx(-93.423897153316)


def test_resets_and_failed_back_transformations_are_counted():
    text = (
        " RMS(Cart) increases - taking linear step, building new B-matrix and trying again\n"
        " RMS(Cart) too big - taking linear step, building new B-matrix and trying again\n"
        " RMS(Cart) too big - taking linear step, building new B-matrix and trying again\n"
        "Reseting .opt file and rebuilding internals.\n"
        "Reseting .opt file and rebuilding internals.\n"
    )
    progress = _read(text)
    assert (progress.resets, progress.back_transform_failures) == (2, 3)


def test_scf_iteration_is_tracked_and_cleared_by_a_new_cycle():
    scf = "    7    -810.2119862773708974    -8.12e-05  1.83e-04  2.12e-03  3.48e-04     2.1\n"
    assert _read(scf).scf_iteration == 7
    both = scf + "         *                GEOMETRY OPTIMIZATION CYCLE   2            *\n"
    assert _read(both).scf_iteration is None


def test_ordinary_indented_numbers_are_not_scf_rows():
    assert _read("    1    -93.3351  not an scf row\n  20   H   :   -0.001051914    0.005269031\n").scf_iteration is None


def test_nothing_printed_means_nothing_known():
    progress = OrcaProgressParser().snapshot()
    assert progress.cycle is None and progress.energy is None and progress.criteria == ()
    assert progress.criteria_met is None and progress.energy_history == ()


def test_a_table_cut_off_by_the_end_of_output_keeps_the_rows_it_had():
    text = (
        "          ----------------------|Geometry convergence|-------------------------\n"
        "          Item                value                   Tolerance       Converged\n"
        "          ---------------------------------------------------------------------\n"
        "          RMS gradient        0.0003380750            0.0000300000      NO\n"
    )
    assert _read(text).criteria_met == (0, 1)


def test_the_energy_history_is_capped():
    parser = OrcaProgressParser()
    parser.MAX_HISTORY = 3
    for i in range(6):
        parser.feed(f"FINAL SINGLE POINT ENERGY       -{i + 1}.000000\n")
    assert parser.snapshot().energy_history == (-4.0, -5.0, -6.0)
