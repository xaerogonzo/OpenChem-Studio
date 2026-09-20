"""What the nomenclature engine knows about a structure, besides its name.

WHY THIS EXISTS. `naming_providers.derived_name_for_structure` calls the
vendored engine's `name_smiles()` and keeps a `str`. Everything the engine
worked out on the way to that string -- which atoms form the parent, where
each functional group sits, how the rings are fused, which centres are R and
which are S, and what it decided at each fork -- is computed and then thrown
away. This module is the second return value that was always there.

Think of it as an ALGORITHMIC STRUCTURAL ANNOTATION ENGINE that happens to
also emit a name: it describes how a molecule is *organised*, which is a
different and in places richer thing than a descriptor's number.

Everything here is keyed by RDKit atom index ON THE MOLECULE PASSED IN.
Verified: the engine does not re-canonicalise, so `candidate.atom_indices`
and `Numbering.atom_to_locant` land on the caller's own indices. That is the
whole reason this can drive per-atom colouring.

NO VENDOR TYPES ESCAPE. Callers get the plain dataclasses below, never
`DetectedFG`/`RingSystem`/`NameTree`. The vendored engine is a big, fast-
moving subtree with its own 3,200-test suite; pinning the rest of the
application to its dataclasses would make it un-upgradable.

MEASURED COVERAGE, over the `benchmarks/naming` corpus -- 187 molecules as
of 2026-09-17, when six reported ones were added. These numbers are the
reason this module is shaped the way it is, and a UI built on it must not
promise more than they support:

    ring systems       59.3% of heavy atoms     every molecule
    functional groups  18.9%                    every molecule
    structural feat.    4.4%                    every molecule
    IUPAC locants      38.4%                    111 of 187 molecules

(The earlier figures, over the 181-row revision, were 45.3 / 19.7 / 34.8 and
105 of 181. A corpus change moves them, so they are dated.)

The locant asymmetry is the important one. Naming dispatches to several tree
shapes, and only one of them carries a numbering:

    LeafTree             95 of 181   retained name, NO atom indices at all
    SubstitutiveTree     81          carries `numbering`
    AdditiveTree          4          none
    FunctionalClassTree   1          none

So 52% of that corpus -- caffeine and camphor among them -- names to a bare
retained string, and for those the tree offers nothing to map. Even a
SubstitutiveTree numbers only its parent: naproxen's covers 3 of 17 atoms,
because its naphthalene lives in a nested prefix subtree whose indices are
FRAGMENT-LOCAL (`FreeValenceInfo.attachment_atoms_in_fragment`, named for
exactly that reason) and mean nothing against the parent molecule.

SUBSTITUENT NUMBERING IS CARRIED BACK since naming round 4 (A12): the carve
records which atom each fragment atom came from, every prefix entry keeps
that map, and `_substituent_locants` composes the maps down the tree. Over
the 187-molecule corpus that took heavy-atom coverage from 38.5% to 47.5%,
and corrected naproxen, whose naphthalene the ring table had numbered as its
mirror image. (The measured table above predates it.)

`_retained_ring_locants` is the mitigation. The vendored ring table holds
371 entries, 302 carrying an `atom_locants` map keyed by the canonical
SMILES of the ISOLATED ring system, so a ring can be extracted, looked up,
and matched back onto the parent to recover its conventional numbering.
Measured over the 181-row revision it lifted coverage from 22.4% to 34.8%
and was the ONLY source of locants for 24 molecules. **PIPERIDINE AND
BENZENE ARE NOT AMONG THE 302**, which is why fentanyl's rings are
unnumbered while its acetyl chain is not -- see `KNOWN_LIMITATIONS.md`.

THIS USED TO CARVE THE RING OUT ITSELF AND FAILED ON SUBSTITUTED
HETEROCYCLES. `MolFragmentToSmiles` on a ring whose aromatic nitrogens are
substituted in the parent drops the substituents and leaves bare `n` atoms
that cannot be kekulised: caffeine came out as `c1nc2ncncc2n1`, which does
not parse at all, so it got no locants despite purine being in the table
with a full map. It now calls
`ring_naming/common.get_ring_canonical_smiles`, the function the engine
uses for exactly this, which carries four fallback strategies and -- more
importantly -- a documented rule for when inserting a phantom `[nH]` is
SAFE. Inserting one arbitrarily on a purine or xanthine selects the wrong
tautomer key, whose locant map is then wrong for the actual substitution
pattern.

Caffeine now resolves to `9H-purine` and takes all nine ring locants,
verified against the fact that it is 1,3,7-trimethylxanthine: the
methylated nitrogens come back N1, N3 and N7 and the bare one N9.

76 of 187 molecules still end up with no locants at all. `LocantSource`
exists so a UI can say which mechanism produced a number rather than
implying the two are equally authoritative, and `locant_coverage()` exists
so it can decline to offer a numbering view instead of rendering a blank
one.

LACTAMS ARE CLAIMED BY NOTHING, and the cause is half deliberate. The
detector carries an explicit endocyclic-amide guard: when an amide's
carbonyl carbon and nitrogen are in the SAME ring, it refuses the amide
classification, because IUPAC names that carbonyl as a ketone (-one/oxo)
rather than as an amide. That refusal is correct. What is missing is the
other half -- the ketone pattern will not claim an N-adjacent carbonyl
either, so the atom falls through both and ends up in no group at all.

Measured, which is the only way to see the shape of it:

    cyclohexanone       -> ketone            (cyclic C=O, claimed)
    N-methylacetamide   -> secondary_amide   (acyclic amide, claimed)
    2-pyrrolidinone     -> NOTHING           (lactam)
    uracil, caffeine    -> NOTHING           (ring-embedded lactams)
    acetate anion       -> NOTHING           (the SMARTS match the acid form)

So the affected class is real and not obscure: lactams, pyrimidinones,
purinones, barbiturates, and anionic acids. Across the naming corpus it is
4 of 181 molecules with a C=O and no group at all.

An empty group list therefore means "the detector claimed nothing here",
NOT "this molecule has no functional groups", and anything rendering it
should say so rather than let a chemist read caffeine as unfunctionalised.

AND `groups` IS NOT THE WHOLE VOCABULARY, which is what the reported
"Functional Groups shows nothing" turned out to be. The detector answers a
NOMENCLATURE question, so a ring nitrogen is absent by design (it is named
by its ring; every amine SMARTS in the engine's table carries `!R`) and an
ether is absent entirely (it has no group form at all). Three fields now
carry the three different answers, and `compute_functional_groups` merges
them into one result whose every row says which detector found it:

    groups     the naming vocabulary (suffix candidates and prefixes)
    features   the engine's `structural_groups` table -- ring amines,
               aromatic N-H -- which nothing in the naming pipeline reads
    rings      ring systems, as they always were

SUPERSEDED FOR THE FUNCTIONAL-GROUP VIEW by vocabulary v2 (branch B,
2026-09-18): what a feature IS lives in `chem/feature_vocabulary.py`, its
detector in `chem/structural_features.py`, and `canonical_features` below is
the one detection every view projects. The engine's groups stay a second
detector, cross-attributed through `ENGINE_GROUP_MAP`. The measurements above
are kept: they are why the vocabulary could not be the naming engine's.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from enum import Enum
from typing import Any

from rdkit import Chem

from openchem.chem.feature_vocabulary import (
    ENGINE_GROUP_MAP,
    VOCABULARY_VERSION,
    ChargeState,
    FeatureCategory,
    ObjectTreatment,
    Projection,
)
from openchem.chem.structural_features import StructuralFeature, detect_features, project
from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import PerAtomDataset


class LocantSource(str, Enum):
    """Which mechanism produced a locant.

    Present because the two mechanisms have genuinely different standing and
    a bare number would hide that: `PARENT` is this molecule's own IUPAC
    numbering as the engine assigned it, while `RETAINED_RING` is a ring
    skeleton's conventional numbering recovered from a lookup table and
    matched on. The second is still correct numbering, but it describes the
    ring rather than the whole named structure.
    """

    PARENT = "parent"
    #: The numbering of a substituent's OWN parent, from its prefix subtree:
    #: naproxen's naphthalene is numbered as "6-methoxynaphthalen-2-yl" says.
    #: Correct, and specific to this molecule, but local to that prefix -- its
    #: "2" and the parent chain's "2" are different positions.
    SUBSTITUENT = "substituent"
    RETAINED_RING = "retained_ring"


class LocantKind(str, Enum):
    """What KIND of label a locant is -- a different question from where it
    came from.

    `LocantSource` answers "who assigned this number" (the molecule's own
    numbering, or a ring skeleton's conventional one). This answers "what is
    this string": 3a is a FUSION locant and N is a HETEROATOM locant, and
    both can come from either source. Overloading one enum with both would
    make "PARENT" mean two things.

    Load-bearing for a view: the editor's numbering overlay draws these on
    the canvas, where `3a` and `N` read as different kinds of position, and
    a reader comparing `4` with `4a` needs to know the second is not the
    fifth atom of anything.
    """

    #: A plain position on the parent chain or ring: 1, 2, 17.
    CHAIN_OR_RING = "chain_or_ring"
    #: An interior atom of a fused system: 3a, 7a, 11b.
    FUSION = "fusion"
    #: An italic heteroatom locant: N, N', O, S.
    HETEROATOM = "heteroatom"


def classify_locant(label: str) -> LocantKind:
    """Which kind of locant `label` is.

    Read off the LABEL rather than taken from the engine, because the engine
    does not report a kind -- `Locant` carries `is_numeric` and a suffix, and
    the three cases are exactly distinguishable from the string: digits then
    a letter is a fusion locant, no leading digit is a heteroatom locant,
    plain digits are a position.
    """
    stripped = label.strip()
    if not stripped:
        return LocantKind.CHAIN_OR_RING
    if not stripped[0].isdigit():
        return LocantKind.HETEROATOM
    trailing = stripped.rstrip("'")
    if trailing and trailing[-1].isalpha():
        return LocantKind.FUSION
    return LocantKind.CHAIN_OR_RING


@dataclass(frozen=True)
class AnnotatedLocant:
    """One atom's IUPAC locant, where it came from, and what kind it is."""

    atom_index: int
    label: str
    source: LocantSource
    kind: LocantKind = LocantKind.CHAIN_OR_RING
    #: For a `SUBSTITUENT` locant: the prefix it numbers ("6-methoxy-
    #: naphthalen-2-yl"), and the atom's index in that carved fragment. The
    #: provenance a view shows, so it never has to re-derive it.
    prefix: str = ""
    fragment_atom: int | None = None


@dataclass(frozen=True)
class AnnotatedGroup:
    """A functional group the engine's detector claimed.

    `atoms` is every atom the group covers; `anchor` is its defining atom
    (the carbon of a COOH, the nitrogen of an amine), which is what a label
    should be drawn at.
    """

    type: str
    atoms: frozenset[int]
    anchor: int
    prefix_form: str
    suffix_eligible: bool
    #: The detector's own seniority number, when it supplied one. Lower wins
    #: the suffix slot in IUPAC's hierarchy, so this is what explains *why*
    #: one group became the suffix and the rest became prefixes.
    seniority: int | None = None
    in_ring: bool = False


@dataclass(frozen=True)
class AnnotatedRing:
    """One perceived ring system -- not one ring.

    Naphthalene is a single `AnnotatedRing` of 10 atoms with `kind="fused"`,
    not two of 6. That matches how the engine names them and how a chemist
    talks about them.
    """

    atoms: frozenset[int]
    kind: str
    aromatic: bool
    size: int
    #: The ring SYSTEM's own name -- "benzene", "1H-indole", "piperidine",
    #: "bicyclo[2.2.1]heptane" -- or None when neither the curated table nor
    #: the engine can name the extracted skeleton (measured: caffeine's
    #: purine needs the table, whose phantom-[nH] rule the extraction cannot
    #: reproduce on its own).
    #:
    #: THE SKELETON'S NAME, NOT THE MOLECULE'S. Sulfolane's ring system is
    #: named "thiolane" here: the two exocyclic oxygens are not ring atoms,
    #: and no stereodescriptor is carried (`_ring_system_name`).
    #:
    #: ONE KNOWN EXCEPTION, measured: where the engine cannot build a single
    #: fused parent, the skeleton's name is SUBSTITUTIVE -- budesonide's
    #: dioxolane comes back as "16,17-methylenedioxy-...cyclopenta[a]-
    #: phenanthrene" (1 of 192 ring systems over both naming corpora). It is
    #: an accurate name of the skeleton, not a parent's; general fusion
    #: construction is the naming engine's recorded open item (cid40000).
    name: str | None = None
    #: Atoms shared between two rings of a fused system, which are the
    #: positions that carry "a"-suffixed locants (4a, 8a) and the ones a
    #: ring explorer most wants to mark.
    fusion_atoms: frozenset[int] = frozenset()
    #: Von Baeyer bridge sizes for a bridged system, e.g. (2, 2, 1) for
    #: norbornane. Empty for every other kind.
    bridge_sizes: tuple[int, ...] = ()
    spiro_sizes: tuple[int, ...] = ()


@dataclass(frozen=True)
class AnnotatedFeature:
    """Something a chemist calls a functional group that nomenclature names
    another way: a ring amine, an indole N-H.

    Separate from `AnnotatedGroup` on purpose. That type means "the
    detector claimed this as a naming group", and widening it would make
    every consumer of `groups` inherit a vocabulary the namer never sees.
    The engine matches these in its own `structural_groups` table, which
    nothing in the naming pipeline reads.
    """

    type: str
    #: One of `FeatureCategory`'s values, as the engine declared it.
    category: str
    atoms: frozenset[int]
    anchor: int


@dataclass(frozen=True)
class AnnotatedStereocenter:
    """A stereocentre with its CIP descriptor.

    `descriptor` is None for a centre that is real but unassigned -- an
    undrawn wedge. That is a different statement from "not a stereocentre",
    and colouring must not treat them alike.
    """

    atom_index: int
    kind: str
    descriptor: str | None


@dataclass(frozen=True)
class StructureAnnotation:
    """Everything the engine worked out about one molecule.

    Deliberately a plain value object with no reference back to the mol: it
    is safe to cache on a molecule model and to hand to the UI thread.
    """

    atom_count: int
    locants: tuple[AnnotatedLocant, ...] = ()
    groups: tuple[AnnotatedGroup, ...] = ()
    rings: tuple[AnnotatedRing, ...] = ()
    #: Chemist-facing groups nomenclature names another way. Empty for most
    #: molecules; never overlapping-deconflicted against `groups`, because a
    #: ring amine's nitrogen legitimately belongs to both its amine and its
    #: ring system.
    features: tuple[AnnotatedFeature, ...] = ()
    stereocenters: tuple[AnnotatedStereocenter, ...] = ()
    #: The engine's own record of the forks it took, as plain strings.
    #: Thin by design on the engine's side -- typically one entry naming the
    #: parent and the principal characteristic group -- so this is a trail,
    #: not a full derivation.
    decisions: tuple[str, ...] = ()
    #: Set when annotation could not run at all. Everything else is then
    #: empty, and a caller should show this rather than an empty result.
    error: str | None = None

    @property
    def locant_by_atom(self) -> dict[int, str]:
        """Atom index -> locant label, for a per-atom lookup."""
        return {loc.atom_index: loc.label for loc in self.locants}

    @property
    def group_by_atom(self) -> dict[int, str]:
        """Atom index -> functional group type.

        An atom claimed by more than one group keeps the first; the
        detector deconflicts overlaps before this module sees them, so in
        practice there are none.
        """
        out: dict[int, str] = {}
        for group in self.groups:
            for idx in group.atoms:
                out.setdefault(idx, group.type)
        return out

    @property
    def ring_by_atom(self) -> dict[int, int]:
        """Atom index -> position of its ring system in `rings`."""
        return {
            idx: position
            for position, ring in enumerate(self.rings)
            for idx in ring.atoms
        }

    def locant_coverage(self) -> float:
        """Fraction of atoms carrying a locant, 0.0-1.0.

        Exposed because it is frequently ZERO -- half the molecules in the
        naming corpus name to a retained string with no numbering to
        recover. A caller should check this before offering a
        numbering-based view, rather than rendering a blank one.
        """
        if not self.atom_count:
            return 0.0
        return len(self.locants) / self.atom_count


def annotate(mol: Chem.Mol, *, with_naming: bool = True) -> StructureAnnotation:
    """Annotate a molecule with everything the nomenclature engine perceives.

    Never raises. The vendored engine is large and its failure modes are its
    own; an annotation is an enhancement to a view, and one molecule it
    cannot parse must degrade to an empty annotation carrying the reason,
    not take down the panel showing it. This mirrors how
    `QuantumChemistryService` treats a spectrum it cannot parse.

    Costs one `Perception` construction plus one naming pass. Measured
    2026-09-18 over the 187-molecule naming corpus, two runs on an idle
    machine: **11.8-13.7 ms mean, 7-9 ms median, 75-79 ms worst** (naproxen
    and a triazole amide). The earlier 8.0 / 59.3 ms was the 181-row corpus
    before naming round 4 added work per call; a run beside the vendored
    suite read 45 ms mean, which is contention, not the code.
    Cheap once per edit, far too expensive per repaint -- cache it against
    the structure, and never call it from a paint path.
    """
    if mol is None:
        return StructureAnnotation(atom_count=0, error="No molecule.")

    atom_count = mol.GetNumAtoms()

    # Imported here rather than at module scope: the vendored engine pulls
    # in a multi-megabyte data loader on first import, and this module is
    # reachable from panels that may never annotate anything.
    try:
        from openchem.vendor.iupac_namer.perception import Perception
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        return StructureAnnotation(
            atom_count=atom_count,
            error=f"Nomenclature engine unavailable: {type(exc).__name__}: {exc}",
        )

    try:
        perception = Perception(mol)
        groups = _groups(perception)
        rings = _rings(perception, mol)
        features = _features(perception)
        stereocenters = _stereocenters(perception)
    except Exception as exc:  # noqa: BLE001
        return StructureAnnotation(
            atom_count=atom_count,
            error=f"Could not perceive structure: {type(exc).__name__}: {exc}",
        )

    perceived = StructureAnnotation(
        atom_count=atom_count,
        groups=groups,
        rings=rings,
        features=features,
        stereocenters=stereocenters,
    )
    if not with_naming:
        return perceived

    # Naming is a separate, more failure-prone pass than perception, and it
    # only contributes locants and decisions. A molecule the namer chokes on
    # still gets its rings, groups and stereocentres.
    locants, decisions = _locants_and_decisions(
        mol, perception.rings.ring_systems
    )
    return replace(perceived, locants=locants, decisions=decisions)


def perceive(mol: Chem.Mol) -> StructureAnnotation:
    """`annotate` WITHOUT the naming pass: groups, rings, structural features
    and stereocentres, no locants and no decisions.

    The naming pass is most of `annotate`'s cost (measured 2026-09-17 over
    227 molecules: 19 ms median and 8.2 s worst for the whole thing, against
    2.0 ms and 0.65 s for perception), and nothing that only asks WHICH
    features a structure has needs a locant.
    """
    return annotate(mol, with_naming=False)


#: How a ring atom is described when it plays a special structural role.
#: These are the positions a chemist looks for first in a polycyclic system,
#: and the ones the engine already knows because it needs them to number a
#: fusion or a von Baeyer skeleton.
_FUSION_NOTE = "fusion"
_BRIDGEHEAD_NOTE = "bridgehead"
_SPIRO_NOTE = "spiro"

#: What the per-atom label should say. A real choice rather than an option
#: added to satisfy the "every calculator has options" convention: which of
#: these is useful depends on the question being asked. Someone reading a
#: fusion pattern wants positions; someone identifying a scaffold wants the
#: structural roles and finds a full set of locants to be clutter.
RING_LABEL_MODES: dict[str, str] = {
    "Locants, with roles": "locants",
    "Structural roles only": "roles",
    "Ring system": "system",
}
_DEFAULT_LABEL_MODE = "Locants, with roles"


def compute_ring_systems(
    mol: Chem.Mol,
    molecule_uuid: str,
    parameters: dict[str, Any] | None = None,
) -> PerAtomDataset:
    """Which ring system each atom belongs to -- the ring explorer.

    Returns a `PerAtomDataset` whose values are RING SYSTEM IDS, not
    magnitudes, so it is marked `scale="categorical"` in provenance and the
    visualization layer indexes a qualitative palette rather than
    interpolating a ramp. Ring system 1 and ring system 2 are not one unit
    apart in any meaningful sense.

    Works on every molecule, which is the reason this is the first
    annotation feature built: unlike IUPAC locants (absent for half of all
    molecules, see the module docstring) ring perception does not depend on
    which naming path a structure takes. Measured coverage over the naming
    corpus: 45.3% of heavy atoms, every molecule annotated.

    An acyclic molecule returns an EMPTY dataset rather than a failed one.
    Ethanol having no rings is a fact about ethanol, not an error, and a
    permanent red "failed" row for it would be wrong -- the same call
    `DescriptorService` already makes for a molecule with no structure yet.
    """
    label_mode = RING_LABEL_MODES.get(
        (parameters or {}).get("label_mode", _DEFAULT_LABEL_MODE), "locants"
    )
    annotation = annotate(mol)
    provenance_parameters: dict[str, Any] = {
        "scale": "categorical",
        "decimal_places": 0,
        "label_mode": label_mode,
    }

    if annotation.error:
        return PerAtomDataset(
            property_id="ring_systems",
            name="Ring Systems",
            units="",
            method="iupac-namer-perception",
            molecule_uuid=molecule_uuid,
            values={},
            cache_state=CacheState.FAILED,
            error=annotation.error,
            provenance=Provenance(
                created_by="core",
                method="iupac-namer-perception",
                parameters=provenance_parameters,
            ),
        )

    values: dict[int, float] = {}
    atom_notes: dict[int, str] = {}
    category_labels: dict[int, str] = {}

    for position, ring in enumerate(annotation.rings, start=1):
        # Von Baeyer bridgeheads are the atoms a bridged system's bridges
        # meet at. The engine reports bridge SIZES rather than the endpoint
        # atoms, so they are found here from the graph: in a fused system
        # the shared-edge atoms are the fusion positions, and in a bridged
        # one the atoms with three ring bonds are the bridgeheads.
        bridgeheads = (
            _bridgeheads(mol, ring.atoms) if ring.kind == "bridged" else frozenset()
        )
        spiro_atoms = (
            _spiro_atoms(mol, ring.atoms) if ring.kind == "spiro" else frozenset()
        )

        descriptor = _describe_ring(ring)
        category_labels[position] = descriptor

        for atom_index in sorted(ring.atoms):
            values[atom_index] = float(position)
            if atom_index in ring.fusion_atoms:
                atom_notes[atom_index] = _FUSION_NOTE
            elif atom_index in bridgeheads:
                atom_notes[atom_index] = _BRIDGEHEAD_NOTE
            elif atom_index in spiro_atoms:
                atom_notes[atom_index] = _SPIRO_NOTE

    if label_mode == "system":
        # Every atom says which system it belongs to -- useful precisely
        # when there are several and the colours alone are ambiguous.
        atom_notes = {
            atom_index: category_labels[int(category)]
            for atom_index, category in values.items()
        }
    elif label_mode == "locants":
        # Merge locants into the role notes where both exist. A locant is
        # the more precise label, but it does NOT always subsume the role:
        # "4a" encodes fusion in the locant itself, so repeating it is
        # noise, while the spiro centre of spiro[4.5]decane is plain "5"
        # and would lose the one fact worth marking if the locant simply
        # overwrote the role. Locants are absent for most molecules (see
        # the module docstring), so this upgrades a label where it can and
        # leaves the role alone elsewhere.
        for locant in annotation.locants:
            if locant.atom_index not in values:
                continue
            role = atom_notes.get(locant.atom_index)
            letter_suffixed = not locant.label.isdigit()
            if role is None or (role == _FUSION_NOTE and letter_suffixed):
                atom_notes[locant.atom_index] = locant.label
            else:
                atom_notes[locant.atom_index] = f"{locant.label} {role}"
    # "roles" leaves atom_notes exactly as the role pass above built it.

    provenance_parameters["atom_notes"] = atom_notes
    provenance_parameters["category_labels"] = category_labels
    provenance_parameters["summary"] = (
        f"{len(annotation.rings)} ring system"
        f"{'' if len(annotation.rings) == 1 else 's'}."
        if annotation.rings
        else "No rings -- this structure is acyclic."
    )

    return PerAtomDataset(
        property_id="ring_systems",
        name="Ring Systems",
        units="",
        method="iupac-namer-perception",
        molecule_uuid=molecule_uuid,
        values=values,
        provenance=Provenance(
            created_by="core",
            method="iupac-namer-perception",
            parameters=provenance_parameters,
        ),
    )


@dataclass(frozen=True)
class FragmentName:
    """What a selected piece of a molecule is called as a substituent.

    `name` is the substituent form -- "phenyl", not "benzene" -- because
    that is the question being asked: a chemist pointing at part of a
    structure wants the name it would carry in the whole molecule's name.
    """

    name: str
    atom_indices: frozenset[int]
    attachment_atom: int | None
    error: str | None = None


def name_fragment(mol: Chem.Mol, atom_indices: set[int] | frozenset[int]) -> FragmentName:
    """Name a selected substructure the way it would appear in a name.

    Never raises, for the same reason `annotate` does not: this answers a
    selection in a UI, and an unnameable selection is an ordinary outcome
    rather than a fault.

    THE ATTACHMENT POINT IS DERIVED, NOT ASKED FOR. A substituent name
    depends on where the fragment joins the rest -- "propan-2-yl" and
    "propyl" are the same three atoms attached at different positions -- so
    the single atom bonded to something outside the selection defines it. A
    selection with several such bonds is a bridging group, which needs a
    different naming form (yldiyl and friends) and is refused explicitly
    rather than named as if it attached once.
    """
    if mol is None:
        return FragmentName(
            name="", atom_indices=frozenset(), attachment_atom=None,
            error="No molecule.",
        )
    selected = frozenset(atom_indices)
    if not selected:
        return FragmentName(
            name="", atom_indices=frozenset(), attachment_atom=None,
            error="Nothing selected.",
        )
    if any(i < 0 or i >= mol.GetNumAtoms() for i in selected):
        return FragmentName(
            name="", atom_indices=selected, attachment_atom=None,
            error="Selection refers to atoms this molecule does not have.",
        )

    attachments = [
        atom_index
        for atom_index in sorted(selected)
        for neighbour in mol.GetAtomWithIdx(atom_index).GetNeighbors()
        if neighbour.GetIdx() not in selected
    ]
    unique_attachments = sorted(set(attachments))
    if len(unique_attachments) > 1:
        return FragmentName(
            name="", atom_indices=selected, attachment_atom=None,
            error=(
                "This selection attaches to the rest of the structure in "
                f"{len(unique_attachments)} places. A bridging group needs a "
                "different naming form than a substituent."
            ),
        )

    try:
        fragment, index_map = _extract_fragment(mol, selected)
    except Exception as exc:  # noqa: BLE001
        return FragmentName(
            name="", atom_indices=selected, attachment_atom=None,
            error=f"Could not isolate the selection: {type(exc).__name__}: {exc}",
        )

    attachment = unique_attachments[0] if unique_attachments else None
    try:
        from openchem.vendor.iupac_namer import name as build_name_tree
        from openchem.vendor.iupac_namer.assembly import assemble
        from openchem.vendor.iupac_namer.strategy import default_strategy
        from openchem.vendor.iupac_namer.types import (
            FreeValenceInfo,
            OutputForm,
            SubstituentMethod,
        )

        if attachment is None:
            # A whole disconnected molecule was selected: there is no free
            # valence, so it gets its ordinary standalone name.
            tree = build_name_tree(fragment, default_strategy())
        else:
            free_valence = FreeValenceInfo(
                bond_orders=(1,),
                method=SubstituentMethod.ALKANYL,
                attachment_atoms_in_fragment=(index_map[attachment],),
                elide_locant_one=True,
            )
            tree = build_name_tree(
                fragment,
                default_strategy(),
                output_form=OutputForm.SUBSTITUENT,
                free_valence=free_valence,
            )
        rendered = assemble(tree)
    except Exception as exc:  # noqa: BLE001
        return FragmentName(
            name="", atom_indices=selected, attachment_atom=attachment,
            error=f"Could not name the selection: {type(exc).__name__}: {exc}",
        )

    if not rendered:
        return FragmentName(
            name="", atom_indices=selected, attachment_atom=attachment,
            error="The naming engine produced no name for this selection.",
        )
    return FragmentName(
        name=rendered, atom_indices=selected, attachment_atom=attachment
    )


def _extract_fragment(
    mol: Chem.Mol, selected: frozenset[int]
) -> tuple[Chem.Mol, dict[int, int]]:
    """The selection as its own molecule, plus parent index -> fragment index.

    Atoms are removed in DESCENDING order so that each removal cannot shift
    an index still waiting to be removed -- the standard RWMol hazard, and
    the reason the map is built from the sorted kept set beforehand rather
    than read off the result.
    """
    kept = sorted(selected)
    index_map = {parent_index: position for position, parent_index in enumerate(kept)}

    editable = Chem.RWMol(mol)
    for atom_index in sorted(set(range(mol.GetNumAtoms())) - selected, reverse=True):
        editable.RemoveAtom(atom_index)
    fragment = editable.GetMol()
    Chem.SanitizeMol(fragment)
    return fragment, index_map


@dataclass(frozen=True)
class DerivationNode:
    """One step in how a name was built -- a node of the nomenclature tree.

    This is the parse tree the engine builds on the way to a name, flattened
    into plain data. `kind` is the naming strategy applied at this node
    (substitutive, retained, multiplicative, ...), `name` is what this
    subtree assembles to, and `children` are the substituent subtrees that
    fed into it.
    """

    kind: str
    name: str
    role: str = ""
    detail: str = ""
    locants: tuple[str, ...] = ()
    children: tuple["DerivationNode", ...] = ()


def name_derivation(mol: Chem.Mol) -> DerivationNode | None:
    """How the engine built this molecule's name, as a tree.

    The nomenclature debugger's data. Returns None when naming fails, which
    a view should present as "no derivation available" rather than an empty
    tree that looks like a molecule with no structure to explain.

    WHAT THIS CAN AND CANNOT SHOW. `TreeBase.choices_made` is thin -- for a
    typical molecule it holds ONE entry naming the parent and the principal
    characteristic group. So this is a record of the STRUCTURE of the
    decision, not a trace of every rule consulted. The genuinely useful
    depth comes from the nested substituent subtrees, each of which carries
    its own parent, suffixes and choices, and each of which assembles to the
    fragment of the name it produced.

    A retained name is a leaf and has nothing below it: caffeine's whole
    derivation is one node saying "retained name: caffeine". That is not a
    failure of this function, it is what the engine did.
    """
    if mol is None:
        return None
    try:
        from openchem.vendor.iupac_namer import name as build_name_tree
        from openchem.vendor.iupac_namer.strategy import default_strategy

        tree = build_name_tree(mol, default_strategy())
    except Exception:  # noqa: BLE001 - a derivation is an explanation, never fatal
        return None
    return _derivation_node(tree)


def _derivation_node(tree, role: str = "") -> DerivationNode:
    from openchem.vendor.iupac_namer.assembly import assemble

    try:
        rendered = assemble(tree)
    except Exception:  # noqa: BLE001 - a node that will not render still has a shape
        rendered = ""

    kind = type(tree).__name__.replace("Tree", "").lower() or "node"
    choices = getattr(tree, "choices_made", ()) or ()
    detail = "; ".join(f"{c.type}: {c.detail}" for c in choices)

    children: list[DerivationNode] = []

    parent = getattr(tree, "named_parent", None)
    if parent is not None:
        children.append(
            DerivationNode(
                kind="parent",
                name=parent.name,
                role="parent hydride",
                detail=f"method: {parent.naming_method}",
            )
        )

    for suffix in getattr(tree, "suffix_groups", ()) or ():
        children.append(
            DerivationNode(
                kind="suffix",
                name=suffix.base_form,
                role="principal characteristic group",
                detail=suffix.fg.type,
                locants=tuple(locant.label for locant in suffix.locants),
            )
        )

    for infix in getattr(tree, "unsaturation", ()) or ():
        children.append(
            DerivationNode(
                kind="unsaturation",
                name=infix.type,
                role="unsaturation",
                locants=tuple(locant.label for locant in infix.locants),
            )
        )

    # The real depth: each prefix carries its own complete subtree, which is
    # why a nested substituent can be expanded and inspected exactly like the
    # molecule it hangs off.
    for prefix in getattr(tree, "prefixes", ()) or ():
        child = _derivation_node(prefix.tree, role="substituent")
        children.append(
            DerivationNode(
                kind=child.kind,
                name=child.name,
                role="substituent",
                detail=child.detail,
                locants=tuple(locant.label for locant in (prefix.locants or ())),
                children=child.children,
            )
        )

    for descriptor in getattr(tree, "stereo_descriptors", ()) or ():
        children.append(
            DerivationNode(
                kind="stereo",
                name=descriptor.descriptor,
                role="stereodescriptor",
                locants=(descriptor.locant.label,) if descriptor.locant else (),
            )
        )

    return DerivationNode(
        kind=kind,
        name=rendered,
        role=role,
        detail=detail,
        children=tuple(children),
    )


#: `LocantSource` -> (category id, colour). Fixed, like the stereo
#: descriptors and for the same reason: which MECHANISM produced a number
#: is the meaning this view carries, and it must not depend on which
#: mechanisms a particular molecule happened to use.
#:
#: The two are deliberately close in hue rather than contrasting. Both are
#: correct IUPAC numbering; the distinction is one of scope, not of
#: reliability, and a red/green split would imply one was suspect.
_LOCANT_SOURCE_CATEGORIES: dict[LocantSource, tuple[int, str]] = {
    LocantSource.PARENT: (1, "#0072b2"),        # blue
    LocantSource.RETAINED_RING: (2, "#56b4e9"),  # sky blue
    LocantSource.SUBSTITUENT: (3, "#3d8fc6"),    # between the two: it is this
                                                 # molecule's numbering, of a prefix
}


def compute_locants(
    mol: Chem.Mol,
    molecule_uuid: str,
    parameters: dict[str, Any] | None = None,
) -> PerAtomDataset:
    """IUPAC numbering projected onto the structure -- which atom is C-3.

    THE COLOUR IS THE SOURCE, THE LABEL IS THE NUMBER. Colouring by locant
    value would mean twenty categories for a twenty-atom molecule, which
    separates nothing; what a reader needs to know beyond the number itself
    is where it came from, since the two mechanisms have different scope.

    THIS IS THE THIN ONE, and the module docstring has the measurements.
    Over the naming corpus only 32.2% of heavy atoms get a locant, and
    **82 of 181 molecules get none at all** -- every molecule whose name is
    retained, which is a little over half of them. That is not a bug to be
    fixed later, it is the shape of the underlying data, and the honest
    response is to say so rather than render a blank molecule. Hence the
    `summary` in provenance: an empty result explains itself.
    """
    # Purine numbering is conventionally cited as N1/N3/N7/N9 rather than
    # as bare digits, and the element is what makes those readable at a
    # glance on a heterocycle. Off by default because on a plain carbon
    # chain it just adds a "C" to every label.
    include_element = bool((parameters or {}).get("include_element", False))
    annotation = annotate(mol)

    provenance_parameters: dict[str, Any] = {
        "scale": "categorical",
        "decimal_places": 0,
        "include_element": include_element,
    }

    if annotation.error:
        return PerAtomDataset(
            property_id="locants",
            name="IUPAC Locants",
            units="",
            method="iupac-namer",
            molecule_uuid=molecule_uuid,
            values={},
            cache_state=CacheState.FAILED,
            error=annotation.error,
            provenance=Provenance(
                created_by="core",
                method="iupac-namer",
                parameters=provenance_parameters,
            ),
        )

    values: dict[int, float] = {}
    atom_notes: dict[int, str] = {}
    category_labels: dict[int, str] = {}
    category_colors: dict[int, str] = {}

    for locant in annotation.locants:
        category, colour = _LOCANT_SOURCE_CATEGORIES[locant.source]
        values[locant.atom_index] = float(category)
        label = locant.label
        if include_element:
            label = f"{mol.GetAtomWithIdx(locant.atom_index).GetSymbol()}{label}"
        atom_notes[locant.atom_index] = label
        category_labels[category] = _describe_locant_source(locant.source)
        category_colors[category] = colour

    provenance_parameters["atom_notes"] = atom_notes
    provenance_parameters["category_labels"] = category_labels
    provenance_parameters["category_colors"] = category_colors
    provenance_parameters["coverage"] = annotation.locant_coverage()
    provenance_parameters["summary"] = _locant_summary(annotation)

    return PerAtomDataset(
        property_id="locants",
        name="IUPAC Locants",
        units="",
        method="iupac-namer",
        molecule_uuid=molecule_uuid,
        values=values,
        provenance=Provenance(
            created_by="core",
            method="iupac-namer",
            parameters=provenance_parameters,
        ),
    )


def _describe_locant_source(source: LocantSource) -> str:
    if source is LocantSource.PARENT:
        return "Parent numbering (this structure's own)"
    if source is LocantSource.SUBSTITUENT:
        return "Substituent numbering (each prefix's own parent)"
    return "Ring numbering (conventional for the skeleton)"


def _locant_summary(annotation: StructureAnnotation) -> str:
    """One sentence about what was numbered, and what was not.

    The empty case gets the most words on purpose. A chemist who asks for
    IUPAC numbering and sees an unmarked molecule will read it as a failure
    unless told otherwise, and the real reason -- that the structure is
    named by a retained name, which carries no derived numbering -- is both
    accurate and something they will recognise.
    """
    if not annotation.locants:
        if annotation.rings:
            return (
                # "could not be matched", not "is not in the tables" --
                # caffeine's purine IS in them, with a full locant map. The
                # match is what fails. Saying otherwise would send anyone
                # investigating to the wrong place.
                "No IUPAC numbering available. This structure is named by a "
                "retained name rather than a derived one, and its ring "
                "skeleton could not be matched to a numbered entry in the "
                "nomenclature tables."
            )
        return (
            "No IUPAC numbering available. This structure is named by a "
            "retained name, which carries no derived numbering."
        )

    numbered = len(annotation.locants)
    total = annotation.atom_count
    sources = {locant.source for locant in annotation.locants}
    if sources == {LocantSource.RETAINED_RING}:
        return (
            f"{numbered} of {total} atoms numbered, from the ring skeleton's "
            f"conventional numbering -- the structure itself is named by a "
            f"retained name."
        )
    if LocantSource.RETAINED_RING in sources:
        return (
            f"{numbered} of {total} atoms numbered, combining this "
            f"structure's parent numbering with a ring skeleton's."
        )
    if LocantSource.SUBSTITUENT in sources:
        return (
            f"{numbered} of {total} atoms numbered, from the parent and from "
            f"each substituent's own numbering, as its prefix name cites it."
        )
    return f"{numbered} of {total} atoms numbered from the parent chain."


#: How a functional group should be labelled on the depiction.
FG_LABEL_MODES: dict[str, str] = {
    "Group name": "name",
    "Prefix form": "prefix",
}
_DEFAULT_FG_LABEL_MODE = "Group name"


@dataclass(frozen=True)
class CanonicalFeatures:
    """ONE detection of a structure's features, which every view projects.

    Plan B2, "one production path": Functional Groups, Fragment Counts and
    the Atom Inspector all read THIS -- none of them runs a SMARTS of its
    own (docs/ARCHITECTURE.md, "A feature is detected once").

    `features` are vocabulary v3 instances (`chem/structural_features`),
    every detection kept, suppressed ones included. `rings` are the ring
    systems the naming engine's perception names. `groups` are the engine's
    own nomenclature groups, kept only to CROSS-ATTRIBUTE: which v2 instance
    the engine also found, its prefix form, whether it is suffix-eligible.
    """

    features: tuple[StructuralFeature, ...] = ()
    rings: tuple["AnnotatedRing", ...] = ()
    groups: tuple["AnnotatedGroup", ...] = ()
    #: Set when the engine's perception failed; the v2 features still stand.
    perception_error: str | None = None

    def engine_groups_for(self, feature: StructuralFeature) -> list["AnnotatedGroup"]:
        """Engine groups the map allows for this feature, on its atoms."""
        return [
            g for g in self.groups
            if feature.feature_id in ENGINE_GROUP_MAP.get(g.type, ()) and g.atoms & feature.atoms
        ]


def canonical_features(mol: Chem.Mol) -> CanonicalFeatures:
    """The canonical feature set of `mol`, cached per exact structure.

    Keyed by the molblock TEXT, which is what the application's fingerprint
    hashes (`calculation_input`): it binds atom order, charges, isotopes and
    components, so an atom-indexed instance cached under it is valid for any
    molecule with the same key by construction. Perception only -- no naming
    pass, which is most of `annotate`'s cost.
    """
    return _canonical_features_cached(VOCABULARY_VERSION, Chem.MolToMolBlock(mol))


@lru_cache(maxsize=256)
def _canonical_features_cached(vocabulary_version: str, molblock: str) -> CanonicalFeatures:
    # `vocabulary_version` is a KEY, not an input: the detector reads the module's
    # own vocabulary. It is here so a cached set can never outlive the version
    # that made it. Today that cannot happen (the cache is process-local and the
    # version a module constant); the key makes the claim checkable.
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    if mol is None:
        return CanonicalFeatures(perception_error="could not read the structure")
    features = detect_features(mol)
    annotation = perceive(mol)
    return CanonicalFeatures(
        features=features,
        rings=annotation.rings,
        groups=annotation.groups + tuple(_feature_groups(annotation)),
        perception_error=annotation.error,
    )


def _feature_groups(annotation: StructureAnnotation) -> list[AnnotatedGroup]:
    """The engine's structural groups as groups, so one list cross-attributes."""
    return [
        AnnotatedGroup(type=f.type, atoms=f.atoms, anchor=f.anchor,
                       prefix_form="", suffix_eligible=False, seniority=None)
        for f in annotation.features
    ]


def compute_functional_groups(
    mol: Chem.Mol,
    molecule_uuid: str,
    parameters: dict[str, Any] | None = None,
) -> PerAtomDataset:
    """Functional groups, coloured by kind -- the group explorer.

    The FUNCTIONAL GROUPS PROJECTION of the canonical feature set: a
    suppressed feature (the ether inside an acetal) is hidden, a contained
    one (the ester inside a lactone) is shown beside its container, and ring
    systems are reported as ring systems. Every instance, with how this view
    treated it, is in the provenance -- the Atom Inspector reads it there.

    COLOURS ARE ASSIGNED WITHIN THE MOLECULE, not fixed per group type, and
    that is the opposite of the call `compute_stereocenters` makes. R and S
    are a closed pair whose colour carries the meaning; here the vocabulary
    is some hundred features against a 7-colour palette, so a fixed mapping would
    collide constantly within one molecule, and the meaning is carried by the
    label. Assignment is by (category, id), sorted, so the same molecule
    always renders alike. Rings are painted first and groups last, so an
    atom in both shows its group.
    """
    label_mode = FG_LABEL_MODES.get(
        (parameters or {}).get("label_mode", _DEFAULT_FG_LABEL_MODE), "name"
    )
    only_suffix_eligible = bool(
        (parameters or {}).get("only_suffix_eligible", False)
    )
    canonical = canonical_features(mol)

    provenance_parameters: dict[str, Any] = {
        "scale": "categorical",
        "decimal_places": 0,
        "label_mode": label_mode,
        "only_suffix_eligible": only_suffix_eligible,
        "vocabulary_version": VOCABULARY_VERSION,
    }

    fg_view = {p.feature.identity: p for p in project(canonical.features, Projection.FUNCTIONAL_GROUPS)}
    inspector_view = {p.feature.identity: p for p in project(canonical.features, Projection.ATOM_INSPECTOR)}

    def keep(feature: StructuralFeature) -> bool:
        if not only_suffix_eligible:
            return True
        return any(g.suffix_eligible for g in canonical.engine_groups_for(feature))

    def label(feature: StructuralFeature) -> str:
        if label_mode == "prefix":
            for g in canonical.engine_groups_for(feature):
                if g.prefix_form:
                    return g.prefix_form
        return feature.label

    shown = [
        f for f in canonical.features
        if keep(f) and fg_view[f.identity].treatment is not ObjectTreatment.HIDDEN
    ]
    rings = [] if only_suffix_eligible else list(canonical.rings)

    kinds = sorted(
        {(f.category.value, f.feature_id) for f in shown}
        | {(FeatureCategory.RING_SYSTEM.value, _ring_key(r)) for r in rings}
    )
    category_of = {kind: position + 1 for position, kind in enumerate(kinds)}

    values: dict[int, float] = {}
    atom_notes: dict[int, str] = {}
    note_category: dict[int, int] = {}
    category_labels: dict[int, str] = {}
    # Rings, then structural features, then groups: the last write wins, and
    # the most specific description is the one an atom should show.
    for ring in rings:
        category = category_of[(FeatureCategory.RING_SYSTEM.value, _ring_key(ring))]
        category_labels[category] = _ring_label(ring)
        for atom in ring.atoms:
            values[atom] = float(category)
        atom_notes[min(ring.atoms)] = _ring_label(ring)
        note_category[min(ring.atoms)] = category
    for wanted in (FeatureCategory.STRUCTURAL_FEATURE, FeatureCategory.FUNCTIONAL_GROUP):
        for feature in shown:
            if feature.category is not wanted:
                continue
            category = category_of[(feature.category.value, feature.feature_id)]
            category_labels[category] = label(feature)
            if fg_view[feature.identity].treatment is ObjectTreatment.SHOWN_NESTED:
                continue  # its container colours and labels those atoms
            for atom in feature.atoms:
                values[atom] = float(category)
            atom_notes[feature.anchor] = label(feature)
            note_category[feature.anchor] = category
    # A LABEL MUST AGREE WITH ITS ATOM'S COLOUR. Painted over, a ring's note
    # stayed on its anchor: caffeine's N1 was coloured urea and labelled
    # "9H-purine" (driven check, magnified shot, 2026-09-18). A note whose
    # category lost the atom goes, and the atom shows its colour's name.
    for atom in [a for a, c in note_category.items() if values.get(a) != float(c)]:
        del atom_notes[atom]

    records = [
        _feature_record(f, label(f), fg_view[f.identity], inspector_view[f.identity],
                        bool(canonical.engine_groups_for(f)))
        for f in canonical.features if keep(f)
    ] + [_ring_record(r) for r in rings]

    provenance_parameters["atom_notes"] = atom_notes
    provenance_parameters["category_labels"] = category_labels
    provenance_parameters["groups_detected"] = sum(
        1 for r in records if r["functional_groups_view"] != ObjectTreatment.HIDDEN.value
    )
    # EVERY INSTANCE, WITH HOW EACH VIEW TREATED IT. A view showing "ether"
    # cannot otherwise say whether an acetal hid a second one, and "the right
    # label on the wrong atoms" is the failure mode a merged vocabulary
    # invites.
    provenance_parameters["features"] = records
    provenance_parameters["summary"] = _feature_summary(shown, rings)
    if canonical.perception_error:
        provenance_parameters["perception_error"] = canonical.perception_error

    return PerAtomDataset(
        property_id="functional_groups",
        name="Functional Groups",
        units="",
        method=VOCABULARY_VERSION,
        molecule_uuid=molecule_uuid,
        values=values,
        provenance=Provenance(
            created_by="core",
            method=VOCABULARY_VERSION,
            parameters=provenance_parameters,
        ),
    )


def _ring_key(ring: AnnotatedRing) -> str:
    return ring.name or ring.kind


def _ring_label(ring: AnnotatedRing) -> str:
    return ring.name or f"{ring.kind} ring system"


def _feature_record(feature, label, fg, inspector, engine_found) -> dict[str, Any]:
    return {
        "key": feature.feature_id,
        "category": feature.category.value,
        "label": label,
        "charge_state": feature.charge_state.value,
        "component": feature.component,
        "atoms": sorted(feature.atoms),
        "roles": [[atom, role] for atom, role in feature.roles],
        "anchor": feature.anchor,
        # "detector", not "source": in a provenance dict "source" names a
        # LITERATURE source key (test_sources_are_current reads it so).
        "detector": "structural_pattern",
        # The engine is a second detector, never a definition: it is named
        # here when it found the same feature, so the two ceasing to agree
        # shows up as this list shrinking rather than silently.
        "found_by": ["structural_pattern"] + (["naming_engine"] if engine_found else []),
        "functional_groups_view": fg.treatment.value,
        "atom_inspector_view": inspector.treatment.value,
        "under": fg.under.feature_id if fg.under is not None else None,
    }


def _ring_record(ring: AnnotatedRing) -> dict[str, Any]:
    return {
        "key": _ring_key(ring),
        "category": FeatureCategory.RING_SYSTEM.value,
        "label": _ring_label(ring),
        "charge_state": ChargeState.NEUTRAL.value,
        "component": None,
        "atoms": sorted(ring.atoms),
        "roles": [],
        "anchor": min(ring.atoms) if ring.atoms else 0,
        "detector": "naming_engine",
        "found_by": ["naming_engine"],
        "functional_groups_view": ObjectTreatment.SHOWN.value,
        "atom_inspector_view": ObjectTreatment.SHOWN.value,
        "under": None,
    }


#: What each category is called in the summary line, singular and plural.
_CATEGORY_WORDS: dict[FeatureCategory, tuple[str, str]] = {
    FeatureCategory.FUNCTIONAL_GROUP: ("functional group", "functional groups"),
    FeatureCategory.STRUCTURAL_FEATURE: ("structural feature", "structural features"),
    FeatureCategory.RING_SYSTEM: ("ring system", "ring systems"),
}


def _feature_summary(shown: list[StructuralFeature], rings: list[AnnotatedRing]) -> str:
    """One sentence saying what was found, BY KIND.

    The kinds are kept apart because they are different claims: "3 features"
    over an amide, a benzene ring and an indole N-H would invite reading all
    three as functional groups.
    """
    counts: dict[FeatureCategory, int] = {}
    for feature in shown:
        counts[feature.category] = counts.get(feature.category, 0) + 1
    if rings:
        counts[FeatureCategory.RING_SYSTEM] = len(rings)
    if not counts:
        return "Nothing matched: no functional group, structural feature or ring system."
    parts = []
    for category, (singular, plural) in _CATEGORY_WORDS.items():
        count = counts.get(category, 0)
        if count:
            parts.append(f"{count} {singular if count == 1 else plural}")
    return ", ".join(parts) + "."


#: CIP descriptor -> (category id, colour). FIXED rather than assigned in
#: order of appearance, and that is a correctness requirement rather than a
#: preference: with positional colours, a molecule containing only S centres
#: would paint them the same blue that R gets in a molecule containing both,
#: and the colour would mean different things in two windows side by side.
#:
#: Blue/vermillion for R/S is the Okabe-Ito pair with the widest separation
#: under the common colour-vision deficiencies, since R vs S is the
#: distinction this view exists to make. Lowercase r/s -- the
#: PSEUDO-ASYMMETRIC centres, which occur in the corpus and are easy to
#: forget -- take lighter relatives of their uppercase counterparts, so they
#: read as a variant of R/S rather than as unrelated categories.
_STEREO_CATEGORIES: dict[str, tuple[int, str]] = {
    "R": (1, "#0072b2"),   # blue
    "S": (2, "#d55e00"),   # vermillion
    "r": (3, "#56b4e9"),   # sky blue -- pseudo-asymmetric R
    "s": (4, "#e69f00"),   # orange -- pseudo-asymmetric S
    "E": (5, "#009e73"),   # green
    "Z": (6, "#cc79a7"),   # reddish purple
}

#: Its own category, and deliberately grey. Everywhere else in this module
#: grey is avoided because it reads as "no data" -- here that reading is
#: exactly right: the centre exists and its configuration is not specified.
_UNASSIGNED_CATEGORY = 7
_UNASSIGNED_COLOUR = "#9e9e9e"
_UNASSIGNED_LABEL = "unassigned"


def compute_stereocenters(
    mol: Chem.Mol,
    molecule_uuid: str,
    parameters: dict[str, Any] | None = None,
) -> PerAtomDataset:
    """Stereocentres coloured by CIP descriptor -- R against S at a glance.

    Measured to agree exactly with RDKit across the naming corpus (13 of 13
    tetrahedral centres), so the engine's own detector is used rather than a
    second one cross-checked against it.

    UNASSIGNED CENTRES ARE ADDED HERE, NOT IN `annotate()`. The nomenclature
    engine reports only centres whose configuration is *specified*: 2-butanol,
    which has an undefined stereocentre, comes back with none at all. Left
    that way this view would show a molecule with no marks and invite the
    conclusion that it has no stereochemistry, when the truth is that it has
    stereochemistry nobody has drawn yet -- which is usually the more
    actionable fact. So RDKit supplies those separately, in their own grey
    category. `annotate()` stays purely what the engine perceives; mixing a
    second source into it would make its provenance a lie.
    """
    include_unassigned = bool(
        (parameters or {}).get("include_unassigned", True)
    )
    annotation = annotate(mol)

    provenance_parameters: dict[str, Any] = {
        "scale": "categorical",
        "decimal_places": 0,
        "include_unassigned": include_unassigned,
    }

    if annotation.error:
        return PerAtomDataset(
            property_id="stereocenters",
            name="Stereocentres",
            units="",
            method="iupac-namer-perception",
            molecule_uuid=molecule_uuid,
            values={},
            cache_state=CacheState.FAILED,
            error=annotation.error,
            provenance=Provenance(
                created_by="core",
                method="iupac-namer-perception",
                parameters=provenance_parameters,
            ),
        )

    values: dict[int, float] = {}
    atom_notes: dict[int, str] = {}
    category_labels: dict[int, str] = {}
    category_colors: dict[int, str] = {}

    for centre in annotation.stereocenters:
        descriptor = centre.descriptor
        if descriptor is None:
            continue
        mapped = _STEREO_CATEGORIES.get(descriptor)
        if mapped is None:
            # An unrecognised descriptor (rel-R and friends) is still a real
            # stereocentre. Report it in the unassigned category rather than
            # dropping the atom, and let the note carry the actual text.
            category, colour, label = (
                _UNASSIGNED_CATEGORY,
                _UNASSIGNED_COLOUR,
                descriptor,
            )
        else:
            category, colour = mapped
            label = descriptor
        values[centre.atom_index] = float(category)
        atom_notes[centre.atom_index] = label
        category_labels[category] = _describe_stereo_category(category, label)
        category_colors[category] = colour

    if include_unassigned:
        for atom_index in _unassigned_stereocenters(mol):
            if atom_index in values:
                continue
            values[atom_index] = float(_UNASSIGNED_CATEGORY)
            atom_notes[atom_index] = _UNASSIGNED_LABEL
            category_labels[_UNASSIGNED_CATEGORY] = "Unassigned (not specified)"
            category_colors[_UNASSIGNED_CATEGORY] = _UNASSIGNED_COLOUR

    provenance_parameters["atom_notes"] = atom_notes
    provenance_parameters["category_labels"] = category_labels
    provenance_parameters["category_colors"] = category_colors
    provenance_parameters["summary"] = (
        f"{len(values)} stereocentre{'' if len(values) == 1 else 's'}."
        if values
        else "No stereocentres found."
    )

    return PerAtomDataset(
        property_id="stereocenters",
        name="Stereocentres",
        units="",
        method="iupac-namer-perception",
        molecule_uuid=molecule_uuid,
        values=values,
        provenance=Provenance(
            created_by="core",
            method="iupac-namer-perception",
            parameters=provenance_parameters,
        ),
    )


def _describe_stereo_category(category: int, label: str) -> str:
    """A legend entry naming what the descriptor means.

    Spelled out because "r" beside "R" in a key is close to unreadable, and
    pseudo-asymmetry is unfamiliar enough that the bare letter does not
    explain itself.
    """
    if category in (1, 2):
        return f"{label} (CIP)"
    if category in (3, 4):
        return f"{label} (pseudo-asymmetric)"
    if category in (5, 6):
        return f"{label} (double bond)"
    return label


def _unassigned_stereocenters(mol: Chem.Mol) -> frozenset[int]:
    """Potential stereocentres whose configuration nobody has specified.

    RDKit rather than the engine, for the reason in `compute_stereocenters`:
    the engine reports only assigned centres by design, so this is the one
    piece of information it structurally cannot supply.
    """
    try:
        found = Chem.FindMolChiralCenters(
            mol, includeUnassigned=True, useLegacyImplementation=False
        )
    except Exception:  # noqa: BLE001 - an enhancement, never fatal
        return frozenset()
    return frozenset(idx for idx, label in found if label == "?")


def _describe_ring(ring: AnnotatedRing) -> str:
    """A ring system in one phrase, for a legend entry.

    Reads as "fused aromatic, 10 atoms" -- the classification first, since
    that is what distinguishes one system from another in a molecule that
    has several.
    """
    parts = [ring.kind]
    if ring.aromatic:
        parts.append("aromatic")
    descriptor = " ".join(parts)
    if ring.bridge_sizes:
        descriptor += f" [{'.'.join(str(s) for s in ring.bridge_sizes)}]"
    elif ring.spiro_sizes:
        descriptor += f" [{'.'.join(str(s) for s in ring.spiro_sizes)}]"
    return f"{descriptor}, {ring.size} atoms"


def _bridgeheads(mol: Chem.Mol, atoms: frozenset[int]) -> frozenset[int]:
    """Atoms where a bridge meets the main skeleton.

    Defined structurally as a ring atom with three or more bonds to other
    atoms of the SAME ring system -- in norbornane exactly the two carbons
    the three bridges run between. Counting bonds within the system rather
    than total degree matters: a substituted bridge carbon has three bonds
    too, and is not a bridgehead.
    """
    found = set()
    for atom_index in atoms:
        atom = mol.GetAtomWithIdx(atom_index)
        neighbours_in_system = sum(
            1 for nbr in atom.GetNeighbors() if nbr.GetIdx() in atoms
        )
        if neighbours_in_system >= 3:
            found.add(atom_index)
    return frozenset(found)


def _spiro_atoms(mol: Chem.Mol, atoms: frozenset[int]) -> frozenset[int]:
    """The single atom two rings of a spiro system share.

    RDKit's ring info gives the individual rings; a spiro atom is one that
    belongs to more than one of them while sharing no BOND with them --
    which is exactly what distinguishes spiro from fused.
    """
    ring_info = mol.GetRingInfo()
    found = set()
    for atom_index in atoms:
        if ring_info.NumAtomRings(atom_index) < 2:
            continue
        atom = mol.GetAtomWithIdx(atom_index)
        shared_bond = any(
            ring_info.NumBondRings(bond.GetIdx()) >= 2 for bond in atom.GetBonds()
        )
        if not shared_bond:
            found.add(atom_index)
    return frozenset(found)


def _groups(perception) -> tuple[AnnotatedGroup, ...]:
    """Functional groups, flattened out of the detector's own types."""
    out = []
    for fg in perception.fgs.detected_fgs:
        properties = fg.properties_dict()
        out.append(
            AnnotatedGroup(
                type=fg.type,
                atoms=frozenset(fg.atoms),
                anchor=fg.anchor,
                prefix_form=fg.prefix_form,
                suffix_eligible=fg.suffix_eligible,
                seniority=properties.get("seniority"),
                in_ring=bool(properties.get("in_ring", False)),
            )
        )
    # Anchor order, so a rendered list is stable across runs rather than
    # following the detector's internal match order.
    return tuple(sorted(out, key=lambda g: g.anchor))


def _features(perception) -> tuple[AnnotatedFeature, ...]:
    """The engine's structural features, flattened out of its own type."""
    try:
        detected = perception.fgs.structural_features
    except AttributeError:  # pragma: no cover - an older vendored engine
        return ()
    return tuple(
        AnnotatedFeature(
            type=f.type,
            category=f.category,
            atoms=frozenset(f.atoms),
            anchor=f.anchor,
        )
        for f in detected
    )


def _rings(perception, mol: Chem.Mol) -> tuple[AnnotatedRing, ...]:
    """Ring systems. Works for every molecule, unlike locants."""
    out = []
    for rs in perception.rings.ring_systems:
        fusion_atoms: set[int] = set()
        if rs.fusion_info is not None:
            for pair in rs.fusion_info.fusion_atoms:
                fusion_atoms.update(pair)
        out.append(
            AnnotatedRing(
                atoms=frozenset(rs.atom_indices),
                kind=rs.type,
                aromatic=bool(rs.aromatic),
                size=rs.ring_size,
                name=_ring_system_name(rs, mol),
                fusion_atoms=frozenset(fusion_atoms),
                bridge_sizes=tuple(rs.bridge_sizes or ()),
                spiro_sizes=tuple(rs.spiro_sizes or ()),
            )
        )
    return tuple(sorted(out, key=lambda r: min(r.atoms) if r.atoms else 0))


@lru_cache(maxsize=512)
def _name_ring_skeleton(ring_smiles: str) -> str | None:
    """A ring skeleton's name, from its extracted SMILES.

    Two sources, in this order:

      1. The curated ring table, whose entries carry the name AND handle the
         rings the extraction alone cannot key -- caffeine's purine among
         them, which needs the engine's documented phantom-[nH] rule.
      2. The engine, naming the skeleton as a molecule in its own right.
         This is what supplies "pyrrolidine" (absent from the curated SMILES
         index, measured), "bicyclo[2.2.1]heptane" and "spiro[4.5]decane".

    Cached on the SMILES: a project full of one scaffold names it once.
    """
    try:
        from openchem.vendor.iupac_namer.data_loader import _RING_CURATED_SMILES
    except Exception:  # noqa: BLE001
        _RING_CURATED_SMILES = {}
    entry = _RING_CURATED_SMILES.get(ring_smiles) or {}
    curated = entry.get("name")
    if curated:
        return str(curated)
    try:
        from openchem.vendor.iupac_namer import name_smiles

        named = name_smiles(ring_smiles)
    except Exception:  # noqa: BLE001 - an unnameable skeleton is not fatal
        return None
    return str(named) if named else None


def _ring_system_name(ring_system, mol: Chem.Mol) -> str | None:
    """`_name_ring_skeleton` for a perceived ring system."""
    try:
        from openchem.vendor.iupac_namer.ring_naming.common import (
            get_ring_canonical_smiles,
        )

        key = get_ring_canonical_smiles(ring_system, mol)
    except Exception:  # noqa: BLE001
        return None
    if not key:
        return None
    # **THE SKELETON HAS NO CONFIGURATION.** The extracted SMILES kept the
    # molecule's stereocentres, and naming it as a molecule put them in front:
    # "(5R)-hexadecahydro-1H-cyclopenta[a]phenanthrene", "trans-decalin" (3 of
    # 192 ring systems over both naming corpora, measured 2026-09-18). The
    # Blue Book's P-91.3 (pdf p. 872): stereodescriptors are ADDED to a name
    # built by the ordinary rules and "do not change the name or the numbering
    # of a compound" -- they describe a compound, not its parent skeleton.
    # Stripped only when present: the curated ring table is keyed by the
    # engine's own canonical form, which a blanket re-canonicalisation could
    # move (none of its 371 keys carries stereo, measured).
    if any(mark in key for mark in "@/\\"):
        skeleton = Chem.MolFromSmiles(key)
        if skeleton is not None:
            Chem.RemoveStereochemistry(skeleton)
            key = Chem.MolToSmiles(skeleton)
    return _name_ring_skeleton(key)


def _stereocenters(perception) -> tuple[AnnotatedStereocenter, ...]:
    """Stereocentres.

    Measured to agree exactly with RDKit's `FindMolChiralCenters` across the
    naming corpus -- 13 of 13 tetrahedral centres -- so this is used in
    preference to a second detector rather than cross-checked against one.
    """
    return tuple(
        AnnotatedStereocenter(
            atom_index=sc.atom_idx,
            kind=sc.type,
            descriptor=sc.descriptor,
        )
        for sc in perception.stereo.stereocenters
    )


def _locants_and_decisions(
    mol: Chem.Mol, ring_systems
) -> tuple[tuple[AnnotatedLocant, ...], tuple[str, ...]]:
    """IUPAC numbering, from the naming tree and then from the ring table.

    Two sources in priority order. The tree's own numbering wins where it
    exists, because it is this molecule's actual assigned numbering; the
    ring table fills in skeletons the tree said nothing about.
    """
    try:
        from openchem.vendor.iupac_namer import name as build_name_tree
        from openchem.vendor.iupac_namer.strategy import default_strategy

        tree = build_name_tree(mol, default_strategy())
    except Exception:  # noqa: BLE001 - locants are optional, groups are not
        return (), ()

    found: dict[int, AnnotatedLocant] = {}

    numbering = getattr(tree, "numbering", None)
    if numbering is not None:
        for atom_idx, locant in numbering.atom_to_locant.items():
            found[atom_idx] = AnnotatedLocant(
                atom_index=atom_idx,
                label=locant.label,
                source=LocantSource.PARENT,
                kind=classify_locant(locant.label),
            )

    # Before the ring table, which can only guess a substituted ring's
    # orientation: it labelled naproxen's attachment carbon 6 and its methoxy
    # carbon 2, the reverse of "6-methoxynaphthalen-2-yl" (round 4, A12).
    _substituent_locants(tree, None, found)

    for atom_idx, label in _retained_ring_locants(mol, ring_systems).items():
        # setdefault: never overwrite the molecule's own numbering with a
        # skeleton's conventional one.
        found.setdefault(
            atom_idx,
            AnnotatedLocant(
                atom_index=atom_idx,
                label=label,
                source=LocantSource.RETAINED_RING,
                kind=classify_locant(label),
            ),
        )

    decisions = tuple(
        f"{choice.type}: {choice.detail}"
        for choice in getattr(tree, "choices_made", ())
    )
    return tuple(sorted(found.values(), key=lambda loc: loc.atom_index)), decisions


def _substituent_locants(tree, to_root: dict[int, int] | None, found: dict) -> None:
    """Each prefix subtree's own numbering, carried onto the structure.

    A subtree's numbering is keyed by FRAGMENT indices. The engine records,
    per prefix, which atom of the molecule named one level up each fragment
    atom was carved from (`PrefixEntry.atom_origin`, stamped by the carve
    and checked injective and element-preserving there); composing those
    maps level by level lands every locant on the caller's atom. `setdefault`
    so the structure's own parent numbering always wins.
    """
    from openchem.vendor.iupac_namer.assembly import assemble

    for entry in getattr(tree, "prefixes", None) or ():
        origin = getattr(entry, "atom_origin", ())
        if not origin:
            continue
        child_to_root = {
            child: (level if to_root is None else to_root[level])
            for child, level in origin
            if to_root is None or level in to_root
        }
        subtree = entry.tree
        numbering = getattr(subtree, "numbering", None)
        # A one-atom substituent's "1" is cited nowhere ("methyl", "chloro")
        # and would only clutter the drawing.
        if numbering is not None and len(numbering.atom_to_locant) > 1:
            try:
                prefix = assemble(subtree)
            except Exception:  # noqa: BLE001 - the name is provenance, not the number
                prefix = ""
            for fragment_atom, locant in numbering.atom_to_locant.items():
                root = child_to_root.get(fragment_atom)
                if root is None:
                    continue
                found.setdefault(
                    root,
                    AnnotatedLocant(
                        atom_index=root,
                        label=locant.label,
                        source=LocantSource.SUBSTITUENT,
                        kind=classify_locant(locant.label),
                        prefix=prefix,
                        fragment_atom=fragment_atom,
                    ),
                )
        _substituent_locants(subtree, child_to_root, found)


def _retained_ring_locants(mol: Chem.Mol, ring_systems) -> dict[int, str]:
    """Conventional ring numbering, recovered from the vendored ring table.

    THE EXTRACTION IS THE ENGINE'S OWN, and that is the whole fix. This
    used to carve the ring out with `MolFragmentToSmiles` and re-parse it,
    which fails on any ring whose aromatic nitrogens are substituted in the
    parent: caffeine's ring system comes out as `c1nc2ncncc2n1`, every N
    having lost the indicated hydrogen it needed, and that does not parse
    at all. `ring_naming/common.get_ring_canonical_smiles` is the function
    the engine uses for exactly this, and it carries four fallback
    strategies plus a documented rule for WHEN inserting a phantom [nH] is
    safe -- inserting one arbitrarily on a purine or xanthine picks the
    wrong tautomer key, whose locant map is then wrong for the actual
    substitution pattern.

    THE TEMPLATE IS PARSED UNSANITISED, which is not a shortcut. The table
    key is a canonical form the engine produces through partial
    sanitisation, and several keys -- purine's bare skeleton among them --
    do not round-trip: `Chem.MolFromSmiles(key)` returns None. Parsing with
    `sanitize=False` preserves the atom ORDER the locant map is keyed to,
    which is all that is needed to carry the numbering across.

    VERIFIED AGAINST KNOWN NUMBERING rather than against itself. Caffeine
    is 1,3,7-trimethylxanthine, so every one of its nine ring locants is
    pinned by the name: the methylated nitrogens are N1, N3 and N7 and the
    bare one is N9. The mapping produced here reproduces that exactly. An
    earlier attempt that assumed the locant map was keyed to the ring atoms
    in sorted parent order returned a full set of confident, WRONG numbers
    -- every atom labelled, nothing raised, N7 reported as position 2 --
    which is the failure this docstring exists to stop anyone repeating.

    WHAT IT STILL DOES NOT DO: this is the SKELETON's conventional
    numbering, not the molecule's IUPAC-assigned numbering. For a
    substituted ring those differ, because real numbering must give the
    substituents the lowest locants and a table lookup cannot know where
    they are. Callers get `LocantSource.RETAINED_RING` so a view can say
    which of the two it is showing.
    """
    try:
        # The engine's BUILT table, not the raw data: it fills the fusion
        # carbons an entry leaves out (indole ships without 3a/7a) and adds
        # the side-table maps, so the drawing numbers what the engine uses
        # (round 4, A12).
        from openchem.vendor.iupac_namer.ring_naming.retained_lookup import _CURATED
        from openchem.vendor.iupac_namer.ring_naming.common import (
            get_ring_canonical_smiles,
        )
    except Exception:  # noqa: BLE001
        return {}

    out: dict[int, str] = {}
    for ring_system in ring_systems or ():
        try:
            key = get_ring_canonical_smiles(ring_system, mol)
        except Exception:  # noqa: BLE001 - an unextractable ring is not fatal
            continue
        if not key:
            continue

        entry = _CURATED.get(key)
        if not entry:
            continue
        atom_locants = entry[3]
        if not atom_locants:
            continue

        # sanitize=False: see the docstring -- several curated keys do not
        # re-parse, and only the atom order matters here.
        template = Chem.MolFromSmiles(key, sanitize=False)
        if template is None:
            continue
        try:
            match = mol.GetSubstructMatch(template)
        except Exception:  # noqa: BLE001
            continue
        if not match:
            continue
        for template_idx, locant in atom_locants.items():
            if 0 <= template_idx < len(match):
                out[match[template_idx]] = str(locant)
    return out
