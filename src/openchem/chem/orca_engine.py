from __future__ import annotations

import re
import time
from pathlib import Path

from rdkit import Chem
from rdkit.Geometry import Point3D

from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.chem.vibrational_modes import classify_mode
from openchem.domain.scientific_result import (
    NMRSpectrumResult,
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
    # The LAST table, found from the last header: `_section` takes the
    # first match, and a geometry optimisation prints one table per cycle.
    last = output_text.rfind("ORBITAL ENERGIES")
    if last == -1:
        return None, None
    end = output_text.find("MULLIKEN", last)
    section = output_text[last:] if end == -1 else output_text[last:end]

    spin_down = section.find("SPIN DOWN ORBITALS")
    if spin_down != -1:
        section = section[:spin_down]
    if not section:
        return None, None

    homo: int | None = None
    lumo: int | None = None
    for match in _ORBITAL_ROW_RE.finditer(section):
        index = int(match.group(1))
        occupation = float(match.group(2))
        if occupation > 0.0:
            homo = index
        elif lumo is None and homo is not None:
            # The first empty orbital AFTER an occupied one. Guarding on
            # `homo` matters for an open-shell beta block, whose table can
            # begin with empty rows.
            lumo = index
    return homo, lumo


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

_CALC_TYPE_KEYWORDS = {"sp": "", "opt": "Opt", "opt_freq": "Opt Freq", "nmr": "NMR", "nmr_coupling": "NMR"}

_SCF_ENERGY_RE = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
_CARTESIAN_BLOCK_RE = re.compile(
    r"CARTESIAN COORDINATES \(ANGSTROEM\)\n-+\n((?:\s*[A-Za-z]{1,2}(?:\s+-?\d+\.\d+){3}\n)+)"
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

_CALC_TYPES = ("sp", "opt", "opt_freq", "nmr", "nmr_coupling")

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
}
# General-purpose presets first, then two aimed specifically at NMR.
#
# Why NMR needs its own: shielding is dominated by electron density in the
# CORE region, and the general-purpose valence bases above carry no tight
# core functions, so they get absolute shieldings meaningfully wrong.
# Jensen's pcSseg-n family is built for exactly this. Confirmed live
# against a real ORCA 6.1.1 run -- "Your calculation utilizes the basis:
# pcSseg-1" -- and the difference is not cosmetic: water's 1H shielding
# moved 1.3 ppm between B3LYP/def2-SVP and B3LYP/pcSseg-1 with CPCM, which
# in a 1H window of roughly 0-12 ppm is the gap between calling a proton
# aromatic or vinyl.
METHOD_BASIS_PRESETS = [
    "B3LYP def2-SVP",
    "PBE0 def2-TZVP",
    "B3LYP 6-31G(d)",
    "B3LYP pcSseg-1",
    "B3LYP pcSseg-2",
]

# Recommended when the calc type is NMR -- the panel preselects this rather
# than silently leaving a general-purpose basis chosen for a job whose whole
# point is shielding accuracy.
NMR_METHOD_BASIS = "B3LYP pcSseg-1"

# CPCM solvents, as ORCA names them. Real spectra are recorded in solvent,
# not gas phase, and the difference is largest exactly where it is most
# visible -- exchangeable protons like COOH/OH. Confirmed live that
# `CPCM(Chloroform)` is accepted and activates ORCA's solvation model.
# "" means gas phase, which stays the default so existing behaviour and
# every previously-cached TMS reference remain valid.
SOLVENTS = ["", "Chloroform", "DMSO", "Water", "Methanol", "Acetone", "Toluene", "Benzene"]


class OrcaOutputError(Exception):
    """Raised when ORCA's output can't be parsed — no SCF energy found
    (job likely failed/didn't converge), or an internal inconsistency.
    Always caught by the service and reported as a failed job, never left
    to crash."""


class OrcaQuantumEngineProvider(QuantumEngineProvider):
    provider_id = "orca"

    def build_input(
        self, mol: Chem.Mol, charge: int, multiplicity: int, method_basis: str, calc_type: str
    ) -> str:
        if calc_type not in _CALC_TYPES:
            raise ValueError(f"Unknown calc_type: {calc_type!r} (expected one of {_CALC_TYPES})")
        keywords = _CALC_TYPE_KEYWORDS[calc_type]
        header = f"! {method_basis} {keywords}".strip()

        conf = mol.GetConformer()
        lines = [header, f"* xyz {charge} {multiplicity}"]
        for atom in mol.GetAtoms():
            pos = conf.GetAtomPosition(atom.GetIdx())
            lines.append(f"{atom.GetSymbol():<3}{pos.x:>14.6f}{pos.y:>14.6f}{pos.z:>14.6f}")
        lines.append("*")
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

    def command_args(self, executable_path: str, input_path: Path) -> list[str]:
        # ORCA's own invocation convention: `orca job.inp`, writing its
        # full output to stdout (no separate --out file argument, unlike
        # Vina) — the service captures that stdout directly.
        return [executable_path, str(input_path)]

    def parse_output(
        self, output_text: str, mol: Chem.Mol, molecule_uuid: str, calc_type: str
    ) -> tuple[list[DescriptorValue], ConformerModel | None]:
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

        if calc_type == "opt_freq":
            descriptors.extend(self._parse_thermochemistry(output_text, molecule_uuid, provenance))

        optimized_conformer = None
        if calc_type in ("opt", "opt_freq"):
            optimized_conformer = self._parse_optimized_conformer(output_text, mol, provenance)

        return descriptors, optimized_conformer

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
            molblock=Chem.MolToMolBlock(new_mol), energy=None, method="orca_opt", provenance=provenance
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

        header_tokens = lines[0].split()
        column_atoms = [int(header_tokens[i]) for i in range(0, len(header_tokens), 2)]

        couplings: dict[tuple[int, int], float] = {}
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            row_atom = int(parts[0])
            values = parts[2:]
            for column_atom, value_text in zip(column_atoms, values):
                if column_atom == row_atom:
                    continue
                key = (min(row_atom, column_atom), max(row_atom, column_atom))
                couplings.setdefault(key, float(value_text))
        return couplings
