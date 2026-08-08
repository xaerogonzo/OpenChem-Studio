"""What a structure IS, as opposed to what atoms it contains.

The app could already add up a structure's atoms and never say what held
them together. Measured before this existed:

    [Na+].[Cl-]   Formula ClNa, Mass 58.443, "Bond count: 0"

Every number right, and not one of them says *1:1 ionic salt*. "Bond
count: 0" is true of table salt and useless about it.

## Four relationships, deliberately not one

    Bond          an actual graph edge: covalent, dative, aromatic
    Association   component <-> component, e.g. Na+ <-> Cl-. NO edge
    Coordination  a PERCEIVED metal-ligand relationship, which may or may
                  not be represented by explicit graph edges
    Hapticity     one ligand bound through a SET of atoms (eta-5)

`[Na+].[Cl-]` has no RDKit bond and **must never grow a fake one**. An
`Association` therefore carries no number: it is qualitative, evidenced by
opposite formal charges, and never acquires a length. A distance between
two ions is a CONTACT measurement, needs a real 3D structure, and belongs
to whatever reports contacts -- not here. That discipline is what keeps
this coherent when crystals arrive, where the same pair has many
distances and no single bond at all.

## Classification carries evidence, and refuses when it cannot tell

    [Na+].[Cl-]              ionic salt, confident
    [Na+].[Cl-].[K+].[Br-]   AMBIGUOUS -- NaCl+KBr, or NaBr+KCl, or a
                             mixture, and nothing in the graph decides
    CCO.c1ccccc1             disconnected NEUTRAL components

Three outcomes rather than two, because "ambiguous" and "mixture" are
different statements. A disconnected graph is not one substance merely
because its charges happen to cancel.

## Classification is not naming

This module says what KIND of thing a structure is. What it is CALLED
comes from the naming engine, independently -- so a bizarre organometallic
the namer cannot name is still classified rather than collapsing to
"unknown".
"""

from __future__ import annotations

import itertools
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from openchem.chem.organometallic_adapter import Metallocene, metallocene
from openchem.domain.report import Basis, Detail, Fact, FactCategory, ReportResult

#: Elements treated as a metal centre for coordination purposes. Broad on
#: purpose: the question here is "does this look like a coordination
#: compound", and answering it for an unusual metal is better than
#: refusing because the element is rare.
_METALS = frozenset(
    "Li Be Na Mg Al K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Rb Sr Y Zr Nb Mo Tc Ru Rh "
    "Pd Ag Cd In Sn Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re "
    "Os Ir Pt Au Hg Tl Pb Bi Fr Ra Ac Th Pa U Np Pu".split()
)


class SubstanceKind(Enum):
    """What kind of thing a structure represents."""

    MOLECULE = "molecule"
    IONIC_SALT = "ionic salt"
    COORDINATION_COMPOUND = "coordination compound"
    ORGANOMETALLIC = "organometallic"
    ION = "ion"
    MIXTURE = "mixture"
    #: Charged components that do not say which ions belong together.
    #: A refusal, and the reason is carried with it.
    AMBIGUOUS_IONIC = "ambiguous ionic components"

    @property
    def label(self) -> str:
        return self.value.capitalize()


@dataclass(frozen=True)
class Component:
    """One connected piece of the structure."""

    atom_indices: tuple[int, ...]
    formula: str
    charge: int
    #: How many identical copies of this component the structure holds.
    count: int = 1

    @property
    def label(self) -> str:
        """ASCII, e.g. "Na+" and "Cl-".

        **Not a typographic minus.** These strings reach `Fact` values,
        exports, logs and Windows console streams, where cp1252 raises on
        U+2212 -- the same trap `test_valence_labels_stay_ascii` and
        `test_every_line_is_ascii` already guard elsewhere. The prettier
        forms are a rendering concern; see `pretty_label`.
        """
        if self.charge == 0:
            return self.formula
        magnitude = "" if abs(self.charge) == 1 else str(abs(self.charge))
        return f"{self.formula}{magnitude}{'+' if self.charge > 0 else '-'}"

    @property
    def pretty_label(self) -> str:
        """The typeset form, for a UI that is not writing to a stream."""
        return self.label.replace("-", "−")


@dataclass(frozen=True)
class Association:
    """A perceived relationship BETWEEN components. Never a bond.

    Carries no number, and must not grow one. See the module docstring:
    a distance between two ions is a contact measurement that needs 3D
    coordinates, and calling it a bond length would be wrong even then.
    """

    left: str
    right: str
    kind: str = "ionic"
    evidence: str = ""

    def describe(self) -> str:
        """ASCII, e.g. "Na+ <-> Cl-". See `Component.label` for why."""
        return f"{self.left} <-> {self.right}"

    def pretty_describe(self) -> str:
        """The typeset form, for the UI only."""
        return f"{self.left} ↔ {self.right}".replace("-", "−").replace("<−>", "↔")


@dataclass(frozen=True)
class Ligand:
    """One ligand, and how it is attached."""

    atom_indices: tuple[int, ...]
    name: str
    #: eta-n where the ligand binds through several atoms at once; None
    #: for a ligand attached through a single donor.
    hapticity: int | None = None

    @property
    def label(self) -> str:
        """ASCII, e.g. "eta5-Cp". See `Component.label` for why."""
        return f"eta{self.hapticity}-{self.name}" if self.hapticity else self.name

    @property
    def pretty_label(self) -> str:
        """The typeset form, e.g. "η⁵-Cp", for the UI only."""
        if not self.hapticity:
            return self.name
        return f"η{_SUPERSCRIPT.get(self.hapticity, self.hapticity)}-{self.name}"


_SUPERSCRIPT = {1: "¹", 2: "²", 3: "³", 4: "⁴",
                5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸"}


_SIN_60 = math.sqrt(3) / 2

#: The reference polyhedra, as unit vectors from the metal to each donor.
#:
#: **Vectors rather than a list of "ideal angles", because the angle set
#: is DERIVED from them** -- writing 90/180 by hand for an octahedron is
#: an invitation to get the multiplicities wrong (it is twelve 90s and
#: three 180s, not "some 90s and some 180s"), and a wrong multiset would
#: still score plausibly.
#:
#: Square pyramidal is here even though the plan named four geometries:
#: it is the alternative to trigonal bipyramidal at five donors, and
#: without it every square-pyramidal complex would either be called
#: irregular or, worse, matched to the only five-donor reference present.
#: Linear and trigonal planar are here because reporting "irregular" for
#: a linear Ag(I) complex would read as a failure of the classifier
#: rather than as a description of the structure.
_REFERENCE_GEOMETRIES: dict[str, tuple[tuple[float, float, float], ...]] = {
    "linear": ((1, 0, 0), (-1, 0, 0)),
    "trigonal planar": ((1, 0, 0), (-0.5, _SIN_60, 0), (-0.5, -_SIN_60, 0)),
    "tetrahedral": ((1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)),
    "square planar": ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)),
    "trigonal bipyramidal": (
        (0, 0, 1), (0, 0, -1), (1, 0, 0), (-0.5, _SIN_60, 0), (-0.5, -_SIN_60, 0),
    ),
    "square pyramidal": ((0, 0, 1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)),
    "octahedral": ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)),
}

#: How close the measured angles must be to a reference, as the RMS
#: deviation in degrees over the WHOLE sorted angle list.
#:
#: **Both bounds were measured, and they leave a narrow window.**
#:
#:   lower  a tris-chelate octahedron with en/bipy bite angles (78 deg)
#:          scores 7.58, and [Co(en)3]3+ is octahedral by any account, so
#:          anything below ~7.6 would refuse the textbook case
#:   upper  the closest two references are trigonal bipyramidal and square
#:          pyramidal at 23.24 deg apart, so a tolerance at or above 11.62
#:          could match both and the answer would depend on dict order
#:
#: 10.0 sits inside [7.6, 11.6) with margin at each end. It accepts bite
#: angles down to about 74 deg; a tris-acetate complex (65 deg, RMSD
#: 15.75) comes out irregular WITH its closest reference named, which is
#: the honest description of a genuinely squashed octahedron.
GEOMETRY_MATCH_TOLERANCE_DEGREES = 10.0

#: Two donors closer together than this are not two directions. Real
#: bidentate ligands reach about 60 deg (acetate, nitrate) and side-on
#: eta-2 binding about 40; anything far below that means the same
#: position modelled twice. Measured on the disordered lithium site of
#: COD 1511792, whose two modelled nitrogen positions subtend 14 deg --
#: without this guard it scores as a five-coordinate complex.
MIN_DISTINCT_DONOR_ANGLE_DEGREES = 30.0

#: Reported when the angles match no reference within tolerance. Not a
#: failure: it is a statement about the structure, and it travels with
#: the closest reference and the deviation so the reader can judge.
IRREGULAR = "irregular"


def _angle_multiset(vectors: Sequence[tuple[float, float, float]]) -> list[float]:
    """Every pairwise angle, in degrees, sorted ascending.

    Sorted because the classification must not depend on which donor is
    numbered first, and ascending order is what makes two angle sets
    comparable term by term -- see `_rmsd_degrees`.
    """
    units = []
    for vector in vectors:
        norm = math.sqrt(sum(component * component for component in vector))
        if norm <= 0:
            continue
        units.append(tuple(component / norm for component in vector))
    angles = []
    for first, second in itertools.combinations(units, 2):
        dot = sum(a * b for a, b in zip(first, second))
        angles.append(math.degrees(math.acos(max(-1.0, min(1.0, dot)))))
    return sorted(angles)


def _rmsd_degrees(measured: Sequence[float], ideal: Sequence[float]) -> float:
    """RMS deviation between two sorted angle lists of the same length.

    **Pairing the two sorted lists term by term is the optimal pairing**,
    not merely a convenient one: for a squared-error cost on the real
    line the monotone coupling minimises the total. Checked rather than
    cited -- brute force over every permutation beat sorted order in 0 of
    2000 random cases.
    """
    return math.sqrt(
        sum((a - b) ** 2 for a, b in zip(measured, ideal)) / len(ideal)
    )


@dataclass(frozen=True)
class CoordinationGeometry:
    """What the donor angles say the shape is, and how strongly.

    `name` is a reference geometry, `IRREGULAR`, or None when no
    comparison was possible at all -- and the three are different
    statements. None always carries a `note` saying which case it was.
    """

    name: str | None
    #: The nearest reference whatever the tolerance, so "irregular" can
    #: still say what it is nearest to. None when no reference exists at
    #: this donor count.
    closest_reference: str | None
    rmsd_degrees: float | None
    #: Why there is no name. None when there is one.
    note: str | None = None
    #: Every donor-metal-donor angle, sorted. Kept so the report can show
    #: the spread rather than only a verdict.
    angles: tuple[float, ...] = ()

    @property
    def summary(self) -> str:
        if self.name and self.name != IRREGULAR:
            return f"{self.name} (RMSD {self.rmsd_degrees:.1f}° from ideal)"
        if self.name == IRREGULAR:
            return (
                f"irregular — closest to {self.closest_reference}, "
                f"RMSD {self.rmsd_degrees:.1f}°"
            )
        return self.note or "not determined"


def classify_coordination_geometry(
    metal_position: tuple[float, float, float],
    donor_positions: Sequence[tuple[float, float, float]],
) -> CoordinationGeometry:
    """Name the coordination polyhedron from real angles.

    **Pure geometry, deliberately.** It takes coordinates rather than an
    RDKit molecule so the same criteria can serve a crystallographic site,
    where the donors come from symmetry images and there is no molecule to
    hand at all.

    **The donor count never decides on its own.** Six things attached in a
    bizarre arrangement can produce several 90° angles without being
    octahedral, so the comparison is over the whole angle distribution.
    """
    vectors = [
        tuple(d[i] - metal_position[i] for i in range(3)) for d in donor_positions
    ]
    if len(vectors) < 2:
        return CoordinationGeometry(
            name=None, closest_reference=None, rmsd_degrees=None,
            note=f"{len(vectors)} donor atom(s) — an angle needs two",
        )
    angles = _angle_multiset(vectors)
    if len(angles) != len(vectors) * (len(vectors) - 1) // 2:
        return CoordinationGeometry(
            name=None, closest_reference=None, rmsd_degrees=None,
            note="a donor atom sits on the metal — no direction to measure",
        )
    if angles[0] < MIN_DISTINCT_DONOR_ANGLE_DEGREES:
        return CoordinationGeometry(
            name=None, closest_reference=None, rmsd_degrees=None,
            note=(
                f"two donor atoms are only {angles[0]:.0f}° apart, which is "
                "one position modelled twice rather than two donors"
            ),
            angles=tuple(angles),
        )
    candidates = [
        (_rmsd_degrees(angles, _angle_multiset(vs)), name)
        for name, vs in _REFERENCE_GEOMETRIES.items()
        if len(vs) == len(vectors)
    ]
    if not candidates:
        return CoordinationGeometry(
            name=None, closest_reference=None, rmsd_degrees=None,
            note=f"no reference polyhedron for {len(vectors)} donor atoms",
            angles=tuple(angles),
        )
    rmsd, closest = min(candidates)
    return CoordinationGeometry(
        name=closest if rmsd <= GEOMETRY_MATCH_TOLERANCE_DEGREES else IRREGULAR,
        closest_reference=closest,
        rmsd_degrees=rmsd,
        angles=tuple(angles),
    )


@dataclass(frozen=True)
class Coordination:
    """A metal centre and what is attached to it.

    **Two counts, both named.** "Coordination number 10" for ferrocene
    invites the reader to supply the wrong convention -- it is the ten Cp
    carbons, not ten ligands -- so the ligand count and the donor-atom
    count are reported separately and never merged into one number.

    `geometry` is None unless a real 3D conformer was available. Six
    things attached does not make something octahedral; that is a claim
    about angles, and a flat drawing has none. When there ARE coordinates
    it carries the measurement rather than a bare word -- see
    `CoordinationGeometry`, which can also say "irregular" and name what
    the structure is nearest to.
    """

    metal_symbol: str
    metal_index: int | None
    ligands: tuple[Ligand, ...]
    oxidation_state: int | None = None
    geometry: CoordinationGeometry | None = None

    @property
    def ligand_count(self) -> int:
        return len(self.ligands)

    @property
    def donor_atom_count(self) -> int:
        return sum(len(ligand.atom_indices) if ligand.hapticity else 1 for ligand in self.ligands)


@dataclass(frozen=True)
class Substance:
    """The perceived identity of a structure -- never its name."""

    kind: SubstanceKind
    components: tuple[Component, ...]
    total_charge: int
    associations: tuple[Association, ...] = ()
    coordination: Coordination | None = None
    evidence: tuple[str, ...] = ()
    #: Why this could not be classified further. Empty unless the kind is
    #: a refusal -- and then it is the useful half of the answer.
    reason: str = ""
    #: The accepted name IF the perception happened to carry one (a pinned
    #: metallocene). **Not identity** -- naming is a separate engine, and
    #: this being empty says nothing about the classification.
    perceived_name: str = ""

    @property
    def is_single_substance(self) -> bool:
        return self.kind not in (SubstanceKind.MIXTURE, SubstanceKind.AMBIGUOUS_IONIC)

    @property
    def formula_unit(self) -> str:
        """The components as a formula unit, e.g. "Na+ · Cl−"."""
        parts = []
        for component in self.components:
            prefix = f"{component.count} × " if component.count > 1 else ""
            parts.append(f"{prefix}{component.label}")
        return " · ".join(parts)


def _component_charge(mol: Chem.Mol, indices) -> int:
    return sum(mol.GetAtomWithIdx(i).GetFormalCharge() for i in indices)


def _fragment_formula(mol: Chem.Mol, indices) -> str:
    """The formula of one fragment, via a real sub-molecule.

    Built with `PathToSubmol`-style extraction rather than counted by hand
    so implicit hydrogens are included the same way RDKit counts them
    everywhere else in the app.
    """
    editable = Chem.RWMol(mol)
    for index in sorted(set(range(mol.GetNumAtoms())) - set(indices), reverse=True):
        editable.RemoveAtom(index)
    fragment = editable.GetMol()
    try:
        Chem.SanitizeMol(fragment)
    except (ValueError, RuntimeError):
        pass
    formula = rdMolDescriptors.CalcMolFormula(fragment)
    # **CalcMolFormula already carries the charge** -- "Na+", "Ca+2",
    # "C5H5-". `Component` holds the charge separately and spells it
    # itself, so leaving it here produced "Na++" and "Ca+22+". Composition
    # and charge are different facts and are stored as such.
    return re.sub(r"[+-]\d*$", "", formula)


def _components(mol: Chem.Mol) -> tuple[Component, ...]:
    """The connected pieces, with identical ones collapsed to a count.

    Collapsing matters for the formula unit: CaCl2 drawn as three
    fragments is one Ca2+ and two Cl-, not three unrelated things.
    """
    seen: dict[tuple[str, int], list[tuple[int, ...]]] = {}
    for indices in Chem.GetMolFrags(mol):
        formula = _fragment_formula(mol, indices)
        charge = _component_charge(mol, indices)
        seen.setdefault((formula, charge), []).append(tuple(indices))
    return tuple(
        Component(
            atom_indices=tuple(sorted(index for group in groups for index in group)),
            formula=formula,
            charge=charge,
            count=len(groups),
        )
        for (formula, charge), groups in seen.items()
    )


def _metal_atoms(mol: Chem.Mol) -> list[int]:
    return [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() in _METALS]


def _coordination_from_metallocene(found: Metallocene) -> Coordination:
    """Turn the vendored perception into this module's vocabulary."""
    ligands = tuple(
        Ligand(atom_indices=ring.atom_indices, name=ring.label, hapticity=len(ring.atom_indices))
        for ring in found.rings
    )
    # Two Cp- rings on a neutral sandwich means a 2+ metal. Stated only
    # for the case the perception actually establishes; anything else
    # leaves it None rather than guessing.
    oxidation = 2 if len(found.rings) == 2 else None
    return Coordination(
        metal_symbol=found.metal_symbol,
        metal_index=found.metal_index,
        ligands=ligands,
        oxidation_state=oxidation,
    )


def _classify_ionic(components: tuple[Component, ...]) -> tuple[SubstanceKind, tuple[str, ...], str]:
    """Ionic salt, or a refusal that says why.

    **The refusal is the useful part.** `[Na+].[Cl-].[K+].[Br-]` could be
    NaCl + KBr, or NaBr + KCl, or a mixture of four ions, and the graph
    does not encode which -- so it says that rather than picking one.
    """
    cations = [c for c in components if c.charge > 0]
    anions = [c for c in components if c.charge < 0]
    total = sum(c.charge * c.count for c in components)

    if len(cations) >= 2 and len(anions) >= 2:
        return (
            SubstanceKind.AMBIGUOUS_IONIC,
            (
                f"{len(cations)} distinct cations, {len(anions)} distinct anions",
                f"total charge {total:+d}",
            ),
            "The structure contains several cation/anion combinations and does "
            "not encode which ions belong to the same formula unit.",
        )

    evidence = [
        f"{len(cations) + len(anions)} charged components",
        f"total charge {total:+d}",
    ]
    if cations:
        evidence.append(f"cation {cations[0].label}")
    if anions:
        evidence.append(f"anion {anions[0].label}")
    if cations and anions:
        ratio = ":".join(str(c.count) for c in (*cations, *anions))
        evidence.append(f"stoichiometry {ratio}")
    return SubstanceKind.IONIC_SALT, tuple(evidence), ""


def _associations(components: tuple[Component, ...]) -> tuple[Association, ...]:
    """Every cation/anion pair, as a qualitative relationship."""
    cations = [c for c in components if c.charge > 0]
    anions = [c for c in components if c.charge < 0]
    return tuple(
        Association(
            left=cation.label,
            right=anion.label,
            kind="ionic",
            evidence="opposite formal charges, no bond in the structure",
        )
        for cation in cations
        for anion in anions
    )


def perceive(mol: Chem.Mol) -> Substance:
    """What this structure represents, with the evidence for the call."""
    if mol is None or mol.GetNumAtoms() == 0:
        return Substance(SubstanceKind.MOLECULE, (), 0, reason="empty structure")

    components = _components(mol)
    total_charge = sum(c.charge * c.count for c in components)

    # Organometallic FIRST. Ferrocene's ionic form is three charged
    # fragments whose charges cancel, so an ionic rule reached first would
    # confidently call it a salt.
    found = metallocene(mol)
    if found is not None:
        coordination = _coordination_from_metallocene(found)
        return Substance(
            kind=SubstanceKind.ORGANOMETALLIC,
            components=components,
            total_charge=total_charge,
            coordination=coordination,
            evidence=(
                f"metal centre {found.metal_symbol}",
                f"{len(found.rings)} cyclopentadienyl rings",
                "sandwich structure recognised by the nomenclature engine",
            ),
            perceived_name=found.retained_name,
        )

    metals = _metal_atoms(mol)
    charged = [c for c in components if c.charge != 0]

    if len(components) == 1:
        # A metal with nothing attached is an ION, not a complex. Found by
        # walking the adjacent case the plan called for: [Na+] came back
        # as "Coordination compound" with zero ligands, which is a
        # category error rather than a rounding one.
        if metals and mol.GetAtomWithIdx(metals[0]).GetDegree() == 0:
            return Substance(
                kind=SubstanceKind.ION if total_charge else SubstanceKind.MOLECULE,
                components=components,
                total_charge=total_charge,
                evidence=(
                    "one atom, nothing bonded to it",
                    f"charge {total_charge:+d}",
                ),
            )
        if metals:
            return Substance(
                kind=SubstanceKind.COORDINATION_COMPOUND,
                components=components,
                total_charge=total_charge,
                coordination=_coordination_from_connectivity(mol, metals[0]),
                evidence=(
                    f"metal centre {mol.GetAtomWithIdx(metals[0]).GetSymbol()}",
                    "single connected component",
                ),
            )
        return Substance(
            kind=SubstanceKind.ION if total_charge else SubstanceKind.MOLECULE,
            components=components,
            total_charge=total_charge,
            evidence=("one connected component", f"total charge {total_charge:+d}"),
        )

    if not charged:
        return Substance(
            kind=SubstanceKind.MIXTURE,
            components=components,
            total_charge=total_charge,
            evidence=(
                f"{sum(c.count for c in components)} disconnected components",
                "no charged components",
            ),
            reason="Disconnected neutral components. Nothing in the structure "
            "says these are one substance rather than several.",
        )

    kind, evidence, reason = _classify_ionic(components)
    return Substance(
        kind=kind,
        components=components,
        total_charge=total_charge,
        associations=_associations(components) if kind is SubstanceKind.IONIC_SALT else (),
        evidence=evidence,
        reason=reason,
    )


def _coordination_from_connectivity(mol: Chem.Mol, metal_index: int) -> Coordination:
    """Ligands read off the metal's actual bonds.

    Each neighbour is one donor atom of one ligand. The geometry is
    measured when -- and only when -- a real 3D conformer is there to
    measure; six neighbours is not octahedral until something has
    measured an angle.
    """
    donor_indices = []
    ligands = []
    for neighbour in mol.GetAtomWithIdx(metal_index).GetNeighbors():
        donor_indices.append(neighbour.GetIdx())
        ligands.append(
            Ligand(atom_indices=(neighbour.GetIdx(),), name=neighbour.GetSymbol())
        )
    return Coordination(
        metal_symbol=mol.GetAtomWithIdx(metal_index).GetSymbol(),
        metal_index=metal_index,
        ligands=tuple(ligands),
        geometry=_geometry_from_conformer(mol, metal_index, donor_indices),
    )


def _geometry_from_conformer(
    mol: Chem.Mol, metal_index: int, donor_indices: Sequence[int]
) -> CoordinationGeometry | None:
    """The polyhedron, or None when there are no 3D coordinates at all.

    **`GetNumConformers() > 0` is not the check.** A molblock written by
    the 2D editor always parses into exactly one conformer with flat
    z-coordinates, so that test is true for every drawn structure and
    would report a geometry for a flat drawing. `Conformer.Is3D()` is the
    one that distinguishes them -- the same rule the shape descriptors
    use, and the reason a 2D structure still gets no geometry at all
    rather than a confidently wrong one.
    """
    if mol.GetNumConformers() == 0:
        return None
    conformer = mol.GetConformer()
    if not conformer.Is3D():
        return None
    position = conformer.GetAtomPosition(metal_index)
    donors = []
    for index in donor_indices:
        donor = conformer.GetAtomPosition(index)
        donors.append((donor.x, donor.y, donor.z))
    return classify_coordination_geometry((position.x, position.y, position.z), donors)


# ---------------------------------------------------------------------------
# The calculator
# ---------------------------------------------------------------------------


def compute_substance_analysis(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """The "Substance & Bonding" calculator.

    **A refusal is a normal result, not `CacheState.FAILED`.** "This
    structure does not encode which ions pair up" is a fact about the
    structure, and a permanent red error row would misfile it as something
    broken -- the same call `oxidation_states` makes for magnetite.
    """
    from openchem.domain.common import Provenance

    substance = perceive(mol)
    facts: list[Fact] = [
        Fact(
            category=FactCategory.IDENTITY,
            label="Substance classification",
            value=substance.kind.value,
            display_value=substance.kind.label,
            source="Substance",
            basis=Basis.HEURISTIC,
            evidence=substance.evidence,
            # The reason travels as a LIMITATION rather than as the value,
            # so a refusal is still a classification with a caveat instead
            # of a blank where an answer should be.
            limitations=(substance.reason,) if substance.reason else (),
        )
    ]

    if substance.components:
        facts.append(
            Fact(
                category=FactCategory.IDENTITY,
                label="Formula",
                value=rdMolDescriptors.CalcMolFormula(mol),
                display_value=rdMolDescriptors.CalcMolFormula(mol),
                source="Substance",
                basis=Basis.DETERMINISTIC,
                # Distinct from the formula unit below, and the pair is
                # the point: ClNa is what the atoms add up to, Na+ . Cl-
                # is what the substance is made of.
                evidence=("what the atoms add up to, ignoring how they associate",),
            )
        )
        facts.append(
            Fact(
                category=FactCategory.IDENTITY,
                label="Formula unit",
                value=substance.formula_unit,
                display_value=substance.formula_unit,
                source="Substance",
                basis=Basis.DETERMINISTIC,
                # There is no NaCl *molecule*. Saying which of the two this
                # is costs one line and stops the number being read as the
                # other one.
                evidence=(
                    "a formula unit is the smallest whole-number ratio of ions, "
                    "not a molecule"
                    if substance.kind is SubstanceKind.IONIC_SALT
                    else "one connected molecular species",
                ),
            )
        )
        facts.append(
            Fact(
                category=FactCategory.IDENTITY,
                label="Components",
                value=len(substance.components),
                display_value=str(len(substance.components)),
                source="Substance",
                basis=Basis.DETERMINISTIC,
            )
        )
        if (parameters or {}).get("list_components"):
            # Each one highlightable in the drawing, which the single
            # "Components: 3" row cannot be. Worth having on a mixture and
            # noise on a salt, which is why it is a choice rather than a
            # default.
            for position, component in enumerate(substance.components, start=1):
                facts.append(
                    Fact(
                        category=FactCategory.IDENTITY,
                        label=f"Component {position}",
                        value=component.label,
                        display_value=(
                            component.label
                            if component.count == 1
                            else f"{component.count} x {component.label}"
                        ),
                        source="Substance",
                        basis=Basis.DETERMINISTIC,
                        highlight=component.atom_indices,
                    )
                )

        facts.append(
            Fact(
                category=FactCategory.ELECTRONIC,
                label="Total charge",
                value=substance.total_charge,
                display_value=f"{substance.total_charge:+d}" if substance.total_charge else "0",
                source="Substance",
                basis=Basis.DETERMINISTIC,
            )
        )

    if substance.kind is SubstanceKind.IONIC_SALT:
        facts.extend(_lattice_energy_facts(substance))

    for association in substance.associations:
        facts.append(
            Fact(
                category=FactCategory.STRUCTURE,
                label="Ionic association",
                value=association.describe(),
                display_value=association.describe(),
                source="Substance",
                basis=Basis.HEURISTIC,
                evidence=(association.evidence,) if association.evidence else (),
                # **Never a length.** An association is not a graph edge,
                # and a distance between two ions needs a real 3D structure
                # and is a CONTACT measurement even then.
                limitations=(
                    "This is a perceived relationship between components, not a bond. "
                    "The structure contains no bond between them and must not grow one.",
                ),
            )
        )

    coordination = substance.coordination
    if coordination is not None:
        facts.append(
            Fact(
                category=FactCategory.STRUCTURE,
                label="Metal centre",
                value=coordination.metal_symbol,
                display_value=(
                    f"{coordination.metal_symbol}({_roman(coordination.oxidation_state)})"
                    if coordination.oxidation_state is not None
                    else coordination.metal_symbol
                ),
                source="Substance",
                basis=Basis.HEURISTIC,
                highlight=(coordination.metal_index,)
                if coordination.metal_index is not None
                else (),
            )
        )
        if coordination.ligands:
            facts.append(
                Fact(
                    category=FactCategory.STRUCTURE,
                    label="Ligands",
                    value=[ligand.label for ligand in coordination.ligands],
                    display_value=_ligand_summary(coordination),
                    source="Substance",
                    basis=Basis.HEURISTIC,
                    highlight=tuple(
                        index
                        for ligand in coordination.ligands
                        for index in ligand.atom_indices
                    ),
                )
            )
        # **Two counts, both named.** "Coordination number 10" for
        # ferrocene invites the reader to supply the wrong convention -- it
        # is the ten Cp carbons, not ten ligands -- so these are never
        # merged into one figure.
        facts.append(
            Fact(
                category=FactCategory.STRUCTURE,
                label="Ligand coordination",
                value=coordination.ligand_count,
                display_value=str(coordination.ligand_count),
                source="Substance",
                basis=Basis.HEURISTIC,
                evidence=("how many separate ligands are bound",),
            )
        )
        facts.append(
            Fact(
                category=FactCategory.STRUCTURE,
                label="Donor-atom count",
                value=coordination.donor_atom_count,
                display_value=str(coordination.donor_atom_count),
                source="Substance",
                basis=Basis.HEURISTIC,
                evidence=("how many ligand atoms are bound to the metal",),
            )
        )
        geometry = coordination.geometry
        if geometry is None:
            # **Six things attached is not octahedral.** That is a claim
            # about angles, and a flat drawing has none -- the same rule
            # the bond report applies to 2D bond lengths.
            facts.append(
                Fact(
                    category=FactCategory.GEOMETRY,
                    label="Coordination geometry",
                    value=None,
                    display_value="Not determined -- needs a 3D structure",
                    source="Substance",
                    basis=Basis.DETERMINISTIC,
                    limitations=(
                        "A geometry is a statement about angles. The number of "
                        "ligands does not imply one, so none is reported from a "
                        "structure without 3D coordinates.",
                    ),
                )
            )
        else:
            limitations = []
            if geometry.name is None:
                limitations.append(
                    "The donor atoms were measured, but no polyhedron could be "
                    f"named: {geometry.note}."
                )
            elif geometry.name == IRREGULAR:
                limitations.append(
                    "No reference polyhedron fits within "
                    f"{GEOMETRY_MATCH_TOLERANCE_DEGREES:.0f}° RMSD. The nearest "
                    f"is {geometry.closest_reference}; the deviation is reported "
                    "so the distortion can be judged rather than rounded away."
                )
            facts.append(
                Fact(
                    category=FactCategory.GEOMETRY,
                    label="Coordination geometry",
                    value=geometry.name,
                    display_value=geometry.summary,
                    source="Substance",
                    # HEURISTIC even though the angles below are not: the
                    # ANGLES are trigonometry, but turning them into a name
                    # takes a chosen tolerance, and a structure 0.1 deg the
                    # wrong side of it gets a different word. The vocabulary
                    # has two members and this is the honest one.
                    basis=Basis.HEURISTIC,
                    evidence=(
                        "RMS deviation over every donor-metal-donor angle, "
                        "against the reference polyhedron with the same donor "
                        "count",
                    ),
                    limitations=tuple(limitations),
                )
            )
            if geometry.angles:
                facts.append(
                    Fact(
                        category=FactCategory.GEOMETRY,
                        label="Donor-metal-donor angles",
                        value=[round(angle, 1) for angle in geometry.angles],
                        display_value=", ".join(
                            f"{angle:.1f}°" for angle in geometry.angles
                        ),
                        source="Substance",
                        # DETERMINISTIC, unlike the name above: an angle
                        # between three known positions involves no
                        # threshold and no judgement.
                        basis=Basis.DETERMINISTIC,
                        # The spread is what makes "irregular" a measurement
                        # rather than a shrug, so it is shown, not summarised.
                        detail=Detail.ADVANCED,
                    )
                )

    return ReportResult(
        molecule_uuid=molecule_uuid,
        report_id="substance_analysis",
        name="Substance & Bonding",
        category="structure",
        facts=tuple(facts),
        limitations=(
            "Perception describes the structure AS DRAWN. It never alters it: an "
            "ionic association is reported without adding a bond, and a dative "
            "interpretation is offered as a fix rather than applied.",
        ),
        provenance=Provenance(
            created_by="core",
            method="perception",
            parameters={"summary": _summary_line(substance)},
        ),
    )


_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII"}


def _roman(state: int) -> str:
    if state < 0:
        return f"-{_ROMAN.get(-state, -state)}"
    return _ROMAN.get(state, str(state))


def _ligand_summary(coordination: Coordination) -> str:
    """"2 x eta5-Cp" rather than the same label listed twice."""
    counts: dict[str, int] = {}
    for ligand in coordination.ligands:
        counts[ligand.label] = counts.get(ligand.label, 0) + 1
    return ", ".join(
        label if count == 1 else f"{count} x {label}" for label, count in counts.items()
    )


def _summary_line(substance: Substance) -> str:
    if substance.formula_unit:
        return f"{substance.kind.label}: {substance.formula_unit}"
    return substance.kind.label


def _lattice_energy_facts(substance: Substance) -> list[Fact]:
    """A Kapustinskii estimate, for a salt of two monatomic ions.

    **An ESTIMATE, and the fact says so in the value itself** -- not in a
    footnote somebody has to open. Validated against 36 experimental
    Born-Haber values (Kaya et al. 2022, Table 3): every one inside 7.3%,
    and the error is systematic rather than random, which is what makes it
    usable at all.

    Silent rather than approximate when it cannot be done. A salt of
    polyatomic ions needs thermochemical radii, which are a different
    measurement from a different source; producing a number anyway would
    be the plausible-but-meaningless failure this project keeps refusing.
    """
    from openchem.chem.lattice_energy import kapustinskii

    cations = [c for c in substance.components if c.charge > 0]
    anions = [c for c in substance.components if c.charge < 0]
    if len(cations) != 1 or len(anions) != 1:
        return []
    # Monatomic only: a formula like "Na" with nothing after it. `formula`
    # has had its charge stripped, so this is purely the composition.
    if not (re.fullmatch(r"[A-Z][a-z]?", cations[0].formula) and
            re.fullmatch(r"[A-Z][a-z]?", anions[0].formula)):
        return []

    result = kapustinskii(
        cations[0].formula, cations[0].charge, anions[0].formula, anions[0].charge
    )
    if result.refused:
        return []

    # 1:1 alkali halides come out 4-7% low; 2:2 oxides and sulfides land
    # inside 2%. Naming which regime this is beats one averaged caveat.
    singly_charged = abs(cations[0].charge) == 1 and abs(anions[0].charge) == 1
    accuracy = (
        "Measured against experiment for salts of this type: 4-7% BELOW the "
        "Born-Haber value, consistently."
        if singly_charged
        else "Measured against experiment for salts of this type: within 2%."
    )
    return [
        Fact(
            category=FactCategory.ELECTRONIC,
            label="Lattice energy (estimated)",
            value=round(result.value),
            display_value=f"~{result.value:.0f}",
            units="kJ/mol",
            source="Kapustinskii",
            basis=Basis.HEURISTIC,
            evidence=(
                f"Kapustinskii from Shannon six-coordinate radii: "
                f"{result.cation} {result.cation_radius:.2f} A, "
                f"{result.anion} {result.anion_radius:.2f} A, "
                f"{result.ion_count} ions per formula unit",
                accuracy,
            ),
            limitations=(
                "An estimate from ionic radii alone, not a measurement. It knows "
                "nothing about the actual crystal structure -- the equation works "
                "without one because the Madelung constant per ion barely varies "
                "between the common structure types.",
                "It omits the dispersion and zero-point terms, which is why it "
                "runs low, and it assumes the bonding is fully ionic. Any covalent "
                "character makes it worse in a direction it cannot report.",
            ),
            detail=Detail.ADVANCED,
        )
    ]
