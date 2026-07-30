from __future__ import annotations

from rdkit import Chem

from openchem.chem.nmr_empirical_smarts import estimate_shifts_by_smarts_environment


def _classify(smiles: str) -> tuple[Chem.Mol, dict]:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    result = estimate_shifts_by_smarts_environment(mol, "test")
    return mol, result


def _range_for(mol: Chem.Mol, result, symbol: str, neighbor_symbols: set[str]) -> tuple[float, float]:
    for atom in mol.GetAtoms():
        if atom.GetSymbol() != symbol:
            continue
        neighbors = {n.GetSymbol() for n in atom.GetNeighbors()}
        if neighbor_symbols <= neighbors:
            return result.ranges[atom.GetIdx()]
    raise AssertionError(f"no {symbol} atom with neighbors including {neighbor_symbols} found")


def test_ethanol_classifies_alkyl_ch3_and_o_ch2_and_oh():
    mol, result = _classify("CCO")

    # Every heavy C and H atom must be classified -- no gaps for a
    # molecule this simple.
    heavy_and_h = {a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() in ("C", "H")}
    assert heavy_and_h <= set(result.values)

    ch3_h_range = _range_for(mol, result, "H", {"C"})
    # Both plain-alkyl and O-CH hydrogens have neighbor set {"C"} --
    # distinguish by range instead: alkyl CH3 protons must land in the
    # narrower low-ppm range, not the O-adjacent one.
    alkyl_ranges = {result.ranges[a.GetIdx()] for a in mol.GetAtoms() if a.GetSymbol() == "H" and a.GetIdx() in result.ranges}
    assert (0.8, 2.0) in alkyl_ranges  # CH3
    assert (3.3, 4.5) in alkyl_ranges  # O-CH2
    assert (0.5, 5.5) in alkyl_ranges  # O-H

    o_ch2_carbon_range = _range_for(mol, result, "C", {"C", "O"})
    assert o_ch2_carbon_range == (50.0, 90.0)
    ch3_carbon_range = _range_for(mol, result, "C", {"C"})
    assert ch3_carbon_range == (0.0, 50.0)


def test_acetic_acid_distinguishes_alpha_ch_from_plain_alkyl_and_flags_the_acid_carbonyl():
    mol, result = _classify("CC(=O)O")

    carbonyl_carbon = next(a for a in mol.GetAtoms() if a.GetSymbol() == "C" and len(a.GetNeighbors()) == 3)
    assert result.ranges[carbonyl_carbon.GetIdx()] == (160.0, 185.0)

    acid_oh = next(a for a in mol.GetAtoms() if a.GetSymbol() == "O" and any(n.GetSymbol() == "H" for n in a.GetNeighbors()))
    acid_h = next(n for n in acid_oh.GetNeighbors() if n.GetSymbol() == "H")
    assert result.ranges[acid_h.GetIdx()] == (10.0, 13.0)

    methyl_carbon = next(a for a in mol.GetAtoms() if a.GetSymbol() == "C" and len(a.GetNeighbors()) == 4)
    methyl_hs = [n for n in methyl_carbon.GetNeighbors() if n.GetSymbol() == "H"]
    assert all(result.ranges[h.GetIdx()] == (2.0, 2.6) for h in methyl_hs)  # alpha-to-carbonyl, not plain alkyl


def test_benzaldehyde_distinguishes_aromatic_from_aldehyde():
    mol, result = _classify("c1ccccc1C=O")

    aromatic_h_ranges = {
        result.ranges[a.GetIdx()]
        for a in mol.GetAtoms()
        if a.GetSymbol() == "H" and any(n.GetIsAromatic() for n in a.GetNeighbors())
    }
    assert aromatic_h_ranges == {(6.5, 8.5)}

    aldehyde_carbon = next(
        a for a in mol.GetAtoms() if a.GetSymbol() == "C" and not a.GetIsAromatic() and a.GetDegree() == 3
    )
    assert result.ranges[aldehyde_carbon.GetIdx()] == (190.0, 220.0)
    aldehyde_h = next(n for n in aldehyde_carbon.GetNeighbors() if n.GetSymbol() == "H")
    assert result.ranges[aldehyde_h.GetIdx()] == (9.5, 10.5)


def test_values_are_range_midpoints():
    mol, result = _classify("CCO")
    for atom_index, (low, high) in result.ranges.items():
        assert result.values[atom_index] == (low + high) / 2


def test_result_carries_reference_source_provenance():
    _mol, result = _classify("CCO")
    assert result.provenance is not None
    assert "reference_source" in result.provenance.parameters
