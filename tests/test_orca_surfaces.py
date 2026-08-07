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

from pathlib import Path

import pytest

from openchem.chem.orca_surfaces import (
    ELECTRON_DENSITY,
    ESP,
    MOLECULAR_ORBITAL,
    SPIN_DENSITY,
    SURFACE_KINDS,
    build_plot_commands,
    baked_job_directory,
    default_density_name,
    _density_files_where_orca_expects_them,
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


def test_the_default_density_name_is_fully_qualified():
    """It used to return the bare `job.scfp`, and **orca_plot refuses
    that**: it compares the answer against its own listing, which prints
    the density as a full path. The refusal was invisible because a
    refused name still writes a cube from the fallback density.

    Asserted as "ends with the stem, and carries the directory" rather
    than as one literal string, so the test says the same thing on a
    platform whose separator differs.
    """
    name = Path(default_density_name(Path("/somewhere/job.gbw")))

    assert name.name == "job.scfp"
    assert name.parent == Path("/somewhere")


def test_a_density_name_the_caller_supplies_is_left_alone():
    """The qualification is a DEFAULT, not a rewrite. A caller asking for
    a specific density -- an MP2 or CI density from the listing -- must
    get exactly the string it passed."""
    commands = build_plot_commands(ESP, density_name="job.pmp2re", resolution=40)

    assert "job.pmp2re" in commands.splitlines()


def test_every_registered_kind_is_reachable_by_id():
    assert set(SURFACE_KINDS) == {"electron_density", "esp", "spin_density", "molecular_orbital"}
    assert SURFACE_KINDS["esp"] is ESP


# --- the path a gbw remembers ------------------------------------------------
#
# A gbw records the absolute directory it was created in, and orca_plot
# follows that path for the density index rather than looking in the
# working directory. Retaining a wavefunction copies the files out of the
# scratch job directory and deletes it, so every ESP surface for every
# stored wavefunction failed with exit 64 and no cube.
#
# Measured A/B against the real binary, identical files in the cwd:
#
#     baked directory present   exit 0, job.scfp.esp.cube written
#     baked directory absent    exit 64, CANNOT OPEN FILE
#
# These run without ORCA: they cover reading the path back out and the
# restore/cleanup around the call, which is where the logic is.


def _gbw_recording(directory: Path, recorded: str) -> Path:
    """A stand-in gbw carrying a recorded path the way a real one does:
    a null-terminated ASCII string in surrounding binary."""
    gbw = directory / "job.gbw"
    gbw.write_bytes(b"\x00\x01\x02" + recorded.encode("ascii") + b"\x00" + b"\xff" * 64)
    return gbw


def test_the_recorded_job_directory_is_read_back_out_of_a_gbw(tmp_path):
    gbw = _gbw_recording(tmp_path, r"D:\scratch\orca_job_933toma8\job")

    assert baked_job_directory(gbw) == Path(r"D:\scratch\orca_job_933toma8")


def test_a_gbw_with_no_recorded_path_reports_none(tmp_path):
    """The honest answer for a gbw from another ORCA version -- better
    than a guessed directory, which would be created and left behind."""
    gbw = tmp_path / "job.gbw"
    gbw.write_bytes(b"\x00" * 128)

    assert baked_job_directory(gbw) is None


def test_stray_bytes_are_not_mistaken_for_a_path(tmp_path):
    r"""`\job` appears in binary by chance; a drive letter and colon is
    what distinguishes a real recorded path."""
    gbw = tmp_path / "job.gbw"
    gbw.write_bytes(b"\xff\xfe\\job\x00" + b"\x03" * 32)

    assert baked_job_directory(gbw) is None


def test_the_density_files_are_restored_where_orca_will_look(tmp_path):
    """Only the two small companions -- the gbw is read from the working
    directory and is the large one."""
    store = tmp_path / "wavefunctions" / "abc"
    store.mkdir(parents=True)
    recorded = tmp_path / "scratch" / "orca_job_x"
    gbw = _gbw_recording(store, str(recorded / "job"))
    (store / "job.densities").write_bytes(b"density")
    (store / "job.densitiesinfo").write_bytes(b"index")

    with _density_files_where_orca_expects_them(gbw) as restored:
        assert restored == recorded
        assert (recorded / "job.densitiesinfo").read_bytes() == b"index"
        assert (recorded / "job.densities").read_bytes() == b"density"
        assert not (recorded / "job.gbw").exists()

    assert not recorded.exists()


def test_a_directory_that_already_exists_is_left_alone(tmp_path):
    """It may belong to a job still running, so it is neither written to
    nor deleted."""
    store = tmp_path / "store"
    store.mkdir()
    recorded = tmp_path / "live_job"
    recorded.mkdir()
    (recorded / "keep.me").write_text("in use")
    gbw = _gbw_recording(store, str(recorded / "job"))

    with _density_files_where_orca_expects_them(gbw) as restored:
        assert restored is None

    assert (recorded / "keep.me").read_text() == "in use"


def test_the_restored_directory_goes_away_even_if_the_call_raises(tmp_path):
    """Otherwise a failed surface leaves a directory behind on every
    attempt, in the scratch area, named after a job that no longer
    exists."""
    store = tmp_path / "store"
    store.mkdir()
    recorded = tmp_path / "scratch" / "orca_job_y"
    gbw = _gbw_recording(store, str(recorded / "job"))

    with pytest.raises(RuntimeError):
        with _density_files_where_orca_expects_them(gbw):
            assert recorded.exists()
            raise RuntimeError("orca_plot blew up")

    assert not recorded.exists()


def test_an_unwritable_recorded_path_does_not_stop_the_run(tmp_path):
    """The recorded drive may not exist on this machine any more. Nothing
    is gained by refusing before trying -- orbitals and electron density
    do not need this file at all."""
    store = tmp_path / "store"
    store.mkdir()
    gbw = _gbw_recording(store, r"\?\Q:\definitely\not\here\job")

    with _density_files_where_orca_expects_them(gbw) as restored:
        assert restored is None
