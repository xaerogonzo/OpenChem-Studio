"""The `orca_plot` command builder.

These tests pin down facts that were established by running the real
binary and that nothing else in the suite would notice going wrong: the
menu numbers, and above all WHICH follow-up question each plot type asks.
An unanswered orca_plot prompt does not fail -- it swallows the next menu
number and the run continues at default settings, producing a real cube of
the right molecule at the wrong resolution, exit code 0. That is invisible
without an assertion on the exact byte sequence, which is what this is.

The subprocess half (`run_orca_plot`) is exercised against the installed
ORCA in `benchmarks/esp/`, since it cannot run where ORCA is absent.
"""

from __future__ import annotations

import pytest

from openchem.chem.orca_surfaces import (
    ELECTRON_DENSITY,
    ESP,
    MOLECULAR_ORBITAL,
    SPIN_DENSITY,
    SURFACE_KINDS,
    build_plot_commands,
    default_density_name,
    _output_name,
)


def _lines(*args, **kwargs) -> list[str]:
    return build_plot_commands(*args, **kwargs).strip().splitlines()


def test_electron_density_answers_the_yes_no_prompt():
    """Types 2 and 3 ask `Is this the one you want (y/n)?`. The `y` is
    load-bearing: without it the `4` below is eaten as the answer, `20`
    becomes a filename, and the plot generates at the default 40x40x40."""
    assert _lines(ELECTRON_DENSITY, resolution=20) == [
        "1", "2", "y", "4", "20", "11", "12",
    ]


def test_spin_density_answers_the_same_prompt():
    assert _lines(SPIN_DENSITY, resolution=20) == [
        "1", "3", "y", "4", "20", "11", "12",
    ]


def test_esp_answers_with_a_density_name_not_yes():
    """Type 43 asks a DIFFERENT question -- `Enter Name for an STATE
    Density:` -- and wants the name itself. Answering `y` here would be
    taken as the density name and rejected."""
    assert _lines(ESP, density_name="job.scfp", resolution=20) == [
        "1", "43", "job.scfp", "4", "20", "11", "12",
    ]


def test_esp_is_plot_type_43():
    """The last entry in a 43-item menu that scrolls off any screen, and
    the single hardest fact here to rediscover."""
    assert ESP.plot_type == 43


def test_an_orbital_needs_its_index_selected():
    assert _lines(MOLECULAR_ORBITAL, orbital_index=4, resolution=20) == [
        "1", "1", "2", "4", "4", "20", "11", "12",
    ]


def test_an_orbital_plot_asks_no_density_question():
    """Type 1 is the only kind with no follow-up. Sending `y` would make
    it the orbital number."""
    assert "y" not in _lines(MOLECULAR_ORBITAL, orbital_index=0, resolution=20)


def test_an_esp_without_a_density_name_is_refused():
    """Rather than defaulted -- an empty answer is exactly the input that
    produces a cube under an unexpected filename."""
    with pytest.raises(ValueError, match="density name"):
        build_plot_commands(ESP)


def test_an_orbital_without_an_index_is_refused():
    with pytest.raises(ValueError, match="orbital index"):
        build_plot_commands(MOLECULAR_ORBITAL)


def test_a_degenerate_resolution_is_refused():
    with pytest.raises(ValueError, match="at least 2"):
        build_plot_commands(ELECTRON_DENSITY, resolution=1)


@pytest.mark.parametrize(
    ("kind", "kwargs", "expected"),
    [
        (ELECTRON_DENSITY, {}, "job.eldens.cube"),
        (SPIN_DENSITY, {}, "job.spindens.cube"),
        (MOLECULAR_ORBITAL, {"orbital_index": 4}, "job.mo4a.cube"),
        (ESP, {"density_name": "job.scfp"}, "job.scfp.esp.cube"),
    ],
)
def test_the_output_filename_is_different_for_every_kind(kind, kwargs, expected):
    """All four measured. The ESP one is the outlier: its stem is the
    DENSITY name, not the gbw's, so predicting it from the job name alone
    is wrong."""
    assert _output_name(kind, "job", **kwargs) == expected


def test_a_beta_orbital_is_named_b():
    assert _output_name(MOLECULAR_ORBITAL, "job", orbital_index=2, operator=1) == "job.mo2b.cube"


def test_the_default_density_name_follows_the_gbw_stem():
    assert default_density_name("/somewhere/job.gbw") == "job.scfp"


def test_every_registered_kind_is_reachable_by_id():
    assert set(SURFACE_KINDS) == {"electron_density", "esp", "spin_density", "molecular_orbital"}
    assert SURFACE_KINDS["esp"] is ESP
