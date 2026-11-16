"""Measured geometries for the small open-shell molecules distance geometry gets wrong (OS3 of docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md).

**WHY.** ETKDG and a force field know nothing about unpaired electrons. Measured: triplet O2 drawn as `[O][O]` came back at 1.316 A and as `O=O` at 1.151 A, against
1.20752 A spectroscopically; NO at 1.424 A against 1.15077. Nothing wrong was published from that (an ORCA optimisation corrects it) but the 3D view and every
geometry-based descriptor of a radical rested on a force-field start. Like the hypervalent templates (`vsepr_geometry`) the geometry is BUILT, not searched: one
deterministic structure, no energy, not optimised, and its note names the source.

**WHAT IS HERE AND WHAT IS NOT.** Eight species, each from a held source:

* the six diatomics O2, NO, OH, SO, S2 and Se2 at the spectroscopic equilibrium distance r_e of Huber and Herzberg 1979 (`huber1979`, ground-state tables, PDF pages 511,
  489, 521, 635, 577 and 595);
* triplet CH2 from the rotation-vibration analysis of Jensen and Bunker 1988 (r(CH) 1.0753 A, HCH 133.931 degrees) and singlet CH2 from Petek et al. 1989 (r_e 1.107 A,
  theta_e 102.4 degrees): the multiplicity decides which (the drawing's, `spin_from_molblock`, carried on the Mol as `SPIN_PROP`; absent means the high-spin default);
* CH3 (planar, 1.079 A, 120 degrees) and NH2 (bent, 1.024 A, 103.4 degrees) AS LISTED BY NIST CCCBDB, which credits Herzberg 1966 (`herzberg1966`). Herzberg's own pages
  were not opened and the bond-length convention (r0, rs, re) is not stated, so these two say 'experimental geometry as listed' and not r_e.

Anything else, a charged species, a substituted radical or a radical with a bigger skeleton, takes the ordinary path as before. Pure RDKit and numpy, no Qt, no state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from rdkit import Chem

from openchem.chem.open_shell import default_multiplicity
from openchem.chem.vsepr_geometry import _VIEW_TILT

#: The Mol property `ChemistryEngine.mol_from_model` sets from the drawing's own stated multiplicity (`open_shell.spin_from_molblock`), because RDKit cannot keep a singlet apart from a triplet.
SPIN_PROP = "_oc_spin_multiplicity"


@dataclass(frozen=True)
class OpenShellEntry:
    """One species, its measured geometry and where it comes from."""

    name: str
    #: Canonical SMILES of the heavy-atom drawing, every way it is commonly drawn.
    smiles: tuple[str, ...]
    #: "diatomic" (a bond along an axis), "planar_xh3" (D3h) or "bent_xh2" (C2v).
    shape: str
    #: Bond length, Angstrom (the X-H or X-Y distance).
    length: float
    #: HXH angle, degrees (bent_xh2 only; ignored by the others, planar_xh3 is 120).
    angle: float
    #: The multiplicity this geometry is of, or None when the molecule has one geometry whatever it is.
    multiplicity: int | None
    source: str
    #: What the numbers are, so none is read as more than it is.
    convention: str


#: How the six diatomics are cited (their pages are in the module docstring).
_HH = "Huber and Herzberg 1979, ground-state r_e"
#: Every species the table builds; an entry is matched by canonical SMILES and, for methylene, by multiplicity.
ENTRIES: tuple[OpenShellEntry, ...] = (
    OpenShellEntry("O2", ("[O][O]", "O=O"), "diatomic", 1.20752, 0.0, None, f"{_HH} (X 3Sigma-g-)", "spectroscopic equilibrium distance r_e"),
    OpenShellEntry("NO", ("[N]=O",), "diatomic", 1.15077, 0.0, None, f"{_HH} (X 2Pi)", "spectroscopic equilibrium distance r_e"),
    OpenShellEntry("OH", ("[OH]",), "diatomic", 0.96966, 0.0, None, f"{_HH} (X 2Pi)", "spectroscopic equilibrium distance r_e"),
    OpenShellEntry("SO", ("O=S",), "diatomic", 1.481087, 0.0, None, f"{_HH} (X 3Sigma-)", "spectroscopic equilibrium distance r_e"),
    OpenShellEntry("S2", ("S=S",), "diatomic", 1.8892, 0.0, None, f"{_HH} (X 3Sigma-g-)", "spectroscopic equilibrium distance r_e"),
    OpenShellEntry("Se2", ("[Se]=[Se]",), "diatomic", 2.1660, 0.0, None, f"{_HH} (X1 3Sigma-g, the lower spin-orbit component)", "spectroscopic equilibrium distance r_e"),
    OpenShellEntry("CH2 (triplet)", ("[CH2]",), "bent_xh2", 1.0753, 133.931, 3, "Jensen and Bunker 1988 (X 3B1)", "equilibrium structure from experimental rotation-vibration data; the angle is 180 degrees less the fitted rho_e 46.0692"),
    OpenShellEntry("CH2 (singlet)", ("[CH2]",), "bent_xh2", 1.107, 102.4, 1, "Petek et al. 1989 (a 1A1)", "equilibrium structure from the rotational constants"),
    OpenShellEntry("CH3", ("[CH3]",), "planar_xh3", 1.079, 120.0, None, "NIST CCCBDB experimental geometry, credited to Herzberg 1966", "as listed; the convention (r0, rs, re) is not stated"),
    OpenShellEntry("NH2", ("[NH2]",), "bent_xh2", 1.024, 103.4, None, "NIST CCCBDB experimental geometry, credited to Herzberg 1966", "as listed; the convention (r0, rs, re) is not stated"),
)

#: At most this many heavy atoms can be in the table, so anything bigger is not even looked up.
_MAX_HEAVY_ATOMS = 2


@dataclass(frozen=True)
class OpenShellGeometry:
    """The built structure: the drawing WITH its hydrogens, one coordinate per atom, and the entry it came from."""

    molecule: Chem.Mol
    coordinates: tuple[tuple[float, float, float], ...]
    entry: OpenShellEntry

    @property
    def note(self) -> str:
        return f"experimental geometry of {self.entry.name} ({self.entry.source}; {self.entry.convention}), not optimised"


def entry_for(mol: Chem.Mol) -> OpenShellEntry | None:
    """The table entry for this drawing, or None (a larger or charged structure, an unlisted species, or the wrong multiplicity for the ones that depend on it)."""
    if mol.GetNumHeavyAtoms() > _MAX_HEAVY_ATOMS or Chem.GetFormalCharge(mol) != 0 or len(Chem.GetMolFrags(mol)) != 1:
        return None
    try:
        key = Chem.MolToSmiles(Chem.RemoveHs(Chem.Mol(mol), sanitize=False))
    except Exception:  # noqa: BLE001 - an unreadable structure has no entry
        return None
    stated = int(mol.GetProp(SPIN_PROP)) if mol.HasProp(SPIN_PROP) else default_multiplicity(mol)
    for entry in ENTRIES:
        if key in entry.smiles and (entry.multiplicity is None or entry.multiplicity == stated):
            return entry
    return None


def _positions(entry: OpenShellEntry, heavy: int, hydrogens: int) -> np.ndarray | None:
    r = entry.length
    if entry.shape == "diatomic":
        if heavy == 2:
            return np.array([[0, 0, -r / 2], [0, 0, r / 2]], dtype=float)
        if heavy == 1 and hydrogens == 1:
            return np.array([[0, 0, 0], [0, 0, r]], dtype=float)
    if entry.shape == "planar_xh3" and heavy == 1 and hydrogens == 3:
        return np.array([[0, 0, 0]] + [[r * math.cos(a), r * math.sin(a), 0.0] for a in (0.0, 2 * math.pi / 3, 4 * math.pi / 3)])
    if entry.shape == "bent_xh2" and heavy == 1 and hydrogens == 2:
        half = math.radians(entry.angle) / 2
        return np.array([[0, 0, 0], [r * math.sin(half), 0.0, r * math.cos(half)], [-r * math.sin(half), 0.0, r * math.cos(half)]])
    return None


def build_open_shell_geometry(mol: Chem.Mol) -> OpenShellGeometry | None:
    """The measured geometry of a listed open-shell species, or None. Coordinates are tilted as the VSEPR templates are, so no species is edge-on to the 3D viewer."""
    entry = entry_for(mol)
    if entry is None:
        return None
    with_hydrogens = Chem.AddHs(Chem.Mol(mol), addCoords=False)
    heavy = sum(1 for a in with_hydrogens.GetAtoms() if a.GetAtomicNum() > 1)
    hydrogens = with_hydrogens.GetNumAtoms() - heavy
    positions = _positions(entry, heavy, hydrogens)
    if positions is None or len(positions) != with_hydrogens.GetNumAtoms():
        return None
    # AddHs appends the hydrogens after the heavy atoms in the order of their parents, which is the order `_positions` lays them out for the single-centre species.
    tilted = positions @ _VIEW_TILT.T
    return OpenShellGeometry(with_hydrogens, tuple((float(x), float(y), float(z)) for x, y, z in tilted), entry)
