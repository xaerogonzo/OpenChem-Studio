from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Callable

from rdkit import Chem

from openchem.chem.vina_engine import VinaEngine, parse_vina_output_pdbqt, select_vina_engine
from openchem.domain.docking import DockingBox, DockingPoseModel
from openchem.plugins.interfaces import DockingProvider
from openchem.services.progress import ProgressHandle

logger = logging.getLogger("openchem.chemistry")

DEFAULT_EXHAUSTIVENESS = 8
DEFAULT_RECEPTOR_PH = 7.4

# PDB/mmCIF water residue names Open Babel's own reader passes through
# unchanged from the source file -- not exhaustive of every convention in
# the wild, but covers the common ones.
_WATER_RESIDUE_NAMES = {"HOH", "WAT", "H2O", "DOD", "TIP", "TIP3", "TIP4"}

# Standard amino acids plus common alternate-protonation-state names some
# tools/force fields emit (histidine tautomers, cysteine states, etc.) --
# anything else non-water is treated as a "cofactor" candidate for
# strip_cofactors. Deliberately protein-only (no nucleotide residues): a
# docking receptor prepared through this pipeline is a protein target.
_STANDARD_RECEPTOR_RESIDUES = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "HID", "HIE", "HIP", "HSD", "HSE", "HSP", "CYX", "CYM", "ASH", "GLH", "LYN",
}


def _filter_pdb_altlocs(pdb_text: str) -> str:
    """Drops ATOM/HETATM lines for any alternate location except the first
    (blank or 'A') -- confirmed live that Open Babel's PDB reader does NOT
    dedupe altlocs itself (a two-altloc atom comes back as two full atoms
    at two different positions, one occupancy-weighted position, not one).
    Column 17 (0-indexed 16) is the PDB format's fixed-width altLoc field;
    non-ATOM/HETATM lines and lines too short to have that column pass
    through unchanged.
    """
    kept_lines = []
    for line in pdb_text.splitlines(keepends=True):
        if line.startswith(("ATOM", "HETATM")) and len(line) > 16:
            altloc = line[16]
            if altloc not in (" ", "A"):
                continue
        kept_lines.append(line)
    return "".join(kept_lines)


class DockingProviderError(Exception):
    """Raised when docking can't be performed — no usable Vina backend, or
    a receptor/ligand preparation failure. Always caught by the service
    layer and reported via CacheState.FAILED, never left to crash."""


class VinaDockingProvider(DockingProvider):
    """AutoDock Vina, via whichever `VinaEngine` is actually usable.

    Engine selection is deliberately re-resolved on every call
    (`_resolve_engine()` below), not cached once at construction time: the
    user can configure a Vina executable path (via the docking panel's
    "Configure Vina..." dialog) *after* the app has already started, and a
    construction-time-only resolution would never pick that up without a
    restart. `select_vina_engine()` still prefers the Python binding when
    importable, falling back to the configured/found executable.

    `executable_path_resolver` is a plain `Callable[[], str]`, not a
    `Settings` object — `chem/` stays fully decoupled from `openchem.app`;
    `DockingService` (which already depends on `Settings`, same as
    `QuantumChemistryService`) supplies a closure over the real settings
    object. `engine` is a test-only override that bypasses path resolution
    entirely.

    Receptor preparation (`_convert_receptor_to_pdbqt`) supports pH-correct
    protonation and water/cofactor stripping via `receptor_prep_options`,
    both through Open Babel (already a dependency) operating on the parsed
    `OBMol`, not raw text — format-agnostic across PDB/mmCIF. Alternate
    locations are handled separately, as a PDB-only fixed-width text
    pre-filter (`_filter_pdb_altlocs`) *before* Open Babel ever reads the
    structure: confirmed live that Open Babel's PDB reader does NOT dedupe
    altlocs on its own (a two-altloc atom comes back as two full atoms at
    two positions, not one) — mmCIF's tag/loop structure has no fixed
    column layout, so this pre-filter only applies to
    `receptor_source_format == "pdb"`. **Still not built**: missing-residue
    repair — a genuinely different problem (needs a dedicated
    structure-repair library), left deferred.
    """

    provider_id = "vina"

    def __init__(
        self,
        executable_path_resolver: Callable[[], str] | None = None,
        engine: VinaEngine | None = None,
    ) -> None:
        self._executable_path_resolver = executable_path_resolver
        self._fixed_engine = engine
        # Set by dock() on every call, so engine_id/engine_version() always
        # describe exactly what the most recent dock() actually used —
        # re-resolving independently in each of the three places (dock(),
        # engine_id, engine_version()) would open a window, however
        # unlikely in practice, for them to disagree if settings changed
        # between calls within the same job.
        self._last_resolved_engine: VinaEngine | None = None

    def _resolve_engine(self) -> VinaEngine | None:
        if self._fixed_engine is not None:
            return self._fixed_engine
        configured_path = self._executable_path_resolver() if self._executable_path_resolver else ""
        return select_vina_engine(configured_path or None)

    @property
    def engine_id(self) -> str:
        """Which `VinaEngine` actually ran — "none" if unavailable. Not part
        of the generic `DockingProvider` ABC (a future non-Vina provider
        wouldn't have this concept); `DockingService` reads it defensively
        via `getattr` for the `DockingResultModel.engine` reproducibility
        field."""
        engine = self._last_resolved_engine if self._last_resolved_engine is not None else self._resolve_engine()
        return engine.engine_id if engine is not None else "none"

    def engine_version(self) -> str:
        engine = self._last_resolved_engine if self._last_resolved_engine is not None else self._resolve_engine()
        return engine.version() if engine is not None else "unknown"

    def dock(
        self,
        receptor_structure_text: str,
        receptor_source_format: str,
        ligand_mol: Chem.Mol,
        box: DockingBox,
        num_poses: int,
        progress: ProgressHandle,
        receptor_prep_options: dict[str, Any] | None = None,
    ) -> list[DockingPoseModel]:
        engine = self._resolve_engine()
        self._last_resolved_engine = engine
        if engine is None:
            raise DockingProviderError(
                "No Vina docking backend available — install the 'vina' Python "
                "package (uv sync --extra docking) or configure a Vina "
                "executable path via 'Configure Vina...' in the Docking panel."
            )

        from openbabel import pybel

        with tempfile.TemporaryDirectory() as scratch_dir:
            scratch = Path(scratch_dir)
            receptor_pdbqt = scratch / "receptor.pdbqt"
            ligand_pdbqt = scratch / "ligand.pdbqt"

            progress.report(0.05, "Preparing receptor")
            self._convert_receptor_to_pdbqt(
                pybel,
                receptor_structure_text,
                receptor_source_format,
                receptor_pdbqt,
                receptor_prep_options or {},
            )

            progress.report(0.15, "Preparing ligand")
            self._convert_ligand_to_pdbqt(pybel, ligand_mol, ligand_pdbqt)

            output_text = engine.dock(
                receptor_pdbqt=receptor_pdbqt,
                ligand_pdbqt=ligand_pdbqt,
                box=box,
                num_poses=num_poses,
                exhaustiveness=DEFAULT_EXHAUSTIVENESS,
                seed=None,
                progress=progress,
            )

        progress.report(0.95, "Finalizing")
        raw_poses = parse_vina_output_pdbqt(output_text)
        return [self._raw_pose_to_model(pybel, raw) for raw in raw_poses]

    def _convert_receptor_to_pdbqt(
        self,
        pybel,
        structure_text: str,
        source_format: str,
        out_path: Path,
        prep_options: dict[str, Any],
    ) -> None:
        try:
            if source_format == "pdb":
                structure_text = _filter_pdb_altlocs(structure_text)
            mol = pybel.readstring(source_format, structure_text)
            self._strip_unwanted_residues(mol.OBMol, prep_options)
            # correctForPH=True + pH (default 7.4, physiological) replaces
            # the old bare mol.addh() (which pybel's own wrapper calls with
            # correctForPH=False) -- confirmed live that OBMol.AddHydrogens
            # takes (polaronly, correctForPH, pH) positionally; pybel's
            # high-level addh() exposes none of these.
            ph = float(prep_options.get("ph", DEFAULT_RECEPTOR_PH))
            mol.OBMol.AddHydrogens(False, True, ph)
            # `opt={"r": None}` is Open Babel's rigid-receptor flag (the
            # `-xr` CLI equivalent) -- without it, `write("pdbqt", ...)`
            # treats the WHOLE receptor as one flexible ligand-style
            # structure, emitting ROOT/BRANCH/TORSDOF records (confirmed
            # live: a 327-atom protein came out with "104 active torsions").
            # A docking receptor must be rigid; only the ligand should carry
            # torsions.
            mol.write("pdbqt", str(out_path), overwrite=True, opt={"r": None})
        except Exception as exc:  # noqa: BLE001 - surface as a clear docking-specific error
            raise DockingProviderError(f"Failed to prepare receptor: {exc}") from exc

    def _strip_unwanted_residues(self, obmol, prep_options: dict[str, Any]) -> None:
        strip_waters = prep_options.get("strip_waters", True)
        strip_cofactors = prep_options.get("strip_cofactors", False)
        if not strip_waters and not strip_cofactors:
            return
        from openbabel import openbabel as ob

        # DeleteResidue() alone leaves the residue's atoms in the molecule
        # (confirmed live: NumResidues() drops but NumAtoms() doesn't) --
        # the actual atoms must be deleted via DeleteAtom(), collected
        # first since deleting while iterating residues would invalidate
        # the iteration.
        atoms_to_delete = []
        for i in range(obmol.NumResidues()):
            residue = obmol.GetResidue(i)
            name = residue.GetName().strip().upper()
            is_water = name in _WATER_RESIDUE_NAMES
            if strip_waters and is_water:
                atoms_to_delete.extend(ob.OBResidueAtomIter(residue))
            elif strip_cofactors and not is_water and name not in _STANDARD_RECEPTOR_RESIDUES:
                atoms_to_delete.extend(ob.OBResidueAtomIter(residue))
        for atom in atoms_to_delete:
            obmol.DeleteAtom(atom)

    def _convert_ligand_to_pdbqt(self, pybel, ligand_mol: Chem.Mol, out_path: Path) -> None:
        try:
            molblock = Chem.MolToMolBlock(ligand_mol)
            mol = pybel.readstring("mol", molblock)
            mol.addh()
            mol.write("pdbqt", str(out_path), overwrite=True)
        except Exception as exc:  # noqa: BLE001
            raise DockingProviderError(f"Failed to prepare ligand: {exc}") from exc

    def _raw_pose_to_model(self, pybel, raw) -> DockingPoseModel:
        pose_pdbqt_text = f"MODEL 1\n{raw.pdbqt_text}ENDMDL\n"
        try:
            mol = pybel.readstring("pdbqt", pose_pdbqt_text)
            pose_molblock = mol.write("mol")
        except Exception as exc:  # noqa: BLE001
            raise DockingProviderError(f"Failed to convert docked pose: {exc}") from exc
        return DockingPoseModel(
            pose_molblock=pose_molblock,
            binding_affinity_kcal_mol=raw.binding_affinity_kcal_mol,
            rmsd_lb=raw.rmsd_lb,
            rmsd_ub=raw.rmsd_ub,
        )
