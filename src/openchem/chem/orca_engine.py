from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import replace
from pathlib import Path

from rdkit import Chem
from rdkit.Geometry import Point3D

from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import ORCA_OPTIMIZED, ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.quantum_methods import METHOD_BASIS_PRESETS, SOLVENTS  # noqa: F401  (moved to domain/; re-exported)
from openchem.chem.conceptual_dft import from_delta_scf, from_frontier_energies
from openchem.chem.fukui import CondensedFukui, condensed_fukui, open_shell_message, start_notes
from openchem.chem.fukui_plan import (
    START_DEFAULT,
    START_HCORE,
    START_HUECKEL,
    STATE_N,
    STATE_OXIDISED,
    STATE_REDUCED,
    JobResult,
    choose_solutions,
    has_diffuse_functions,
    plan_fukui,
    state_of,
)
from openchem.chem.orca_led import build_led_input, parse_led
from openchem.chem.vibrational_modes import classify_mode
from openchem.domain.scientific_result import (
    NMRSpectrumResult,
    PerAtomDataset,
    VibrationalMode,
    VibrationalSpectrumResult,
)
from openchem.plugins.interfaces import QuantumEngineProvider


def _section(text: str, start_marker: str, end_marker: str) -> str:
    """The text between two markers, or from the start marker to the end.

    Bounded rather than searched unbounded through the whole file, for the
    reason `_SHIELDING_ROW_RE` already documents: an unbounded numeric-row
    regex can false-positive-match an unrelated later table with the same
    shape. ORCA output is long and contains several.
    """
    start = text.find(start_marker)
    if start == -1:
        return ""
    end = text.find(end_marker, start + len(start_marker))
    return text[start:] if end == -1 else text[start:end]


def _mol_at_final_geometry(output_text: str, mol: Chem.Mol) -> Chem.Mol:
    """`mol` carrying the LAST geometry ORCA printed, or `mol` unchanged.

    Frequencies are computed at the optimised geometry, so anything that
    reasons about bond directions has to use that one. Returns the original
    molecule rather than None when no coordinate block is present (a plain
    `Freq` job on a fixed geometry), since there the submitted geometry IS
    the right one.
    """
    blocks = _CARTESIAN_BLOCK_RE.findall(output_text)
    if not blocks:
        return mol
    rows = [line.split() for line in blocks[-1].strip().splitlines() if line.split()]
    if len(rows) != mol.GetNumAtoms():
        # A mismatch means this block is not this molecule. Using it would
        # silently attach one structure's coordinates to another.
        return mol
    try:
        updated = Chem.Mol(mol)
        conformer = Chem.Conformer(updated.GetNumAtoms())
        for index, row in enumerate(rows):
            conformer.SetAtomPosition(
                index, Point3D(float(row[1]), float(row[2]), float(row[3]))
            )
        updated.RemoveAllConformers()
        updated.AddConformer(conformer, assignId=True)
        return updated
    except Exception:  # noqa: BLE001 - fall back to the submitted geometry
        return mol


def parse_frontier_orbitals(output_text: str) -> tuple[int | None, int | None]:
    """(HOMO, LUMO) orbital indices from the ORBITAL ENERGIES table.

    Needed because `orca_plot` asks for an orbital by NUMBER, and that
    number is a property of the basis set rather than of the molecule:
    water's HOMO is orbital 4 in def2-SVP and benzene's is 20. Asking a
    user to type it is asking them to guess, and a wrong index plots a
    real orbital that is not the one they wanted -- so it is read from the
    job that will be plotted.

    The LAST table in the file is used. A geometry optimisation prints one
    per cycle, and the orbitals belong to the converged geometry; an
    unbounded search would return the first SCF's.

    ALPHA ORBITALS ONLY for an open-shell system. An unrestricted job
    prints "SPIN UP ORBITALS" and "SPIN DOWN ORBITALS" under one
    ORBITAL ENERGIES heading, and reading straight through both is not a
    small error: on a real methyl-radical transcript it returned HOMO 3
    from the spin-down block and LUMO 5 from the spin-up one, a frontier
    pair that does not exist in either. Alpha is the right set to return
    rather than merely the safe one -- `orca_plot`'s operator 0 IS the
    alpha set, so these indices are the ones its default plot will use.

    Returns (None, None) when there is no table, and a None LUMO when
    every orbital in the basis is occupied -- which cannot happen for a
    real basis set but is not worth crashing over.
    """
    section = _frontier_section(output_text)
    if section is None:
        return None, None
    homo, lumo = _scan_frontier(section)
    return (homo[0] if homo else None), (lumo[0] if lumo else None)


def _frontier_section(output_text: str) -> str | None:
    """The alpha block of the LAST ORBITAL ENERGIES table, or None.

    Shared by both frontier parsers so the last-table and alpha-only rules
    -- each of which was got wrong once, and the second of which returned a
    frontier pair that exists in neither spin block -- are stated once.
    """
    # `_section` takes the FIRST match, and a geometry optimisation prints
    # one table per cycle; the orbitals belong to the converged geometry.
    last = output_text.rfind("ORBITAL ENERGIES")
    if last == -1:
        return None
    end = output_text.find("MULLIKEN", last)
    section = output_text[last:] if end == -1 else output_text[last:end]

    spin_down = section.find("SPIN DOWN ORBITALS")
    if spin_down != -1:
        section = section[:spin_down]
    return section or None


def _scan_frontier(
    section: str,
) -> tuple[tuple[int, float] | None, tuple[int, float] | None]:
    """(index, E in eV) for the HOMO and the LUMO of one orbital table.

    The energies were captured by `_ORBITAL_ROW_RE` and thrown away from
    the first version of this parser onwards. Frontier energies are what
    conceptual-DFT descriptors are built from, so keeping group 4 costs
    nothing and saves a second pass over the same table.
    """
    homo: tuple[int, float] | None = None
    lumo: tuple[int, float] | None = None
    for match in _ORBITAL_ROW_RE.finditer(section):
        index = int(match.group(1))
        occupation = float(match.group(2))
        electron_volts = float(match.group(4))
        if occupation > 0.0:
            homo = (index, electron_volts)
        elif lumo is None and homo is not None:
            # The first empty orbital AFTER an occupied one. Guarding on
            # `homo` matters for an open-shell beta block, whose table can
            # begin with empty rows.
            lumo = (index, electron_volts)
    return homo, lumo


def parse_frontier_energies(output_text: str) -> tuple[float | None, float | None]:
    """(E_HOMO, E_LUMO) in eV from the ORBITAL ENERGIES table.

    Same table, same last-table and alpha-only rules as
    `parse_frontier_orbitals` -- see that function for why both matter.
    Separate entry point because the two callers want different things: a
    plot needs the orbital NUMBER, and a descriptor needs the ENERGY.

    Measured on a real ORCA 6.1.1 B3LYP/def2-SVP run of water: HOMO is
    orbital 4 at -7.8408 eV and LUMO orbital 5 at +1.2983 eV.
    """
    section = _frontier_section(output_text)
    if section is None:
        return None, None
    homo, lumo = _scan_frontier(section)
    return (homo[1] if homo else None), (lumo[1] if lumo else None)


def _parse_normal_modes(
    output_text: str, atom_count: int
) -> dict[int, tuple[tuple[float, float, float], ...]]:
    """Mode index -> per-atom (dx, dy, dz), from the NORMAL MODES block.

    The block is column-major in chunks: a header row of mode indices, then
    3N rows where row index = 3*atom + component. Confirmed present in the
    `.out` file on a real run, so the separate `.hess` file does not need
    to be read.

    Returned per ATOM rather than as ORCA's flat 3N vector because both
    consumers -- animating a mode, and classifying it as a stretch or a
    bend -- want it that way, and doing the regrouping once here keeps the
    off-by-three risk in one place.
    """
    section = _section(output_text, _NORMAL_MODES_HEADER, "IR SPECTRUM")
    if not section:
        return {}

    columns: dict[int, list[float]] = {}
    current: list[int] = []
    for line in section.splitlines():
        parts = line.split()
        if not parts:
            continue
        # A header row is all bare integers; a data row starts with the
        # coordinate index and continues with signed decimals.
        if all(part.isdigit() for part in parts):
            current = [int(part) for part in parts]
            for mode_index in current:
                columns.setdefault(mode_index, [])
            continue
        if not current or not parts[0].isdigit():
            continue
        try:
            values = [float(part) for part in parts[1:]]
        except ValueError:
            continue
        if len(values) != len(current):
            continue
        for mode_index, value in zip(current, values):
            columns[mode_index].append(value)

    modes: dict[int, tuple[tuple[float, float, float], ...]] = {}
    for mode_index, flat in columns.items():
        if len(flat) != atom_count * 3:
            # A partially-read column is worse than no column: it would
            # animate the wrong atoms. Drop it rather than pad it.
            continue
        modes[mode_index] = tuple(
            (flat[3 * i], flat[3 * i + 1], flat[3 * i + 2]) for i in range(atom_count)
        )
    return modes

# ORCA's simple, well-documented "! <keywords>" / "* xyz <charge> <mult> ...
# *" input format — the shape below is confirmed against ORCA's public
# input manual.
#
# THIS COMMENT USED TO SAY the output-parsing regexes were "NOT verified
# against a real ORCA run in this project (ORCA is external, separately-
# licensed software this session cannot install)". That has not been true
# for some time: ORCA is installed on the reference machine, Phase 7.6
# verified the SCF/thermochemistry/geometry path end-to-end against it, the
# NMR shielding regex was confirmed live, and the vibrational regexes below
# were driven by two real ORCA 6.1.1 transcripts. The caveat is removed
# rather than softened, because a stale "unverified" note is worse than no
# note -- it invites someone to re-do work that was already done.

_CALC_TYPE_KEYWORDS = {
    "sp": "",
    "opt": "Opt",
    "opt_freq": "Opt Freq",
    "nmr": "NMR",
    "nmr_coupling": "NMR",
    # Three single points, no Opt: see `_build_delta_scf_input` for why
    # optimizing here would silently make the answer something else.
    "delta_scf": "",
    # The states of a Fukui run (two for an anion, three otherwise, and extra starts at a diffuse basis), with Hirshfeld
    # populations printed for each: see `_build_fukui_input`.
    "fukui": "",
    # The whole keyword line comes from `chem/orca_led.py` -- LED is
    # defined on DLPNO-CCSD(T) with two auxiliary bases, so the caller's
    # method/basis choice does not apply.
    "led": "",
}

_SCF_ENERGY_RE = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
# ORCA's output has CRLF line ends on Windows, so every newline here is `\r?\n`: with a bare `\n` this found no
# block at all and an optimized geometry was silently never read (found by a live tautomer-NMR run).
_CARTESIAN_BLOCK_RE = re.compile(
    r"CARTESIAN COORDINATES \(ANGSTROEM\)\r?\n-+\r?\n((?:\s*[A-Za-z]{1,2}(?:\s+-?\d+\.\d+){3}\r?\n)+)"
)
_ENTHALPY_RE = re.compile(r"Total [Ee]nthalpy\s+\.\.\.\s+(-?\d+\.\d+)")
_ENTROPY_TERM_RE = re.compile(r"Final entropy term\s+\.\.\.\s+(-?\d+\.\d+)")
_GIBBS_RE = re.compile(r"Final Gibbs free energy\s+\.\.\.\s+(-?\d+\.\d+)")
# Confirmed live against a real ORCA 6.1.1 run's banner text: "Program
# Version 6.1.1  -  RELEASE   -".
_VERSION_RE = re.compile(r"Program Version\s+(\S+)\s*-\s*(\w+)")

#: A row of the ORBITAL ENERGIES table: index, occupation, E(Eh), E(eV).
#: Anchored to four columns so it cannot match the thermochemistry or
#: population tables that also carry rows of numbers -- the same
#: false-positive concern `_SHIELDING_ROW_RE` documents.
_ORBITAL_ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$", re.MULTILINE
)

#: The charge and multiplicity ORCA echoes in each job's input summary. A compound input prints one pair per
#: job, which is how a Fukui parse knows the three tables are the neutral's, the cation's and the anion's.
_TOTAL_CHARGE_RE = re.compile(r"Total Charge\s+Charge\s+\.\.\.\.\s+(-?\d+)")
#: Its companion: the multiplicity each job echoes, so a Fukui parse can insist the neutral is a singlet.
_MULTIPLICITY_RE = re.compile(r"Multiplicity\s+Mult\s+\.\.\.\.\s+(\d+)")
#: The guess ORCA says a job started from ("INITIAL GUESS: HCORE"). `[^\r\n]` because ORCA's output has CRLF line ends on Windows.
_GUESS_RE = re.compile(r"INITIAL GUESS:[ \t]*([^\r\n]+)")
#: The extra starts, by the words ORCA 6.1.1 prints for them: the core-Hamiltonian guess ("HCORE") and the extended-Hueckel one ("MINIMAL BASIS EHT").
#: ORCA's default is "MODEL POTENTIAL" for the first job and "MOREAD" for a later one, and neither is an extra start (a state's first job is its default).
_START_OF_GUESS = {"HCORE": START_HCORE, "MINIMAL BASIS EHT": START_HUECKEL}
#: The title line of ORCA's Hirshfeld block, which starts a table (`parse_hirshfeld_tables`).
_HIRSHFELD_HEADER = "HIRSHFELD ANALYSIS"
#: ORCA prints this once per UNRESTRICTED job, so a compound Fukui output holds two, the cation's then the anion's (the neutral closed shell prints none).
_S_SQUARED_RE = re.compile(r"Expectation value of <S\*\*2>\s*:\s*(-?\d+\.\d+)")
#: A row of the Hirshfeld table: index, element, charge, spin. Four columns exactly, so the MBIS table (which has
#: a population column as well) and the valence-shell table cannot match it.
_HIRSHFELD_ROW_RE = re.compile(r"^\s*(\d+)\s+([A-Za-z]{1,2})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")


def parse_hirshfeld_tables(output_text: str) -> list[list[tuple[str, float]]]:
    """Every Hirshfeld table in `output_text`, in file order, each a list of (element, charge) in atom order.

    Printed by a job run with ``Print[P_Hirshfeld] 1``; a compound input prints one per job. A table is the rows
    of four columns under ``ATOM CHARGE SPIN`` and ends at the first line that is not one (the ``TOTAL`` row), so
    nothing after it can be read as an atom.
    """
    lines = output_text.splitlines()
    tables: list[list[tuple[str, float]]] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() != _HIRSHFELD_HEADER:
            index += 1
            continue
        index += 1
        while index < len(lines) and not (lines[index].split()[:3] == ["ATOM", "CHARGE", "SPIN"]):
            index += 1
        index += 1
        rows: list[tuple[str, float]] = []
        while index < len(lines):
            match = _HIRSHFELD_ROW_RE.match(lines[index])
            if match is None:
                break
            rows.append((match.group(2), float(match.group(3))))
            index += 1
        tables.append(rows)
    return tables


# Confirmed live against a real ORCA 6.1.1 `! NMR` run (HF/STO-3G, water):
#
#   --------------------------------
#   CHEMICAL SHIELDING SUMMARY (ppm)
#   --------------------------------
#
#
#     Nucleus  Element    Isotropic     Anisotropy
#     -------  -------  ------------   ------------
#         0       O          365.694          4.029
#         1       H           33.679         15.151
#         2       H           33.679         15.151
#
# The row regex is bounded to the text between this header and ORCA's own
# "NMR shielding tensor and spin rotation calculation done" line (also
# confirmed present immediately after the table) rather than searched
# unbounded through the rest of the file, since an unbounded search could
# false-positive-match an unrelated later numeric table with the same
# "int, symbol, float, float" shape.
_SHIELDING_HEADER_RE = re.compile(r"CHEMICAL SHIELDING SUMMARY \(ppm\)")
_SHIELDING_ROW_RE = re.compile(r"^\s*(\d+)\s+([A-Za-z]{1,2})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$", re.MULTILINE)
_SHIELDING_END_MARKER = "NMR shielding tensor and spin rotation calculation done"

# Confirmed live against a real ORCA 6.1.1 `%eprnmr ... ssall` run -- see
# parse_spin_spin_coupling's own docstring for the exact captured format.
_COUPLING_SUMMARY_HEADER_RE = re.compile(r"SUMMARY OF ISOTROPIC COUPLING CONSTANTS J \(Hz\)")
_COUPLING_END_MARKER = "NMR spin-spin coupling calculation done"

# Confirmed live against a real ORCA 6.1.1 `! B3LYP def2-SVP Opt Freq`
# run on water, and a second `! Freq` run on a deliberately LINEAR water
# to capture the saddle-point shape. Both transcripts drove these regexes;
# none of it is from documentation.
#
#   VIBRATIONAL FREQUENCIES
#   ------------------------
#
#   Scaling factor for frequencies =  1.000000000  (already applied!)
#
#        0:       0.00 cm**-1
#        ...
#        6:    1637.69 cm**-1
#
# and from the linear (saddle-point) run:
#
#        5:   -1436.35 cm**-1  ***imaginary mode***
#
# TWO THINGS THAT LOOK LIKE DETAILS AND ARE NOT:
#
# 1. THE ZERO-MODE COUNT IS NOT ALWAYS SIX. Nonlinear water reports six
#    0.00 modes (3N-6); linear water reports FIVE (3N-5). Anything that
#    hardcodes six silently mislabels a mode on every linear molecule.
#    ORCA states the boundary itself -- "The first frequency considered
#    to be a vibration is N" -- so that is read rather than derived.
#
# 2. THE IR SPECTRUM TABLE OMITS IMAGINARY MODES ENTIRELY. In the linear
#    run, modes 5 and 6 are imaginary and the IR table starts at mode 7;
#    ORCA counts them as non-vibrations. So frequencies MUST come from the
#    VIBRATIONAL FREQUENCIES block and intensities be joined on by mode
#    index. Building the spectrum from the IR table alone would report a
#    clean spectrum for a saddle point -- which is the exact silent
#    failure that makes every thermochemistry number from the same job
#    meaningless without saying so.
_FREQ_HEADER = "VIBRATIONAL FREQUENCIES"
_FREQ_ROW_RE = re.compile(
    r"^\s*(\d+):\s*(-?\d+\.\d+)\s*cm\*\*-1(\s*\*\*\*imaginary mode\*\*\*)?\s*$",
    re.MULTILINE,
)
_FREQ_SCALING_RE = re.compile(
    r"Scaling factor for frequencies\s*=\s*(\d+\.\d+)"
)
_FIRST_VIBRATION_RE = re.compile(
    r"The first frequency considered to be a vibration is\s+(\d+)"
)
# " Mode   freq       eps      Int      T**2         TX        TY        TZ"
# "  6:   1637.69   0.010942   55.30  0.002085  (-0.000862 -0.045655  0.000000)"
# `Int` (3rd number) is the IR intensity in km/mol.
_IR_HEADER = "IR SPECTRUM"
_IR_ROW_RE = re.compile(
    r"^\s*(\d+):\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*\(",
    re.MULTILINE,
)
# The NORMAL MODES block is a set of column-major chunks: a header row of
# mode indices, then one row per CARTESIAN COORDINATE (3N of them), where
# row index = 3*atom + component. Confirmed present in the .out file, so
# the .hess file does not need to be read.
_NORMAL_MODES_HEADER = "NORMAL MODES"

HARTREE_TO_KCAL_MOL = 627.5094740631

_CALC_TYPES = ("sp", "opt", "opt_freq", "nmr", "nmr_coupling", "delta_scf", "fukui", "led")

# Public, chemistry-layer source of truth for calc_type display names and
# real method/basis presets -- both used to live UI-panel-private in
# quantum_chemistry_panel.py (`_CALC_TYPE_LABELS`/`_METHOD_BASIS_PRESETS`).
# Moved here (Phase 21) so bootstrap.py's CalculatorRegistry registrations
# and the panel's own combo boxes read from one place instead of two
# hand-synced copies that could silently drift apart. Keyed display-name ->
# calc_type (not the other way around) to match the panel's original
# `addItems(list(...keys()))` / `[...currentText()]` usage unchanged.
CALC_TYPE_LABELS = {
    "Single Point": "sp",
    "Geometry Optimization": "opt",
    "Optimization + Frequency": "opt_freq",
    "NMR (raw shielding)": "nmr",
    "NMR + Spin-Spin Coupling": "nmr_coupling",
    "Hardness / Softness (delta-SCF)": "delta_scf",
    "Fukui functions (Hirshfeld)": "fukui",
    # Named for what it answers rather than for the method, like every
    # other entry here. The method/basis combo is IGNORED for this one --
    # LED is defined on DLPNO-CCSD(T) and picking B3LYP would produce a
    # job ORCA refuses.
    "Interaction energy breakdown (LED)": "led",
}
# Recommended when the calc type is NMR -- the panel preselects this rather
# than silently leaving a general-purpose basis chosen for a job whose whole
# point is shielding accuracy.
NMR_METHOD_BASIS = "B3LYP pcSseg-1"



#: Measured on Salvinorin A (59 atoms, B3LYP/pcSseg-1 NMR, this machine, ORCA
#: 6.1.1): 1 core 743 s, 8 cores 97 s, 16 cores 111 s. Past about eight the
#: job stops scaling and starts paying for the extra processes, so the
#: automatic choice is capped there; the setting can still go higher.
AUTO_CORES_CAP = 8
#: Where the MS-MPI installer puts `mpiexec`, for a process started before the
#: installer changed the system PATH.
_MPI_BIN_DIRS = (r"C:\Program Files\Microsoft MPI\Bin",)


def find_mpi_bin() -> str | None:
    """The directory holding `mpiexec`, or None when no MPI is installed.

    ORCA on Windows starts a parallel job by calling `mpiexec`, and without it
    aborts in Startup ("'mpiexec' is not recognized") -- so a core count above
    one is only ever requested when this finds one. The installer puts the
    directory on the system PATH, but a process started BEFORE the install
    never sees that, hence the fixed fallback.
    """
    found = shutil.which("mpiexec")
    if found:
        return str(Path(found).parent)
    for directory in _MPI_BIN_DIRS:
        if Path(directory, "mpiexec.exe").is_file():
            return directory
    return None


def default_cores() -> int:
    """Half the logical cores, capped at `AUTO_CORES_CAP`, at least one."""
    return max(1, min(AUTO_CORES_CAP, (os.cpu_count() or 2) // 2))


def add_parallel_block(input_text: str, cores: int) -> str:
    """Puts `%pal nprocs N end` straight after the `!` line. One core adds
    nothing: a serial job needs no MPI at all."""
    if cores <= 1:
        return input_text
    lines = input_text.split("\n")
    for index, line in enumerate(lines):
        if line.lstrip().startswith("!"):
            lines.insert(index + 1, f"%pal nprocs {cores} end")
            return "\n".join(lines)
    return input_text


class OrcaOutputError(Exception):
    """Raised when ORCA's output can't be parsed — no SCF energy found
    (job likely failed/didn't converge), or an internal inconsistency.
    Always caught by the service and reported as a failed job, never left
    to crash."""


class OrcaQuantumEngineProvider(QuantumEngineProvider):
    provider_id = "orca"
    # The service adds a `%pal` block only for an engine that says it can use
    # one, so a fake or a future engine is never handed ORCA syntax.
    supports_parallel = True

    def build_input(
        self, mol: Chem.Mol, charge: int, multiplicity: int, method_basis: str, calc_type: str
    ) -> str:
        if calc_type not in _CALC_TYPES:
            raise ValueError(f"Unknown calc_type: {calc_type!r} (expected one of {_CALC_TYPES})")
        keywords = _CALC_TYPE_KEYWORDS[calc_type]
        header = f"! {method_basis} {keywords}".strip()

        conf = mol.GetConformer()
        coordinates = [
            f"{atom.GetSymbol():<3}"
            f"{conf.GetAtomPosition(atom.GetIdx()).x:>14.6f}"
            f"{conf.GetAtomPosition(atom.GetIdx()).y:>14.6f}"
            f"{conf.GetAtomPosition(atom.GetIdx()).z:>14.6f}"
            for atom in mol.GetAtoms()
        ]

        if calc_type == "delta_scf":
            return self._build_delta_scf_input(header, coordinates, charge, multiplicity)

        if calc_type == "fukui":
            return self._build_fukui_input(
                header, coordinates, charge, multiplicity, diffuse=has_diffuse_functions(method_basis)
            )

        if calc_type == "led":
            return self._build_led_input(mol, charge, multiplicity)

        lines = [header, f"* xyz {charge} {multiplicity}", *coordinates, "*"]
        if calc_type == "nmr_coupling":
            # Confirmed live against a real ORCA 6.1.1 run: the %eprnmr
            # block MUST come AFTER the coordinate (`* xyz ... *`) block --
            # ORCA aborts at startup ("nuclear properties are requested
            # but no coordinates have been read") if it's placed before,
            # unlike every other ORCA block in this file which precedes
            # coordinates. `ssall` requests spin-spin coupling to every
            # other listed nucleus; `shift` keeps the shielding summary
            # (same one plain "nmr" already produces) so a coupling run
            # doesn't lose that data.
            lines.extend(
                [
                    "",
                    "%eprnmr",
                    " Nuclei = all C { shift, ssall }",
                    " Nuclei = all H { shift, ssall }",
                    "end",
                ]
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _ion_multiplicity(multiplicity: int) -> int:
        """Spin multiplicity of the molecule with one electron added or removed.

        A closed-shell neutral is unambiguous: no unpaired electrons
        becomes exactly one, so a singlet gives doublet ions and that is
        the case essentially every use of this hits.

        For an OPEN-shell neutral it is a guess. A doublet's cation can be
        a singlet or a triplet and nothing in the structure says which is
        lower, so the lower-spin state is taken and the result says so
        rather than presenting a choice as a fact.
        """
        return multiplicity + 1 if multiplicity == 1 else multiplicity - 1

    def _build_delta_scf_input(
        self, header: str, coordinates: list[str], charge: int, multiplicity: int
    ) -> str:
        """Neutral, cation and anion in ONE input, via ORCA's `$new_job`.

        Confirmed live against ORCA 6.1.1: a compound input runs all three
        and prints three FINAL SINGLE POINT ENERGY lines in order, so this
        stays one job with one output and the service needs no notion of
        chained runs.

        **All three use the geometry as supplied, and none of them
        optimizes.** That is what makes I and A VERTICAL, which is what
        the descriptors are defined against. Optimizing the ions would
        give adiabatic values -- a different and smaller quantity -- and
        optimizing only the neutral would leave the ions at a geometry
        that is no longer the neutral's, which is the silent version of
        the same error. Run a geometry optimization first if the drawn
        geometry is not good enough; this deliberately will not do it for
        you.
        """
        ion_multiplicity = self._ion_multiplicity(multiplicity)
        blocks = [
            (charge, multiplicity),
            (charge + 1, ion_multiplicity),
            (charge - 1, ion_multiplicity),
        ]
        lines: list[str] = []
        for index, (job_charge, job_multiplicity) in enumerate(blocks):
            if index:
                lines.extend(["", "$new_job"])
            lines.extend([header, f"* xyz {job_charge} {job_multiplicity}", *coordinates, "*"])
        return "\n".join(lines) + "\n"

    #: ORCA's integration grid for every job of a Fukui input. Hirshfeld charges are INTEGRALS on that grid, and at ORCA's default one seven anions
    #: at 6-311+G** summed 0.010 to 0.073 electrons short of their charge (a diffuse electron the grid does not reach), so those runs were refused; on this
    #: grid every one came within 0.005 (benchmarks/fukui_gate/PREREGISTRATION.md 11.5, 11.6). It changed NO value of the 14 jobs of the first gate (0.0000, at
    #: 6-31G**), no f+ or f- of aspirin, caffeine or ibuprofen at B3LYP/6-31G* by more than 0.00001 and no f- of seven bound anions at B3LYP/6-31+G* by more than
    #: 0.0004, and it costs 8% to 28% of a run on those three molecules and up to a third on the small anions (benchmarks/fukui_gate_2/DESIGN.md).
    _FUKUI_GRID = ("%method", "  IntAcc 6.0", "end")
    #: How the grid is named in a result's provenance.
    _FUKUI_GRID_NAME = "IntAcc 6.0"

    def _build_fukui_input(
        self, header: str, coordinates: list[str], charge: int, multiplicity: int, *, diffuse: bool = False
    ) -> str:
        """The states of a Fukui run in ONE input, Hirshfeld populations printed for each (`chem.fukui_plan.plan_fukui` says which).

        The delta-SCF input with ``%output Print[P_Hirshfeld] 1`` in every job, and for the same reasons: ORCA
        runs the jobs and prints one table each, in order, nothing is optimized (the Fukui function is the
        response at FIXED nuclei, so the ions stay at the neutral geometry), and one job means one output for
        the service to read. The blocks sit BEFORE the coordinates, like every ORCA block except ``%eprnmr``.

        **A species with unpaired electrons is refused**, where delta-SCF takes the lower-spin ion and says so.
        Its cation and anion each have more than one reachable spin state and nothing in the structure says
        which the Fukui function is about; a guess would produce a table of numbers that looks like an answer.
        A charged closed-shell species (a carboxylate, an ammonium) is fine: the ions are doublets.

        **A species with a negative charge ends with a dianion job**: its N+1 state is a dianion (see `chem.fukui_plan`), the one state here that is only the
        basis set's, and f- does not need it, so it is written after everything f- needs.
        **At a basis set with diffuse functions** each anionic state also gets `chem.fukui_plan.EXTRA_STARTS`, written after the default jobs of the states f- needs and,
        for an anion, before its dianion: ORCA ends the compound input at the first job that does not converge, so the jobs the answer needs must precede any that can
        fail, and a dianion that does not converge costs f+ and nothing else. An explicit guess keyword in a later
        job replaces the "read the previous job's orbitals" default (measured on ORCA 6.1.1: the output's INITIAL GUESS line names HCORE or MINIMAL BASIS EHT
        where an unmarked job says MOREAD).

        **Every job states whether it is restricted** (``HFTyp RHF`` for a singlet, ``UHF`` for a doublet; ORCA's RHF also means RKS). Without it a closed-shell
        job written AFTER an open-shell one ran UNRESTRICTED: ORCA switches the first doublet to UHF/UKS and keeps the setting for the later jobs of a compound input
        (measured: the extra starts of a closed-shell anion printed ``HFTyp .... UHF`` and an <S**2> of 0). A singlet that is free to break spin symmetry is not
        the closed-shell state the N state means, and a lower broken-symmetry solution found by an extra start would have been read as a better solution of it.
        """
        if multiplicity != 1:
            raise ValueError(open_shell_message(multiplicity))
        plan = plan_fukui(charge, multiplicity, diffuse=diffuse)
        lines: list[str] = []
        for index, job in enumerate(plan.jobs):
            if index:
                lines.extend(["", "$new_job"])
            job_header = header if job.start == START_DEFAULT else f"{header} {job.start}"
            lines.extend(
                [job_header, "%scf", f"  HFTyp {'RHF' if job.multiplicity == 1 else 'UHF'}", "end", *self._FUKUI_GRID,
                 "%output", "  Print[P_Hirshfeld] 1", "end", f"* xyz {job.charge} {job.multiplicity}", *coordinates, "*"]
            )
        return "\n".join(lines) + "\n"

    def _build_led_input(self, mol: Chem.Mol, charge: int, multiplicity: int) -> str:
        """The two fragments are the molecule's DISCONNECTED COMPONENTS.

        That is not a shortcut, it is what LED is for: an interaction energy
        is between two species held together by something other than a
        covalent bond, and in RDKit that is exactly two fragments. It also
        makes the refusal below correct rather than arbitrary -- a single
        connected molecule has no partners to decompose an interaction
        between, whatever the user hoped.

        Drawing the partners as separate species is therefore the input
        format, and the message says so rather than reporting a failure the
        user cannot act on.
        """
        pieces = Chem.GetMolFrags(mol)
        if len(pieces) != 2:
            raise ValueError(
                f"An LED interaction breakdown needs exactly two separate species; "
                f"this structure has {len(pieces)}. Draw the two partners as "
                "separate molecules (a Lewis acid and its base, a hydrogen-bonded "
                "pair) rather than joined by a bond."
            )

        fragment_of = {index: 1 for index in pieces[0]}
        fragment_of.update({index: 2 for index in pieces[1]})

        conf = mol.GetConformer()
        coordinates = [
            (
                atom.GetSymbol(),
                conf.GetAtomPosition(atom.GetIdx()).x,
                conf.GetAtomPosition(atom.GetIdx()).y,
                conf.GetAtomPosition(atom.GetIdx()).z,
            )
            for atom in mol.GetAtoms()
        ]
        return build_led_input(
            coordinates,
            [fragment_of[atom.GetIdx()] for atom in mol.GetAtoms()],
            charge=charge,
            multiplicity=multiplicity,
        )

    def command_args(self, executable_path: str, input_path: Path) -> list[str]:
        # ORCA's own invocation convention: `orca job.inp`, writing its
        # full output to stdout (no separate --out file argument, unlike
        # Vina) — the service captures that stdout directly.
        return [executable_path, str(input_path)]

    def parse_output(
        self, output_text: str, mol: Chem.Mol, molecule_uuid: str, calc_type: str
    ) -> tuple[list[DescriptorValue], ConformerModel | None]:
        # A geometry optimization prints "FINAL SINGLE POINT ENERGY" once per
        # cycle, not once per job -- RDX alone takes 28. `.search()` (first
        # match) silently returned cycle 1's energy, essentially the
        # MMFF94-preoptimized starting geometry, not the converged minimum;
        # measured live, this was 44-109 kJ/mol off (RDX/HMX/PETN) for an
        # energetics survey that had been treating it as the converged
        # value. `sp`/`nmr`/`nmr_coupling` print exactly one such line, so
        # last == first for them. `delta_scf`/`led` run a compound job with
        # multiple SINGLE POINTS (no optimization) in a fixed, meaningful
        # order (neutral/cation/anion; dimer/fragments) -- taking the FIRST
        # there is correct by construction and must not change.
        if calc_type in ("opt", "opt_freq"):
            scf_matches = list(_SCF_ENERGY_RE.finditer(output_text))
            if not scf_matches:
                raise OrcaOutputError(
                    "Could not find 'FINAL SINGLE POINT ENERGY' in ORCA output — "
                    "the job likely failed or did not converge."
                )
            scf_energy_hartree = float(scf_matches[-1].group(1))
        else:
            scf_match = _SCF_ENERGY_RE.search(output_text)
            if scf_match is None:
                raise OrcaOutputError(
                    "Could not find 'FINAL SINGLE POINT ENERGY' in ORCA output — "
                    "the job likely failed or did not converge."
                )
            scf_energy_hartree = float(scf_match.group(1))
        now = time.time()
        # One shared Provenance for every DescriptorValue/ConformerModel/
        # SpectrumResult this call produces -- same ORCA run, same "what
        # produced this," so they should carry an identical timestamp
        # rather than each grabbing a slightly different time.time().
        # ORCA's own version is recorded here too -- output format drifts
        # between ORCA versions (confirmed live the shielding-summary
        # table format itself, so future-parser compatibility is a real
        # concern, not speculative).
        version_match = _VERSION_RE.search(output_text)
        provenance = Provenance(
            created_by="core",
            method=self.provider_id,
            parameters={"orca_version": version_match.group(1) if version_match else "unknown"},
            timestamp=now,
        )

        descriptors = [
            DescriptorValue(
                descriptor_id="orca.scf_energy",
                name="SCF Energy",
                units="Hartree",
                category="quantum_chemistry",
                provider="orca",
                molecule_uuid=molecule_uuid,
                value=scf_energy_hartree,
                timestamp=now,
                cache_state=CacheState.COMPLETED,
                provenance=provenance,
            )
        ]

        if calc_type == "delta_scf":
            descriptors.extend(self._parse_delta_scf(output_text, molecule_uuid, provenance))
        elif calc_type == "led":
            descriptors.extend(self._parse_led(output_text, molecule_uuid, provenance))
        elif calc_type == "fukui":
            # The per-atom datasets are `parse_per_atom_output`'s. Read here too, and the result thrown away,
            # because this call is the one whose failure fails the RUN: a Fukui job whose three tables will not
            # read has produced nothing, and "completed" with no numbers would say otherwise.
            self._condensed_fukui(output_text, mol)
        else:
            # NOT for delta_scf, NOT for fukui, and NOT for led. All write COMPOUND inputs,
            # so their output holds three orbital tables and the frontier
            # parsers take the LAST one -- the ANION's for delta-SCF and Fukui, the
            # second FRAGMENT's for LED. Koopmans numbers computed from
            # either would be silently about a different species, and would
            # look entirely reasonable. Every other calc type has one table.
            descriptors.extend(
                self._parse_conceptual_dft(output_text, molecule_uuid, provenance)
            )

        if calc_type == "opt_freq":
            descriptors.extend(self._parse_thermochemistry(output_text, molecule_uuid, provenance))

        optimized_conformer = None
        if calc_type in ("opt", "opt_freq"):
            optimized_conformer = self._parse_optimized_conformer(output_text, mol, provenance)

        return descriptors, optimized_conformer

    #: (descriptor id suffix, display name, units, attribute on ConceptualDFT).
    _CONCEPTUAL_DFT_FIELDS = (
        ("homo_energy", "E(HOMO)", "eV", None),
        ("lumo_energy", "E(LUMO)", "eV", None),
        ("ionization_potential", "Ionization Potential (Koopmans)", "eV", "ionization_potential"),
        ("electron_affinity", "Electron Affinity (Koopmans)", "eV", "electron_affinity"),
        ("electronegativity", "Electronegativity", "eV", "electronegativity"),
        ("chemical_potential", "Chemical Potential", "eV", "chemical_potential"),
        ("hardness", "Chemical Hardness", "eV", "hardness"),
        ("softness", "Chemical Softness", "1/eV", "softness"),
        ("electrophilicity", "Electrophilicity Index", "eV", "electrophilicity"),
    )

    #: delta-SCF reports the same descriptor names as Koopmans, minus the
    #: orbital energies -- there is no single HOMO here, and I and A did
    #: not come from one. The ids differ so a molecule can carry both sets
    #: and a reader can tell which is which.
    _DELTA_SCF_FIELDS = (
        ("dscf_ionization_potential", "Ionization Potential (delta-SCF)", "eV", "ionization_potential"),
        ("dscf_electron_affinity", "Electron Affinity (delta-SCF)", "eV", "electron_affinity"),
        ("dscf_electronegativity", "Electronegativity (delta-SCF)", "eV", "electronegativity"),
        ("dscf_chemical_potential", "Chemical Potential (delta-SCF)", "eV", "chemical_potential"),
        ("dscf_hardness", "Chemical Hardness (delta-SCF)", "eV", "hardness"),
        ("dscf_softness", "Chemical Softness (delta-SCF)", "1/eV", "softness"),
        ("dscf_electrophilicity", "Electrophilicity Index (delta-SCF)", "eV", "electrophilicity"),
    )

    def _parse_led(
        self, output_text: str, molecule_uuid: str, provenance: Provenance
    ) -> list[DescriptorValue]:
        """The interaction energy and its terms, one descriptor each.

        Every term is reported, including the total, and NOTHING here
        combines them into a score. That is the same choice `AdductEvidence`
        makes and for the same reason: the terms answer different questions,
        and the one that matters depends on the pair.
        """
        decomposition = parse_led(output_text)
        if not decomposition:
            raise OrcaOutputError(decomposition.error)

        caveat = " ".join(decomposition.limitations + decomposition.warnings)
        annotated = replace(
            provenance,
            parameters={
                **provenance.parameters,
                "caveat": caveat,
                # So a reader can see how completely the terms account for
                # the total without recomputing it.
                "residual_kcal": round(decomposition.residual_kcal, 4),
            },
        )
        descriptors = [
            DescriptorValue(
                descriptor_id="orca.led_interaction",
                name="Interaction energy (LED)",
                units="kcal/mol",
                category="quantum_chemistry",
                provider="orca",
                molecule_uuid=molecule_uuid,
                value=decomposition.interaction_kcal,
                timestamp=provenance.timestamp,
                cache_state=CacheState.COMPLETED,
                provenance=annotated,
            )
        ]
        descriptors.extend(
            DescriptorValue(
                descriptor_id=f"orca.led_{term.label.split()[0].lower()}",
                name=term.label,
                units="kcal/mol",
                category="quantum_chemistry",
                provider="orca",
                molecule_uuid=molecule_uuid,
                value=term.kcal,
                timestamp=provenance.timestamp,
                cache_state=CacheState.COMPLETED,
                provenance=annotated,
            )
            for term in decomposition.terms
        )
        return descriptors

    @staticmethod
    def _fukui_job_results(output_text: str, symbols: list[str]) -> list[JobResult]:
        """One `JobResult` per job of a `fukui` output, in the order ORCA ran them, or `OrcaOutputError` saying what is wrong.

        A job is the stretch of output from its echo of the charge and multiplicity to the next job's echo: ORCA prints that echo once per job before
        anything else of it (measured on ORCA 6.1.1, five jobs, five echoes), so the SCF energy, the Hirshfeld table and the ``<S**2>`` found in a stretch are
        THAT job's, and a job that failed to converge is a stretch with no energy and no table, named as such, where counting every energy in the file could
        only say that the total was wrong. Which state a job is comes from its own echoed charge and multiplicity against the FIRST job's (the species'), and a
        state's first job is its default start while any later one is an extra start, named by the guess ORCA says it used (`INITIAL GUESS:`). Each table
        must list the elements of `mol` in order, so a table of another molecule cannot be differenced with it.
        """
        starts = [match.start() for match in _TOTAL_CHARGE_RE.finditer(output_text)]
        if not starts:
            raise OrcaOutputError(
                "This output echoes no job's charge and multiplicity, so it holds no Fukui calculation; the job most likely failed before its first SCF."
            )
        segments = [output_text[begin:end] for begin, end in zip(starts, [*starts[1:], len(output_text)])]
        reference = int(_TOTAL_CHARGE_RE.match(segments[0]).group(1))
        results: list[JobResult] = []
        seen: set[str] = set()
        for position, segment in enumerate(segments, start=1):
            charge = int(_TOTAL_CHARGE_RE.match(segment).group(1))
            multiplicity_match = _MULTIPLICITY_RE.search(segment)
            multiplicity = int(multiplicity_match.group(1)) if multiplicity_match else 0
            state = state_of(reference, charge, multiplicity)
            # The first job is the N state by construction (the species' own charge is its echo, and a multiplicity other than 1 is no state at all).
            if state is None:
                raise OrcaOutputError(
                    f"Job {position} of this output has charge {charge:+d} and multiplicity {multiplicity}, which is not the N, N-1 or N+1 state of a "
                    f"closed-shell species of charge {reference:+d}; its table cannot be assigned to a state."
                )
            if state in seen:
                guess = _GUESS_RE.search(segment)
                guess_name = guess.group(1).strip() if guess else ""
                start = _START_OF_GUESS.get(guess_name, guess_name.title() or f"start {position}")
            else:
                start = START_DEFAULT
            seen.add(state)
            energies = _SCF_ENERGY_RE.findall(segment)
            tables = parse_hirshfeld_tables(segment)
            table = tables[-1] if tables else None
            if table is not None and [element.upper() for element, _charge in table] != symbols:
                raise OrcaOutputError(
                    f"Job {position}'s Hirshfeld table lists {len(table)} atoms that are not this molecule's {len(symbols)} in order, "
                    "so its charges cannot be matched to the structure."
                )
            squares = _S_SQUARED_RE.findall(segment)
            results.append(
                JobResult(
                    state=state,
                    charge=charge,
                    multiplicity=multiplicity,
                    start=start,
                    energy_hartree=float(energies[-1]) if energies else None,
                    charges=tuple(value for _element, value in table) if table is not None else None,
                    s_squared=float(squares[-1]) if squares else None,
                )
            )
        return results

    def _condensed_fukui(self, output_text: str, mol: Chem.Mol) -> CondensedFukui:
        """The condensed Fukui functions of a `fukui` job's output, or `OrcaOutputError` saying what is wrong.

        Per job (`_fukui_job_results`), and checked where ORCA lets it be: each job echoes its own charge and multiplicity, which is how the
        tables are assigned to the N, N-1 and N+1 states and how an extra start is told from a state. The N and N-1 states must have finished, and the N+1 state
        too for every species that is not an anion. **An anion's N+1 state is a dianion, which f- does not need**, so an output of an anion whose dianion job did not
        finish (or that has none) gives f- alone and says why, where the same failure for any other species fails the run. Of the jobs of one state the solution read
        is `chem.fukui_plan.choose_solutions`'s.
        """
        symbols = [atom.GetSymbol().upper() for atom in mol.GetAtoms()]
        results = self._fukui_job_results(output_text, symbols)
        reference = results[0].charge
        solutions = choose_solutions(results)
        needed = [STATE_N, STATE_OXIDISED] + ([STATE_REDUCED] if reference >= 0 else [])
        for state in needed:
            if state not in solutions:
                jobs = [position for position, result in enumerate(results, start=1) if result.state == state]
                where = f"job {jobs[0]}" if jobs else "it"
                raise OrcaOutputError(
                    f"The {state} state of this Fukui calculation did not finish: ORCA printed no SCF energy and Hirshfeld table for {where}. "
                    "That calculation most likely failed to converge."
                )
        chosen = {state: solution.chosen for state, solution in solutions.items()}
        reduced = chosen.get(STATE_REDUCED)
        unavailable = ""
        if reduced is None:  # only an anion can be here: the N+1 state of every other species was required above
            dianion_jobs = [position for position, result in enumerate(results, start=1) if result.state == STATE_REDUCED]
            unfinished = [position for position, result in enumerate(results, start=1) if not result.complete]
            if dianion_jobs:
                unavailable = (
                    f"ORCA printed no SCF energy and Hirshfeld table for the dianion (job {dianion_jobs[0]}), most likely because its SCF did not converge."
                )
            elif unfinished:
                # ORCA ends a compound input at the first job that does not converge, and the dianion is written after the extra starts of the anion.
                unavailable = f"ORCA ended the run at job {unfinished[0]}, which did not converge, before it reached the dianion."
        read = [STATE_N, STATE_OXIDISED] + ([STATE_REDUCED] if reduced is not None else [])
        result = condensed_fukui(
            chosen[STATE_N].charges,
            chosen[STATE_OXIDISED].charges,
            reduced.charges if reduced is not None else None,
            total_charge=reference,
            energy_neutral_hartree=chosen[STATE_N].energy_hartree,
            energy_anion_hartree=reduced.energy_hartree if reduced is not None else None,
            # The N-1 and N+1 states' own values, or unknown: a restricted ion (or an output that printed none) says nothing about its
            # contamination, and nothing is guessed.
            cation_s_squared=chosen[STATE_OXIDISED].s_squared,
            anion_s_squared=reduced.s_squared if reduced is not None else None,
            solutions=tuple(solutions[state] for state in read),
            anion_unavailable=unavailable,
        )
        if not result:
            raise OrcaOutputError(result.reason)
        return result

    #: (property id suffix, display name, attribute on CondensedFukui). The scheme is in every name so a later
    #: scheme is a new dataset beside these and not a reinterpretation of them.
    _FUKUI_DATASETS = (
        ("fukui_plus", "Fukui f+ (Hirshfeld)", "f_plus"),
        ("fukui_minus", "Fukui f- (Hirshfeld)", "f_minus"),
        ("fukui_zero", "Fukui f0 (Hirshfeld)", "f_zero"),
        ("fukui_dual", "Dual descriptor f+ - f- (Hirshfeld)", "dual"),
    )

    def parse_per_atom_output(
        self, output_text: str, mol: Chem.Mol, molecule_uuid: str, calc_type: str
    ) -> list[PerAtomDataset]:
        """The per-atom Fukui datasets of a `fukui` job (four, or f- alone for an anion whose dianion gave nothing usable); nothing for any other calc type."""
        if calc_type != "fukui":
            return []
        result = self._condensed_fukui(output_text, mol)
        version_match = _VERSION_RE.search(output_text)
        parameters: dict[str, object] = {
            "orca_version": version_match.group(1) if version_match else "unknown",
            "charge_scheme": "hirshfeld",
            "states": "vertical",
            "grid": self._FUKUI_GRID_NAME,
            "reference_charge": result.reference_charge,
            "functions": "f+ f- f0 dual" if result.computes_f_plus else "f-",
            "caveat": " ".join(result.caveats),
        }
        if result.f_plus_note:
            parameters["f_plus_note"] = result.f_plus_note
        if result.unbound_anion_ev is not None:
            parameters["unbound_anion_ev"] = result.unbound_anion_ev
        if result.cation_s_squared is not None:
            parameters["cation_s_squared"] = result.cation_s_squared
        if result.anion_s_squared is not None:
            parameters["anion_s_squared"] = result.anion_s_squared
        # How many jobs the choice among SCF solutions saw, how many did not finish, and the largest amount an extra start was below the default
        # one; recorded for every run, so a run with one start per state says so with 1, 0 and 0.0 where a missing key would say nothing.
        parameters["starts_run"] = sum(solution.finished + len(solution.failed) for solution in result.solutions)
        parameters["starts_failed"] = sum(len(solution.failed) for solution in result.solutions)
        parameters["start_gain_ev"] = max((solution.gain_ev for solution in result.solutions), default=0.0)
        note = " ".join(start_notes(result.solutions, result.reference_charge))
        if note:
            parameters["start_note"] = note
        provenance = Provenance(
            created_by="core", method=self.provider_id, parameters=parameters, timestamp=time.time()
        )
        return [
            PerAtomDataset(
                property_id=f"orca.{suffix}",
                name=name,
                units="",
                method=self.provider_id,
                molecule_uuid=molecule_uuid,
                values={index: float(value) for index, value in enumerate(getattr(result, attribute))},
                category="quantum_chemistry",
                provenance=provenance,
                timestamp=provenance.timestamp,
            )
            for suffix, name, attribute in self._FUKUI_DATASETS
            if getattr(result, attribute)
        ]

    def _parse_delta_scf(
        self, output_text: str, molecule_uuid: str, provenance: Provenance
    ) -> list[DescriptorValue]:
        """Vertical I and A from the three energies of a compound job.

        The three FINAL SINGLE POINT ENERGY lines are in the order the
        jobs were written -- neutral, cation, anion. Positional, because
        ORCA gives no other way to tell them apart, which is exactly why
        `_build_delta_scf_input` is the only thing that writes this input.
        """
        energies = [float(value) for value in _SCF_ENERGY_RE.findall(output_text)]
        if len(energies) < 3:
            raise OrcaOutputError(
                "A delta-SCF job must produce three SCF energies (neutral, cation, "
                f"anion) and this output has {len(energies)}. One of the ion "
                "calculations most likely failed to converge."
            )
        result = from_delta_scf(*energies[:3])
        if not result:
            return []

        annotated = replace(
            provenance,
            parameters={**provenance.parameters, "caveat": " ".join(result.caveats)},
        )
        return [
            DescriptorValue(
                descriptor_id=f"orca.{suffix}",
                name=name,
                units=units,
                category="quantum_chemistry",
                provider="orca",
                molecule_uuid=molecule_uuid,
                value=getattr(result, attribute),
                timestamp=provenance.timestamp,
                cache_state=CacheState.COMPLETED,
                provenance=annotated,
            )
            for suffix, name, units, attribute in self._DELTA_SCF_FIELDS
        ]

    def _parse_conceptual_dft(
        self, output_text: str, molecule_uuid: str, provenance: Provenance
    ) -> list[DescriptorValue]:
        """Frontier energies and the Koopmans descriptors built on them.

        Emitted from EVERY calc type rather than a dedicated one: the
        orbital energy table is printed by any job that reaches an SCF, so
        these cost one extra pass over text already in memory and ride the
        existing descriptor path -- stored, cached and reused with nothing
        bespoke.

        Reporting hardness from Koopmans at all is a deliberate call rather
        than an oversight. Measured against real B3LYP/def2-SVP runs it
        INVERTS ammonia against phosphine, so `conceptual_dft` attaches a
        caveat naming that failure and it travels with the number.
        """
        homo_ev, lumo_ev = parse_frontier_energies(output_text)
        if homo_ev is None or lumo_ev is None:
            return []

        result = from_frontier_energies(homo_ev, lumo_ev)
        values: dict[str, float] = {"homo_energy": homo_ev, "lumo_energy": lumo_ev}
        if result:
            values.update(
                {
                    suffix: getattr(result, attribute)
                    for suffix, _name, _units, attribute in self._CONCEPTUAL_DFT_FIELDS
                    if attribute is not None
                }
            )

        # The caveat rides on provenance rather than the descriptor name so
        # it reaches the inspector without making every label unreadable.
        annotated = replace(
            provenance,
            parameters={**provenance.parameters, "caveat": " ".join(result.caveats)},
        )
        return [
            DescriptorValue(
                descriptor_id=f"orca.{suffix}",
                name=name,
                units=units,
                category="quantum_chemistry",
                provider="orca",
                molecule_uuid=molecule_uuid,
                value=values[suffix],
                timestamp=provenance.timestamp,
                cache_state=CacheState.COMPLETED,
                provenance=annotated,
            )
            for suffix, name, units, _attribute in self._CONCEPTUAL_DFT_FIELDS
            if suffix in values
        ]

    def parse_vibrational_spectrum(
        self, output_text: str, mol: Chem.Mol, molecule_uuid: str, calc_type: str
    ) -> "VibrationalSpectrumResult | None":
        """The IR spectrum from a frequency job, or None if there is none.

        Only `opt_freq` runs a vibrational analysis, so every other calc
        type returns None rather than an empty spectrum -- "this job did
        not compute one" and "this molecule has no modes" are different
        statements and a view should not show the second for the first.

        The frequency list and the intensity table are joined ON MODE
        INDEX rather than zipped positionally. That is load-bearing: the
        IR table omits imaginary modes, so the two lists have different
        lengths exactly when something has gone wrong with the geometry.
        """
        if calc_type != "opt_freq":
            return None
        if _FREQ_HEADER not in output_text:
            return None

        scaling_match = _FREQ_SCALING_RE.search(output_text)
        # ORCA applies its own factor before printing and says so. Recorded
        # so nothing downstream applies it a second time.
        scaling = float(scaling_match.group(1)) if scaling_match else 1.0

        first_vibration_match = _FIRST_VIBRATION_RE.search(output_text)
        # Fall back to "anything non-zero is a vibration" only if ORCA did
        # not state the boundary; never to a hardcoded 6, which is wrong
        # for every linear molecule (3N-5, confirmed on linear water).
        first_vibration = (
            int(first_vibration_match.group(1)) if first_vibration_match else None
        )

        frequencies: dict[int, float] = {}
        for match in _FREQ_ROW_RE.finditer(
            _section(output_text, _FREQ_HEADER, _NORMAL_MODES_HEADER)
        ):
            frequencies[int(match.group(1))] = float(match.group(2))

        intensities: dict[int, float] = {}
        ir_section = _section(output_text, _IR_HEADER, "THERMOCHEMISTRY")
        for match in _IR_ROW_RE.finditer(ir_section):
            intensities[int(match.group(1))] = float(match.group(4))

        displacements = _parse_normal_modes(output_text, mol.GetNumAtoms())

        # CLASSIFY AGAINST THE GEOMETRY THE MODES WERE COMPUTED AT, not the
        # one that was submitted. An `opt_freq` optimises first and runs the
        # frequency analysis on the RESULT, so `mol`'s conformer is the
        # wrong geometry -- and mode character is decided by projecting
        # displacements onto bond axes, which are exactly what moved.
        # Caught on a real transcript: classifying a linear-water frequency
        # run against a bent input labelled both O-H stretches "bend".
        geometry = _mol_at_final_geometry(output_text, mol)

        modes = []
        for index in sorted(frequencies):
            wavenumber = frequencies[index]
            # Skip the translational/rotational modes ORCA reports as 0.00.
            # An IMAGINARY mode is below the boundary too and must NOT be
            # skipped -- it is the whole point of looking.
            if first_vibration is not None and index < first_vibration:
                if wavenumber >= 0.0:
                    continue
            elif wavenumber == 0.0:
                continue
            modes.append(
                VibrationalMode(
                    wavenumber_cm1=wavenumber,
                    ir_intensity_km_mol=intensities.get(index),
                    displacements=displacements.get(index, ()),
                    character=classify_mode(geometry, displacements.get(index, ())),
                )
            )

        imaginary = [mode for mode in modes if mode.is_imaginary]
        warning = ""
        if imaginary:
            listed = ", ".join(f"{m.wavenumber_cm1:.1f}" for m in imaginary)
            warning = (
                f"{len(imaginary)} imaginary frequency/frequencies ({listed} cm-1): "
                f"this geometry is a saddle point, not a minimum. The "
                f"thermochemistry from this same job is not valid for it."
            )

        return VibrationalSpectrumResult(
            spectrum_type="ir",
            name="IR Spectrum (harmonic)",
            units="cm-1",
            method=self.provider_id,
            molecule_uuid=molecule_uuid,
            modes=tuple(modes),
            scaling_factor=scaling,
            imaginary_warning=warning,
        )

    def _parse_thermochemistry(
        self, output_text: str, molecule_uuid: str, provenance: Provenance
    ) -> list[DescriptorValue]:
        descriptors = []
        now = time.time()
        enthalpy_match = _ENTHALPY_RE.search(output_text)
        if enthalpy_match is not None:
            descriptors.append(
                DescriptorValue(
                    descriptor_id="orca.enthalpy",
                    name="Enthalpy (H, 298.15K)",
                    units="Hartree",
                    category="quantum_chemistry",
                    provider="orca",
                    molecule_uuid=molecule_uuid,
                    value=float(enthalpy_match.group(1)),
                    timestamp=now,
                    cache_state=CacheState.COMPLETED,
                    provenance=provenance,
                )
            )
        entropy_match = _ENTROPY_TERM_RE.search(output_text)
        if entropy_match is not None:
            descriptors.append(
                DescriptorValue(
                    descriptor_id="orca.entropy_term",
                    name="Entropy Term (T*S, 298.15K)",
                    units="Hartree",
                    category="quantum_chemistry",
                    provider="orca",
                    molecule_uuid=molecule_uuid,
                    value=float(entropy_match.group(1)),
                    timestamp=now,
                    cache_state=CacheState.COMPLETED,
                    provenance=provenance,
                )
            )
        gibbs_match = _GIBBS_RE.search(output_text)
        if gibbs_match is not None:
            descriptors.append(
                DescriptorValue(
                    descriptor_id="orca.gibbs_free_energy",
                    name="Gibbs Free Energy (G, 298.15K)",
                    units="Hartree",
                    category="quantum_chemistry",
                    provider="orca",
                    molecule_uuid=molecule_uuid,
                    value=float(gibbs_match.group(1)),
                    timestamp=now,
                    cache_state=CacheState.COMPLETED,
                    provenance=provenance,
                )
            )
        return descriptors

    def _parse_optimized_conformer(
        self, output_text: str, mol: Chem.Mol, provenance: Provenance
    ) -> ConformerModel | None:
        blocks = _CARTESIAN_BLOCK_RE.findall(output_text)
        if not blocks:
            return None
        # ORCA prints this block at every optimization step -- the LAST
        # one is the final, converged geometry.
        final_block = blocks[-1]
        atom_lines = [line for line in final_block.splitlines() if line.strip()]
        if len(atom_lines) != mol.GetNumAtoms():
            # Atom count mismatch (e.g. a differently-formatted block this
            # regex wasn't meant to match) -- don't silently apply wrong
            # coordinates to the wrong atoms.
            return None

        new_mol = Chem.Mol(mol)
        conf = new_mol.GetConformer()
        for idx, line in enumerate(atom_lines):
            parts = line.split()
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            conf.SetAtomPosition(idx, Point3D(x, y, z))

        return ConformerModel(
            molblock=Chem.MolToMolBlock(new_mol), energy=None, method=ORCA_OPTIMIZED, provenance=provenance
        )

    def parse_spectrum_output(
        self, output_text: str, mol: Chem.Mol, molecule_uuid: str, calc_type: str
    ) -> NMRSpectrumResult | None:
        if calc_type not in ("nmr", "nmr_coupling"):
            return None
        shieldings = self._parse_shielding_summary(output_text)
        version_match = _VERSION_RE.search(output_text)
        provenance = Provenance(
            created_by="core",
            method=self.provider_id,
            parameters={"orca_version": version_match.group(1) if version_match else "unknown"},
        )
        return NMRSpectrumResult(
            spectrum_type="nmr_raw_shielding",
            name="NMR Isotropic Shielding (raw, not yet referenced to TMS)",
            # Raw shielding, not a chemical shift, and that is still the
            # right output HERE -- but the referencing it needs now exists
            # and this comment used to say it did not. `chem/nmr_reference`
            # runs TMS at the same method/basis and converts, and
            # `QuantumChemistryService.request_reference_calibration`
            # caches that per (method_basis, ORCA version) so it is not
            # re-run per molecule. The engine stays reference-free because
            # the cache lives at the service layer; when no reference has
            # been calibrated yet, this raw result is what the panel shows,
            # labelled as such. Confirmed live against a real ORCA run.
            units="ppm (isotropic shielding)",
            method=self.provider_id,
            molecule_uuid=molecule_uuid,
            values={index: isotropic for index, (_element, isotropic) in shieldings.items()},
            elements={index: element for index, (element, _isotropic) in shieldings.items()},
            provenance=provenance,
        )

    def _parse_shielding_summary(self, output_text: str) -> dict[int, tuple[str, float]]:
        header_match = _SHIELDING_HEADER_RE.search(output_text)
        if header_match is None:
            raise OrcaOutputError(
                "Could not find 'CHEMICAL SHIELDING SUMMARY' in ORCA output — "
                "the NMR calculation likely failed."
            )
        end_index = output_text.find(_SHIELDING_END_MARKER, header_match.end())
        table_text = output_text[header_match.end() : end_index if end_index != -1 else None]

        shieldings: dict[int, tuple[str, float]] = {}
        for row_match in _SHIELDING_ROW_RE.finditer(table_text):
            atom_index = int(row_match.group(1))
            element = row_match.group(2)
            isotropic = float(row_match.group(3))
            shieldings[atom_index] = (element, isotropic)

        if not shieldings:
            raise OrcaOutputError(
                "Found the 'CHEMICAL SHIELDING SUMMARY' header but no per-nucleus rows "
                "under it — ORCA's output format may have changed."
            )
        return shieldings

    def parse_spin_spin_coupling(
        self, output_text: str, calc_type: str
    ) -> dict[tuple[int, int], float] | None:
        """Real ab initio J-coupling constants (Hz) between atom-index
        pairs -- `None` for any calc_type other than "nmr_coupling" (the
        only one that requests the `%eprnmr ... ssall` block).

        Confirmed live against a real ORCA 6.1.1 run (HF/STO-3G,
        formaldehyde, `%eprnmr Nuclei = all C,H { shift, ssall }`):

            -----------------------------------------------------------------------------
                            SUMMARY OF ISOTROPIC COUPLING CONSTANTS J (Hz)
            -----------------------------------------------------------------------------
                              0 C        2 H        3 H
                  0 C        0.000    122.043    122.043
                  2 H      122.043      0.000     37.978
                  3 H      122.043     37.978      0.000

        A symmetric matrix, not a flat per-pair list like the shielding
        summary -- the header row gives column atom indices (paired with
        their element symbol), each following row repeats its own atom
        index/element then one coupling value per column. The diagonal
        (self-coupling, always 0.000) and the redundant lower/upper
        triangle duplicate are both collapsed to one entry per unordered
        pair. Real values sanity-checked against known formaldehyde
        chemistry: 1J(C-H) >> 2J(H-H), both in the right ballpark for this
        crude minimal-basis method (real values are method/basis-
        dependent, not claimed to be quantitatively accurate at HF/STO-3G).

        **ORCA WRAPS A WIDE MATRIX INTO SEVERAL COLUMN BLOCKS, EACH WITH ITS
        OWN HEADER LINE.** Formaldehyde's 3-atom matrix fits in one block, so
        the code above was never exercised against a second one -- confirmed
        live against a real ORCA 6.1.1 ethanol run (9 atoms, 8 counting only
        C/H), whose matrix wraps after 6 columns:

            SUMMARY OF ISOTROPIC COUPLING CONSTANTS J (Hz)
            ...
                              0 C        1 C        3 H        4 H        5 H        6 H
                  0 C        0.000     41.862    132.613    133.239    134.368     -8.913
                  ...
                  8 H        0.269     -8.803      1.145     -3.319     -1.026      1.420
                              7 H        8 H
                  0 C       -9.963      0.269
                  ...
                  8 H       14.093      0.000

        Treating every line after the first as a data row (the previous
        implementation) reads that second header line as a row: `int("7")`
        parses fine as an atom index, and it crashes on
        `float("H")` for the coupling value. Every line is now classified by
        whether its own third token parses as a float -- a data row's first
        coupling value always does; a header line's second index token never
        does -- so a matrix wrapped into any number of blocks parses the
        same way a single-block one does.
        """
        if calc_type != "nmr_coupling":
            return None
        header_match = _COUPLING_SUMMARY_HEADER_RE.search(output_text)
        if header_match is None:
            raise OrcaOutputError(
                "Could not find 'SUMMARY OF ISOTROPIC COUPLING CONSTANTS' in ORCA output — "
                "the spin-spin coupling calculation likely failed."
            )
        end_index = output_text.find(_COUPLING_END_MARKER, header_match.end())
        block = output_text[header_match.end() : end_index if end_index != -1 else None]
        lines = [line for line in block.splitlines() if line.strip() and set(line.strip()) != {"-"}]
        if not lines:
            raise OrcaOutputError(
                "Found the coupling-constants summary header but no matrix rows under it — "
                "ORCA's output format may have changed."
            )

        def _is_header_line(tokens: list[str]) -> bool:
            # Token[2] is not the discriminator: a header's second atom
            # index ("...1 C...") parses as a float just as well as a data
            # row's first coupling value does. Token[3] is what differs --
            # a header's second ELEMENT symbol never parses as a float, a
            # data row's second coupling value always does. A one-column
            # block has no token[3] at all in either shape, so its length
            # alone (2 for a header, 3 for a data row) is unambiguous.
            if len(tokens) < 2:
                return False
            if len(tokens) < 4:
                return len(tokens) == 2
            try:
                float(tokens[3])
            except ValueError:
                return True
            return False

        couplings: dict[tuple[int, int], float] = {}
        column_atoms: list[int] = []
        for line in lines:
            tokens = line.split()
            if not tokens:
                continue
            if _is_header_line(tokens):
                column_atoms = [int(tokens[i]) for i in range(0, len(tokens), 2)]
                continue
            if not column_atoms:
                continue  # a row before any header has been seen -- unparseable
            row_atom = int(tokens[0])
            values = tokens[2:]
            for column_atom, value_text in zip(column_atoms, values):
                if column_atom == row_atom:
                    continue
                key = (min(row_atom, column_atom), max(row_atom, column_atom))
                couplings.setdefault(key, float(value_text))
        return couplings
