"""Vocabulary v2's detector, relation resolution and projections.

**WHAT A FEATURE MEANS IS NOT DECIDED HERE.** That is `feature_vocabulary.py`,
written first; this file operationalises it. Each spec is one or more SMARTS
whose atom-map numbers name the ROLE of the atom they match (map i = role i of
the feature), so an instance's atoms and roles are read off the match rather
than off a hand-kept index list. Unmapped pattern atoms are context -- the R
groups a definition requires but does not own.

**THE STRUCTURE IS READ AS DRAWN.** No normalisation, no tautomer
canonicalisation, no neutralisation: pyridin-2-ol and pyridin-2(1H)-one are
different drawings and get different features, and a carboxylate is detected
anionic because it IS anionic on the page (choosing the pH-relevant form is
upstream's job). The charge state is MEASURED -- the sign of the summed
formal charge over the instance's atoms -- never taken from the pattern.

**EVERY DETECTION IS KEPT.** An ether inside an acetal is still detected; the
declared relation says it is not the primary description of those atoms, and
each projection decides what that means for it (`PROJECTION_POLICY`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from rdkit import Chem

from openchem.chem.feature_vocabulary import (
    FEATURE_BY_ID,
    FEATURE_ORDER,
    PROJECTION_POLICY,
    RELATIONS,
    VOCABULARY_VERSION,
    ChargeState,
    ObjectTreatment,
    Projection,
    RelationKind,
)

# --- reusable SMARTS fragments -----------------------------------------------
# An UPPER-CASE element in SMARTS is ALIPHATIC: `[OX2]` can never match furan's
# `o`, so the `!a` beside some of them states intent rather than doing work
# (a mutation deleting one changed nothing, measured). Where an aromatic atom
# must be admitted -- a pyridone's ring N, a coumarin's ring O -- the pattern
# says `#7` / `#8`, which is element only.
#: A carbon that is not acyl-like: no double bond to O, S or N. The
#: "hydrocarbyl" R of the Gold Book's formulas, aromatic carbons included.
_HC = "[#6;!$([#6]=[O,S,#7]);!$([#6]#[#7])]"
#: Carbon or hydrogen as the R of a carbonyl: the carbonyl carbon has a carbon
#: neighbour or is a CH (formyl). Written as a property OF the carbonyl carbon.
_R_C_OR_H = "$([#6][#6]),$([#6H1]),$([#6H2])"
#: An amide nitrogen: anything but N or O on it (those are hydrazides and
#: hydroxamic acids). The Gold Book's amides entry includes N-acyl and
#: N-sulfonyl amides ("one, two or three acyl groups on a given nitrogen").
_AMIDE_N = "[#7;!$([#7]-[#7]);!$([#7]-[#8])"
#: Amine nitrogen exclusions: no non-carbon neighbour (N, O, S, P ...), and no
#: carbon neighbour that is acyl, thioacyl, imidoyl or a nitrile carbon.
_AMINE_EXCL = "!a;!$([#7]~[!#6;!#1]);!$([#7][#6]=,#[O,S,#7])"


@dataclass(frozen=True)
class FeatureSpec:
    feature_id: str
    #: Alternatives; an instance from any of them is the same feature.
    smarts: tuple[str, ...]
    #: An extra condition SMARTS cannot state, on (mol, role-1 atoms).
    predicate: Callable[[Chem.Mol, dict[int, int]], bool] | None = None


def _carbocyclic_smallest_ring(mol: Chem.Mol, roles: dict[int, int]) -> bool:
    """The hydroxy's carbon's SMALLEST ring is all carbon (phenols, p. 1095)."""
    (oxygen,) = [a for a, r in roles.items() if r == 1]
    carbon = next(n.GetIdx() for n in mol.GetAtomWithIdx(oxygen).GetNeighbors())
    rings = [r for r in mol.GetRingInfo().AtomRings() if carbon in r]
    smallest = min(rings, key=len)
    return all(mol.GetAtomWithIdx(i).GetAtomicNum() == 6 for i in smallest)


def _hetero_smallest_ring(mol: Chem.Mol, roles: dict[int, int]) -> bool:
    return not _carbocyclic_smallest_ring(mol, roles)


def _s(fid: str, *smarts: str, predicate=None) -> FeatureSpec:
    return FeatureSpec(fid, tuple(smarts), predicate)


#: A carbonyl carbon whose R is carbon or H, as role 1 (the acyl carbon).
_ACYL_C = f"[#6X3;{_R_C_OR_H}:1]"

#: One spec per feature, keyed by id. A test checks the keys equal the
#: vocabulary's, so a feature cannot exist without a detector or vice versa.
SPECS: dict[str, FeatureSpec] = {s.feature_id: s for s in (
    _s("fg:carboxylic_acid", f"{_ACYL_C}(=[OX1:2])[OX2H1,OX1-:3]"),
    _s("fg:carboxylic_ester", f"{_ACYL_C}(=[OX1:2])[#8X2:3]{_HC}"),
    _s("fg:lactone", f"{_ACYL_C}(=[OX1:2])@[#8X2:3]@{_HC}"),
    _s("fg:carbonate_ester", "[#6X3:1](=[OX1:2])([#8X2:3][#6])[#8;X2,X1-:3]"),
    _s("fg:carboxylic_anhydride",
       f"{_ACYL_C}(=[OX1:2])[#8X2:3][#6X3;{_R_C_OR_H}:1]=[OX1:2]"),
    _s("fg:acyl_halide", "[#6X3:1](=[OX1:2])[F,Cl,Br,I;X1:3]",
       "[#16X4:1](=[OX1:2])(=[OX1:2])[F,Cl,Br,I;X1:3]"),
    _s("fg:carboxamide", f"{_ACYL_C}(=[OX1:2]){_AMIDE_N}:3]"),
    _s("fg:lactam", f"{_ACYL_C}(=[OX1:2])@{_AMIDE_N}:3]"),
    _s("fg:imide", "[#6X3:1](=[OX1:2])[#7:3][#6X3:1]=[OX1:2]"),
    _s("fg:urea", "[#7:3][#6X3:1](=[OX1:2])[#7:3]"),
    _s("fg:thiourea", "[#7:3][#6X3:1](=[SX1:2])[#7:3]"),
    # The ester O needs a SECOND carbon: `$([#8X2][#6])` is satisfied by the
    # carbonyl carbon itself, and matched carbamic acid (measured).
    _s("fg:carbamate", "[#7:3][#6X3:1](=[OX1:2])[#8;$([#8X2](-[#6])-[#6]),$([#8X1-]):4]"),
    _s("fg:thioester", f"{_ACYL_C}(=[OX1:2])[SX2:3][#6]",
       f"{_ACYL_C}(=[SX1:2])[OX2:3][#6]", f"{_ACYL_C}(=[SX1:2])[SX2:3][#6]"),
    _s("fg:thioamide", f"{_ACYL_C}(=[SX1:2]){_AMIDE_N}:3]"),
    _s("fg:hydroxamic_acid", "[#6X3:1](=[OX1:2])[#7:3]-[OX2;$([OH1]),$([#8][#6]):4]"),
    # The terminal N may be =C: an N-acylhydrazone is a hydrazide (-NRNR2 with
    # R2 alkylidene) AND a hydrazone. Requiring it single-bonded left the C=O
    # of every acylhydrazone claimed by nothing (Ertl cross-check, 1.17% of ChEMBL).
    _s("fg:hydrazide", "[#6X3:1](=[OX1:2])[#7:3]-[#7:4]",
       "[#16X4:1](=[OX1:2])(=[OX1:2])[#7:3]-[#7:4]"),
    _s("fg:aldehyde", "[#6X3;$([#6H1][#6]),$([#6H2]):1]=[OX1:2]"),
    _s("fg:ketone", "[#6X3;$([#6]([#6])([#6])=[OX1]):1]=[OX1:2]"),
    _s("fg:thioketone", "[#6X3;$([#6]([#6])([#6])=[SX1]):1]=[SX1:2]"),
    _s("fg:amidine",
       f"[#6X3;{_R_C_OR_H}:1](=[#7;!$([#7]-[#8]);!$([#7]-[#7]):2])[#7;!$([#7]-[#8]):3]"),
    _s("fg:guanidine", "[#6X3:1](=[#7:2])([#7:3])[#7:3]"),
    # `$([#8](-[#6])-[#6])`, two carbons: one of them is the imidate carbon
    # itself (the carbamic-acid lesson).
    _s("fg:imidate",
       f"[#6X3;{_R_C_OR_H}:1](=[#7;!$([#7]-[#8]);!$([#7]-[#7]):2])-[OX2;$([OH1]),$([#8](-[#6])-[#6]):3]"),
    _s("fg:isourea", "[#7:3]-[#6X3:1](=[#7:2])-[OX2;$([OH1]),$([#8](-[#6])-[#6]):4]"),
    _s("fg:imine", "[#6X3;!$([#6]-[!#6;!#1]):1]=[#7;!$([#7]-[!#6;!#1]):2]"),
    _s("fg:oxime", "[#6X3;!$([#6]-[!#6;!#1]):1]=[#7X2:2]-[#8X2;$([#8H1]),$([#8][#6]):3]"),
    _s("fg:hydrazone", "[#6X3;!$([#6]-[!#6;!#1]):1]=[#7X2:2]-[#7X3;!$([#7]=*):3]"),
    _s("fg:nitrone", "[#6X3:1]=[#7X3+:2]-[OX1-:3]"),
    _s("fg:carbodiimide", "[#7:2]=[#6X2:1]=[#7:2]"),
    _s("fg:isocyanate", "[#7X2:1]=[#6X2:2]=[OX1:3]"),
    _s("fg:isothiocyanate", "[#7X2:1]=[#6X2:2]=[SX1:3]"),
    _s("fg:nitrile", "[#6X2;$([#6][#6]),$([#6H1]):1]#[#7X1:2]"),
    _s("fg:isocyanide", "[#7X2+:1]#[#6X1-:2]"),
    _s("fg:alcohol", "[OX2H1,OX1-;$([#8][CX4]):1]"),
    _s("fg:phenol", "[OX2H1,OX1-;$([#8]c):1]", predicate=_carbocyclic_smallest_ring),
    _s("fg:heteroarenol", "[OX2H1,OX1-;$([#8]c):1]", predicate=_hetero_smallest_ring),
    _s("fg:enol", "[OX2H1:1][#6X3:2]=[#6X3:2]"),
    _s("fg:ether", f"[OX2;!a:1]({_HC}){_HC}"),
    _s("fg:epoxide", "[OX2;r3:1]1[#6X4:2][#6X4:2]1"),
    _s("fg:acetal", "[CX4:1]([OX2:2][#6;!$([#6]=[O,S])])[OX2:2][#6;!$([#6]=[O,S])]"),
    _s("fg:hemiacetal", "[CX4:1]([OX2H1:2])[OX2:3][#6;!$([#6]=[O,S])]"),
    _s("fg:aminal", "[CX4:1](-[NX3;!$([#7]=*):2])-[NX3;!$([#7]=*):2]"),
    # BOTH of the O's carbons non-acyl: with only one required, the central
    # carbon satisfied it and an acyloxymethylamine matched (measured).
    _s("fg:hemiaminal",
       "[CX4:1](-[OX2;$([OH1]),$([#8](-[#6;!$([#6]=[O,S])])-[#6;!$([#6]=[O,S])]):2])"
       "-[NX3;!$([#7]=*):3]"),
    _s("fg:thioacetal", "[CX4:1](-[SX2:2]-[#6])-[SX2:2]-[#6]",
       "[CX4:1](-[SX2:2]-[#6])-[OX2:3]-[#6;!$([#6]=[O,S])]"),
    _s("fg:peroxide", "[#6][OX2:1]-[OX2:1][#6]"),
    _s("fg:hydroperoxide", "[#6][OX2:1]-[OX2H1:2]"),
    _s("fg:primary_amine", f"[NX3;H2;{_AMINE_EXCL}:1]", f"[NX4+;H3;{_AMINE_EXCL}:1]"),
    _s("fg:secondary_amine", f"[NX3;H1;{_AMINE_EXCL}:1]", f"[NX4+;H2;{_AMINE_EXCL}:1]"),
    _s("fg:tertiary_amine", f"[NX3;H0;{_AMINE_EXCL}:1]", f"[NX4+;H1;{_AMINE_EXCL}:1]"),
    _s("fg:quaternary_ammonium", "[NX4+;H0;!a:1]([#6])([#6])([#6])[#6]"),
    _s("fg:amine_oxide", "[NX4+;!a;!$([#7](~[!#6;!#1])~[!#6;!#1]):1]-[OX1-:2]"),
    _s("fg:hydroxylamine",
       "[NX3;!a;!$([#7][#6]=[O,S,#7]);!$([#7](-[!#6;!#1])-[!#6;!#1]):1]"
       "-[OX2;$([OH1]),$(O[#6]):2]"),
    _s("fg:hydrazine", "[NX3;!a;!$([#7][#6]=[O,S,#7]):1]-[NX3;!a;!$([#7][#6]=[O,S,#7]):1]"),
    _s("fg:azo", "[#6][NX2;!a:1]=[NX2;!a:1][#6]"),
    _s("fg:azide", "[#6][NX2:1]=[NX2+:1]=[NX1-:1]", "[#6][NX2-:1][NX2+:1]#[NX1:1]"),
    _s("fg:diazo", "[#6X3:1]=[NX2+:2]=[NX1-:2]", "[#6X3-:1][NX2+:2]#[NX1:2]"),
    _s("fg:diazonium", "[#6][NX2+:1]#[NX1:1]"),
    _s("fg:nitro", "[#6,#7,#8][NX3+:1](=[OX1:2])[OX1-:2]"),
    _s("fg:nitroso", "[#6,#7,#8][NX2:1]=[OX1:2]"),
    _s("fg:thiol", "[SX2H1,SX1-;$([#16][#6;!$([#6]=[O,S])]):1]"),
    _s("fg:sulfide", f"[SX2;!a:1]({_HC}){_HC}"),
    _s("fg:disulfide", "[#6][SX2:1]-[SX2:1][#6]"),
    _s("fg:sulfoxide", "[#6][SX3:1](=[OX1:2])[#6]", "[#6][SX3+:1](-[OX1-:2])[#6]"),
    _s("fg:sulfone", "[#6][SX4:1](=[OX1:2])(=[OX1:2])[#6]"),
    _s("fg:sulfonic_acid", "[#6][SX4:1](=[OX1:2])(=[OX1:2])[OX2H1,OX1-:3]"),
    _s("fg:sulfonic_ester", "[#6][SX4:1](=[OX1:2])(=[OX1:2])[OX2:3][#6]"),
    _s("fg:sulfate_ester",
       "[#6][OX2:3][SX4:1](=[OX1:2])(=[OX1:2])[OX2:3][#6]",
       "[#6][OX2:3][SX4:1](=[OX1:2])(=[OX1:2])[OX2H1,OX1-:4]"),
    _s("fg:sulfonamide", "[#6][SX4:1](=[OX1:2])(=[OX1:2])[#7;!$([#7]-[#7]):3]"),
    _s("fg:sulfamide", "[#7:3][SX4:1](=[OX1:2])(=[OX1:2])[#7:3]"),
    _s("fg:sulfamate",
       "[#7:3][SX4:1](=[OX1:2])(=[OX1:2])[#8;$([#8X2H1]),$([#8X2][#6]),$([#8X1-]):4]"),
    _s("fg:phosphinic_acid", "[#6][PX4:1](=[OX1:2])([#6])[OX2H1,OX1-:3]",
       "[#6][PX4;H1:1](=[OX1:2])[OX2H1,OX1-:3]"),
    _s("fg:phosphonic_acid", "[#6][PX4:1](=[OX1:2])([OX2H1,OX1-:3])[OX2H1,OX1-:3]"),
    _s("fg:phosphonate_ester",
       "[#6][PX4:1](=[OX1:2])([OX2:3][#6])[OX2:3][#6]",
       "[#6][PX4:1](=[OX1:2])([OX2:3][#6])[OX2H1,OX1-:4]"),
    _s("fg:phosphate_ester",
       "[#6][OX2:3][PX4:1](=[OX1:2])([OX2:3][#6])[OX2:3][#6]",
       "[#6][OX2:3][PX4:1](=[OX1:2])([OX2:3][#6])[OX2H1,OX1-:4]",
       "[#6][OX2:3][PX4:1](=[OX1:2])([OX2H1,OX1-:4])[OX2H1,OX1-:4]"),
    _s("fg:phosphine", "[PX3;!$([#15]~[!#6;!#1]);$([#15][#6]):1]"),
    _s("fg:phosphine_oxide", "[#6][PX4:1](=[OX1:2])([#6])[#6]",
       "[#6][PX4+:1](-[OX1-:2])([#6])[#6]"),
    _s("fg:boronic_acid", "[#6][BX3:1]([OX2H1:2])[OX2H1:2]"),
    _s("fg:boronic_ester", "[#6][BX3:1]([OX2:2][#6])[OX2:2][#6]"),
    _s("fg:silanol", "[SiX4;$([Si][#6]):1]-[OX2H1:2]"),
    _s("fg:silyl_ether", "[SiX4:1]-[OX2:2][#6]"),
    _s("fg:siloxane", "[SiX4:1]-[OX2:2]-[SiX4:1]"),
    _s("fg:fluoro", "[FX1:1][#6]"),
    _s("fg:chloro", "[ClX1:1][#6]"),
    _s("fg:bromo", "[BrX1:1][#6]"),
    _s("fg:iodo", "[IX1:1][#6]"),
    _s("fg:alkene", "[#6;+0:1]=[#6;+0:1]"),
    _s("fg:alkyne", "[#6;+0:1]#[#6;+0:1]"),
    _s("fg:onium", "[S,P,O,Se,As,Br,Cl,I;+1;!a;!$([*]-[OX1-]):1]"),
    _s("sf:aromatic_nh", "[nH1;+0:1]"),
    _s("sf:heteroarene_n_oxide", "[n+:1]-[OX1-:2]"),
    _s("sf:alpha_beta_unsaturated_carbonyl", "[#6X3:4]=[#6X3:3]-[#6X3:1]=[OX1:2]"),
    _s("sf:carbocation", "[#6+1;!$([#6]~[#8-,#7-]):1]"),
    _s("sf:carbanion", "[#6-1;!$([#6]~[#7+]):1]"),
)}


@dataclass(frozen=True)
class StructuralFeature:
    """One detected instance of one feature.

    `identity` is (vocabulary version, feature id, sorted atoms, component):
    the display label is excluded, so rewording one cannot orphan a stored
    result, and the component is included, so two identical salts' anions are
    two instances rather than one.
    """

    feature_id: str
    atoms: frozenset[int]
    #: (atom index, role name), atom order.
    roles: tuple[tuple[int, str], ...]
    charge_state: ChargeState
    component: int
    label: str

    @property
    def identity(self) -> tuple[str, str, tuple[int, ...], int]:
        return (VOCABULARY_VERSION, self.feature_id, tuple(sorted(self.atoms)), self.component)

    @property
    def anchor(self) -> int:
        """The lowest-index atom of role 1, where a label is drawn."""
        return min(atom for atom, _ in self.roles_of(1))

    def roles_of(self, index: int) -> list[tuple[int, str]]:
        name = FEATURE_BY_ID[self.feature_id].roles[index - 1]
        return [(a, r) for a, r in self.roles if r == name]

    @property
    def category(self):
        return FEATURE_BY_ID[self.feature_id].category


@lru_cache(maxsize=None)
def _compiled(smarts: str) -> Chem.Mol:
    pattern = Chem.MolFromSmarts(smarts)
    if pattern is None:
        raise ValueError(f"unparseable SMARTS {smarts!r}")
    return pattern


def _charge_state(mol: Chem.Mol, atoms) -> ChargeState:
    total = sum(mol.GetAtomWithIdx(i).GetFormalCharge() for i in atoms)
    if total == 0:
        return ChargeState.NEUTRAL
    return ChargeState.ANIONIC if total < 0 else ChargeState.CATIONIC


def _label(mol: Chem.Mol, feature_id: str, state: ChargeState, roles: dict[int, int]) -> str:
    definition = FEATURE_BY_ID[feature_id]
    if definition.label_by_element:
        centre = min(a for a, r in roles.items() if r == 1)
        symbol = mol.GetAtomWithIdx(centre).GetSymbol()
        return definition.label_by_element.get(symbol, definition.labels[state])
    return definition.labels[state]


class UndeclaredChargeState(ValueError):
    """A pattern matched a group in a charge state its feature does not
    declare -- a pattern defect, never something to label by guesswork."""


def detect_features(mol: Chem.Mol) -> tuple[StructuralFeature, ...]:
    """Every instance of every feature, in declared vocabulary order.

    `mol` must be sanitized (ring perception included), as every structure the
    application holds is: the ring bonds and the phenol ring test read it.

    Deterministic: sorted by (declared order, component, atoms), so the same
    structure under any atom ordering yields the same instances in the same
    order (the permutation test checks exactly that).
    """
    component_of: dict[int, int] = {}
    for index, fragment in enumerate(Chem.GetMolFrags(mol)):
        for atom in fragment:
            component_of[atom] = index
    found: dict[tuple, StructuralFeature] = {}
    for feature_id, spec in SPECS.items():
        definition = FEATURE_BY_ID[feature_id]
        for smarts in spec.smarts:
            pattern = _compiled(smarts)
            role_of_query = {
                q.GetIdx(): q.GetAtomMapNum() for q in pattern.GetAtoms() if q.GetAtomMapNum()
            }
            for match in mol.GetSubstructMatches(pattern, uniquify=False, maxMatches=100000):
                roles = {match[q]: r for q, r in role_of_query.items()}
                if spec.predicate is not None and not spec.predicate(mol, roles):
                    continue
                atoms = frozenset(roles)
                component = component_of[next(iter(atoms))]
                key = (feature_id, atoms, component)
                if key in found:
                    continue
                state = _charge_state(mol, atoms)
                if state not in definition.labels:
                    raise UndeclaredChargeState(
                        f"{feature_id} matched {state.value} atoms {sorted(atoms)}, "
                        f"a state its definition does not declare"
                    )
                found[key] = StructuralFeature(
                    feature_id=feature_id,
                    atoms=atoms,
                    roles=tuple(sorted(
                        (a, definition.roles[r - 1]) for a, r in roles.items()
                    )),
                    charge_state=state,
                    component=component,
                    label=_label(mol, feature_id, state, roles),
                )
    return tuple(sorted(
        found.values(),
        key=lambda f: (FEATURE_ORDER[f.feature_id], f.component, tuple(sorted(f.atoms))),
    ))


# --- relations and projections -------------------------------------------------


@dataclass(frozen=True)
class RelationHit:
    """A declared relation that holds between two detected instances."""

    subject: StructuralFeature
    kind: RelationKind
    object: StructuralFeature


def relation_hits(features: tuple[StructuralFeature, ...]) -> tuple[RelationHit, ...]:
    """Every declared relation that holds, instance by instance.

    SUPPRESSES and CONTAINS hold when the object's atoms are a subset of the
    subject's; OVERLAPS when they intersect; EXCLUDES when they are equal
    (and is a violation -- see `exclusion_violations`). Same component only.
    """
    by_subject: dict[str, list] = {}
    for relation in RELATIONS:
        by_subject.setdefault(relation.subject, []).append(relation)
    hits = []
    for subject in features:
        for relation in by_subject.get(subject.feature_id, ()):
            for obj in features:
                if obj.feature_id != relation.object or obj.component != subject.component:
                    continue
                if relation.kind in (RelationKind.SUPPRESSES, RelationKind.CONTAINS):
                    holds = obj.atoms <= subject.atoms
                elif relation.kind is RelationKind.OVERLAPS:
                    holds = bool(obj.atoms & subject.atoms)
                else:
                    holds = obj.atoms == subject.atoms
                if holds:
                    hits.append(RelationHit(subject, relation.kind, obj))
    return tuple(hits)


def exclusion_violations(features: tuple[StructuralFeature, ...]) -> tuple[RelationHit, ...]:
    return tuple(h for h in relation_hits(features) if h.kind is RelationKind.EXCLUDES)


@dataclass(frozen=True)
class ProjectedFeature:
    feature: StructuralFeature
    treatment: ObjectTreatment
    #: The instance this one is nested under or suppressed by, if any.
    under: StructuralFeature | None = None


def project(features: tuple[StructuralFeature, ...], projection: Projection) -> tuple[ProjectedFeature, ...]:
    """What `projection` does with each instance, in detection order.

    An instance that is the object of several relations takes the strongest
    treatment (HIDDEN over NON_PRIMARY over NESTED over SHOWN): an ether both
    suppressed by an acetal and overlapped by something else is still hidden.
    """
    policy = PROJECTION_POLICY[projection]
    strength = {
        ObjectTreatment.SHOWN: 0,
        ObjectTreatment.SHOWN_NESTED: 1,
        ObjectTreatment.SHOWN_NON_PRIMARY: 2,
        ObjectTreatment.HIDDEN: 3,
    }
    treatment: dict[tuple, tuple[ObjectTreatment, StructuralFeature | None]] = {}
    for hit in relation_hits(features):
        if hit.kind is RelationKind.EXCLUDES:
            continue
        new = policy[hit.kind]
        current = treatment.get(hit.object.identity, (ObjectTreatment.SHOWN, None))
        if strength[new] > strength[current[0]]:
            treatment[hit.object.identity] = (new, hit.subject)
    out = []
    for feature in features:
        how, under = treatment.get(feature.identity, (ObjectTreatment.SHOWN, None))
        out.append(ProjectedFeature(feature, how, under))
    return tuple(out)
