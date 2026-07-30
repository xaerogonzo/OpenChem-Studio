from __future__ import annotations

import re
import time
from pathlib import Path

from rdkit import Chem
from rdkit.Geometry import Point3D

from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.scientific_result import SpectrumResult
from openchem.plugins.interfaces import QuantumEngineProvider

# ORCA's simple, well-documented "! <keywords>" / "* xyz <charge> <mult> ...
# *" input format — the shape below is confirmed against ORCA's public
# input manual. The SCF-energy/thermochemistry/cartesian-coordinates
# output-parsing regexes below are NOT verified against a real ORCA run in
# this project (ORCA is external, separately-licensed software this
# session cannot install) — they target ORCA's well-known, stable output
# markers, based on documented/widely-referenced ORCA output shape, not a
# byte-perfect transcript. The NMR shielding-summary regex below IS
# verified against a real ORCA 6.1.1 run (HF/STO-3G, water) — see
# `_SHIELDING_HEADER_RE`'s own note.

_CALC_TYPE_KEYWORDS = {"sp": "", "opt": "Opt", "opt_freq": "Opt Freq", "nmr": "NMR"}

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

HARTREE_TO_KCAL_MOL = 627.5094740631

_CALC_TYPES = ("sp", "opt", "opt_freq", "nmr")


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
    ) -> SpectrumResult | None:
        if calc_type != "nmr":
            return None
        shieldings = self._parse_shielding_summary(output_text)
        version_match = _VERSION_RE.search(output_text)
        provenance = Provenance(
            created_by="core",
            method=self.provider_id,
            parameters={"orca_version": version_match.group(1) if version_match else "unknown"},
        )
        return SpectrumResult(
            spectrum_type="nmr_raw_shielding",
            name="NMR Isotropic Shielding (raw, not yet referenced to TMS)",
            # Deliberately NOT yet a chemical shift (delta, ppm relative to
            # a reference compound like TMS) -- that needs a reference-
            # compound calculation at the same method/basis, cached and
            # reused rather than re-run per molecule (a real cost concern
            # for a real ab initio calculation), which is real, separately
            # scoped follow-up work, not built here. This is the engine's
            # raw isotropic shielding constant per nucleus, confirmed live
            # against a real ORCA run.
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
