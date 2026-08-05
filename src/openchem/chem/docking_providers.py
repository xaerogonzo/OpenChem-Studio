from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Callable

from rdkit import Chem

from openchem.chem.pose_analysis import (
    filter_altlocs,
    is_excluded_chain,
    is_stripped_residue,
)
from openchem.chem.vina_engine import VinaEngine, parse_vina_output_pdbqt, select_vina_engine
from openchem.domain.docking import DockingBox, DockingPoseModel
from openchem.plugins.interfaces import DockingProvider
from openchem.services.progress import ProgressHandle

logger = logging.getLogger("openchem.chemistry")

DEFAULT_EXHAUSTIVENESS = 8
DEFAULT_RECEPTOR_PH = 7.4


def _raise_if_cancelled(progress: ProgressHandle) -> None:
    if progress.is_cancelled():
        raise DockingProviderError("Docking cancelled by user")


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
    locations are handled separately, as a text pre-filter
    (`pose_analysis.filter_altlocs`) *before* Open Babel reads the
    structure: confirmed live that Open Babel does NOT dedupe altlocs on
    its own, in either format — a two-altloc atom comes back as two full
    atoms at two positions. BOTH formats are covered now; the filter used
    to be PDB-only, which meant an mmCIF receptor was docked with its
    doubled atoms intact.

    **MISSING-RESIDUE REPAIR: MEASURED AND NOT SHIPPED.** This was carried
    for many phases as "the one docking gap", on the assumption that the
    blocker was a missing dependency. A spike settled all three questions
    and only one of them the expected way.

    *Installing it is easy now.* PDBFixer pulls three packages, 125 MB, and
    OpenMM 8.5.2 publishes cp313 Windows wheels — no compiler, no conda.
    Whatever was true before, the toolchain objection is gone.

    *The gaps are not where docking cares.* Across the 49 curated
    receptors: 47 have unobserved residues (12,615 of them), but they are
    termini and distal loops. ZERO receptors have a chain break within
    10 A of their binding site; the library minimum is 10.8 A and the
    median 30.6 A. Counting incomplete SIDE CHAINS instead — a different
    and more pocket-relevant defect — only 3 of 48 have any within 10 A.

    *And the repair cannot be trusted where it would matter.* PDBFixer
    BUILDS the missing atoms from templates, so the output is a
    prediction. 4DAJ supplies ground truth for it: four crystallographic
    copies of the same receptor, so a side chain unmodelled in one is
    often observed in another. Rebuilding and comparing 374 atoms against
    their observed counterparts gave a median deviation of 2.30 A, with
    only 18% within 1.0 A and 58% beyond 2.0 A. A hydrogen bond is
    2.8-3.2 A, and the worst cases (8.9 A) are LYS NZ and ARG NH2 — the
    salt-bridging atoms docking depends on most. Some of that spread is
    genuine conformational difference between copies rather than rebuild
    error, so it is an upper bound on accuracy; it is still far too loose
    to put into a pocket, where it would manufacture contacts that were
    never observed.

    So the honest summary is not "blocked" but "measured, low value, and
    unsafe in the one place it would help". Revisit if a repair method
    reports per-atom confidence, so rebuilt atoms near a site could be
    excluded from scoring rather than silently trusted.
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

            # Cancellation is best-effort, checked at these phase
            # boundaries -- neither VinaEngine implementation exposes a
            # mid-search cancellation hook (the actual Vina run is one
            # blocking call either way), so a cancel requested during the
            # search itself only takes effect once that call returns, not
            # instantly.
            _raise_if_cancelled(progress)
            progress.report(0.05, "Preparing receptor")
            self._convert_receptor_to_pdbqt(
                pybel,
                receptor_structure_text,
                receptor_source_format,
                receptor_pdbqt,
                receptor_prep_options or {},
            )

            _raise_if_cancelled(progress)
            self._require_receptor_in_box(receptor_pdbqt, box)

            _raise_if_cancelled(progress)
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

        _raise_if_cancelled(progress)
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
            structure_text = filter_altlocs(structure_text, source_format)
            mol = pybel.readstring(source_format, structure_text)
            self._drop_symmetry_copies(mol.OBMol)
            self._drop_untyped_atoms(mol.OBMol)
            self._strip_unselected_chains(mol.OBMol, prep_options)
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

    def _require_receptor_in_box(self, receptor_pdbqt: Path, box: DockingBox) -> None:
        """Refuse to dock into a box that holds no receptor.

        Vina does not object: given a box in open solvent it searches it,
        finds nothing to score against, and returns poses with plausible
        affinities. The result looks exactly like a result.

        The box can come to be empty without anyone doing something
        obviously wrong. A box placed from a co-crystallised ligand and
        then narrowed to a chain the ligand does not sit on is the
        expected route now that chains can be excluded; stripping
        cofactors out from under a box centred on one is another.

        Read from the PREPARED PDBQT rather than from the source
        structure, so the atoms counted are exactly the atoms Vina is
        about to be handed -- after altloc filtering, symmetry-copy
        removal, chain exclusion, residue stripping and hydrogen
        addition. Checking the input file instead would answer a question
        about a different receptor, which is the failure this module keeps
        being bitten by.
        """
        cx, cy, cz = box.center
        hx, hy, hz = (size / 2.0 for size in box.size)
        inside = 0
        for line in receptor_pdbqt.read_text().splitlines():
            if not line.startswith(("ATOM", "HETATM")):
                continue
            try:
                # PDBQT keeps PDB's fixed columns for coordinates.
                x = float(line[30:38])
                y = float(line[38:46])
                z = float(line[46:54])
            except ValueError:
                continue
            if abs(x - cx) <= hx and abs(y - cy) <= hy and abs(z - cz) <= hz:
                inside += 1
                # One atom is enough to know the box is not empty; the
                # count is not otherwise interesting and a receptor can be
                # 70,000 lines.
                return
        if not inside:
            raise DockingProviderError(
                f"The search box at ({cx:.1f}, {cy:.1f}, {cz:.1f}) contains no "
                "receptor atoms after preparation. Docking into empty space "
                "returns poses with meaningless scores, so it was not run. "
                "Check the box position, and whether a chain or cofactor the "
                "box was placed on has since been excluded."
            )

    def _drop_untyped_atoms(self, obmol) -> None:
        """Delete atoms Open Babel could not assign an element to.

        ONE of them destroys the whole docking run. Open Babel writes such
        an atom into the PDBQT with an empty AutoDock type and the name
        `*`, and AutoDock Vina 1.2.7 refuses to parse the file at all --
        "An internal error occurred in ... parse_pdbqt.cpp(69)" -- so the
        receptor is rejected entire, not just that atom. What reaches the
        user is `returned non-zero exit status 1`, which names neither the
        atom nor the file.

        Found on 4DKL, a receptor in the bundled catalogue: a single
        chloride ion comes back with `atomicnum == 0`, and docking against
        it failed outright. 3,674 good atoms discarded because of one.

        This mirrors `receptor_atoms_from_structure`, which has always
        skipped `atom.atomicnum == 0` -- the analysis path filtered these
        and the preparation path did not, which is the same divergence
        that `is_stripped_residue`, `filter_altlocs` and
        `is_symmetry_generated` each exist to close. Here the two paths
        disagreeing did not produce a wrong answer, it produced no answer.
        """
        from openbabel import openbabel as ob

        doomed = [atom for atom in ob.OBMolAtomIter(obmol) if atom.GetAtomicNum() == 0]
        for atom in doomed:
            obmol.DeleteAtom(atom)

    def _drop_symmetry_copies(self, obmol) -> None:
        """Delete the unit-cell copies Open Babel invents for structures
        whose space group it cannot recognise.

        See `pose_analysis.is_symmetry_generated` for the measurements.
        The short version: 6WGT's 8,100-atom deposit reached this method
        as 64,764 atoms and left it as a 73,707-atom receptor, eight
        overlapping copies of the protein, and Vina docked into that.

        This runs BEFORE `_strip_unwanted_residues` and is not optional,
        exactly like the altloc filter: no preparation setting should be
        able to leave phantom copies in. It also has to be done here
        rather than only in the analysis parser -- the whole point of the
        shared `is_stripped_residue` predicate is that what gets docked
        and what gets analysed cannot disagree, and a fix on one side
        only would reintroduce that split.
        """
        from openbabel import openbabel as ob

        # Collected before deleting: mutating while iterating the atom
        # list invalidates the iteration, the same reason
        # `_strip_unwanted_residues` gathers first.
        doomed = [atom for atom in ob.OBMolAtomIter(obmol) if atom.GetResidue() is None]
        for atom in doomed:
            obmol.DeleteAtom(atom)

    def _strip_unselected_chains(self, obmol, prep_options: dict[str, Any]) -> None:
        """Keep only the chains the user chose, if they chose any.

        The reason this option exists: 32 of the 49 curated receptors are
        multi-polymer complexes, and a deposited "receptor" routinely
        includes things that are not the target. 3SN6 is five polymer
        chains -- a T4-lysozyme-fused receptor, a Gs heterotrimer and a
        nanobody -- so docking the whole file searches a box that may sit
        against a G protein.

        Uses `pose_analysis.is_excluded_chain`, the SAME predicate the
        interaction analysis applies, for the reason
        `_strip_unwanted_residues` records: a receptor prepared one way
        and analysed another produces contacts with atoms that were not
        there. Because `keep_chains` travels in `receptor_prep_options`,
        which the service already hands to both, the two cannot be given
        different answers.

        An empty selection means keep everything, so this is inert unless
        a user opts in.
        """
        keep_chains = prep_options.get("keep_chains") or ()
        if not keep_chains:
            return
        from openbabel import openbabel as ob

        # Same collect-then-delete shape as `_strip_unwanted_residues`:
        # deleting while iterating invalidates the iteration.
        atoms_to_delete = []
        for i in range(obmol.NumResidues()):
            residue = obmol.GetResidue(i)
            if is_excluded_chain(str(residue.GetChain()), keep_chains):
                atoms_to_delete.extend(ob.OBResidueAtomIter(residue))
        for atom in atoms_to_delete:
            obmol.DeleteAtom(atom)

    def _strip_unwanted_residues(self, obmol, prep_options: dict[str, Any]) -> None:
        strip_waters = prep_options.get("strip_waters", True)
        strip_cofactors = prep_options.get("strip_cofactors", False)
        # The residues named here go regardless of the two flags above --
        # see `is_stripped_residue` for the measurement. In short: the
        # receptor library builds every box from a co-crystallised ligand,
        # and leaving that ligand in the box it defined docks into an
        # occupied pocket (indinavir into its own 1HSG: -5.34 vs -9.78).
        strip_ligand_codes = tuple(prep_options.get("strip_ligand_codes", ()) or ())
        if not strip_waters and not strip_cofactors and not strip_ligand_codes:
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
            # The same predicate `receptor_atoms_from_structure` uses, so
            # what gets docked and what gets analysed cannot disagree.
            if is_stripped_residue(
                residue.GetName(), strip_waters, strip_cofactors, strip_ligand_codes
            ):
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
