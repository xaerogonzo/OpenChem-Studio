### Task 6: Cited ion catalog

**Files:**
- Create: `src/openchem/chem/data/ionic_species.json`
- Create: `src/openchem/chem/ionic_species.py`
- Modify: `docs/sources.toml` — add `used_by` path on a new `salt_ion_catalog` entry (**no DOI**). Do not claim CRC pKa numbers.
- Test: `tests/test_ionic_species.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class IonicSpeciesRow:
    ion_id: str
    name: str
    ion_smiles: str
    charge: int
    parent_smiles: str | None
    relationship: str
    source_key: str


def load_ionic_species() -> tuple[IonicSpeciesRow, ...]:
    ...


def row_by_id(ion_id: str) -> IonicSpeciesRow | None:
    ...
```

JSON shape:

```json
{
  "_source_key": "salt_ion_catalog",
  "ions": [
    {
      "id": "chloride",
      "name": "chloride",
      "ion_smiles": "[Cl-]",
      "charge": -1,
      "parent_smiles": "Cl",
      "relationship": "hydrohalide",
      "source_key": "salt_ion_catalog"
    }
  ]
}
```

v1 rows (exact ids): `chloride`, `bromide`, `iodide`, `hydrogen_sulfate`, `sulfate`, `dihydrogen_phosphate`, `hydrogen_phosphate`, `phosphate`, `acetate`, `nitrate`, `ammonium`, `pyridinium`.

SMILES (must round-trip through `fragment_key` after `MolFromSmiles`):

- chloride `[Cl-]` parent `Cl` relationship `hydrohalide`
- bromide `[Br-]` parent `Br` relationship `hydrohalide`
- iodide `[I-]` parent `I` relationship `hydrohalide`
- hydrogen_sulfate `OS(=O)(=O)[O-]` parent `OS(=O)(=O)O` relationship `first_dissociation`
- sulfate `[O-]S(=O)(=O)[O-]` parent `OS(=O)(=O)O` relationship `second_dissociation`
- dihydrogen_phosphate `OP(=O)(O)[O-]` parent `OP(=O)(O)O` relationship `first_dissociation`
- hydrogen_phosphate `OP(=O)([O-])[O-]` parent `OP(=O)(O)O` relationship `second_dissociation`
- phosphate `[O-]P(=O)([O-])[O-]` parent `OP(=O)(O)O` relationship `third_dissociation`
- acetate `CC(=O)[O-]` parent `CC(=O)O` relationship `first_dissociation`
- nitrate `[O-][N+](=O)[O-]` parent `O[N+](=O)[O-]` relationship `first_dissociation`
- ammonium `[NH4+]` parent `N` relationship `protonated_base`
- pyridinium `c1cc[nH+]cc1` parent `c1ccncc1` relationship `protonated_base`

If `fragment_key` of `MolFromSmiles(ion_smiles)` differs from the JSON string, **store the `fragment_key` form** so identity matches Mode B.

`salt_ion_catalog` in `docs/sources.toml`:

```toml
[[source]]
key = "salt_ion_catalog"
kind = "dataset"
citation = "OpenChem Studio v1 salt ion catalog: named common ions as canonical SMILES for composition, not a pharmaceutical list."
identifier_type = "none"
identifier = "salt_ion_catalog"
status = "shipped"
verification = "citation"
verified_date = 2026-11-11
used_by = ["src/openchem/chem/data/ionic_species.json"]
reason = """
STRUCTURES ONLY. Each row is a named ion's graph and its parent, so Mode A
workflow 2 and the catalog agree on identity. No pKa numbers. Not safety or
acceptability. Hydrogen sulfate and sulfate are different rows.
"""
```

If `identifier_type = "none"` is rejected by `tests/test_sources_are_current.py`, use the same `identifier_type` a similar internal dataset uses (search `kind = "dataset"`). Do not invent a DOI.

- [ ] **Step 1: Write failing tests** (file missing).

```python
from openchem.chem.ionic_species import load_ionic_species, row_by_id
from openchem.chem.salt_components import fragment_formal_charge, fragment_key
from rdkit import Chem


def test_hydrogen_sulfate_and_sulfate_are_different_rows() -> None:
    hso4 = row_by_id("hydrogen_sulfate")
    so4 = row_by_id("sulfate")
    assert hso4 is not None and so4 is not None
    assert hso4.ion_smiles != so4.ion_smiles
    assert hso4.charge == -1
    assert so4.charge == -2


def test_every_row_round_trips_to_its_charge_and_key() -> None:
    for row in load_ionic_species():
        mol = Chem.MolFromSmiles(row.ion_smiles)
        assert mol is not None, row.ion_id
        assert fragment_formal_charge(mol) == row.charge, row.ion_id
        assert fragment_key(mol) == row.ion_smiles, row.ion_id


def test_catalog_is_not_a_pharma_whitelist() -> None:
    ids = {row.ion_id for row in load_ionic_species()}
    assert "chloride" in ids
    # An unusual ion is simply absent, not forbidden.
    assert row_by_id("hexafluorophosphate") is None
```

- [ ] **Step 2: Run — FAIL import.**

- [ ] **Step 3: Add JSON, loader, sources.toml entry.** Loader reads `Path(__file__).resolve().parent / "data" / "ionic_species.json"`. Refuse a row whose `charge` disagrees with `fragment_formal_charge` at load time by raising `ValueError` naming `id` (fail closed).

`REACHED_BY` on the loader module.

- [ ] **Step 4: Run `tests/test_ionic_species.py` and `tests/test_sources_are_current.py` (or the tests that fail on an unregistered `used_by` path / DOI).**

If `test_sources_are_current` requires `SOURCES.md` regeneration, run `uv run --no-sync python tools/build_sources_doc.py` and include the generated file.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/chem/ionic_species.py src/openchem/chem/data/ionic_species.json docs/sources.toml docs/SOURCES.md tests/test_ionic_species.py
git commit -m "Catalog named salt ions as graphs, with sulfate and hydrogen sulfate kept apart."
```

---

