"""Psi4 as a second quantum-chemistry engine: `Psi4QuantumEngineProvider` (`docs/PSI4_ENGINE_DESIGN.md`).

Psi4 itself is [source:psi42020]; this module is only the driver around it. An engine PROVIDER on the seam ORCA already uses: this module builds an input and reads an output, and the service owns the process. Version 1 runs two calculation types, `sp` and `opt`, at the methods
in `PSI4_METHODS`. Everything measured here was measured against a real Psi4 1.11 on Windows (the spike, 2026-10-19); the fixtures in `tests/fixtures/psi4/` are real outputs.

THE FUNCTIONAL IS MAPPED BY NAME THROUGH A TABLE, NEVER PASSED THROUGH, because the same label is not the same functional. Measured on water at def2-SVP against ORCA, exact integrals both sides:

    Psi4 `b3lyp`   -76.35814 Eh      ORCA `B3LYP`   -76.32109 Eh      37 mEh (23 kcal/mol) apart: Psi4's B3LYP uses the VWN1RPA form
    Psi4 `b3lyp5`  -76.32099 Eh      ORCA `B3LYP`   -76.32109 Eh      0.1 mEh: ORCA's B3LYP is VWN5
    Psi4 `b3lyp`   -76.35814 Eh      ORCA `B3LYP/G` -76.35824 Eh      0.1 mEh

So an ORCA-style "B3LYP" means Psi4's `b3lyp5`. The other entries were checked the same way (0.1 to 0.2 mEh, which is the two programs' different default integration grids; HF agrees to 1e-9 Eh).

THE BASIS IS PASSED THROUGH, but with `puream true` always: Psi4 uses CARTESIAN d functions for the Pople bases by default and ORCA uses spherical ones, which for 6-31G(d) on water is a 1.8 mEh difference
(`puream true` brings it to 0.08 mEh). The def2 and pcSseg families are spherical in both, so forcing it changes nothing there.

**A FAILED PSI4 RUN IS EXIT CODE 1 AND ENDS "Psi4 encountered an error"** (measured on a bad functional and a bad basis; a successful run ends "Psi4 exiting successfully", a failed one prints
neither that line nor anything after the error banner). The service does not look at the exit code, so `parse_output` is what turns a failure into a failed run, and it does so by that marker. (An earlier note in the design
document said a failed run still prints the success banner; that was a misreading of two outputs read together and is corrected there.)

The engine writes exact integrals (`scf_type pk`), not Psi4's default density fitting (`df`): the preregistered agreement check (`benchmarks/psi4_agreement/PLAN.md`, run 2026-10-19) found that density fitting alone moves the Hartree-Fock energy by 0.37 to 0.45 mEh at 6-31G(d), a method-sized change that made the comparison with ORCA
(whose default is exact) NOT EVALUABLE. The scf_type is recorded in the provenance with the exact functional keyword so two engines' numbers are never read as one.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path

from rdkit import Chem
from rdkit.Geometry import Point3D

from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import PSI4_OPTIMIZED, ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.plugins.interfaces import QuantumEngineProvider

#: The functional labels an input may name (compared case-insensitively) and the Psi4 method keyword each one MEANS: the one that gives the same energy as ORCA's functional of that name.
#: Anything else is refused by `build_input`, never guessed (see the module docstring for why a name is not enough).
PSI4_METHODS = {
    "hf": "scf",
    "b3lyp": "b3lyp5",
    "b3lyp/g": "b3lyp",
    "pbe0": "pbe0",
    "m062x": "m06-2x",
}

#: The calculation types version 1 runs.
PSI4_CALC_TYPES = frozenset({"sp", "opt"})

#: The memory a job is given, in the input. Psi4's own default (500 MB) is too small for a def2-TZVP job on a drug-sized molecule and a failed allocation reads like a broken input.
_MEMORY = "2 GB"

#: What the SCF is converged to, tighter than Psi4's default (1e-6) so that two engines' energies differ by their methods and not by an unconverged SCF.
_CONVERGENCE = "1e-8"

#: The release line of Psi4's banner ("Psi4 1.11 release").
_VERSION_RE = re.compile(r"Psi4 (\d+\.\d+(?:\.\d+)?) release")
#: The "Total Energy =" line of Psi4's energy summary, one per SCF (an optimization prints one per step).
_ENERGY_RE = re.compile(r"^\s+Total Energy =\s+(-?\d+\.\d+)\s*$", re.MULTILINE)
#: What a failed run prints (and exits 1): the only reliable sign of failure, since the service reads no exit code.
_ERROR_MARKER = "Psi4 encountered an error"
#: The heading of the converged geometry an optimization prints last.
_FINAL_GEOMETRY = "Final optimized geometry and variables:"
#: One atom of that geometry: element, then x, y, z in Angstrom.
_GEOMETRY_ROW = re.compile(r"^\s+([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")


class Psi4OutputError(RuntimeError):
    """Psi4 ran and said it failed, or finished without the result a calculation type needs."""


def split_method_basis(method_basis: str) -> tuple[str, str, str]:
    """`"B3LYP def2-SVP"` -> (the Psi4 method keyword, the basis as written, the functional label as written).

    Exactly two words. Anything more (a solvent keyword, a dispersion correction, an ORCA flag) is refused by name: version 1 does not run it, and silently dropping a word would compute a different calculation under the same label.
    """
    parts = method_basis.split()
    if len(parts) != 2:
        raise ValueError(
            f"The Psi4 engine takes a method and a basis ('B3LYP def2-SVP'), not {method_basis!r}; "
            "a solvent, dispersion correction or other keyword is not supported by this engine yet."
        )
    label, basis = parts
    keyword = PSI4_METHODS.get(label.lower())
    if keyword is None:
        raise ValueError(f"The functional {label!r} is not offered for the Psi4 engine (known: {', '.join(sorted(PSI4_METHODS))}).")
    return keyword, basis, label


def _default_threads() -> int:
    from openchem.chem.orca_engine import default_cores

    return default_cores()


class Psi4QuantumEngineProvider(QuantumEngineProvider):
    provider_id = "psi4"
    display_name = "Psi4"
    supported_calc_types = PSI4_CALC_TYPES
    #: Threads are `-n` on the command line, not an input block, so the service adds nothing of its own.
    supports_parallel = False

    def __init__(self, threads: Callable[[], int] | None = None) -> None:
        self._threads = threads if threads is not None else _default_threads

    def executable_setting(self) -> str:
        return "psi4/executable_path"

    def executable_names(self) -> tuple[str, ...]:
        return ("psi4",)

    # -- input ---------------------------------------------------------------------------------------------------

    def build_input(self, mol: Chem.Mol, charge: int, multiplicity: int, method_basis: str, calc_type: str) -> str:
        if calc_type not in PSI4_CALC_TYPES:
            raise ValueError(f"The Psi4 engine does not run {calc_type!r} (it runs {', '.join(sorted(PSI4_CALC_TYPES))}).")
        keyword, basis, _label = split_method_basis(method_basis)
        conf = mol.GetConformer()
        rows = [
            f"{atom.GetSymbol():<3}{conf.GetAtomPosition(atom.GetIdx()).x:>16.8f}{conf.GetAtomPosition(atom.GetIdx()).y:>16.8f}{conf.GetAtomPosition(atom.GetIdx()).z:>16.8f}"
            for atom in mol.GetAtoms()
        ]
        # `symmetry c1`, `no_reorient` and `no_com` keep the atoms where the molecule has them and in its order: an optimized geometry must map back onto the same atoms.
        # A closed shell is `rhf` and anything else `uhf`, written down and not left to a default (a default can change the state: the ORCA Fukui work found that).
        verb = "optimize" if calc_type == "opt" else "energy"
        return "\n".join([
            f"memory {_MEMORY}", "molecule {", f"{charge} {multiplicity}", *rows, "symmetry c1", "no_reorient", "no_com", "}",
            f"set reference {'rhf' if multiplicity == 1 else 'uhf'}", f"set basis {basis}", "set puream true", "set scf_type pk",
            f"set e_convergence {_CONVERGENCE}", f"set d_convergence {_CONVERGENCE}", f"{verb}('{keyword}')", "",
        ])

    def command_args(self, executable_path: str, input_path: Path) -> list[str]:
        # `-o stdout`: the output arrives on the pipe the service already reads (measured: the same text as the output file).
        return [executable_path, "-n", str(max(1, int(self._threads()))), "-o", "stdout", str(input_path)]

    # -- output --------------------------------------------------------------------------------------------------

    def parse_output(
        self, output_text: str, mol: Chem.Mol, molecule_uuid: str, calc_type: str
    ) -> tuple[list[DescriptorValue], ConformerModel | None]:
        if _ERROR_MARKER in output_text:
            raise Psi4OutputError(_failure_message(output_text))
        energies = _ENERGY_RE.findall(output_text)
        if not energies:
            raise Psi4OutputError("Psi4 finished without printing a total energy.")
        version = _VERSION_RE.search(output_text)
        provenance = Provenance(
            created_by="core",
            method=self.provider_id,
            parameters={"psi4_version": version.group(1) if version else "unknown", "scf_type": "pk", "puream": True},
            timestamp=time.time(),
        )
        descriptors = [
            DescriptorValue(
                descriptor_id="psi4.scf_energy",
                name="SCF Energy",
                units="Hartree",
                category="quantum_chemistry",
                provider="psi4",
                molecule_uuid=molecule_uuid,
                # The LAST energy: for an optimization every step prints one and the last is at the converged geometry.
                value=float(energies[-1]),
                timestamp=provenance.timestamp,
                cache_state=CacheState.COMPLETED,
                provenance=provenance,
            )
        ]
        conformer = self._parse_optimized_conformer(output_text, mol, provenance) if calc_type == "opt" else None
        return descriptors, conformer

    def _parse_optimized_conformer(self, output_text: str, mol: Chem.Mol, provenance: Provenance) -> ConformerModel:
        if "Optimizer: Optimization complete!" not in output_text:
            raise Psi4OutputError("Psi4's geometry optimization did not converge.")
        start = output_text.rfind(_FINAL_GEOMETRY)
        if start < 0:
            raise Psi4OutputError("Psi4 reported a converged optimization but printed no final geometry.")
        rows = []
        for line in output_text[start:].splitlines()[1:]:
            match = _GEOMETRY_ROW.match(line)
            if match:
                rows.append(match.groups())
            elif rows:
                break
        atoms = list(mol.GetAtoms())
        symbols = [a.GetSymbol() for a in atoms]
        if [r[0] for r in rows] != symbols:
            # Never apply coordinates to the wrong atoms: the element sequence must be the input's.
            raise Psi4OutputError(f"Psi4's final geometry has atoms {[r[0] for r in rows]}, not the input's {symbols}.")
        new_mol = Chem.Mol(mol)
        conf = new_mol.GetConformer()
        for index, (_symbol, x, y, z) in enumerate(rows):
            conf.SetAtomPosition(index, Point3D(float(x), float(y), float(z)))
        return ConformerModel(molblock=Chem.MolToMolBlock(new_mol), energy=None, method=PSI4_OPTIMIZED, provenance=provenance)


def _failure_message(output_text: str) -> str:
    """Psi4's own words for what went wrong: the last boxed message (`!  ...  !`) before the error banner, else the last line that is not the banner."""
    lines = output_text.splitlines()

    def boxed(line: str) -> bool:
        return line.startswith("!") and bool(set(line.strip()) - set("!- "))

    rows = [i for i, line in enumerate(lines) if boxed(line)]
    if rows:
        # The box of the failing statement is the LAST contiguous run of `!` lines.
        last = first = rows[-1]
        while first > 0 and lines[first - 1].startswith("!"):
            first -= 1
        return " ".join(re.sub(r"^!\s?|\s*!$", "", line).strip() for line in lines[first : last + 1] if boxed(line))
    tail = [line for line in lines if line.strip() and not line.startswith("***")]
    return tail[-1].strip() if tail else "Psi4 reported an error."
