"""MMFF94 partial charges, against the paper that defines them.

**THE ORACLE IS HALGREN'S OWN TABLE**, not "MMFF94 ran": part II (J. Comput.
Chem. 1996, 17, 520), Table V, lists MMFF94 atom types and charges for 20
small molecules and ions, transcribed as printed into
`fixtures/mmff94_halgren1996_table5.csv`.

Two layers, kept apart on purpose:

    (a) the ATOMIC charge and type RDKit assigns, against the table
    (b) the FOLDED value -- an atom plus its implicit hydrogens -- against
        the atomic charges it is built from, and never against Halgren,
        because the paper defines no such quantity

The table has two defects of its own, and both are asserted rather than
skipped, so the record cannot drift from what the page says: a misprinted
hydrogen type, and a zwitterion carboxylate carbon (0.900) that disagrees
with the same table's acetate row (0.906) for the same types in the same
bonding.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import rdForceFieldHelpers

from openchem.chem.descriptor_providers import MMFF94, compute_mmff94_charges

FIXTURE = Path(__file__).parent / "fixtures" / "mmff94_halgren1996_table5.csv"
TOLERANCE = 0.0005  # the table prints three decimals


def _rows() -> list[dict[str, str]]:
    lines = [line for line in FIXTURE.read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
    return list(csv.DictReader(lines))


ROWS = _rows()


def _typed(smiles: str):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    properties = rdForceFieldHelpers.MMFFGetMoleculeProperties(mol)
    assert properties is not None, smiles
    return mol, properties


def _neighbours(atom) -> str:
    return "".join(sorted(n.GetSymbol() for n in atom.GetNeighbors()))


def _matching(row, mol, properties, *, by_type: bool):
    return [
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if atom.GetSymbol() == row["element"]
        and _neighbours(atom) == row["neighbours"]
        and (not by_type or properties.GetMMFFAtomType(atom.GetIdx()) == int(row["mmff_type"]))
    ]


def test_the_fixture_covers_the_whole_table():
    """ASSERTS ITS OWN SETUP: twenty molecules, as the table prints."""
    assert len({row["molecule"] for row in ROWS}) == 20
    assert {row["status"] for row in ROWS} == {"computed", "type_misprint", "contradicted"}


@pytest.mark.parametrize(
    "row", [r for r in ROWS if r["status"] == "computed"],
    ids=lambda r: f"{r['molecule']}:{r['atom']}",
)
def test_rdkit_reproduces_the_printed_charge_and_type(row):
    """Layer (a). Every atom the row describes -- all of them, not the
    first: pyridine's two C-3 carbons and three ring hydrogens share one row."""
    mol, properties = _typed(row["smiles"])
    atoms = _matching(row, mol, properties, by_type=True)
    assert atoms, f"no atom matches {row}"
    for index in atoms:
        assert properties.GetMMFFPartialCharge(index) == pytest.approx(
            float(row["charge"]), abs=TOLERANCE
        ), (row, index)


def test_the_misprinted_hydrogen_type_is_a_misprint_and_its_charge_agrees():
    """Imidazole's ring hydrogens are printed as type 15. RDKit types them
    5, like every other aromatic C-H in the table, and the CHARGE agrees --
    so this is the page, not the port."""
    (row,) = [r for r in ROWS if r["status"] == "type_misprint"]
    mol, properties = _typed(row["smiles"])
    atoms = _matching(row, mol, properties, by_type=False)
    assert len(atoms) == 3
    for index in atoms:
        assert properties.GetMMFFAtomType(index) != int(row["mmff_type"])
        assert properties.GetMMFFPartialCharge(index) == pytest.approx(float(row["charge"]), abs=TOLERANCE)


def test_the_contradicted_zwitterion_carbon_matches_the_tables_own_acetate_row():
    """THE PAGE DISAGREES WITH ITSELF, and RDKit sides with the acetate row.

    Same atom type (41), same neighbours (a type-1 carbon and two type-32
    oxygens): eq. (7) gives those one charge. The table prints 0.906 for
    acetate and 0.900 for the zwitterion. Asserted both ways so a later
    "fix" of the fixture cannot quietly erase the disagreement."""
    (row,) = [r for r in ROWS if r["status"] == "contradicted"]
    acetate = [r for r in ROWS if r["molecule"] == "CH3CO2(-)" and r["mmff_type"] == "41"][0]
    mol, properties = _typed(row["smiles"])
    (index,) = _matching(row, mol, properties, by_type=True)
    printed, table_elsewhere = float(row["charge"]), float(acetate["charge"])
    assert printed != table_elsewhere, "setup: the contradiction is no longer in the fixture"
    assert properties.GetMMFFPartialCharge(index) == pytest.approx(table_elsewhere, abs=TOLERANCE)


@pytest.mark.parametrize("smiles", sorted({r["smiles"] for r in ROWS}))
def test_every_charge_set_sums_to_the_formal_charge(smiles):
    mol, properties = _typed(smiles)
    total = sum(properties.GetMMFFPartialCharge(i) for i in range(mol.GetNumAtoms()))
    assert total == pytest.approx(Chem.GetFormalCharge(mol), abs=1e-6)


# --- layer (b): the folded value is arithmetic on (a), nothing more -----------


@pytest.mark.parametrize("smiles", sorted({r["smiles"] for r in ROWS}))
def test_a_folded_value_is_the_atom_plus_exactly_its_own_implicit_hydrogens(smiles):
    drawn = Chem.MolFromSmiles(smiles)
    full, properties = _typed(smiles)
    folded, every = compute_mmff94_charges(drawn, include_hydrogens=True)
    separate, _ = compute_mmff94_charges(drawn, include_hydrogens=False)
    for index in range(drawn.GetNumAtoms()):
        expected = properties.GetMMFFPartialCharge(index) + sum(
            properties.GetMMFFPartialCharge(n.GetIdx())
            for n in full.GetAtomWithIdx(index).GetNeighbors()
            if n.GetIdx() >= drawn.GetNumAtoms()
        )
        assert folded[index] == pytest.approx(expected, abs=1e-9)
        assert separate[index] == pytest.approx(properties.GetMMFFPartialCharge(index), abs=1e-9)
    assert sum(folded.values()) == pytest.approx(Chem.GetFormalCharge(drawn), abs=1e-6)
    assert every == pytest.approx(Chem.GetFormalCharge(drawn), abs=1e-6)


def test_a_drawn_hydrogen_atom_keeps_its_own_value_and_is_not_folded():
    drawn = Chem.AddHs(Chem.MolFromSmiles("CO"))
    folded, _ = compute_mmff94_charges(drawn, include_hydrogens=True)
    _full, properties = _typed("CO")
    assert set(folded) == set(range(drawn.GetNumAtoms()))
    assert folded[5] == pytest.approx(0.400, abs=TOLERANCE)  # the O-H hydrogen, type 21


# --- through the registry --------------------------------------------------------


def _registry():
    from openchem.bootstrap import build_service_container

    return build_service_container().calculator_registry


def test_the_calculator_offers_the_method_by_code_with_a_label():
    definition = _registry().get("gasteiger_charge_at_ph")
    (method,) = [p for p in definition.parameters if p.name == "method"]
    assert method.choices == ["gasteiger", "mmff94"]
    assert method.choice_labels == ["Gasteiger", "MMFF94"]
    assert method.default == "gasteiger"


def test_the_registered_calculator_computes_mmff94_on_the_microspecies():
    """Methylamine at pH 7.4 is the cation, and Table V has that cation:
    N -0.853, C +0.503 -- the table's numbers, arriving through the whole
    path (registry, protonation, renumbering, folding off)."""
    result = _registry().compute("gasteiger_charge_at_ph", Chem.MolFromSmiles("CN"), "u", {"pH": 7.4, "method": MMFF94})
    assert result.name == "Partial Charge (MMFF94) at pH 7.4"
    assert result.values[0] == pytest.approx(0.503, abs=TOLERANCE)
    assert result.values[1] == pytest.approx(-0.853, abs=TOLERANCE)
    assert result.provenance.parameters["charge_method"] == MMFF94
    assert result.provenance.parameters["hydrogen_aggregation"] == "separate"


def test_the_two_methods_are_different_calculations():
    """Not a tuning knob: the same atom gets a different number, and the
    identity a stored result is filed under says which."""
    from openchem.services.result_cache import parameters_key

    registry = _registry()
    mol = Chem.MolFromSmiles("CO")
    gasteiger = registry.compute("gasteiger_charge_at_ph", mol, "u", {"pH": 7.4, "method": "gasteiger"})
    mmff = registry.compute("gasteiger_charge_at_ph", mol, "u", {"pH": 7.4, "method": MMFF94})
    assert gasteiger.values[1] != pytest.approx(mmff.values[1], abs=0.01)
    assert "Gasteiger" in gasteiger.name and "MMFF94" in mmff.name
    assert parameters_key({"pH": 7.4, "method": "gasteiger"}) != parameters_key({"pH": 7.4, "method": MMFF94})


def test_a_structure_mmff94_cannot_type_is_a_limit_not_a_fault():
    result = _registry().compute("gasteiger_charge_at_ph", Chem.MolFromSmiles("[Xe]"), "u", {"pH": 7.4, "method": MMFF94})
    assert result.cache_state.value == "failed"
    assert result.inapplicable


def test_an_unknown_method_is_refused_rather_than_defaulted():
    with pytest.raises(ValueError, match="Unknown charge method"):
        _registry().compute("gasteiger_charge_at_ph", Chem.MolFromSmiles("CO"), "u", {"method": "eem"})
