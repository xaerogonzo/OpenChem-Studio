"""Shipped structure templates, 2D molblocks, and placement.

The UI never imports RDKit: it asks this module for a molblock.
"""

from __future__ import annotations

import json
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Geometry import Point3D

from openchem.chem.engine import ChemistryEngine, InvalidStructureError
from openchem.domain.structure_template import (
    TemplateCategory,
    TemplateEntry,
    TemplateError,
    TemplateKind,
    TemplateOrigin,
    parse_kind,
)

#: Directory of the committed shipped JSON catalogs.
SHIPPED_DIR = Path(__file__).resolve().parent / "data" / "structure_templates"

#: Gap between the existing drawing's right edge and the inserted fragment, Å.
PLACEMENT_GAP_ANGSTROM = 2.0

#: Shipped catalog files, in the order the dialog lists them.
_SHIPPED_FILES = (
    "rings.json",
    "amino_acids.json",
    "nucleobases.json",
    "sugars.json",
    "cycloalkanes.json",
    "heterocycles.json",
    "solvents_reagents.json",
    "alkaloids.json",
    "flavonoids.json",
    "vitamins.json",
    "functional_groups.json",
    "polycycles.json",
    "peptide_building_blocks.json",
    "allotropes.json",
    "reactive_species.json",
    "cofactors.json",
    "terpenoids_steroids.json",
)


def load_shipped(engine: ChemistryEngine | None = None) -> tuple[TemplateCategory, ...]:
    """Every shipped category, each entry validated to a 2D molblock."""
    engine = engine or ChemistryEngine()
    categories = []
    seen_ids: set[str] = set()
    for name in _SHIPPED_FILES:
        path = SHIPPED_DIR / name
        category = _load_shipped_file(path, engine, seen_ids)
        categories.append(category)
    return tuple(categories)


def molblock_for(entry: TemplateEntry, engine: ChemistryEngine | None = None) -> str:
    """A usable 2D molblock for insertion or preview."""
    engine = engine or ChemistryEngine()
    if entry.kind is not TemplateKind.COMPLETE_MOLECULE:
        raise TemplateError(f"{entry.id}: only complete molecules can be inserted")
    if entry.molblock and entry.molblock.strip():
        mol = engine.mol_from_molblock(entry.molblock)
        _refuse_unsupported(mol, entry.id)
        return _ensure_2d(mol, entry.id)
    if entry.smiles and entry.smiles.strip():
        mol = engine.mol_from_smiles(entry.smiles)
        _refuse_unsupported(mol, entry.id)
        rdDepictor.Compute2DCoords(mol)
        return _molblock_with_up_down_bonds(mol)
    raise TemplateError(f"{entry.id}: a template needs exactly one of smiles or molblock")


def place_to_the_right(canvas_molblock: str, template_molblock: str) -> str:
    """Translate `template_molblock` so it sits to the right of the canvas drawing."""
    if not canvas_molblock.strip():
        return template_molblock
    canvas = Chem.MolFromMolBlock(canvas_molblock, removeHs=False)
    fragment = Chem.MolFromMolBlock(template_molblock, removeHs=False)
    if canvas is None:
        raise InvalidStructureError("Could not parse the canvas molblock")
    if fragment is None:
        raise InvalidStructureError("Could not parse the template molblock")
    canvas_box = _bounds(canvas)
    fragment_box = _bounds(fragment)
    if canvas_box is None:
        return template_molblock
    if fragment_box is None:
        raise InvalidStructureError("the template has no 2D coordinates")
    canvas_max_x, _canvas_min_y, _canvas_max_y = canvas_box[1], canvas_box[2], canvas_box[3]
    frag_min_x = fragment_box[0]
    dx = canvas_max_x + PLACEMENT_GAP_ANGSTROM - frag_min_x
    return _translate(fragment, dx, 0.0)


def bounds_2d(molblock: str) -> tuple[float, float, float, float] | None:
    """(min_x, max_x, min_y, max_y), or None when there are no 2D points."""
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    if mol is None:
        return None
    return _bounds(mol)


def import_mol_file(path: Path, category_id: str, engine: ChemistryEngine | None = None) -> tuple[list[TemplateEntry], list[tuple[str, str]]]:
    """Read one .mol or .sdf into entries. Bad records are skipped with a reason."""
    engine = engine or ChemistryEngine()
    added: list[TemplateEntry] = []
    skipped: list[tuple[str, str]] = []
    suffix = path.suffix.lower()
    if suffix == ".sdf":
        supplier = Chem.SDMolSupplier(str(path), removeHs=False, sanitize=False)
        for index, mol in enumerate(supplier, start=1):
            label = f"{path.name}#{index}"
            try:
                added.append(_entry_from_mol(mol, category_id, label, path, engine, index))
            except (TemplateError, InvalidStructureError) as exc:
                skipped.append((label, str(exc)))
        return added, skipped
    if suffix in {".mol", ".mdl"}:
        try:
            mol = engine.mol_from_molblock(path.read_text(encoding="utf-8"))
            added.append(_entry_from_mol(mol, category_id, path.stem, path, engine, 1))
        except (TemplateError, InvalidStructureError, OSError) as exc:
            skipped.append((path.name, str(exc)))
        return added, skipped
    skipped.append((path.name, "not a .mol or .sdf file"))
    return added, skipped


def _load_shipped_file(path: Path, engine: ChemistryEngine, seen_ids: set[str]) -> TemplateCategory:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TemplateError(f"{path.name}: not an object")
    category_id = raw.get("id")
    title = raw.get("title")
    if not isinstance(category_id, str) or not isinstance(title, str):
        raise TemplateError(f"{path.name}: needs id and title")
    description = raw.get("description") if isinstance(raw.get("description"), str) else ""
    entries_raw = raw.get("entries")
    if not isinstance(entries_raw, list):
        raise TemplateError(f"{path.name}: entries must be a list")
    entries = []
    for item in entries_raw:
        entry = _shipped_entry(item, category_id)
        if entry.id in seen_ids:
            raise TemplateError(f"duplicate template id {entry.id!r}")
        seen_ids.add(entry.id)
        molblock_for(entry, engine)
        entries.append(entry)
    return TemplateCategory(
        id=category_id,
        title=title,
        origin=TemplateOrigin.SHIPPED,
        description=description,
        entries=tuple(entries),
    )


def _shipped_entry(raw: object, category_id: str) -> TemplateEntry:
    if not isinstance(raw, dict):
        raise TemplateError("a shipped template is not an object")
    tags_raw = raw.get("tags") or []
    if not isinstance(tags_raw, list) or not all(isinstance(t, str) for t in tags_raw):
        raise TemplateError("tags must be a list of strings")
    return TemplateEntry(
        id=str(raw.get("id") or ""),
        name=str(raw.get("name") or ""),
        category_id=category_id,
        smiles=raw.get("smiles") if isinstance(raw.get("smiles"), str) else None,
        molblock=raw.get("molblock") if isinstance(raw.get("molblock"), str) else None,
        description=raw.get("description") if isinstance(raw.get("description"), str) else "",
        tags=tuple(tags_raw),
        source=raw.get("source") if isinstance(raw.get("source"), str) else "",
        kind=parse_kind(raw.get("kind")),
    )


def _refuse_unsupported(mol: Chem.Mol, entry_id: str) -> None:
    if any(atom.GetAtomicNum() == 0 for atom in mol.GetAtoms()):
        raise TemplateError(
            f"{entry_id}: dummy atoms are wildcards, not attachment points, and are not stored"
        )
    if any(atom.HasQuery() for atom in mol.GetAtoms()):
        raise TemplateError(f"{entry_id}: query atoms cannot be stored as templates")
    try:
        groups = Chem.GetMolSubstanceGroups(mol)
    except (AttributeError, RuntimeError):
        groups = ()
    if groups:
        raise TemplateError(f"{entry_id}: S-groups cannot be stored as templates")


def _ensure_2d(mol: Chem.Mol, entry_id: str) -> str:
    del entry_id
    if mol.GetNumConformers() == 0:
        rdDepictor.Compute2DCoords(mol)
        return _molblock_with_up_down_bonds(mol)
    conf = mol.GetConformer()
    zs = [abs(conf.GetAtomPosition(i).z) for i in range(mol.GetNumAtoms())]
    if zs and max(zs) > 0.05:
        rdDepictor.Compute2DCoords(mol)
    return _molblock_with_up_down_bonds(mol)


def _molblock_with_up_down_bonds(mol: Chem.Mol) -> str:
    """Wedge/hash bonds for specified stereo so the 2D editor shows up/down by default."""
    if mol.GetNumConformers() == 0:
        rdDepictor.Compute2DCoords(mol)
    Chem.WedgeMolBonds(mol, mol.GetConformer())
    return Chem.MolToMolBlock(mol)


def _bounds(mol: Chem.Mol) -> tuple[float, float, float, float] | None:
    if mol.GetNumConformers() == 0 or mol.GetNumAtoms() == 0:
        return None
    conf = mol.GetConformer()
    xs, ys = [], []
    for i in range(mol.GetNumAtoms()):
        pos = conf.GetAtomPosition(i)
        xs.append(pos.x)
        ys.append(pos.y)
    return min(xs), max(xs), min(ys), max(ys)


def _translate(mol: Chem.Mol, dx: float, dy: float) -> str:
    conf = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        pos = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, Point3D(pos.x + dx, pos.y + dy, pos.z))
    return Chem.MolToMolBlock(mol)


def _entry_from_mol(
    mol: Chem.Mol | None,
    category_id: str,
    label: str,
    path: Path,
    engine: ChemistryEngine,
    index: int,
) -> TemplateEntry:
    if mol is None:
        raise TemplateError("could not parse the structure")
    try:
        Chem.SanitizeMol(mol)
    except Exception as exc:  # noqa: BLE001 - RDKit's own refusal
        raise TemplateError(f"could not sanitise the structure: {exc}") from exc
    _refuse_unsupported(mol, label)
    molblock = _ensure_2d(mol, label)
    name = mol.GetProp("_Name") if mol.HasProp("_Name") and mol.GetProp("_Name").strip() else ""
    if not name:
        name = f"Untitled {index}"
    entry_id = f"{category_id}:{path.stem}:{index}"
    return TemplateEntry(
        id=entry_id,
        name=name,
        category_id=category_id,
        molblock=molblock,
        kind=TemplateKind.COMPLETE_MOLECULE,
        provenance={"import_filename": path.name, "source_format": path.suffix.lower().lstrip(".")},
    )
