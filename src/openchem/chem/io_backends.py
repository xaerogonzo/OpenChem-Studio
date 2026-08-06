from __future__ import annotations

from pathlib import Path

from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.domain.molecule import MoleculeModel
from openchem.plugins.interfaces import Exporter, Importer

# RDKit and Open Babel handle disjoint format sets here by design: RDKit is
# tried whenever it can parse/write a format at all, Open Babel only covers
# the formats RDKit doesn't support well (MOL2, PDB, XYZ, CML).
#
# These backends implement the same Importer/Exporter ABCs a future plugin
# would (openchem.plugins.interfaces) rather than private copies.
RDKIT_IMPORT_FORMATS = {"mol", "sdf", "smi", "smiles", "inchi"}
RDKIT_EXPORT_FORMATS = {"mol", "sdf", "smi"}
OPENBABEL_FALLBACK_FORMATS = {"mol2", "pdb", "xyz", "cml"}


class RDKitImporter(Importer):
    def __init__(self, engine: ChemistryEngine) -> None:
        self._engine = engine

    def supported_formats(self) -> set[str]:
        return set(RDKIT_IMPORT_FORMATS)

    def import_file(self, path: Path) -> list[MoleculeModel]:
        fmt = path.suffix.lstrip(".").lower()
        if fmt == "mol":
            mol = Chem.MolFromMolFile(str(path))
            return [self._mol_to_model(mol, path)] if mol is not None else []
        if fmt == "sdf":
            supplier = Chem.SDMolSupplier(str(path))
            return [self._mol_to_model(mol, path) for mol in supplier if mol is not None]
        if fmt in ("smi", "smiles"):
            models = []
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                mol = Chem.MolFromSmiles(line.split()[0])
                if mol is not None:
                    models.append(self._mol_to_model(mol, path))
            return models
        if fmt == "inchi":
            mol = Chem.MolFromInchi(path.read_text(encoding="utf-8").strip())
            return [self._mol_to_model(mol, path)] if mol is not None else []
        raise ValueError(f"RDKitImporter cannot handle format: {fmt}")

    def _mol_to_model(self, mol: Chem.Mol, path: Path) -> MoleculeModel:
        model = MoleculeModel(display_name=path.stem, molblock=Chem.MolToMolBlock(mol))
        return self._engine.canonicalize(model)


def mol_for_export(engine: ChemistryEngine, model: MoleculeModel):
    """The molecule to write out: its computed 3D geometry when it has one.

    `MoleculeModel.molblock` is the 2D structure the editor drew, so every
    exporter that built from it wrote a FLAT molecule -- measured: aspirin
    exported to `.xyz` had all 13 atoms at z = 0.0, and did so even when
    the molecule had a real MMFF-optimised conformer sitting beside it.

    That is worst for the formats people export FOR. `.xyz` and `.pdb`
    exist to carry 3D coordinates into another program; a planar one is
    syntactically valid, silently wrong, and re-imports as something that
    is not the molecule (aspirin came back as
    `[C]C(=O)Oc1[c][c][c][c]c1C([O])=O`, because bond perception from flat
    coordinates has nothing to work with).

    Using the conformer also gets EXPLICIT HYDROGENS for free -- conformers
    are embedded after `AddHs`, so the exported file has the 21 atoms of
    aspirin rather than its 13 heavy ones, which is what any downstream QM
    or docking tool needs.

    Conformer 1 rather than an arbitrary one: the provider sorts ascending
    by energy, so the first is the lowest-energy geometry found.
    """
    if model.conformers:
        molblock = model.conformers[0].molblock
        if molblock:
            return engine.mol_from_molblock(molblock)
    return engine.mol_from_model(model)


class RDKitExporter(Exporter):
    def __init__(self, engine: ChemistryEngine) -> None:
        self._engine = engine

    def supported_formats(self) -> set[str]:
        return set(RDKIT_EXPORT_FORMATS)

    def export_file(self, model: MoleculeModel, path: Path, fmt: str) -> None:
        mol = mol_for_export(self._engine, model)
        if fmt == "mol":
            Chem.MolToMolFile(mol, str(path))
        elif fmt == "sdf":
            writer = Chem.SDWriter(str(path))
            try:
                writer.write(mol)
            finally:
                writer.close()
        elif fmt == "smi":
            path.write_text(Chem.MolToSmiles(mol) + "\n", encoding="utf-8")
        else:
            raise ValueError(f"RDKitExporter cannot handle format: {fmt}")


class OpenBabelImporter(Importer):
    """Fallback importer for formats RDKit handles poorly (MOL2, PDB, XYZ, CML).

    Imports `openbabel` lazily, inside the method body, so the rest of the
    app never pays the import cost — or requires it installed — unless one
    of these formats is actually used.
    """

    def __init__(self, engine: ChemistryEngine) -> None:
        self._engine = engine

    def supported_formats(self) -> set[str]:
        return set(OPENBABEL_FALLBACK_FORMATS)

    def import_file(self, path: Path) -> list[MoleculeModel]:
        from openbabel import pybel

        fmt = path.suffix.lstrip(".").lower()
        models = []
        for obmol in pybel.readfile(fmt, str(path)):
            molblock = obmol.write("mol")
            model = MoleculeModel(display_name=path.stem, molblock=molblock)
            models.append(self._engine.canonicalize(model))
        return models


class OpenBabelExporter(Exporter):
    def __init__(self, engine: ChemistryEngine) -> None:
        self._engine = engine

    def supported_formats(self) -> set[str]:
        return set(OPENBABEL_FALLBACK_FORMATS)

    def export_file(self, model: MoleculeModel, path: Path, fmt: str) -> None:
        from openbabel import pybel

        # These are the 3D formats -- xyz, pdb, mol2 -- so this is where
        # writing the editor's flat 2D layout did the most damage. See
        # `mol_for_export`.
        mol = mol_for_export(self._engine, model)
        obmol = pybel.readstring("mol", Chem.MolToMolBlock(mol))
        obmol.write(fmt, str(path), overwrite=True)
