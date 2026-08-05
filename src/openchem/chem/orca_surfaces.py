"""Driving `orca_plot` non-interactively to get real QM surfaces.

EVERYTHING IN THIS FILE WAS ESTABLISHED AGAINST THE INSTALLED BINARY
(ORCA 6.1.1, `D:\\ORCA\\orca_plot.exe`), NOT FROM DOCUMENTATION. That is
this project's standing rule for ORCA, and it earned its keep here: three
of the five facts below are not guessable.

THE INVOCATION. `orca_plot` advertises two forms::

    orca_plot gbw-file plot-inputfile
    orca_plot gbw-file -i            (interactive)

The first is the one that sounds right and it is NOT used here. Its
plot-input-file format is a fixed-field layout that could not be
determined against this binary: every shape tried failed at
`Error reading MO/OP in ORCA_PLOT` or produced no cube at all, including
the obvious "same numbers as the menu". Rather than ship a guessed format,
this drives the interactive menu with its answers on stdin -- which is
verified working for all five surface kinds below. The cost of that
choice is honest: the menu's ORDER is a UI, and a future ORCA could
renumber it. `_MENU` is therefore one table, so a drift is one edit.

THE MENU NUMBERS THAT MATTER, read off the real binary:

    1  - enter type of plot          2  - enter orbital number
    4  - enter number of grid points 11 - generate      12 - exit

and within "type of plot": 1 = molecular orbitals, 2 = SCF electron
density, 3 = SCF spin density, and **43 = Electrostatic Potential**.
43 is the last entry of a 43-item list that scrolls well past a screen,
which is exactly why it is written down here.

FOUR THINGS THAT WOULD HAVE BEEN GOT WRONG, ALL FOUND BY RUNNING IT:

1. **Three of the four kinds ask a follow-up question, and they ask
   DIFFERENT ones.** This is the trap, because an unanswered prompt does
   not fail -- it eats the next menu number.

   * Types 2 and 3 (density, spin density) print
     `The default name of the density would be: job.scfp` /
     `Is this the one you want (y/n)?` and want **`y`**.
   * Type 43 (ESP) prints `Enter Name for an STATE Density:` and wants
     the **name itself** (`job.scfp`), not `y` and not an index.
   * Type 1 (orbitals) asks nothing.

   Getting this wrong is silent. Sending `1,2,4,20,11,12` for a density
   -- the sequence that looks right -- feeds `4` to the y/n prompt and
   `20` to the filename prompt that follows a "no", then generates at the
   DEFAULT 40x40x40 and exits 0. The cube is real, the molecule is right,
   and the resolution is simply not the one that was asked for.

2. **A spin density on a closed shell is silently the ELECTRON density.**
   Requesting type 3 for a closed-shell molecule prints
   `The density job.scfr does not exist!` and then writes
   `job.spindens.cube` anyway, exit code 0 -- and its contents are
   byte-identical to that job's `job.eldens.cube`. Not zeros, which would
   at least read as "no spin density": the total electron density, every
   value positive and entirely plausible, under a filename that says spin.
   `_MISSING_DENSITY_MARKER` is checked for exactly this.

3. **The output filename is different for every kind**, and is not
   derived from the gbw stem in the ESP case. See `_output_name`.

4. **Grid resolution is asked once, not once per axis**, and the number
   entered is the number of POINTS, not intervals: entering 40 yields a
   40x40x40 grid whose spacing is range/39.

A rejected density NAME (type 43 given something that is not a listed
density) prints `Wrong Density Name selected` / `WARNING: Density NOT
assigned` and also still writes a cube at exit 0. Measured, that file was
byte-identical to the correct one -- orca_plot falls back to the default
density -- so the hazard there is not the values but the NAME: the output
is called after whatever string was entered, so a caller predicting the
path looks for a file that does not exist.

Cubes are written into the working directory, so callers run this with
`cwd` set to the job directory and pass a bare filename. That also
sidesteps ORCA's space-in-path defect, which `quantum_chemistry_service`
already documents.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

#: Grid points per axis. `scalar_field.DEFAULT_RESOLUTION` is 48 for the
#: point-charge field and the same reasoning applies -- cost is cubic --
#: but a QM cube is written once per job rather than recomputed per view,
#: so it can afford to be finer than the interactive path.
DEFAULT_RESOLUTION = 60


class OrcaPlotError(RuntimeError):
    """`orca_plot` did not produce the cube that was asked for.

    Its own exit code is not sufficient to detect this -- see point 1 in
    the module docstring, where a rejected density name still exits 0 --
    so this is raised on the absence of the expected FILE, not on the
    return code.
    """


#: How a plot type answers the density question that follows it. See
#: point 1 of the module docstring -- these three are not interchangeable
#: and picking the wrong one is silent.
DENSITY_PROMPT_NONE = "none"
DENSITY_PROMPT_CONFIRM = "confirm"  # "Is this the one you want (y/n)?"
DENSITY_PROMPT_NAME = "name"  # "Enter Name for an STATE Density:"

#: orca_plot prints this and then writes a cube anyway. Point 2 of the
#: module docstring: on a closed shell the file it writes is the electron
#: density under a spin-density name.
_MISSING_DENSITY_MARKER = "does not exist"
#: Printed when a type-43 density name is not one of the listed densities.
_REJECTED_NAME_MARKER = "Wrong Density Name selected"


@dataclass(frozen=True)
class SurfaceKind:
    """One kind of surface `orca_plot` can produce."""

    id: str
    label: str
    #: The entry to choose in the "type of plot" submenu.
    plot_type: int
    #: What the values mean. Cube carries no units field, so this is the
    #: only place the information exists -- see `cube.py` on why the
    #: values are never rescaled.
    units: str
    #: Which follow-up question this type asks. One of the
    #: DENSITY_PROMPT_* constants.
    density_prompt: str = DENSITY_PROMPT_NONE
    #: Whether the type needs an orbital index (menu entry 2).
    needs_orbital: bool = False


ELECTRON_DENSITY = SurfaceKind(
    id="electron_density",
    label="Electron density",
    plot_type=2,
    units="e/Bohr^3",
    density_prompt=DENSITY_PROMPT_CONFIRM,
)
ESP = SurfaceKind(
    id="esp",
    label="Electrostatic potential (ab initio)",
    plot_type=43,
    units="Hartree/e",
    density_prompt=DENSITY_PROMPT_NAME,
)
SPIN_DENSITY = SurfaceKind(
    id="spin_density",
    label="Spin density",
    plot_type=3,
    units="e/Bohr^3",
    density_prompt=DENSITY_PROMPT_CONFIRM,
)
MOLECULAR_ORBITAL = SurfaceKind(
    id="molecular_orbital",
    label="Molecular orbital",
    plot_type=1,
    units="Bohr^-3/2",
    needs_orbital=True,
)

SURFACE_KINDS: dict[str, SurfaceKind] = {
    kind.id: kind
    for kind in (ELECTRON_DENSITY, ESP, SPIN_DENSITY, MOLECULAR_ORBITAL)
}

#: The interactive menu, in one place so a version drift is one edit.
_MENU_SET_TYPE = "1"
_MENU_SET_ORBITAL = "2"
_MENU_SET_RESOLUTION = "4"
_MENU_GENERATE = "11"
_MENU_EXIT = "12"


def build_plot_commands(
    kind: SurfaceKind,
    *,
    orbital_index: int | None = None,
    density_name: str = "",
    resolution: int = DEFAULT_RESOLUTION,
) -> str:
    """The stdin script that drives `orca_plot -i` for one surface.

    Separated from running it so it is testable without ORCA installed --
    the sequence is the part that encodes everything measured above, and
    it is worth pinning in a test that runs everywhere.
    """
    if kind.needs_orbital and orbital_index is None:
        raise ValueError(f"{kind.id} needs an orbital index")
    if kind.density_prompt == DENSITY_PROMPT_NAME and not density_name:
        # Refused rather than defaulted: an empty answer to the density
        # prompt is the exact input that yields a cube under a name the
        # caller is not expecting. See the module docstring.
        raise ValueError(
            f"{kind.id} prompts for a density name and orca_plot will "
            "silently name its output after whatever it is given"
        )
    if resolution < 2:
        raise ValueError(f"resolution must be at least 2, got {resolution}")

    lines = [_MENU_SET_TYPE, str(kind.plot_type)]
    # THE ANSWER MUST MATCH THE PROMPT. An unanswered prompt does not
    # fail; it consumes the next menu number and the run continues at
    # default settings. See point 1 of the module docstring.
    if kind.density_prompt == DENSITY_PROMPT_NAME:
        lines.append(density_name)
    elif kind.density_prompt == DENSITY_PROMPT_CONFIRM:
        lines.append("y")
    if kind.needs_orbital:
        lines.extend([_MENU_SET_ORBITAL, str(orbital_index)])
    lines.extend([_MENU_SET_RESOLUTION, str(resolution)])
    lines.extend([_MENU_GENERATE, _MENU_EXIT])
    return "\n".join(lines) + "\n"


def _output_name(
    kind: SurfaceKind,
    gbw_stem: str,
    *,
    orbital_index: int | None = None,
    density_name: str = "",
    operator: int = 0,
) -> str:
    """What `orca_plot` will call the file, per kind. All four measured.

    The ESP case is the one that surprises: the stem is the DENSITY NAME,
    not the gbw's. For a job called `job` the density is `job.scfp` and
    the cube is `job.scfp.esp.cube`.
    """
    if kind is ESP:
        return f"{density_name}.esp.cube"
    if kind is ELECTRON_DENSITY:
        return f"{gbw_stem}.eldens.cube"
    if kind is SPIN_DENSITY:
        return f"{gbw_stem}.spindens.cube"
    if kind is MOLECULAR_ORBITAL:
        # "a" for operator 0 (closed shell / alpha), "b" for 1 (beta) --
        # the menu's own note, and confirmed on a real closed-shell run
        # producing job.mo4a.cube.
        return f"{gbw_stem}.mo{orbital_index}{'a' if operator == 0 else 'b'}.cube"
    raise ValueError(f"unknown surface kind {kind.id!r}")


def default_density_name(gbw_path: Path | str) -> str:
    """The SCF density name for a job, which is the gbw stem + `.scfp`.

    Confirmed against `orca_plot job.densities`, which listed exactly
    `job.scfp` and `job.P0.tmp` for a normal closed-shell SCF run.
    """
    return f"{Path(gbw_path).stem}.scfp"


def run_orca_plot(
    orca_plot_executable: str | Path,
    gbw_path: Path | str,
    kind: SurfaceKind,
    *,
    orbital_index: int | None = None,
    density_name: str | None = None,
    resolution: int = DEFAULT_RESOLUTION,
    timeout: float = 600.0,
) -> Path:
    """Generate one cube and return its path.

    Success is decided by the FILE, never by the exit code -- orca_plot
    exits 0 after refusing a density name (module docstring, point 1).
    """
    gbw = Path(gbw_path)
    if not gbw.is_file():
        raise OrcaPlotError(f"no gbw file at {gbw}")

    if kind.density_prompt == DENSITY_PROMPT_NAME and density_name is None:
        density_name = default_density_name(gbw)

    commands = build_plot_commands(
        kind,
        orbital_index=orbital_index,
        density_name=density_name or "",
        resolution=resolution,
    )
    expected = gbw.parent / _output_name(
        kind,
        gbw.stem,
        orbital_index=orbital_index,
        density_name=density_name or "",
    )
    # Removed first so a stale cube from an earlier run cannot be mistaken
    # for this one's output -- the failure mode that "check the file, not
    # the exit code" would otherwise introduce.
    if expected.exists():
        expected.unlink()

    try:
        completed = subprocess.run(
            [str(orca_plot_executable), gbw.name, "-i"],
            input=commands,
            capture_output=True,
            text=True,
            # Bare filename + cwd, so a space anywhere in the absolute
            # path cannot reach ORCA's argument parsing.
            cwd=str(gbw.parent),
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OrcaPlotError(f"orca_plot timed out after {timeout}s") from exc

    output = completed.stdout or ""

    # CHECKED BEFORE THE FILE EXISTS TEST, because both of these produce a
    # file. Exit code is 0 in both cases too, which is why neither is
    # detected by anything else here.
    if _MISSING_DENSITY_MARKER in output:
        raise OrcaPlotError(
            f"orca_plot reported the density for {kind.id} does not exist in "
            f"{gbw.name} (a spin density needs an open-shell calculation). "
            "It wrote a cube anyway -- on a closed shell that file is a copy "
            "of the ELECTRON density, which would render as a plausible and "
            "entirely wrong spin density."
        )
    if _REJECTED_NAME_MARKER in output:
        raise OrcaPlotError(
            f"orca_plot rejected the density name {density_name!r} for "
            f"{gbw.name} and fell back to its default."
        )
    if not expected.is_file():
        raise OrcaPlotError(
            f"orca_plot exited {completed.returncode} without writing "
            f"{expected.name}. Tail of its output:\n{output[-800:]}"
        )
    return expected
