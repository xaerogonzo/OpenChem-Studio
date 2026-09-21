"""The KNOWN DEVIATIONS guard (naming round 8): the engine's few deliberate departures from the Blue Book, and nothing else.

`benchmarks/naming/known_deviations.toml` lists the ONLY curated ring locants the engine writes in the former CAS form (`10b`, `10c`, ...) where the book's
PIN uses superscripts (`3a1`, `5a1`, P-25.3.3.3.1, pdf p. 224), each with its normative target, its reason and what the oracle says. Two things must stay true:

* a NEW legacy locant cannot be added to the ring table on the argument that OPSIN parses it: any curated ring whose interior carbon carries a letter label that is
  not the book's form must be declared, and a declaration that no longer matches the table is stale;
* a declared deviation is REPORTED as one and never counted as an exact PREFERRED match, whatever the name round-trips to.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from rdkit import Chem, RDLogger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks" / "naming"))
sys.path.insert(0, str(ROOT / "tools"))

import known_deviations as kd  # noqa: E402

BOOK_INTERIOR_FORM = re.compile(r"\d+[a-z]\d+")  # 3a1, 5a1, 6b1: a peripheral locant, its letter, the bond count


def _table():
    from openchem.vendor.iupac_namer.data_loader import _RING_CURATED_SMILES

    RDLogger.DisableLog("rdApp.*")
    return _RING_CURATED_SMILES


def _interior_letter_labels() -> dict[str, list[str]]:
    """{curated ring name: its interior-carbon labels that carry a LETTER}, over the table's own atom_locants."""
    found: dict[str, list[str]] = {}
    for smiles, entry in _table().items():
        locants = entry.get("atom_locants")
        mol = Chem.MolFromSmiles(smiles) if locants else None
        if mol is None:
            continue
        rings = mol.GetRingInfo()
        labels = [
            str(locants[a.GetIdx()])
            for a in mol.GetAtoms()
            if rings.NumAtomRings(a.GetIdx()) >= 3 and a.GetIdx() in locants and re.search(r"[a-z]", str(locants[a.GetIdx()]))
        ]
        if labels:
            found[entry["name"]] = labels
    return found


def test_the_registry_is_well_formed():
    devs = kd.load()
    assert devs, "no deviation declared: then delete the guard, do not leave it empty"
    assert len({d["id"] for d in devs}) == len(devs), "duplicate ids"
    for d in devs:
        assert len(d["engine"]) == len(d["normative"]) >= 1, d["id"]
        assert set(d["engine"]).isdisjoint(d["normative"]), f"{d['id']}: the deviation equals its target"
        assert all(BOOK_INTERIOR_FORM.fullmatch(n) for n in d["normative"]), f"{d['id']}: a normative locant not in the book's form"
        assert d["target_basis"] in ("PRINTED", "DERIVED"), d["id"]
        assert d["rule"].startswith("P-") and 1 <= d["page"] <= 1160, d["id"]
        assert d["reason"].strip() and d["oracle_statement"].strip(), f"{d['id']}: a deviation with no reason or no oracle statement"


def _fully_aromatic(ring_name: str) -> bool:
    """The scan's DOMAIN. An atom in three SSSR rings is an INTERIOR carbon only in a peri-fused ring system; in a hydro or bridged cage it is a bridgehead. Three curated
    hydro/bridged entries have such atoms with ordinary-looking labels ('12a'/'12b', '6a', '13a'), and this guard does NOT classify them: it scans the fully aromatic entries
    (pyrene, perylene), where the reading is unambiguous, and the declared non-aromatic one (benz[de]isoquinoline) is checked by its declaration. KNOWN_LIMITATIONS says so."""
    for smiles, entry in _table().items():
        if entry.get("name") == ring_name:
            mol = Chem.MolFromSmiles(smiles)
            return mol is not None and all(a.GetIsAromatic() for a in mol.GetAtoms() if a.IsInRing())
    return False


def test_a_curated_interior_locant_is_the_books_or_is_declared():
    declared = {d["ring"]: set(d["engine"]) for d in kd.load()}
    undeclared = {}
    for ring, labels in _interior_letter_labels().items():
        if not _fully_aromatic(ring):
            continue
        legacy = {label for label in labels if not BOOK_INTERIOR_FORM.fullmatch(label)}
        if legacy - declared.get(ring, set()):
            undeclared[ring] = sorted(legacy - declared.get(ring, set()))
    assert not undeclared, (
        f"interior locants in the former CAS form that are not declared in known_deviations.toml: {undeclared}. OPSIN reading a name does not make it preferred; "
        "declare the deviation with its target, its reason and the oracle statement, or use the book's form."
    )


def test_every_declared_deviation_still_occurs_in_the_table():
    present = _interior_letter_labels()
    stale = [
        d["id"] for d in kd.load()
        if not set(d["engine"]) <= {label for label in present.get(d["ring"], [])}
    ]
    assert not stale, f"declared but no longer in the ring table (remove them with the fix): {stale}"


def test_the_normative_target_is_what_the_generic_rule_gives():
    """The DERIVED targets are the engine's own P-25.3.3.3.1 rule applied to the ring's peripheral locants, so a ring whose numbering is wrong cannot be excused by a wrong target."""
    from openchem.vendor.iupac_namer.ring_naming.fusion_orientation import _interior_carbon_locant
    from openchem.vendor.iupac_namer.types import Locant

    by_ring = {d["ring"]: d for d in kd.load()}
    for smiles, entry in _table().items():
        dev = by_ring.get(entry.get("name"))
        if dev is None:
            continue
        mol = Chem.MolFromSmiles(smiles)
        rings = mol.GetRingInfo()
        peripheral = {a.GetIdx() for a in mol.GetAtoms() if rings.NumAtomRings(a.GetIdx()) < 3}
        loc = {}
        for idx, label in entry["atom_locants"].items():
            m = re.fullmatch(r"(\d+)([a-z]*)", str(label))
            if idx in peripheral and m:
                loc[idx] = Locant.numeric(int(m.group(1)), m.group(2))
        interior = sorted(
            (a.GetIdx() for a in mol.GetAtoms() if rings.NumAtomRings(a.GetIdx()) >= 3 and re.search(r"[a-z]", str(entry["atom_locants"].get(a.GetIdx(), "")))),
            key=lambda i: dev["engine"].index(str(entry["atom_locants"][i])),
        )
        computed = []
        for idx in interior:
            got = _interior_carbon_locant(mol, idx, loc, peripheral)
            computed.append(f"{got._numeric_value}{got.suffix}")
        assert computed == dev["normative"], f"{dev['id']}: the rule gives {computed}, the registry says {dev['normative']}"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("10b-methyl-10bH-pyrene", "KD-pyrene"),
        ("4,10c-dihydropyrene", "KD-pyrene"),
        ("12c-methylperylene", "KD-perylene"),
        ("3a1H-phenalene", None),            # the book's form is not a deviation
        ("10b-methylanthracene", None),      # a legacy-looking label beside a ring that is not declared
        ("3a1,5a1-dimethylpyrene", None),
        ("pyrene", None),
        (None, None),
    ],
)
def test_a_name_is_flagged_only_for_a_declared_label_beside_its_own_ring(name, expected):
    assert kd.deviation_in(name) == expected


def test_a_deviating_name_is_never_an_exact_preferred_match():
    """Even when the adjudicated target IS the deviating name (a PubChem-style one entered by mistake), the scorer refuses to count it."""
    import naming_stage_artifact as stage

    smiles = Chem.MolToSmiles(Chem.MolFromSmiles("c1cc2ccc3cccc4ccc(c1)c2c34"))
    record = {"smiles": smiles, "name": "10b-methyl-10bH-pyrene", "pubchem_name": "10b-methyl-10bH-pyrene"}
    scores = stage._preferred_scores([record], {smiles: "10b-methyl-10bH-pyrene"})
    assert scores["adjudicated_rows"] == 1
    assert scores["engine"] == 0 and scores["known_deviation"] == 1
    plain = {"smiles": smiles, "name": "pyrene", "pubchem_name": "pyrene"}
    assert stage._preferred_scores([plain], {smiles: "pyrene"})["engine"] == 1
