"""The chemist's functional-group vocabulary, where nomenclature has none.

WHY THIS EXISTS BESIDE THE NAMING ENGINE'S DETECTOR. That detector answers a
nomenclature question -- which group becomes the suffix, which become
prefixes -- and it is the right answer to that question. It is not the answer
to "what functional groups does this molecule have". Measured 2026-09-17 on
the molecules this was reported for:

    acetyl fentanyl   tertiary_amide                     and nothing else
    MPMI              nothing at all
    4-HO-MPMI         phenol                             and nothing else

So a fentanyl showed one group and a tryptamine showed none, which reads as
a broken calculator. Three different reasons, and only the first is fixed
here:

  * A ring nitrogen is named by its ring, so every amine SMARTS in the
    engine's table carries `!R`. Fixed IN the engine, in its own
    `structural_groups` table (ring amines, aromatic N-H) -- see
    `vendor/data/functional_groups.json`.
  * An ether, a thioether and an ammonium have no suffix and no prefix that
    the engine emits as a group, so they are absent from its vocabulary
    entirely. That is this file.
  * A benzene or an indole is a RING SYSTEM, which the annotation layer
    already models (`AnnotatedRing`). Nothing new is needed and nothing is
    duplicated: `compute_functional_groups` reads `annotation.rings`.

**A SPEC, NOT A BARE PATTERN.** The SMARTS says what matches; the spec says
what the match MEANS -- its category, what it deliberately excludes, and
what its charge policy is. Two of the three defects this file's own review
predicted were exclusion defects (an amide N read as an amine, a pyridine N
read as an N-H), so the exclusions are written down and tested rather than
left implicit in a long bracket expression.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from rdkit import Chem

#: Bumped when a key's MEANING changes, not when a pattern is tuned. It is
#: part of a feature's identity, so a stored result cannot be silently
#: reinterpreted by a later definition of "tertiary_amine".
VOCABULARY_VERSION = "openchem-structural-features-v1"


class FeatureCategory(str, Enum):
    """What KIND of thing a feature is.

    A benzene ring and an amide are both worth showing and are not the same
    kind of claim, and code downstream must not have to infer that from a
    key's spelling.
    """

    FUNCTIONAL_GROUP = "functional_group"
    RING_SYSTEM = "ring_system"
    STRUCTURAL_FEATURE = "structural_feature"


class FeatureSource(str, Enum):
    """Which detector found it. A KEY, never the display text."""

    NAMING_ENGINE = "naming_engine"
    STRUCTURAL_PATTERN = "structural_pattern"


@dataclass(frozen=True)
class PatternSpec:
    """One entry of the catalogue."""

    key: str
    category: FeatureCategory
    label: str
    smarts: str
    #: Which pattern atom the label is drawn at.
    anchor_index: int
    #: What this pattern deliberately does NOT match, in words. Every clause
    #: here is covered by a negative fixture in
    #: `tests/test_functional_group_features.py`.
    excludes: str
    #: Whether the key means the neutral species, the protonated one, or is
    #: indifferent. Stated because the app shows pH-selected structures, so
    #: "amine" and "ammonium" can both be on screen for one compound.
    charge_policy: str
    reference: str


#: The catalogue. Four entries, deliberately: each one is a group a chemist
#: names and the nomenclature vocabulary has NO group for. Anything the
#: engine already detects (amide, phenol, nitrile, the halogens) stays with
#: the engine, and a ring amine belongs in ITS `structural_groups` table --
#: two detectors claiming one key is how a vocabulary starts disagreeing
#: with itself.
PATTERNS: tuple[PatternSpec, ...] = (
    PatternSpec(
        key="ether",
        category=FeatureCategory.FUNCTIONAL_GROUP,
        label="ether",
        smarts="[OX2;H0;!a;!$(O[C,S,P]=[O,S,N]);!$(O[N+](=O))]([#6])[#6]",
        anchor_index=0,
        excludes=(
            "an ester, carbonate, anhydride or sulfonate oxygen (O next to C=O "
            "or S=O), and a nitrate O. The constraint is on the oxygen ITSELF "
            "being non-aromatic, not on its neighbours: an aromatic ring O "
            "(furan) belongs to the ring system, while anisole and diphenyl "
            "ether ARE ethers. An earlier `!$(Oa)` excluded both of those -- "
            "measured, which is why this reads the way it does."
        ),
        charge_policy="neutral",
        reference="IUPAC P-63.2.4 names these as -oxy prefixes or 'ether' class names",
    ),
    PatternSpec(
        key="thioether",
        category=FeatureCategory.FUNCTIONAL_GROUP,
        label="thioether (sulfide)",
        smarts="[SX2;H0;!a;!$(S[C,S,P]=[O,S,N]);!$([S+])]([#6])[#6]",
        anchor_index=0,
        excludes=(
            "a thioester, a disulfide-to-carbonyl, a sulfonium, and an "
            "aromatic ring S (thiophene). As for the ether, the aromaticity "
            "constraint is on the sulfur itself, so thioanisole matches."
        ),
        charge_policy="neutral",
        reference="IUPAC P-63.2.4",
    ),
    PatternSpec(
        key="ammonium",
        category=FeatureCategory.FUNCTIONAL_GROUP,
        label="ammonium (protonated amine)",
        smarts="[NX4+;H1,H2,H3;!$([N+]a)]",
        anchor_index=0,
        excludes=(
            "a quaternary ammonium (no N-H), an aromatic N-H+ (pyridinium), "
            "and a nitro or N-oxide nitrogen, which are N+ but not ammonium"
        ),
        charge_policy="protonated",
        reference="IUPAC P-73.1; separate from 'amine' so a pH-selected structure "
                 "reports what is actually drawn",
    ),
    PatternSpec(
        key="quaternary_ammonium",
        category=FeatureCategory.FUNCTIONAL_GROUP,
        label="quaternary ammonium",
        smarts="[NX4+;H0]([#6])([#6])([#6])[#6]",
        anchor_index=0,
        excludes="a protonated amine (has at least one N-H), and any N+ bearing a "
                 "non-carbon substituent (nitro, N-oxide)",
        charge_policy="cationic",
        reference="IUPAC P-73.1",
    ),
)


#: Display labels for the ENGINE's structural keys. Its own type names are
#: identifiers, and LOWERCASE like the naming vocabulary's own labels
#: ("tertiary amide"): the view that shows these mixes the two lists, and
#: Title Case here read as two different vocabularies on one screen.
#: identifiers ("aromatic_amine_nh"), and the de-underscored form reads as
#: broken English on screen. Keys absent here fall back to that form, which
#: is fine for the naming vocabulary ("tertiary amide").
ENGINE_FEATURE_LABELS: dict[str, str] = {
    "ring_tertiary_amine": "tertiary amine (ring)",
    "ring_secondary_amine": "secondary amine (ring)",
    "aromatic_amine_nh": "aromatic N-H (pyrrole type)",
}


@dataclass(frozen=True)
class PatternMatch:
    """One match of one spec."""

    spec: PatternSpec
    atoms: frozenset[int]
    anchor: int


def match_patterns(mol: Chem.Mol) -> tuple[PatternMatch, ...]:
    """Every catalogue match on `mol`, anchor order.

    A bad pattern is skipped rather than raised: this feeds a display, and
    one unparseable SMARTS must not cost the molecule its other features.
    """
    out: list[PatternMatch] = []
    for spec in PATTERNS:
        pattern = Chem.MolFromSmarts(spec.smarts)
        if pattern is None:  # pragma: no cover - guarded by test_patterns_parse
            continue
        for match in mol.GetSubstructMatches(pattern):
            anchor = match[spec.anchor_index] if spec.anchor_index < len(match) else match[0]
            out.append(PatternMatch(spec=spec, atoms=frozenset(match), anchor=anchor))
    return tuple(sorted(out, key=lambda m: (m.anchor, m.spec.key)))


@dataclass(frozen=True)
class FeatureInstance:
    """One feature of one molecule, from whichever detector found it.

    `identity` is what makes two detections the same feature: the same
    vocabulary, kind, key and atom set. Two detectors finding THAT are one
    feature; two features that merely share an atom are two features (a ring
    amine's nitrogen belongs to its amine and to its ring system, and
    dropping either would be a lie about the structure).

    The display `label` is deliberately NOT part of the identity, so
    rewording a label cannot orphan a stored result.
    """

    key: str
    category: FeatureCategory
    atoms: frozenset[int]
    anchor: int
    label: str
    #: The canonical producer.
    source: FeatureSource
    #: Every detector that found this identity, canonical first. Kept so a
    #: later change to the catalogue shows up as the two detectors ceasing
    #: to agree, rather than silently.
    found_by: tuple[FeatureSource, ...]

    @property
    def identity(self) -> tuple[str, str, str, tuple[int, ...]]:
        return (
            VOCABULARY_VERSION,
            self.category.value,
            self.key,
            tuple(sorted(self.atoms)),
        )


def merge_features(candidates: list[FeatureInstance]) -> list[FeatureInstance]:
    """One instance per identity, the naming engine canonical.

    Order is by (category, anchor, key), so a rendered list and a screenshot
    are stable across runs.
    """
    by_identity: dict[tuple, FeatureInstance] = {}
    for candidate in candidates:
        existing = by_identity.get(candidate.identity)
        if existing is None:
            by_identity[candidate.identity] = candidate
            continue
        # Same feature, two detectors: keep the naming engine's instance and
        # record that both saw it.
        canonical = (
            existing
            if existing.source is FeatureSource.NAMING_ENGINE
            else candidate
        )
        other = candidate if canonical is existing else existing
        found_by = tuple(
            dict.fromkeys(canonical.found_by + other.found_by)
        )
        by_identity[candidate.identity] = replace(canonical, found_by=found_by)
    order = {
        FeatureCategory.FUNCTIONAL_GROUP: 0,
        FeatureCategory.STRUCTURAL_FEATURE: 1,
        FeatureCategory.RING_SYSTEM: 2,
    }
    return sorted(
        by_identity.values(),
        key=lambda f: (order.get(f.category, 9), f.anchor, f.key),
    )
