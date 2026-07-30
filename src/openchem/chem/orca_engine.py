from __future__ import annotations

import re
import time
from pathlib import Path

from rdkit import Chem
from rdkit.Geometry import Point3D

from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.plugins.interfaces import QuantumEngineProvider

# ORCA's simple, well-documented "! <keywords>" / "* xyz <charge> <mult> ...
# *" input format — the shape below is confirmed against ORCA's public
# input manual. The output-parsing regexes further down are NOT verified
# against a real ORCA run in this project (ORCA is external, separately-
# licensed software this session cannot install) — they target ORCA's
# well-known, stable output markers ("FINAL SINGLE POINT ENERGY", the
# "CARTESIAN COORDINATES (ANGSTROEM)" block, and the "THERMOCHEMISTRY"
# section's labeled lines), based on documented/widely-referenced ORCA
# output shape, not a byte-perfect transcript.

_CALC_TYPE_KEYWORDS = {"sp": "", "opt": "Opt", "opt_freq": "Opt Freq"}

_SCF_ENERGY_RE = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
_CARTESIAN_BLOCK_RE = re.compile(
    r"CARTESIAN COORDINATES \(ANGSTROEM\)\n-+\n((?:\s*[A-Za-z]{1,2}(?:\s+-?\d+\.\d+){3}\n)+)"
)
_ENTHALPY_RE = re.compile(r"Total [Ee]nthalpy\s+\.\.\.\s+(-?\d+\.\d+)")
_ENTROPY_TERM_RE = re.compile(r"Final entropy term\s+\.\.\.\s+(-?\d+\.\d+)")
_GIBBS_RE = re.compile(r"Final Gibbs free energy\s+\.\.\.\s+(-?\d+\.\d+)")

HARTREE_TO_KCAL_MOL = 627.5094740631

_CALC_TYPES = ("sp", "opt", "opt_freq")


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
        # One shared Provenance for every DescriptorValue/ConformerModel
        # this call produces -- same ORCA run, same "what produced this,"
        # so they should carry an identical timestamp rather than each
        # grabbing a slightly different time.time().
        provenance = Provenance(created_by="core", method=self.provider_id, timestamp=now)

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
