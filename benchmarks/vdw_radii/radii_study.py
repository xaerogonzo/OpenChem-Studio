"""What the choice of van der Waals radius table changes: areas over a drug-like set, the steric series, and checks
against Bondi's own published group volumes, transcribed twice (by hand from his Tables XV and XVI, and from Zhao,
Abraham and Zissimos's Tables 1 and 3).

Reproduces the measurements in `docs/VDW_RADII_ASSESSMENT.md`. Run from the repository root:

    uv run python benchmarks/vdw_radii/radii_study.py

Three tables are compared: RDKit's (equal to Batsanov 2001 Table 9), Bondi 1964 as printed (hydrogen 1.20), and the
CRC Handbook 97th edition / the docking module's own table (Bondi's values with hydrogen 1.10). The geometry is one
RDKit-embedded, MMFF94-relaxed conformer per molecule (seed 7), the area routine the application itself uses, and
the steric series is the application's own `compute_steric_analysis` with its radius lookup swapped (the application
itself has used Bondi's list for the steric calculator since method steric-v2).

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


def _lookup(table: dict[str, float]):
    """A stand-in for `steric.bondi_radius` that answers from one of the tables above."""
    periodic = Chem.GetPeriodicTable()

    def radius(number: int) -> float:
        return table.get(periodic.GetElementSymbol(number), periodic.GetRvdw(number))

    return radius


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
    original = steric.bondi_radius  # since steric-v2 this IS Bondi's list; the study swaps it for each table in turn
    try:
        for label in ("RDKit/Batsanov", "Bondi 1964"):
            steric.bondi_radius = _lookup(TABLES[label])
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
        steric.bondi_radius = original


#: Bondi 1964, Tables XV and XVI, in cm3/mole: the volume increments of the groups that make up the molecules below
#: (read from the page images). None of these molecules has a hydrogen bond or a crowding correction (Table XVII).
_CH3, _CH2, _CH, _C = 13.67, 10.23, 6.78, 3.33
#: (name, SMILES, Bondi's group sum in cm3/mole).
GROUP_CASES = [
    ("methane", "C", 17.12), ("ethane", "CC", 2 * _CH3), ("propane", "CCC", 2 * _CH3 + _CH2),
    ("n-hexane", "CCCCCC", 2 * _CH3 + 4 * _CH2), ("isobutane", "CC(C)C", 3 * _CH3 + _CH),
    ("neopentane", "CC(C)(C)C", 4 * _CH3 + _C), ("fluoroethane", "CCF", _CH3 + _CH2 + 5.72),
    ("chloromethane", "CCl", _CH3 + 11.62), ("chloroethane", "CCCl", _CH3 + _CH2 + 11.62),
    ("bromoethane", "CCBr", _CH3 + _CH2 + 14.40), ("iodoethane", "CCI", _CH3 + _CH2 + 19.18),
    ("diethyl ether", "CCOCC", 2 * _CH3 + 2 * _CH2 + 3.7), ("acetonitrile", "CC#N", _CH3 + 14.70),
    ("acetone", "CC(C)=O", 2 * _CH3 + 11.70), ("nitromethane", "C[N+](=O)[O-]", _CH3 + 16.8),
    ("dimethyl sulfide", "CSC", 2 * _CH3 + 10.8), ("trimethylamine", "CN(C)C", 3 * _CH3 + 4.33),
]


def _grid_volume(mol: Chem.Mol, table: dict[str, float], step: float = 0.04) -> float:
    """The volume of the fused spheres by a 0.04 angstrom grid, so any radius table can be used."""
    pos = mol.GetConformer().GetPositions()
    radii = np.array([table[a.GetSymbol()] for a in mol.GetAtoms()])
    low, high = (pos - radii[:, None]).min(0), (pos + radii[:, None]).max(0)
    axes = [np.arange(low[k], high[k] + step, step) for k in range(3)]
    xs, ys = np.meshgrid(axes[0], axes[1], indexing="ij")
    inside = 0
    for z in axes[2]:
        d2 = (xs[..., None] - pos[:, 0]) ** 2 + (ys[..., None] - pos[:, 1]) ** 2 + (z - pos[:, 2]) ** 2
        inside += int(((d2 <= radii**2).any(-1)).sum())
    return inside * step**3


def group_volumes() -> None:
    """Which table reproduces the volumes Bondi himself published for these molecules (an implementation-and-table check)."""
    errors: dict[str, list[float]] = {label: [] for label in TABLES}
    for name, smiles, groups in GROUP_CASES:
        mol = _conformer(smiles)
        reference = groups / 0.602214  # cm3/mole -> cubic angstrom per molecule
        for label, table in TABLES.items():
            errors[label].append(100 * (_grid_volume(mol, table) - reference) / reference)
    for label, values in errors.items():
        print(f"vdW volume vs Bondi's group sums, {len(values)} molecules  {label:15} mean {statistics.mean(values):+.2f}%  "
              f"mean abs {statistics.mean(abs(v) for v in values):.2f}%  max abs {max(abs(v) for v in values):.2f}%")


#: Zhao, Abraham & Zissimos 2003, Tables 1 and 3: Bondi's group-contribution volumes in A^3/molecule (no crowding
#: or hydrogen-bond correction), by kind. (name, SMILES, volume, kind).
ZHAO_CASES = [
    ("methane", "C", 28.44, "acyclic"), ("ethane", "CC", 45.42, "acyclic"), ("propane", "CCC", 62.41, "acyclic"),
    ("butane", "CCCC", 79.40, "acyclic"), ("isobutane", "CC(C)C", 79.39, "acyclic"), ("pentane", "CCCCC", 96.40, "acyclic"),
    ("neopentane", "CC(C)(C)C", 96.36, "acyclic"), ("hexane", "CCCCCC", 113.39, "acyclic"),
    ("octane", "CCCCCCCC", 147.38, "acyclic"), ("decane", "CCCCCCCCCC", 181.36, "acyclic"),
    ("allene", "C=C=C", 51.2, "acyclic"), ("ethene", "C=C", 39.7, "acyclic"), ("2-methylpropene", "CC(C)=C", 73.6, "acyclic"),
    ("2-methyl-2-butene", "CC=C(C)C", 90.5, "acyclic"), ("2,3-dimethyl-2-butene", "CC(C)=C(C)C", 107.5, "acyclic"),
    ("ethyne", "C#C", 38.4, "acyclic"), ("propyne", "CC#C", 55.3, "acyclic"),
    ("dimethyl ether", "COC", 51.6, "hetero"), ("methanol", "CO", 36.1, "hetero"), ("acetone", "CC(C)=O", 64.9, "hetero"),
    ("dimethyl sulfide", "CSC", 63.4, "hetero"), ("methanethiol", "CS", 47.3, "hetero"), ("methylamine", "CN", 40.2, "hetero"),
    ("dimethylamine", "CNC", 58.8, "hetero"), ("trimethylamine", "CN(C)C", 75.3, "hetero"),
    ("acetonitrile", "CC#N", 47.1, "hetero"), ("nitromethane", "C[N+](=O)[O-]", 50.6, "hetero"),
    ("trimethylphosphine", "CP(C)C", 85.5, "hetero"),
    ("fluoromethane", "CF", 32.2, "halide"), ("2-fluoropropane", "CC(C)F", 67.0, "halide"),
    ("difluoromethane", "FCF", 36.9, "halide"), ("chloromethane", "CCl", 42.0, "halide"),
    ("2-chloropropane", "CC(C)Cl", 77.0, "halide"), ("bromomethane", "CBr", 46.6, "halide"),
    ("2-bromopropane", "CC(C)Br", 80.9, "halide"), ("iodomethane", "CI", 54.6, "halide"),
    ("2-iodopropane", "CC(C)I", 90.5, "halide"),
    ("cyclohexane", "C1CCCCC1", 102.0, "ring"), ("cyclohexanol", "OC1CCCCC1", 109.6, "ring"),
    ("tetrahydropyran", "C1CCOCC1", 91.1, "ring"), ("adamantane", "C1C2CC3CC1CC(C2)C3", 147.0, "ring"),
    ("bicyclohexyl", "C1CCC(CC1)C1CCCCC1", 192.5, "ring"),
    ("benzene", "c1ccccc1", 80.3, "aromatic"), ("naphthalene", "c1ccc2ccccc2c1", 122.9, "aromatic"),
    ("toluene", "Cc1ccccc1", 98.9, "aromatic"), ("hexylbenzene", "CCCCCCc1ccccc1", 183.8, "aromatic"),
]


def zhao_volumes() -> None:
    """The same question on 46 molecules from a second transcription of Bondi's volumes, by kind of molecule."""
    errors: dict[str, dict[str, list[float]]] = {}
    for _name, smiles, reference, kind in ZHAO_CASES:
        mol = _conformer(smiles)
        for label, table in TABLES.items():
            error = 100 * (_grid_volume(mol, table) - reference) / reference
            for key in (kind, "all"):
                errors.setdefault(key, {}).setdefault(label, []).append(error)
    for kind, by_table in errors.items():
        for label, values in by_table.items():
            print(f"vdW volume vs Zhao et al. Tables 1 and 3, {kind:8} n={len(values):2d}  {label:15} "
                  f"mean {statistics.mean(values):+5.2f}%  mean abs {statistics.mean(abs(v) for v in values):5.2f}%  "
                  f"max abs {max(abs(v) for v in values):5.1f}%")


if __name__ == "__main__":
    areas()
    steric_series()
    group_volumes()
    zhao_volumes()
