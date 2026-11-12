"""Named common ions as graphs for salt composition.

Structures only. No pKa numbers, and not a pharmaceutical acceptability list.
Hydrogen sulfate and sulfate are different rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rdkit import Chem

from openchem.chem.salt_components import fragment_formal_charge, fragment_key

#: The catalog is not on the window. Remove this when something reachable
#: from ``openchem.main`` imports the module.
REACHED_BY = (
    "tooling: consumed by tests/test_ionic_species.py; the ion catalog is not "
    "on the window yet"
)


@dataclass(frozen=True)
class IonicSpeciesRow:
    ion_id: str
    name: str
    ion_smiles: str
    charge: int
    parent_smiles: str | None
    relationship: str
    source_key: str


def _catalog_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "ionic_species.json"


def load_ionic_species() -> tuple[IonicSpeciesRow, ...]:
    """Read the cited catalog. A charge that is not the graph's formal charge raises ``ValueError`` naming the id."""
    payload = json.loads(_catalog_path().read_text(encoding="utf-8"))
    rows: list[IonicSpeciesRow] = []
    seen: set[str] = set()
    for item in payload["ions"]:
        row = _row(item)
        if row.ion_id in seen:
            raise ValueError(f"{row.ion_id}: duplicate id")
        seen.add(row.ion_id)
        rows.append(row)
    return tuple(rows)


def row_by_id(ion_id: str) -> IonicSpeciesRow | None:
    for row in load_ionic_species():
        if row.ion_id == ion_id:
            return row
    return None


def _row(item: dict) -> IonicSpeciesRow:
    ion_id = item["id"]
    smiles = item["ion_smiles"]
    charge = item["charge"]
    if type(charge) is not int:
        raise ValueError(f"{ion_id}: charge is not an integer")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"{ion_id}: ion_smiles could not be read")
    graph_charge = fragment_formal_charge(mol)
    if graph_charge != charge:
        raise ValueError(
            f"{ion_id}: charge {charge} disagrees with fragment_formal_charge {graph_charge}"
        )
    # Mode B identifies a drawn ion by fragment_key. A stored spelling that
    # is not that key would miss the same graph.
    if fragment_key(mol) != smiles:
        raise ValueError(f"{ion_id}: ion_smiles is not the fragment_key form")
    parent = item["parent_smiles"]
    if parent is not None and not isinstance(parent, str):
        raise ValueError(f"{ion_id}: parent_smiles is not a string")
    return IonicSpeciesRow(
        ion_id=ion_id,
        name=item["name"],
        ion_smiles=smiles,
        charge=charge,
        parent_smiles=parent,
        relationship=item["relationship"],
        source_key=item["source_key"],
    )
