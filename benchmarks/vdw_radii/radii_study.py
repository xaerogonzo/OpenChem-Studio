"""What the choice of van der Waals radius table changes: areas over a drug-like set, and the steric series.

Reproduces the measurements in `docs/VDW_RADII_ASSESSMENT.md`. Run from the repository root:

    uv run python benchmarks/vdw_radii/radii_study.py

Three tables are compared: RDKit's (equal to Batsanov 2001 Table 9), Bondi 1964 as printed (hydrogen 1.20), and the
CRC Handbook 97th edition / the docking module's own table (Bondi's values with hydrogen 1.10). The geometry is one
RDKit-embedded, MMFF94-relaxed conformer per molecule (seed 7), the area routine the application itself uses, and
the steric series is the application's own `compute_steric_analysis` with its radius lookup swapped.

It writes nothing and touches no settings.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from openchem.chem import steric  # noqa: E402
from openchem.chem.sasa import accessible_areas  # noqa: E402

#: Bondi 1964, as printed (read from the paper; agrees with Poater et al. 2009 Table 1 and Batsanov 2001 Table 1).
BONDI = {"H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52, "F": 1.47, "P": 1.80, "S": 1.80, "Cl": 1.75, "Br": 1.85, "I": 1.98}
#: The CRC Handbook's choice: Bondi's values with Rowland and Taylor's hydrogen.
CRC = dict(BONDI, H=1.10)
#: The tables compared, by name.
TABLES = {
    "RDKit/Batsanov": {s: Chem.GetPeriodicTable().GetRvdw(s) for s in BONDI},
    "Bondi 1964": BONDI,
    "CRC (H 1.10)": CRC,
}
#: A drug-like set with every element the tables disagree about.
MOLECULES = {
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O", "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O", "paracetamol": "CC(=O)Nc1ccc(O)cc1",
    "morphine": "CN1CCC23C4C1CC5=C2C(=C(C=C5)O)OC3C(C=C4)O", "fluoxetine": "CNCCC(c1ccccc1)Oc1ccc(cc1)C(F)(F)F",
    "chloroquine": "CCN(CC)CCCC(C)Nc1ccnc2cc(Cl)ccc12",
    "sildenafil": "CCCc1nn(C)c2c1nc([nH]c2=O)-c1cc(ccc1OCC)S(=O)(=O)N1CCN(C)CC1", "glyphosate": "OC(=O)CNCP(O)(O)=O",
    "bromobenzene": "Brc1ccccc1", "iodobenzene": "Ic1ccccc1", "DMSO": "CS(C)=O", "urea": "NC(N)=O",
    "glycine": "NCC(O)=O", "ethanol": "CCO", "benzene": "c1ccccc1", "trimethyl phosphate": "COP(=O)(OC)OC",
}
#: The phosphine series of Tolman's appendix, as SMILES.
SERIES = [
    ("PH3", "P"), ("PMe3", "CP(C)C"), ("PEt3", "CCP(CC)CC"), ("PPh3", "c1ccccc1P(c1ccccc1)c1ccccc1"),
    ("PCy3", "C1CCCCC1P(C1CCCCC1)C1CCCCC1"), ("PtBu3", "CC(C)(C)P(C(C)(C)C)C(C)(C)C"),
]
#: Tolman 1977, Appendix B, in the order of `SERIES`.
TOLMAN = [87, 118, 132, 145, 170, 182]
#: Clavier and Nolan 2010, Table 1, %Vbur at M-P 2.28 A: PMe3, PEt3, PPh3, PCy3 (P(t-Bu)3 left out, see the assessment).
PUBLISHED_VBUR = {"PMe3": 22.2, "PEt3": 27.8, "PPh3": 29.6, "PCy3": 31.8}


def _conformer(smiles: str) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


class _Table:
    """Stands in for RDKit's periodic table inside `steric`, answering from one of the tables above."""

    def __init__(self, table: dict[str, float]) -> None:
        self._table = table

    def GetRvdw(self, number: int) -> float:  # noqa: N802 - the name RDKit's own object uses
        periodic = Chem.GetPeriodicTable()
        symbol = periodic.GetElementSymbol(number)
        return self._table.get(symbol, periodic.GetRvdw(number))


def areas() -> None:
    rows = {}
    for name, smiles in MOLECULES.items():
        mol = _conformer(smiles)
        positions = mol.GetConformer().GetPositions()
        symbols = [a.GetSymbol() for a in mol.GetAtoms()]
        rows[name] = {
            label: tuple(accessible_areas(positions, np.array([table[s] for s in symbols]), probe).sum() for probe in (1.4, 0.0))
            for label, table in TABLES.items()
        }
    for index, quantity in enumerate(("accessible area (1.4 A probe)", "van der Waals area (probe 0)")):
        for label in ("Bondi 1964", "CRC (H 1.10)"):
            change = [100 * (rows[n][label][index] - rows[n]["RDKit/Batsanov"][index]) / rows[n]["RDKit/Batsanov"][index] for n in rows]
            print(f"{quantity:30} {label:13} vs RDKit: mean {statistics.mean(change):+.1f}%  min {min(change):+.1f}%  max {max(change):+.1f}%")


def steric_series() -> None:
    original = steric._PERIODIC_TABLE
    try:
        for label in ("RDKit/Batsanov", "Bondi 1964"):
            steric._PERIODIC_TABLE = _Table(TABLES[label])
            angles, volumes = [], []
            for _name, smiles in SERIES:
                result = steric.compute_steric_analysis(Chem.MolFromSmiles(smiles), "m", {"conformers": 10})
                facts = {f.label: f.display_value for f in result.facts}
                angles.append(float(facts["Exact cone angle"]))
                volumes.append(float(facts["Percent buried volume"]))
            error = statistics.mean(abs(volumes[i] - PUBLISHED_VBUR[name]) for i, (name, _s) in enumerate(SERIES) if name in PUBLISHED_VBUR)
            print(f"{label:15} cone angles {angles}\n{'':15} %Vbur {volumes}\n{'':15} r(cone, Tolman) = {np.corrcoef(angles, TOLMAN)[0, 1]:.3f}; "
                  f"mean absolute error against the published %Vbur of PMe3, PEt3, PPh3, PCy3 = {error:.1f} points")
    finally:
        steric._PERIODIC_TABLE = original


if __name__ == "__main__":
    areas()
    steric_series()
