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

MEASURED COVERAGE, over the 181-molecule `benchmarks/naming` corpus. These
numbers are the reason this module is shaped the way it is, and a UI built
on it must not promise more than they support:

    ring systems       45.3% of heavy atoms     every molecule
    functional groups  19.7%                    every molecule
    IUPAC locants      34.8%                    105 of 181 molecules

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

`_retained_ring_locants` is the mitigation. The vendored ring table holds
371 entries, 302 carrying an `atom_locants` map keyed by the canonical
SMILES of the ISOLATED ring system, so a ring can be extracted, looked up,
and matched back onto the parent to recover its conventional numbering.
Measured over the corpus it lifts coverage from 22.4% to **34.8%** and is
the ONLY source of locants for 24 molecules.

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

76 of 181 molecules still end up with no locants at all. `LocantSource`
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

`chem/functional_group_patterns.py` holds the fourth source (ether,
thioether, ammonium) and the identity the four are merged on.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from enum import Enum
from typing import Any

from rdkit import Chem

from openchem.chem.functional_group_patterns import (
    ENGINE_FEATURE_LABELS,
    VOCABULARY_VERSION,
    FeatureCategory,
    FeatureInstance,
    FeatureSource,
    match_patterns,
    merge_features,
)
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
    #: named "thiolane" here: the two exocyclic oxygens are not ring atoms.
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


def annotate(mol: Chem.Mol) -> StructureAnnotation:
    """Annotate a molecule with everything the nomenclature engine perceives.

    Never raises. The vendored engine is large and its failure modes are its
    own; an annotation is an enhancement to a view, and one molecule it
    cannot parse must degrade to an empty annotation carrying the reason,
    not take down the panel showing it. This mirrors how
    `QuantumChemistryService` treats a spectrum it cannot parse.

    Costs one `Perception` construction plus one naming pass. Measured over
    the 181-molecule naming corpus: **8.0 ms mean, 59.3 ms worst case**.
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

    # Naming is a separate, more failure-prone pass than perception, and it
    # only contributes locants and decisions. A molecule the namer chokes on
    # still gets its rings, groups and stereocentres.
    locants, decisions = _locants_and_decisions(
        mol, perception.rings.ring_systems
    )

    return StructureAnnotation(
        atom_count=atom_count,
        locants=locants,
        groups=groups,
        rings=rings,
        features=features,
        stereocenters=stereocenters,
        decisions=decisions,
    )


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
        from openchem.vendor.iupac_namer.strategy import IUPACCanonical
        from openchem.vendor.iupac_namer.types import (
            FreeValenceInfo,
            OutputForm,
            SubstituentMethod,
        )

        if attachment is None:
            # A whole disconnected molecule was selected: there is no free
            # valence, so it gets its ordinary standalone name.
            tree = build_name_tree(fragment, IUPACCanonical())
        else:
            free_valence = FreeValenceInfo(
                bond_orders=(1,),
                method=SubstituentMethod.ALKANYL,
                attachment_atoms_in_fragment=(index_map[attachment],),
                elide_locant_one=True,
            )
            tree = build_name_tree(
                fragment,
                IUPACCanonical(),
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
        from openchem.vendor.iupac_namer.strategy import IUPACCanonical

        tree = build_name_tree(mol, IUPACCanonical())
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
    return f"{numbered} of {total} atoms numbered from the parent chain."


#: How a functional group should be labelled on the depiction.
FG_LABEL_MODES: dict[str, str] = {
    "Group name": "name",
    "Prefix form": "prefix",
}
_DEFAULT_FG_LABEL_MODE = "Group name"


def compute_functional_groups(
    mol: Chem.Mol,
    molecule_uuid: str,
    parameters: dict[str, Any] | None = None,
) -> PerAtomDataset:
    """Functional groups, coloured by type -- the group explorer.

    COLOURS ARE ASSIGNED WITHIN THE MOLECULE, not fixed per group type, and
    that is the opposite of the call `compute_stereocenters` makes. The two
    cases genuinely differ. R and S are a closed pair whose colour carries
    the meaning, so a fixed mapping is a correctness requirement there. The
    group vocabulary is 114 types against a 7-colour palette, so a fixed
    mapping would collide constantly *within* one molecule -- and here the
    meaning is carried by the label, not the colour, whose only job is to
    separate one group from its neighbour. Distinctness in the molecule
    being looked at therefore wins over consistency between molecules.

    Assignment is by sorted type name rather than by detection order, so the
    same molecule always renders identically and two molecules with the same
    groups agree with each other.

    Lactams, anionic acids and other ring-embedded carbonyls are claimed by
    nothing -- see the module docstring for the measured shape of that. It
    is why `groups_detected` is reported in provenance: a view needs to be
    able to say "none found" rather than leave a molecule silently bare.
    """
    label_mode = FG_LABEL_MODES.get(
        (parameters or {}).get("label_mode", _DEFAULT_FG_LABEL_MODE), "name"
    )
    only_suffix_eligible = bool(
        (parameters or {}).get("only_suffix_eligible", False)
    )
    annotation = annotate(mol)

    provenance_parameters: dict[str, Any] = {
        "scale": "categorical",
        "decimal_places": 0,
        "label_mode": label_mode,
        "only_suffix_eligible": only_suffix_eligible,
    }

    if annotation.error:
        return PerAtomDataset(
            property_id="functional_groups",
            name="Functional Groups",
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

    features = collect_features(mol, annotation, label_mode=label_mode)
    if only_suffix_eligible:
        suffix_atoms = {
            tuple(sorted(group.atoms))
            for group in annotation.groups
            if group.suffix_eligible
        }
        features = [
            feature
            for feature in features
            if tuple(sorted(feature.atoms)) in suffix_atoms
        ]

    # Sorted by (category, key) so the colour mapping is deterministic for a
    # given molecule and two molecules sharing a feature agree on its colour.
    kinds = sorted({(feature.category.value, feature.key) for feature in features})
    category_of = {kind: position + 1 for position, kind in enumerate(kinds)}

    values: dict[int, float] = {}
    atom_notes: dict[int, str] = {}
    category_labels: dict[int, str] = {}

    for feature in features:
        category = category_of[(feature.category.value, feature.key)]
        category_labels[category] = feature.label
        for atom_index in feature.atoms:
            values[atom_index] = float(category)
        # Only the ANCHOR is labelled, not every atom the feature covers.
        # Repeating "carboxylic acid" on all three of its atoms is noise on
        # a small depiction, and the anchor is the atom the name belongs to.
        atom_notes[feature.anchor] = feature.label

    provenance_parameters["atom_notes"] = atom_notes
    provenance_parameters["category_labels"] = category_labels
    provenance_parameters["groups_detected"] = len(features)
    provenance_parameters["vocabulary_version"] = VOCABULARY_VERSION
    # EVERY INSTANCE, WITH ITS PROVENANCE. A view that shows "tertiary amine"
    # cannot otherwise say which detector claimed it or on which atoms, and
    # "the right label on the wrong atoms" is the failure mode a merged
    # vocabulary invites.
    provenance_parameters["features"] = [
        {
            "key": feature.key,
            "category": feature.category.value,
            "label": feature.label,
            "source": feature.source.value,
            "found_by": [source.value for source in feature.found_by],
            "atoms": sorted(feature.atoms),
            "anchor": feature.anchor,
        }
        for feature in features
    ]
    provenance_parameters["summary"] = _feature_summary(features)

    return PerAtomDataset(
        property_id="functional_groups",
        name="Functional Groups",
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


def collect_features(
    mol: Chem.Mol,
    annotation: StructureAnnotation,
    label_mode: str = "name",
) -> list[FeatureInstance]:
    """Every feature of `mol`, from all three sources, merged.

    THREE SOURCES, ONE VOCABULARY:

        annotation.groups     the naming engine's detector (the suffix
                              candidates and the prefixes it emits)
        annotation.features   the engine's `structural_groups` table -- ring
                              amines, aromatic N-H
        annotation.rings      ring systems, which `AnnotatedRing` already
                              models; NOT re-detected here, so there is one
                              place that says what a ring system is
        `functional_group_patterns.PATTERNS`   the chemist's vocabulary that
                              nomenclature has no group for at all (ether,
                              thioether, ammonium)

    Identical identities merge with the naming engine canonical; features
    that merely share atoms all survive. See `merge_features`.
    """
    candidates: list[FeatureInstance] = []
    for group in annotation.groups:
        candidates.append(
            FeatureInstance(
                key=group.type,
                category=FeatureCategory.FUNCTIONAL_GROUP,
                atoms=frozenset(group.atoms),
                anchor=group.anchor,
                label=_describe_group(group, label_mode),
                source=FeatureSource.NAMING_ENGINE,
                found_by=(FeatureSource.NAMING_ENGINE,),
            )
        )
    for feature in annotation.features:
        candidates.append(
            FeatureInstance(
                key=feature.type,
                category=_FEATURE_CATEGORIES.get(
                    feature.category, FeatureCategory.FUNCTIONAL_GROUP
                ),
                atoms=frozenset(feature.atoms),
                anchor=feature.anchor,
                label=ENGINE_FEATURE_LABELS.get(
                    feature.type, feature.type.replace("_", " ")
                ),
                source=FeatureSource.NAMING_ENGINE,
                found_by=(FeatureSource.NAMING_ENGINE,),
            )
        )
    for ring in annotation.rings:
        candidates.append(
            FeatureInstance(
                # The ring's NAME is the key when there is one, so two
                # benzene rings are two instances of one key rather than two
                # unrelated "monocyclic" blobs.
                key=ring.name or ring.kind,
                category=FeatureCategory.RING_SYSTEM,
                atoms=frozenset(ring.atoms),
                anchor=min(ring.atoms) if ring.atoms else 0,
                label=ring.name or f"{ring.kind} ring system",
                source=FeatureSource.NAMING_ENGINE,
                found_by=(FeatureSource.NAMING_ENGINE,),
            )
        )
    for match in match_patterns(mol):
        candidates.append(
            FeatureInstance(
                key=match.spec.key,
                category=match.spec.category,
                atoms=frozenset(match.atoms),
                anchor=match.anchor,
                label=match.spec.label,
                source=FeatureSource.STRUCTURAL_PATTERN,
                found_by=(FeatureSource.STRUCTURAL_PATTERN,),
            )
        )
    return merge_features(candidates)


#: The engine declares its structural groups' category as a plain string.
_FEATURE_CATEGORIES: dict[str, FeatureCategory] = {
    "functional_group": FeatureCategory.FUNCTIONAL_GROUP,
    "structural_feature": FeatureCategory.STRUCTURAL_FEATURE,
    "ring_system": FeatureCategory.RING_SYSTEM,
}

#: What each category is called in the summary line, singular and plural.
_CATEGORY_WORDS: dict[FeatureCategory, tuple[str, str]] = {
    FeatureCategory.FUNCTIONAL_GROUP: ("functional group", "functional groups"),
    FeatureCategory.STRUCTURAL_FEATURE: ("structural feature", "structural features"),
    FeatureCategory.RING_SYSTEM: ("ring system", "ring systems"),
}


def _feature_summary(features: list[FeatureInstance]) -> str:
    """One sentence saying what was found, BY KIND.

    The kinds are kept apart because they are different claims: "3 features"
    over an amide, a benzene ring and an indole N-H would invite reading all
    three as functional groups.
    """
    if not features:
        return (
            "Nothing matched. Note that ring carbonyls next to a ring "
            "nitrogen (lactams, uracil, caffeine) are claimed by no group, "
            "so this does not always mean the structure has none."
        )
    counts: dict[FeatureCategory, int] = {}
    for feature in features:
        counts[feature.category] = counts.get(feature.category, 0) + 1
    parts = []
    for category, (singular, plural) in _CATEGORY_WORDS.items():
        count = counts.get(category, 0)
        if count:
            parts.append(f"{count} {singular if count == 1 else plural}")
    return ", ".join(parts) + "."


def _describe_group(group: AnnotatedGroup, label_mode: str) -> str:
    """A group's label.

    The prefix form ("carboxy", "hydroxy") is what the group is CALLED in a
    name, which is the more useful label when the point is to read the
    structure the way the namer does. The type name is the more familiar one
    otherwise, so it is the default -- with underscores turned back into
    spaces, since `secondary_amide` is the detector's identifier rather than
    anything a chemist writes.
    """
    if label_mode == "prefix" and group.prefix_form:
        return group.prefix_form
    return group.type.replace("_", " ")


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
    return _name_ring_skeleton(key) if key else None


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
        from openchem.vendor.iupac_namer.strategy import IUPACCanonical

        tree = build_name_tree(mol, IUPACCanonical())
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
        from openchem.vendor.iupac_namer.data_loader import _RING_CURATED_SMILES
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

        entry = _RING_CURATED_SMILES.get(key)
        if not entry:
            continue
        atom_locants = entry.get("atom_locants")
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
