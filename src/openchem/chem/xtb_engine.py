"""xtb (GFN-xTB tight binding) as a third quantum-chemistry engine: `XtbQuantumEngineProvider` (`docs/EXTERNAL_TOOL_CANDIDATES.md`).

xtb itself is Grimme's group's program [source:bannwarth2021xtb]; this module is only the driver around it, on the seam ORCA and Psi4 use: it builds an input and reads an output, and the service owns the process.
It runs three calculation types, `sp`, `opt` and `opt_freq`, at GFN2-xTB or GFN1-xTB. Everything here was measured against a real xtb 6.7.1pre on Windows (the spike, 2026-10-27);
the fixtures in `tests/fixtures/xtb/` are real outputs, produced by this module's own `build_input` and `command_args`. It is registered with `QuantumChemistryService` (used only when `xtb/executable_path` is set or xtb is on PATH), has a locate-only External Tools tab and its own method presets; nothing here has been compared with ORCA or Psi4.

THE INPUT FILE CARRIES THE JOB. `command_args(executable_path, input_path)` is handed neither the charge, the spin nor the calculation type, and xtb takes all three on its command line. So `build_input` writes them into
a header comment on the first line of the file and `command_args` reads that line back (a plain file read; the provider still owns no process or thread). The file the service writes is always called `job.inp`, and xtb
chooses a geometry reader by file name: a `.inp` file is refused ("coordinates not present"). It does read a Turbomole `$coord` block by content, so that is the format written (in Bohr, lower-case symbols, atom order
unchanged). Measured: the energy through this route equals the energy of the same geometry as an `.xyz` file to 1e-12 Eh.

THE SPIN IS ALWAYS WRITTEN AND ALWAYS CHECKED. xtb with `--uhf 0` on a methyl radical (7 electrons) ran, exited 0, printed `unpaired electrons 0` and gave -3.5627 Eh against -3.5630 Eh for `--uhf 1`: an impossible
electron count is not an error to it. `build_input` therefore refuses a charge and multiplicity that do not fit the molecule's electrons, before anything runs.

A FAILED RUN is exit code 128 and, on STDERR, `abnormal termination of xtb`; the service reads no exit code and only the stdout, and `normal termination of xtb` is also on stderr, so neither can be relied on. What stdout does carry:
a `[ERROR]` block for a failure, and `* finished run on ...` as the last banner of a run that completed. `parse_output` fails a run on the first and on the absence of the second (a cut-off run), and still honours the stderr
marker should the channels ever be merged. An optimization that does not converge still completes (measured with `--cycles 2`: `*** FAILED TO CONVERGE GEOMETRY OPTIMIZATION`), so convergence is read from its own line.

WHAT THE STDOUT DOES NOT CARRY, and is therefore not reported: the IR intensities (only in the `vibspectrum` file in the working folder) and the entropy term. The frequencies are in the stdout.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path

from rdkit import Chem
from rdkit.Geometry import Point3D

from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import XTB_OPTIMIZED, ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.scientific_result import VibrationalMode, VibrationalSpectrumResult
from openchem.plugins.interfaces import QuantumEngineProvider

#: The method labels an input may name (compared case-insensitively) and xtb's `--gfn` level each one means. GFN-FF is a force field with no electrons and GFN0 is not offered: neither has been measured here.
XTB_METHODS = {"gfn2-xtb": 2, "gfn1-xtb": 1}

#: The calculation types the engine runs: a single point, an optimization, and an optimization followed by a frequency analysis.
XTB_CALC_TYPES = frozenset({"sp", "opt", "opt_freq"})

#: The calculation type -> the flags that run it. `tight` is xtb's own optimization level (the one the spike measured); an unflagged run is a single point.
_JOB_FLAGS = {"sp": [], "opt": ["--opt", "tight"], "opt_freq": ["--ohess", "tight"]}

#: The heaviest element GFN1/GFN2 are parametrized for.
MAX_ATOMIC_NUMBER = 86

#: Bohr per Angstrom: the input is written in Bohr (a Turbomole block) and the final geometry xtb prints back is in Bohr too.
_BOHR_PER_ANGSTROM = 1.8897261246257702

#: How the header comment on the input's first line begins.
_HEADER_PREFIX = "# openchem-xtb"
#: The header line as a whole: the charge, the unpaired electrons, the calculation type and the GFN level `command_args` reads back, so a file this provider did not write is told apart from one it did.
_HEADER_RE = re.compile(r"^# openchem-xtb charge=(-?\d+) uhf=(\d+) job=(\w+) gfn=(\d)\s*$")

#: The banner's `xtb version 6.7.1pre (5071a88)`, for the provenance.
_VERSION_RE = re.compile(r"xtb version (\S+)")
#: The summary's `| TOTAL ENERGY  -11.39 Eh |` line, one per SCF summary (an optimization with a Hessian prints two, at the same geometry).
_ENERGY_RE = re.compile(r"\|\s+TOTAL ENERGY\s+(-?\d+\.\d+) Eh\s+\|")
#: The summary's `| TOTAL ENTHALPY ... |` line, printed by a frequency job.
_ENTHALPY_RE = re.compile(r"\|\s+TOTAL ENTHALPY\s+(-?\d+\.\d+) Eh\s+\|")
#: The summary's `| TOTAL FREE ENERGY ... |` line, printed by a frequency job (the quasi-RRHO free energy at 298.15 K).
_FREE_ENERGY_RE = re.compile(r"\|\s+TOTAL FREE ENERGY\s+(-?\d+\.\d+) Eh\s+\|")
#: The `:: zero point energy` line of a frequency job's summary.
_ZPE_RE = re.compile(r":: zero point energy\s+(-?\d+\.\d+) Eh")
#: The last banner of a run that completed, on STDOUT (`normal termination of xtb` is on stderr, which the service does not read).
_FINISHED = "finished run on"
#: The stderr marker of a failed run, honoured if the channels are ever merged.
_ERROR_END = "abnormal termination of xtb"
#: What a failure prints on STDOUT.
_ERROR_BLOCK = "[ERROR]"
#: The line an optimization prints when it converges; one that ran out of cycles prints `_OPT_FAILED` instead and still completes.
_OPT_CONVERGED = "GEOMETRY OPTIMIZATION CONVERGED"
#: The line an optimization that ran out of cycles prints.
_OPT_FAILED = "FAILED TO CONVERGE GEOMETRY OPTIMIZATION"
#: The heading of the converged geometry an optimization prints, in the format the input was given in.
_FINAL_GEOMETRY = "final structure:"
#: The heading of the frequency analysis's own section (the Hessian step prints an earlier, equal list).
_FREQUENCY_PRINTOUT = "Frequency Printout"
#: "projected vibrational frequencies" for a nonlinear molecule and a bare "vibrational frequencies" for a linear one (measured on CO2), so the shorter text is matched.
_FREQUENCY_HEADING = "vibrational frequencies"
#: One row of the frequency list: `eigval :  223.27  341.42 ...` in cm-1, six to a row.
_EIGVAL_ROW = re.compile(r"^eigval :\s+(.*)$")
#: One atom of a Turbomole block: x, y, z in Bohr, then the lower-case symbol.
_COORD_ROW = re.compile(r"^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+([A-Za-z]{1,2})\s*$")
#: A line of xtb's own error report: `[ERROR] ...` or the numbered `-1- Error: ...` lines under it.
_ERROR_LINE = re.compile(r"^(?:\[ERROR\].*|-\d+- .*)$")


class XtbOutputError(RuntimeError):
    """xtb ran and said it failed, or finished without the result a calculation type needs."""


def split_method(method_basis: str) -> tuple[int, str]:
    """`"GFN2-xTB"` -> (2, the label as written). One word: xtb has no basis set, and a solvent or other keyword is refused by name, not dropped."""
    parts = method_basis.split()
    if len(parts) != 1 or parts[0].lower() not in XTB_METHODS:
        raise ValueError(
            f"The xtb engine takes a method alone ({', '.join(sorted(XTB_METHODS))}), not {method_basis!r}; "
            "xtb has no basis set, and a solvent or other keyword is not supported by this engine yet."
        )
    return XTB_METHODS[parts[0].lower()], parts[0]


def check_electrons(mol: Chem.Mol, charge: int, multiplicity: int) -> None:
    """Refuse a charge and multiplicity the molecule's electrons cannot have (xtb does not: see the module docstring)."""
    if multiplicity < 1:
        raise ValueError(f"The multiplicity must be at least 1, not {multiplicity}.")
    electrons = sum(atom.GetAtomicNum() for atom in mol.GetAtoms()) - charge
    unpaired = multiplicity - 1
    if electrons < unpaired or (electrons - unpaired) % 2:
        raise ValueError(f"{electrons} electrons cannot have multiplicity {multiplicity} (charge {charge:+d}).")


def _default_threads() -> int:
    from openchem.chem.orca_engine import default_cores

    return default_cores()


class XtbQuantumEngineProvider(QuantumEngineProvider):
    provider_id = "xtb"
    display_name = "xtb"
    supported_calc_types = XTB_CALC_TYPES
    method_basis_presets = ("GFN2-xTB", "GFN1-xTB")
    #: Threads are `-P` on the command line, not an input block, so the service adds nothing of its own.
    supports_parallel = False

    def __init__(self, threads: Callable[[], int] | None = None) -> None:
        # A callable, read each time a command is built: Settings applies as it changes.
        self._threads = threads if threads is not None else _default_threads

    def executable_setting(self) -> str:
        return "xtb/executable_path"

    def executable_names(self) -> tuple[str, ...]:
        return ("xtb",)

    # -- input ---------------------------------------------------------------------------------------------------

    def build_input(self, mol: Chem.Mol, charge: int, multiplicity: int, method_basis: str, calc_type: str) -> str:
        if calc_type not in XTB_CALC_TYPES:
            raise ValueError(f"The xtb engine does not run {calc_type!r} (it runs {', '.join(sorted(XTB_CALC_TYPES))}).")
        gfn, _label = split_method(method_basis)
        for atom in mol.GetAtoms():
            if not 1 <= atom.GetAtomicNum() <= MAX_ATOMIC_NUMBER:
                raise ValueError(f"xtb's GFN methods cover elements 1 to {MAX_ATOMIC_NUMBER}, not {atom.GetSymbol()!r}.")
        check_electrons(mol, charge, multiplicity)
        conf = mol.GetConformer()
        rows = []
        for atom in mol.GetAtoms():
            pos = conf.GetAtomPosition(atom.GetIdx())
            rows.append(f"  {pos.x * _BOHR_PER_ANGSTROM:.10f}  {pos.y * _BOHR_PER_ANGSTROM:.10f}  {pos.z * _BOHR_PER_ANGSTROM:.10f}  {atom.GetSymbol().lower()}")
        header = f"{_HEADER_PREFIX} charge={charge} uhf={multiplicity - 1} job={calc_type} gfn={gfn}"
        return "\n".join([header, "$coord", *rows, "$end", ""])

    def command_args(self, executable_path: str, input_path: Path) -> list[str]:
        first_line = Path(input_path).read_text(encoding="utf-8").splitlines()[0] if Path(input_path).stat().st_size else ""
        match = _HEADER_RE.match(first_line)
        if match is None or match.group(3) not in _JOB_FLAGS:
            # Never guess a charge or a spin: a file this provider did not write has no job to run.
            raise ValueError(f"{input_path} does not start with this engine's job header, so its charge, spin and calculation cannot be read.")
        charge, uhf, job, gfn = match.groups()
        return [
            executable_path, str(input_path), "--gfn", gfn, "--chrg", charge, "--uhf", uhf,
            "-P", str(max(1, int(self._threads()))), *_JOB_FLAGS[job],
        ]

    # -- output --------------------------------------------------------------------------------------------------

    def parse_output(
        self, output_text: str, mol: Chem.Mol, molecule_uuid: str, calc_type: str
    ) -> tuple[list[DescriptorValue], ConformerModel | None]:
        _raise_if_failed(output_text)
        energies = _ENERGY_RE.findall(output_text)
        if not energies:
            raise XtbOutputError("xtb finished without printing a total energy.")
        provenance = self._provenance(output_text)
        now = provenance.timestamp

        def descriptor(descriptor_id: str, name: str, value: float) -> DescriptorValue:
            return DescriptorValue(
                descriptor_id=descriptor_id, name=name, units="Hartree", category="quantum_chemistry", provider="xtb",
                molecule_uuid=molecule_uuid, value=value, timestamp=now, cache_state=CacheState.COMPLETED, provenance=provenance,
            )

        # The LAST energy: a frequency job prints the energy of the optimization and then of the Hessian step, at the same geometry.
        descriptors = [descriptor("xtb.scf_energy", "Total Energy (xtb)", float(energies[-1]))]
        if calc_type == "opt_freq":
            descriptors.extend(self._thermochemistry(output_text, descriptor))
        conformer = self._parse_optimized_conformer(output_text, mol, provenance) if calc_type in ("opt", "opt_freq") else None
        return descriptors, conformer

    def parse_vibrational_spectrum(
        self, output_text: str, mol: Chem.Mol, molecule_uuid: str, calc_type: str
    ) -> VibrationalSpectrumResult | None:
        if calc_type != "opt_freq":
            return None
        values = _printed_frequencies(output_text)
        if values is None:
            return None
        # The translations and rotations print as 0.00 (5 for a linear molecule, 6 otherwise); every other value is a vibration, imaginary ones negative.
        zero_modes = [v for v in values if v == 0.0]
        if len(zero_modes) not in (5, 6) or len(values) != 3 * mol.GetNumAtoms():
            return None
        modes = tuple(VibrationalMode(wavenumber_cm1=v) for v in values if v != 0.0)
        warning = ""
        if any(m.is_imaginary for m in modes):
            warning = "xtb found imaginary frequencies: this geometry is not a minimum at this level, and its thermochemistry is not valid."
        return VibrationalSpectrumResult(
            spectrum_type="ir", name="Harmonic frequencies (xtb)", units="cm-1", method=self.provider_id,
            molecule_uuid=molecule_uuid, modes=modes, scaling_factor=1.0, imaginary_warning=warning,
        )

    def _provenance(self, output_text: str) -> Provenance:
        version = _VERSION_RE.search(output_text)
        return Provenance(
            created_by="core", method=self.provider_id,
            parameters={"xtb_version": version.group(1) if version else "unknown"}, timestamp=time.time(),
        )

    @staticmethod
    def _thermochemistry(output_text: str, descriptor: Callable[[str, str, float], DescriptorValue]) -> list[DescriptorValue]:
        found = []
        for regex, descriptor_id, name in (
            (_ENTHALPY_RE, "xtb.enthalpy", "Enthalpy (H, 298.15K, xtb)"),
            (_FREE_ENERGY_RE, "xtb.gibbs_free_energy", "Gibbs Free Energy (G, 298.15K, xtb)"),
            (_ZPE_RE, "xtb.zero_point_energy", "Zero-Point Energy (xtb)"),
        ):
            match = regex.search(output_text)
            if match is not None:
                found.append(descriptor(descriptor_id, name, float(match.group(1))))
        if not found:
            raise XtbOutputError("xtb's frequency job printed no thermochemistry.")
        return found

    def _parse_optimized_conformer(self, output_text: str, mol: Chem.Mol, provenance: Provenance) -> ConformerModel:
        if _OPT_FAILED in output_text or _OPT_CONVERGED not in output_text:
            raise XtbOutputError("xtb's geometry optimization did not converge.")
        start = output_text.rfind(_FINAL_GEOMETRY)
        if start < 0:
            raise XtbOutputError("xtb reported a converged optimization but printed no final geometry.")
        # xtb prints the final structure in the format it was given: here a Turbomole `$coord` block, in BOHR, lower-case symbols, ending `$end` (measured; an `.xyz` input would print Angstrom).
        rows = []
        for line in output_text[start:].splitlines()[1:]:
            if line.strip() == "$end":
                break
            match = _COORD_ROW.match(line)
            if match is not None:
                x, y, z, symbol = match.groups()
                rows.append((symbol.capitalize(), float(x) / _BOHR_PER_ANGSTROM, float(y) / _BOHR_PER_ANGSTROM, float(z) / _BOHR_PER_ANGSTROM))
        symbols = [a.GetSymbol() for a in mol.GetAtoms()]
        if [r[0] for r in rows] != symbols:
            # Never apply coordinates to the wrong atoms: the element sequence must be the input's.
            raise XtbOutputError(f"xtb's final geometry has atoms {[r[0] for r in rows]}, not the input's {symbols}.")
        new_mol = Chem.Mol(mol)
        conf = new_mol.GetConformer()
        for atom_index, (_symbol, x, y, z) in enumerate(rows):
            conf.SetAtomPosition(atom_index, Point3D(x, y, z))
        return ConformerModel(molblock=Chem.MolToMolBlock(new_mol), energy=None, method=XTB_OPTIMIZED, provenance=provenance)


def _raise_if_failed(output_text: str) -> None:
    if _ERROR_BLOCK in output_text or _ERROR_END in output_text:
        raise XtbOutputError(_failure_message(output_text))
    if _FINISHED not in output_text:
        raise XtbOutputError("xtb did not finish (no 'finished run' line); the run was cut short.")


def _failure_message(output_text: str) -> str:
    """xtb's own words: its error lines (`[ERROR] ...` and `-1- Error: ...`), else a generic line."""
    lines = [line.strip() for line in output_text.splitlines() if _ERROR_LINE.match(line.strip())]
    return " ".join(lines) if lines else "xtb terminated abnormally."


def _printed_frequencies(output_text: str) -> list[float] | None:
    """The projected frequencies of the Frequency Printout, in the order printed (all 3N, the translations and rotations as 0.00), or None when there are none."""
    printout = output_text.rfind(_FREQUENCY_PRINTOUT)
    if printout < 0:
        return None
    lines = output_text[printout:].splitlines()
    values: list[float] = []
    reading = False
    for line in lines:
        if _FREQUENCY_HEADING in line:
            reading = True
            continue
        if not reading:
            continue
        match = _EIGVAL_ROW.match(line.strip())
        if match is None:
            break
        values.extend(float(token) for token in match.group(1).split())
    return values or None
