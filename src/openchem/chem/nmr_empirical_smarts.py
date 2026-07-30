from __future__ import annotations

from rdkit import Chem

from openchem.domain.common import Provenance
from openchem.domain.scientific_result import NMRSpectrumResult

# Curated SMARTS-based characteristic-environment lookup -- standard
# organic-chemistry reference ranges (the kind of table in every intro
# spectroscopy textbook, e.g. Pavia & Lampman's "Introduction to
# Spectroscopy" or Silverstein's "Spectrometric Identification of Organic
# Compounds"). This is a TYPICAL-RANGE ESTIMATE, not a quantitative
# prediction -- same "not a prediction" honesty framing as Phase 20's
# hERG risk-factor checklist. Ordered most-specific-first; the first
# pattern that matches a given atom wins, so a narrower environment (e.g.
# an acid's carbonyl carbon) is checked before the general fallback it
# would otherwise also satisfy.
#
# Every SMARTS is wrapped as a single-atom recursive query (`[$(...)]`)
# so `GetSubstructMatches` always returns the one heavy atom of interest
# at match index 0, unambiguous even for chemically-symmetric environments
# (e.g. both carbons of a C=C double bond independently satisfy "alkene
# carbon" and are found as separate single-atom matches, not one 2-atom
# match with an arbitrary side picked as index 0).
_CARBON_PATTERNS: list[tuple[str, str, tuple[float, float]]] = [
    ("aldehyde/ketone carbonyl C", "[$([CX3H1]=O),$([CX3](=O)([#6])[#6])]", (190.0, 220.0)),
    ("acid/ester/amide carbonyl C", "[$([CX3](=O)[OX2,NX3])]", (160.0, 185.0)),
    ("nitrile C", "[$([CX2]#[NX1])]", (110.0, 125.0)),
    ("aromatic C", "[c]", (100.0, 150.0)),
    ("alkene C", "[$([CX3]=[CX3])]", (100.0, 150.0)),
    ("alkyne C", "[$([CX2]#[CX2])]", (65.0, 90.0)),
    ("C-O (alcohol/ether)", "[$([CX4][OX2])]", (50.0, 90.0)),
    ("C-N (amine)", "[$([CX4][NX3])]", (35.0, 60.0)),
    ("alkyl C", "[CX4]", (0.0, 50.0)),
]

_HYDROGEN_PATTERNS: list[tuple[str, str, tuple[float, float]]] = [
    ("carboxylic acid OH", "[$([OX2H1][CX3]=O)]", (10.0, 13.0)),
    ("aldehyde CH", "[$([CX3H1]=O)]", (9.5, 10.5)),
    ("aromatic H", "[cH]", (6.5, 8.5)),
    ("alkene H", "[$([CX3H1,CX3H2]=[CX3])]", (4.5, 6.5)),
    ("O-CH (alcohol/ether)", "[$([CX4][OX2])]", (3.3, 4.5)),
    ("alcohol/phenol OH", "[OX2H1]", (0.5, 5.5)),
    ("amine NH", "[NX3;H1,H2;!$(NC=O)]", (0.5, 5.0)),
    ("alpha to carbonyl CH", "[$([CX4][CX3]=O)]", (2.0, 2.6)),
    ("alkyne CH", "[$([CX2]#[CX2])]", (1.8, 3.1)),
    ("allylic CH", "[$([CX4][CX3]=[CX3])]", (1.6, 2.6)),
    ("alkyl CH", "[CX4]", (0.8, 2.0)),
]


def _classify(mol: Chem.Mol, patterns: list[tuple[str, str, tuple[float, float]]], element: str, assign_to_h: bool):
    values: dict[int, float] = {}
    elements: dict[int, str] = {}
    ranges: dict[int, tuple[float, float]] = {}
    for _label, smarts, (low, high) in patterns:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is None:
            continue
        for match in mol.GetSubstructMatches(pattern):
            heavy_atom_index = match[0]
            if not assign_to_h:
                if heavy_atom_index in values:
                    continue
                values[heavy_atom_index] = (low + high) / 2
                ranges[heavy_atom_index] = (low, high)
                elements[heavy_atom_index] = element
                continue
            heavy_atom = mol.GetAtomWithIdx(heavy_atom_index)
            for neighbor in heavy_atom.GetNeighbors():
                if neighbor.GetSymbol() != "H" or neighbor.GetIdx() in values:
                    continue
                values[neighbor.GetIdx()] = (low + high) / 2
                ranges[neighbor.GetIdx()] = (low, high)
                elements[neighbor.GetIdx()] = "H"
    return values, elements, ranges


def estimate_shifts_by_smarts_environment(mol: Chem.Mol, molecule_uuid: str) -> NMRSpectrumResult:
    """Typical-range chemical shift estimate from the curated SMARTS
    environment tables above -- ORCA-free, milliseconds to compute.
    `values` holds each matched range's midpoint (so any consumer
    expecting a single number, e.g. the 2D correlation tables, still
    works); `ranges` holds the full `(low, high)` per atom. `mol` should
    have explicit hydrogens (`Chem.AddHs`) for 1H entries to be produced
    at all -- an implicit-H mol still gets 13C entries.
    """
    c_values, c_elements, c_ranges = _classify(mol, _CARBON_PATTERNS, "C", assign_to_h=False)
    h_values, h_elements, h_ranges = _classify(mol, _HYDROGEN_PATTERNS, "H", assign_to_h=True)

    values = {**c_values, **h_values}
    elements = {**c_elements, **h_elements}
    ranges = {**c_ranges, **h_ranges}

    return NMRSpectrumResult(
        spectrum_type="nmr_empirical",
        name="NMR Chemical Shift (empirical, SMARTS-based typical range)",
        units="ppm (typical range midpoint)",
        method="smarts_lookup",
        molecule_uuid=molecule_uuid,
        values=values,
        elements=elements,
        ranges=ranges,
        provenance=Provenance(
            created_by="core",
            method="smarts_lookup",
            parameters={"reference_source": "Pavia & Lampman characteristic shift tables"},
        ),
    )
