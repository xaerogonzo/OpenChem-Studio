"""Tautomer distribution: candidate generation, deterministic 3D embedding,
and population estimation from ORCA-computed electronic energies.

**What this is, precisely.** A gas-phase electronic-energy Boltzmann
population ESTIMATE over the lowest calculated minimum of each enumerated
tautomer -- not a full equilibrium probability model. There is no vibrational,
thermal, or entropic correction and no solvent model. Since model revision 4 each
stereoisomer gets a SAMPLED conformer search (`chem/tautomer_conformers.py`), not
an exhaustive one; revision 3 optimized one embedded start geometry, which put
acetylacetone's enol 14.7 kcal/mol too high. `enumerate_tautomers`
(`chem/structure_generators.py`) already flags one tautomer "(canonical)"
using RDKit's own internal empirical scoring rules -- useful, but not a
probability, not an energy, and not validated against anything. This module
is the real thing: real ORCA energies, Boltzmann-weighted
(`chem/boltzmann.py`'s own `boltzmann_weights`, unmodified), with an
explicit, auditable incomplete-run story when not every candidate succeeds.

Orchestrating the actual ORCA jobs (sequential, one logical operation, one
`QuantumChemistryRun`) lives in `services/quantum_chemistry_service.py`,
mirroring its own existing `_BoltzmannRun`/`_finish_conformer_job`
machinery for "N QC jobs over N candidate structures of one molecule, one
Boltzmann-combined result" -- this module only does the chemistry-layer,
Qt-free pieces: which candidates exist, what their stable identity is, how
they get a 3D starting geometry, and what the final numbers mean.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field, fields
from enum import Enum

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers, StereoEnumerationOptions
from rdkit.Chem.MolStandardize import rdMolStandardize

from openchem.chem.boltzmann import STANDARD_TEMPERATURE_K, boltzmann_weights
from openchem.chem.conformer_providers import DEFAULT_ENERGY_WINDOW, DEFAULT_RMS_THRESHOLD
from openchem.chem.tautomer_conformers import (
    SEARCH_FULL,
    SEARCH_SINGLE,
    SEARCH_TOPK,
    build_pool,
    etkdg_signature,
)
from openchem.chem.tautomer_ranking import RDKIT_VERSION, cross_check, score_tautomer
from openchem.domain.common import Provenance
from openchem.domain.scientific_result import StructureEntry, StructureSetResult

#: 1 Hartree in kcal/mol (CODATA) -- the exact constant this project's own
#: Boltzmann tests already use (`tests/test_boltzmann.py`'s `KCAL_PER_MOL`
#: is `1 / this value`). Display-only: `boltzmann_weights` itself keeps
#: taking raw Hartree throughout, never this converted value.
HARTREE_TO_KCAL_PER_MOL = 627.5094740631

#: Matches `structure_generators.DEFAULT_MAX_STRUCTURES` -- the RDKit
#: enumerator's own cap, which is free. The expensive-QC cap below is a
#: separate, much smaller number.
DEFAULT_MAX_CANDIDATES = 200

#: Candidates at or under this count queue without confirmation; above it,
#: the caller must show the user the actual count ("this will run N
#: geometry optimizations with ORCA") before queuing them. This is
#: OpenChem's own expensive-QC-work threshold, not Marvin's unrelated
#: "eight tautomers shown at once" display convention -- chosen to land
#: near it, but justified by cost here, not by what Marvin's viewer shows.
CONFIRMATION_THRESHOLD = 8

#: A population below this is shown as "<0.01%" rather than a bare
#: "0.00%", which would read as exactly zero. Applied at display time only
#: -- the stored `population` value is always the full-precision weight
#: `boltzmann_weights` returned, never pre-rounded.
_SMALL_POPULATION_DISPLAY_FLOOR = 0.0001


#: The most UNIQUE stereo jobs (after enantiomer deduplication) one tautomer
#: may queue. A cost cap on ORCA work, so it counts what would actually be
#: submitted, never the raw number RDKit emits: five enantiomer pairs are ten
#: raw isomers and five jobs, and must not read as truncated at 8.
MAX_STEREOISOMERS_PER_TAUTOMER = 8

#: Generation of the algorithm/schema (what a result's structure means).
#: Distinct from `ModelPolicy`, which is the exact configuration: a change to
#: how the stereo search works bumps this even if every policy value is kept.
#: Revision 2 was #177's pinned single configuration; 3 enumerates stereoisomers;
#: 4 adds a conformer search per stereo class (`chem.tautomer_conformers`); 5 tells
#: aromatic tautomers apart (revision 4 merged any two that differ only in which ring
#: nitrogen carries the hydrogen, so an azole's other tautomer was never calculated).
TAUTOMER_MODEL_REVISION = 5


@dataclass(frozen=True)
class ModelPolicy:
    """The scientific-model choices that define what a tautomer distribution
    MEANS, as machine-readable values.

    **THE MODEL IDENTITY IS BUILT FROM THESE VALUES, NEVER FROM THE ENGLISH
    IN `model_assumptions`.** Hashing prose would mint a new scientific model
    whenever a sentence was reworded, which is the opposite of what a model
    version is for. The sentences shown to the user are derived FROM this.

    Frozen on purpose: no invocation may alter global model identity.
    """

    #: Most unique stereo jobs queued per tautomer.
    stereo_cap: int = MAX_STEREOISOMERS_PER_TAUTOMER
    #: An enantiomer pair is calculated once (identical energies in an
    #: achiral gas-phase model).
    enantiomer_policy: str = "dedupe_mirror"
    #: Merging a pair inverts tetrahedral configuration ONLY; E/Z isomers are
    #: never merged.
    bond_stereo_policy: str = "preserve"
    #: A tautomer is represented by its lowest SUCCESSFUL stereoisomer.
    tautomer_representative: str = "lowest_successful_stereo"
    #: One tautomer is one statistical state: stereochemical degeneracy
    #: (an enantiomer pair's multiplicity, diastereomer partition weights) is
    #: intentionally NOT included.
    state_degeneracy: str = "unit"
    #: No population is shown over an incomplete set.
    incomplete_population_policy: str = "withhold"
    #: How a stereo class's start geometries are chosen: one embedded geometry
    #: (`single`, what revision 3 computed), the `topk` lowest distinct MMFF
    #: conformers (`mmff_topk`), or every retained conformer of the sampled, pruned
    #: pool up to `conformer_cap` (`full_orca`, NOT exhaustive enumeration).
    conformer_search: str = SEARCH_TOPK
    #: Embedding engine and release: ETKDG, the force fields and their ordering are
    #: implementation-defined, so a different RDKit is a different pool.
    conformer_engine: str = f"rdkit-{RDKIT_VERSION}-etkdgv3"
    #: The EFFECTIVE embedding parameters (`tautomer_conformers.etkdg_signature`).
    conformer_embed_params: str = etkdg_signature()
    #: Embedding attempts per stereo class.
    conformer_embeds: int = 50
    #: Conformers sent to ORCA per stereo class under `mmff_topk`.
    conformer_topk: int = 3
    #: Hard cap per stereo class under `full_orca`; above it the class is truncated.
    conformer_cap: int = 10
    #: Distinctness: heavy atoms plus polar hydrogens, symmetry-aware, with the
    #: energy veto, exactly `conformer_providers.distinct_conformers`.
    conformer_prune: str = (
        f"distinct_conformers(skeleton_polar_h,rms={DEFAULT_RMS_THRESHOLD},window={DEFAULT_ENERGY_WINDOW})"
    )
    #: Scoring rule for the pool. A RULE, so the model says what happens where MMFF
    #: has no parameters instead of that being a runtime surprise.
    conformer_prefilter: str = "mmff94_with_uff_fallback"
    conformer_prefilter_max_iters: int = 2000

    def canonical(self) -> str:
        """One deterministic serialization (declaration order), so equal
        policies can never yield different version strings."""
        return ";".join(f"{f.name}={getattr(self, f.name)}" for f in fields(self))


#: The policies a result can be computed under. Frozen and fixed: choosing between
#: them is a setting, mutating one is not possible. **They are different SCIENTIFIC
#: MODELS** (`model_version` differs), so each needs its own validation record
#: before it may show a percentage; the full mode never inherits the top-K one.
MODEL_POLICY_TOPK = ModelPolicy()
#: Every distinct conformer of the sampled pool is optimized, up to the cap.
MODEL_POLICY_FULL = ModelPolicy(conformer_search=SEARCH_FULL)
#: Revision 3's behaviour (one embedded start geometry per stereo class), kept so
#: its results stay interpretable and its tests stay honest.
MODEL_POLICY_SINGLE = ModelPolicy(conformer_search=SEARCH_SINGLE)
#: The policy every result is computed under unless one is passed.
MODEL_POLICY = MODEL_POLICY_TOPK


def policy_for_mode(full_orca: bool) -> ModelPolicy:
    """The policy the "Full ORCA conformer optimization" setting selects."""
    return MODEL_POLICY_FULL if full_orca else MODEL_POLICY_TOPK


def model_assumptions(policy: ModelPolicy = MODEL_POLICY) -> tuple[str, ...]:
    """The human-readable form of `policy`, for the result's own text. Derived,
    never hashed: rewording a sentence here changes no model version."""
    out: list[str] = []
    if policy.enantiomer_policy == "dedupe_mirror" and policy.state_degeneracy == "unit":
        out.append(
            "Enantiomer multiplicity is computationally deduplicated and statistically "
            "assigned unit degeneracy."
        )
    if policy.tautomer_representative == "lowest_successful_stereo":
        out.append(
            "A tautomer's weight comes from its lowest successful stereoisomer; higher-energy "
            "diastereomers are retained for audit and display but contribute no separate "
            "statistical weight."
        )
    out.append(
        f"At most {policy.stereo_cap} unique stereoisomers are calculated per tautomer; beyond "
        "that the tautomer uses one fallback configuration and the result is marked incomplete."
    )
    if policy.conformer_search == SEARCH_SINGLE:
        out.append(
            "One embedded start geometry is optimized per stereoisomer; no conformer search was "
            "done, so a tautomer's rotamers are not explored."
        )
    elif policy.conformer_search == SEARCH_TOPK:
        out.append(
            f"Conformer search: {policy.conformer_embeds} ETKDG conformers per stereoisomer are "
            f"scored with a force field and reduced to the distinct set; the {policy.conformer_topk} "
            "lowest are optimized with ORCA. This is a sampled search, not exhaustive: a tautomer "
            "is complete when every conformer the policy selected succeeded."
        )
    elif policy.conformer_search == SEARCH_FULL:
        out.append(
            f"Conformer search: {policy.conformer_embeds} ETKDG conformers per stereoisomer are "
            f"scored with a force field and reduced to the distinct set; every one, up to "
            f"{policy.conformer_cap}, is optimized with ORCA. This is every conformer of the "
            "sampled pool, not exhaustive enumeration; beyond the cap the tautomer is incomplete."
        )
    if policy.incomplete_population_policy == "withhold":
        out.append("No population is shown when any tautomer is incomplete.")
    return tuple(out)


def _tautomer_fingerprint(tautomer: Chem.Mol) -> str:
    """A tautomer's identity: its pre-embedding molblock AND its isomeric SMILES.

    **THE MOLBLOCK ALONE IS NOT ENOUGH, AND THAT WAS MEASURED.** A molblock states atoms and
    bonds, not how many hydrogens an aromatic nitrogen carries, so 1H- and 2H-indazole, the two
    triazole pairs and hypoxanthine's N7-H and N9-H forms wrote IDENTICAL molblocks and were
    merged into one candidate: the app calculated one structure of a two-state system and
    reported it complete. (Plain RDKit enumerates all of them; the loss was here.) The SMILES
    carries the hydrogen placement, so two tautomers that differ only there never collide."""
    return _fingerprint(
        Chem.MolToMolBlock(tautomer, kekulize=False) + "|" + Chem.MolToSmiles(tautomer, isomericSmiles=True)
    )


def _fingerprint(molblock: str) -> str:
    """A candidate's stable identity: SHA-256 over its EXACT pre-embedding
    molblock text, never a canonicalized form -- the same technique
    `chem.calculation_input._fingerprint` uses, for the same reason (a
    cosmetic difference and a real structural difference must never
    collide). Taken before 3D embedding and never regenerated from the
    optimized geometry: different optimized coordinates for the same
    enumerated tautomer must not become a different candidate."""
    return hashlib.sha256(molblock.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StereoStatus:
    """What the stereo search did for one candidate's TAUTOMER.

    These are facts about how the search went. Whether the tautomer is
    scientifically complete is NEVER read back from them: `TautomerState` is
    the one authority, derived once in `build_outcome`, so a consumer cannot
    reconstruct completeness from `isomers_calculated == isomers_total` (which
    deduplication and the fallback make mean different things).
    """

    #: This candidate's enumeration index within its tautomer, THIS run only.
    #: Presentation and provenance: RDKit's enumeration order may change
    #: between releases, so it is never identity, a lookup key or a mapping key.
    index: int = 0
    #: True when the cap was exceeded and this is the single fallback
    #: configuration, a SUCCESSFUL optimization of an INCOMPLETE stereo search.
    fallback: bool = False
    fallback_reason: str = ""
    #: This candidate stands for an enantiomer pair, calculated once.
    enantiomer_merged: bool = False
    #: Exact number of UNIQUE stereo classes when the search finished under the
    #: cap, else `None` (more than the cap; never a fabricated count).
    isomers_total: int | None = 1
    isomers_total_known: bool = True
    #: Unique candidates actually queued for this tautomer.
    isomers_calculated: int = 1
    truncated: bool = False
    #: Classes of this tautomer whose 3D embedding failed and were dropped, so
    #: its stereo search is incomplete even if every queued job succeeds.
    embedding_failed: int = 0


@dataclass(frozen=True)
class ConformerStatus:
    """What the conformer search did for one candidate's STEREO CLASS, and which
    conformer this candidate is. Facts about how the search went: completeness is
    still read only from `TautomerState`.

    The default is the revision-3 situation (one embedded geometry, no search).
    """

    #: `tautomer_conformers.SEARCH_*`: the policy this candidate was made under.
    search: str = SEARCH_SINGLE
    #: Position among the SELECTED conformers (lowest prefilter energy first),
    #: assigned after selection. Presentation only, never identity.
    index: int = 0
    #: Identity: how this conformer was made (`tautomer_conformers.recipe_fingerprint`).
    recipe_fingerprint: str = ""
    #: The stereo class this conformer belongs to (the revision-3 candidate fingerprint).
    stereo_fingerprint: str = ""
    seed: int = 0
    #: Per STEREO CLASS, never per tautomer.
    generated: int = 1
    distinct: int = 1
    selected: int = 1
    #: `full_orca` only: more distinct conformers than the cap.
    truncated: bool = False
    #: The force field that scored the pool (`mmff94` / `uff`); empty without a search.
    prefilter: str = ""
    prefilter_energy_kcal: float | None = None
    prefilter_ok: int = 0
    prefilter_failed: int = 0
    retained_recipes: tuple[str, ...] = ()
    selected_recipes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TautomerCandidate:
    """One stereo-specified candidate of one enumerated tautomer,
    deduplicated, embedded in 3D, ready for a geometry-optimization QC job.

    Identity chain: the unspecified tautomer's fingerprint
    (`tautomer_fingerprint`) -> this candidate's fingerprint (over the
    stereo-specified PRE-embedding structure) -> embedded start geometry ->
    ORCA result. Never from optimized coordinates.
    """

    fingerprint: str
    mol: Chem.Mol  # embedded: AddHs + a real 3D conformer
    embedding_seed: int
    #: What the result shows and labels this candidate with. Real wedges only
    #: when the tautomer has more than one stereo job (or fell back), where the
    #: configuration is what tells them apart; otherwise the structure AS
    #: DRAWN -- see `_display_molblock`.
    display_molblock: str = ""
    tautomer_fingerprint: str = ""
    stereo: StereoStatus = field(default_factory=StereoStatus)
    #: RDKit's raw heuristic preference score for this candidate's tautomer
    #: (`chem.tautomer_ranking`). Informational only: it never feeds a
    #: population, an energy or the validation gate.
    rdkit_score: float | None = None
    conformer: ConformerStatus = field(default_factory=ConformerStatus)


def _stereo_elements(mol: Chem.Mol) -> tuple[list[int], list[int], int]:
    """`(unspecified centre atoms, unspecified double bonds, specified count)`.

    `Unknown` counts as unspecified: the tautomer enumerator marks a bond it
    has just created `STEREOANY`, which ETKDG treats as free -- measured, an
    acyclic enol's C=C embeds E and Z across seeds."""
    atoms: list[int] = []
    bonds: list[int] = []
    specified = 0
    for info in Chem.FindPotentialStereo(mol):
        if info.type == Chem.StereoType.Atom_Tetrahedral:
            target = atoms
        elif info.type == Chem.StereoType.Bond_Double:
            target = bonds
        else:
            continue
        if info.specified == Chem.StereoSpecified.Specified:
            specified += 1
        else:
            target.append(info.centeredOn)
    return atoms, bonds, specified


#: Tetrahedral tag -> its mirror image. Deliberately TETRAHEDRAL ONLY (see
#: `_mirror_stereo`): double-bond stereo has no handedness.
_MIRRORED_TAGS = {
    Chem.ChiralType.CHI_TETRAHEDRAL_CW: Chem.ChiralType.CHI_TETRAHEDRAL_CCW,
    Chem.ChiralType.CHI_TETRAHEDRAL_CCW: Chem.ChiralType.CHI_TETRAHEDRAL_CW,
}


def _mirror_stereo(mol: Chem.Mol) -> Chem.Mol:
    """The mirror image: every TETRAHEDRAL tag inverted and nothing else.

    **NEVER A GENERIC "FLIP EVERY STEREO TAG".** That would turn an E bond
    into a Z one and merge a pair of genuinely different isomers as
    "enantiomers"; double-bond stereo has no handedness and is untouched.
    """
    mirror = Chem.Mol(mol)
    for atom in mirror.GetAtoms():
        flipped = _MIRRORED_TAGS.get(atom.GetChiralTag())
        if flipped is not None:
            atom.SetChiralTag(flipped)
    Chem.AssignStereochemistry(mirror, cleanIt=True, force=True)
    return mirror


def _stereo_class_key(isomer: Chem.Mol) -> str:
    """Equal for an isomer and its mirror image, distinct for everything else.

    ISOMERIC SMILES on both sides: a non-isomeric comparison would collapse
    structures that must stay distinct. With a drawn centre in the molecule the
    mirror of one generated isomer is never another generated isomer (their
    drawn centre would have to invert too), so diastereomers are never merged.
    """
    own = Chem.MolToSmiles(isomer, isomericSmiles=True)
    mirror = Chem.MolToSmiles(_mirror_stereo(isomer), isomericSmiles=True)
    return min(own, mirror)


@dataclass(frozen=True)
class _StereoSearch:
    #: `(isomer, stands_for_an_enantiomer_pair)` per unique class, in
    #: enumeration order. When truncated: the single fallback only.
    classes: list[tuple[Chem.Mol, bool]]
    total: int | None
    total_known: bool
    truncated: bool
    #: The tautomer had stereo elements the structure left unspecified.
    unspecified: bool


def _enumerate_stereo_classes(tautomer: Chem.Mol, cap: int) -> _StereoSearch:
    """Every unique stereo class of `tautomer`'s UNSPECIFIED elements, lazily,
    stopping as soon as more than `cap` unique classes have been seen.

    Counting unique classes (not raw RDKit output) keeps the cap a cost
    control on ORCA jobs. `maxIsomers=0` matters: any other value makes RDKit
    SAMPLE at random once the combinations exceed it, which would make the
    fallback configuration differ from run to run.
    """
    atoms, bonds, _specified = _stereo_elements(tautomer)
    if not atoms and not bonds:
        return _StereoSearch([(Chem.Mol(tautomer), False)], 1, True, False, False)

    options = StereoEnumerationOptions(
        onlyUnassigned=True, unique=True, tryEmbedding=False, maxIsomers=0
    )
    # key -> [(own SMILES, isomer), ...]: one member, or two when the class is
    # an enantiomer pair (its mirror image was enumerated as well).
    classes: dict[str, list[tuple[str, Chem.Mol]]] = {}
    truncated = False
    for isomer in EnumerateStereoisomers(tautomer, options=options):
        key = _stereo_class_key(isomer)
        own = Chem.MolToSmiles(isomer, isomericSmiles=True)
        if key in classes:
            classes[key].append((own, isomer))  # its mirror image: same energy, calculated once
            continue
        if len(classes) >= cap:
            truncated = True
            break
        classes[key] = [(own, isomer)]
    if not classes:
        return _StereoSearch([(Chem.Mol(tautomer), False)], 1, True, False, True)

    def representative(key: str, members: list[tuple[str, Chem.Mol]]) -> Chem.Mol:
        # For an enantiomer pair, the member whose own SMILES IS the class key:
        # the same structure whichever mirror image RDKit happened to list
        # first, so identity and start geometry never depend on its ordering.
        for own, isomer in members:
            if own == key:
                return isomer
        return members[0][1]

    if truncated:
        key, members = next(iter(classes.items()))
        return _StereoSearch([(representative(key, members), False)], None, False, True, True)
    return _StereoSearch(
        [(representative(key, members), len(members) > 1) for key, members in classes.items()],
        len(classes),
        True,
        False,
        True,
    )


#: `StereoStatus.fallback_reason` when a tautomer had more unique stereo classes
#: than the cap and only the single fallback configuration was calculated.
FALLBACK_ENUMERATION_CAP_EXCEEDED = "enumeration_cap_exceeded"


def _candidate_fingerprint(
    tautomer_fingerprint: str, tautomer: Chem.Mol, isomer: Chem.Mol, has_unspecified: bool
) -> str:
    """The candidate's identity. A tautomer with nothing to enumerate keeps its
    own fingerprint (unchanged from before stereo enumeration); otherwise the
    stereo-specified structure is part of the hashed text, so two candidates
    differing in one retained centre or one E/Z bond can never collide. A
    molblock without coordinates carries no stereo, hence the isomeric SMILES."""
    if not has_unspecified:
        return tautomer_fingerprint
    molblock = Chem.MolToMolBlock(tautomer, kekulize=False)
    return _fingerprint(molblock + "|" + Chem.MolToSmiles(isomer, isomericSmiles=True))


def _display_molblock(tautomer: Chem.Mol) -> str:
    """A 2D drawing of one tautomer, with exactly the stereo it was given.

    **THE 3D START GEOMETRY MUST NOT BE WHAT IS SHOWN.** ORCA needs real
    coordinates, and embedding picks ONE spatial arrangement for every
    stereocentre the input left unspecified. Reading chirality back off that
    3D molblock (what `Chem.MolFromMolBlock` does) then labels a racemic
    propylene glycol `C[C@@H](O)CO` -- a specific enantiomer nobody drew.
    The energies are unaffected (enantiomers are degenerate), but the label
    claimed a compound that was never specified. This is built from the
    pre-embedding tautomer instead, so an undrawn centre stays undrawn and a
    drawn one (a wedge the user placed) is kept.
    """
    flat = Chem.Mol(tautomer)
    flat.RemoveAllConformers()
    AllChem.Compute2DCoords(flat)
    Chem.WedgeMolBonds(flat, flat.GetConformer())
    return Chem.MolToMolBlock(flat)


def generate_tautomer_candidates(
    mol: Chem.Mol,
    max_tautomers: int = DEFAULT_MAX_CANDIDATES,
    base_seed: int = 0,
    stereo_cap: int | None = None,
    policy: ModelPolicy = MODEL_POLICY,
) -> tuple[list[TautomerCandidate], int]:
    """Enumerates, deduplicates, deterministically orders, and embeds every
    tautomer RDKit's standardizer can reach from `mol` -- and, for each
    tautomer, every unique stereoisomer of the elements the structure leaves
    unspecified (up to `stereo_cap`; see `_enumerate_stereo_classes`).

    `policy` decides the conformer search (`chem.tautomer_conformers`): each stereo
    class yields one candidate under `single`, or one per SELECTED conformer under
    `mmff_topk` / `full_orca`, so the number of candidates is the number of ORCA jobs.

    Returns `(candidates, embedding_failures)`. A candidate whose 3D
    embedding fails is dropped and counted, never silently merged into the
    others nor silently absent with no record at all -- the caller is
    expected to surface `embedding_failures` the same way it surfaces a
    failed QC job (see `CandidateStatus.FAILED`). The survivors of a tautomer
    whose sibling failed to embed carry `stereo.embedding_failed`, so that
    tautomer is reported incomplete rather than looking fully searched.

    Deliberately duplicates `structure_generators.enumerate_tautomers`'s
    own `TautomerEnumerator` setup rather than calling it: that function
    returns 2D-only `StructureEntry` molblocks for the structure grid, and
    must stay unchanged for its own existing callers/tests -- this needs
    raw, 3D-embeddable `Chem.Mol` objects instead.
    """
    # An explicit `stereo_cap` overrides the policy's for a test that needs a tiny
    # cap; a result computed that way does not match its model version, which is
    # why production code passes only `policy`.
    stereo_cap = policy.stereo_cap if stereo_cap is None else stereo_cap
    enumerator = rdMolStandardize.TautomerEnumerator()
    enumerator.SetMaxTautomers(max_tautomers)
    tautomers = list(enumerator.Enumerate(mol))

    # Deduplicate by the same fingerprint used for candidate identity below
    # -- two enumerator outputs serializing to the same molblock become one
    # candidate, not two -- and sort by it, so queue order is deterministic
    # and independent of the enumerator's own (incidental) ordering.
    by_fingerprint: dict[str, Chem.Mol] = {}
    for tautomer in tautomers:
        by_fingerprint.setdefault(_tautomer_fingerprint(tautomer), tautomer)

    candidates: list[TautomerCandidate] = []
    embedding_failures = 0
    for tautomer_index, tautomer_fingerprint in enumerate(sorted(by_fingerprint)):
        tautomer = by_fingerprint[tautomer_fingerprint]
        search = _enumerate_stereo_classes(tautomer, stereo_cap)
        # Real wedges only where the configuration distinguishes jobs. A lone
        # class standing for an enantiomer pair keeps the structure AS DRAWN:
        # showing one enantiomer would name a compound nobody specified.
        show_wedges = search.unspecified and (len(search.classes) > 1 or search.truncated)
        #: `(job fingerprint, embedded mol, seed, display, stereo index, merged, conformer)`
        embedded_here: list[tuple[str, Chem.Mol, int, str, int, bool, ConformerStatus]] = []
        failed_here = 0
        for stereo_index, (isomer, merged) in enumerate(search.classes):
            position = tautomer_index * (stereo_cap + 1) + stereo_index
            stereo_fingerprint = _candidate_fingerprint(
                tautomer_fingerprint, tautomer, isomer, search.unspecified
            )
            display = _display_molblock(isomer if show_wedges else tautomer)
            if policy.conformer_search == SEARCH_SINGLE:
                # Seed stable per (tautomer position, class index): adding a
                # tautomer elsewhere does not move this candidate's start geometry.
                embedded, seed = _embed_candidate(isomer, base_seed, position)
                if embedded is None:
                    failed_here += 1
                    embedding_failures += 1
                    continue
                embedded_here.append(
                    (stereo_fingerprint, embedded, seed, display, stereo_index, merged, ConformerStatus())
                )
                continue
            # +1: a pool seeded with 0 returns N IDENTICAL conformers (measured).
            pool_seed = 1 + base_seed + position
            pool = build_pool(
                isomer,
                stereo_fingerprint=stereo_fingerprint,
                seed=pool_seed,
                search=policy.conformer_search,
                embeds=policy.conformer_embeds,
                topk=policy.conformer_topk,
                cap=policy.conformer_cap,
                rms_threshold=DEFAULT_RMS_THRESHOLD,
                energy_window=DEFAULT_ENERGY_WINDOW,
                max_iters=policy.conformer_prefilter_max_iters,
                embed_policy=policy.canonical(),
            )
            if not pool.selected:
                # No usable conformer: the class is dropped and counted exactly as
                # an embedding failure is, which makes its tautomer INCOMPLETE.
                failed_here += 1
                embedding_failures += 1
                continue
            for member_index, member in enumerate(pool.selected):
                status = ConformerStatus(
                    search=policy.conformer_search,
                    index=member_index,
                    recipe_fingerprint=member.recipe_fingerprint,
                    stereo_fingerprint=stereo_fingerprint,
                    seed=pool.seed,
                    generated=pool.produced,
                    distinct=pool.distinct,
                    selected=len(pool.selected),
                    truncated=pool.truncated,
                    prefilter=pool.prefilter,
                    prefilter_energy_kcal=member.prefilter_energy,
                    prefilter_ok=pool.prefilter_ok,
                    prefilter_failed=pool.prefilter_failed,
                    retained_recipes=pool.retained_recipes,
                    selected_recipes=pool.selected_recipes,
                )
                embedded_here.append(
                    (
                        _fingerprint(stereo_fingerprint + "|conformer|" + member.recipe_fingerprint),
                        member.mol,
                        pool.seed,
                        display,
                        stereo_index,
                        merged,
                        status,
                    )
                )
        for fingerprint, embedded, seed, display, stereo_index, merged, conformer in embedded_here:
            candidates.append(
                TautomerCandidate(
                    fingerprint=fingerprint,
                    mol=embedded,
                    embedding_seed=seed,
                    display_molblock=display,
                    tautomer_fingerprint=tautomer_fingerprint,
                    rdkit_score=score_tautomer(tautomer),
                    conformer=conformer,
                    stereo=StereoStatus(
                        index=stereo_index,
                        fallback=search.truncated,
                        fallback_reason=FALLBACK_ENUMERATION_CAP_EXCEEDED if search.truncated else "",
                        enantiomer_merged=merged,
                        isomers_total=search.total,
                        isomers_total_known=search.total_known,
                        isomers_calculated=len(search.classes),
                        truncated=search.truncated,
                        embedding_failed=failed_here,
                    ),
                )
            )
    return candidates, embedding_failures


def _embed_candidate(mol: Chem.Mol, base_seed: int, index: int) -> tuple[Chem.Mol | None, int]:
    """One deterministic 3D embedding.

    Seed = `base_seed` offset by this candidate's own position in the
    already fingerprint-sorted list, not one shared seed consumed in
    sequence -- so a candidate's starting geometry stays stable
    independent of another candidate being added or removed. Same
    ETKDGv3 settings and random-coordinates retry
    `conformer_providers.py`'s own `_embed_one` uses, for the same reason:
    some strained/unusual structures fail ETKDG's distance-geometry pass
    on the first attempt.

    `Chem.AddHs` here only fills in currently-implicit hydrogens to match
    each atom's valence -- it does not move the tautomeric proton the
    enumerator already placed, so the candidate's intended protonation
    pattern survives into the embedded structure unchanged.
    """
    seed = base_seed + index
    conf_mol = Chem.AddHs(Chem.Mol(mol))
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    conf_id = AllChem.EmbedMolecule(conf_mol, params)
    if conf_id < 0:
        params.useRandomCoords = True
        conf_id = AllChem.EmbedMolecule(conf_mol, params)
    if conf_id < 0:
        return None, seed
    return conf_mol, seed


class CandidateStatus(str, Enum):
    """A candidate's own outcome -- deliberately NOT `RunStatus`
    (`domain/quantum_chemistry_run.py`), which describes a whole run's
    lifecycle and a candidate is not itself a run; and deliberately not an
    added value on the shared `OutputStatus` either, since that enum's
    existing values are used across unrelated output kinds this feature
    has no business extending. A small, new, explicitly-scoped vocabulary
    instead, named closely enough that its meaning is obvious next to
    those two."""

    #: A usable energy was obtained: embedded, optimized, converged, parsed.
    SUCCEEDED = "succeeded"
    #: Attempted (embedding or the QC job) but did not produce a usable
    #: energy -- `failure_reason_code` says which specific way.
    FAILED = "failed"
    #: Enumerated and deduplicated, but never reached before the parent
    #: operation was cancelled.
    NOT_RUN = "not_run"


#: Machine-readable categories for `CandidateResult.failure_reason_code` --
#: easier to test/filter than parsing `failure_reason`'s prose later.
#: This one: the candidate's 3D embedding itself failed (ETKDG could not
#: find a usable starting geometry), before any ORCA job was ever queued.
FAILURE_EMBEDDING_FAILED = "embedding_failed"
#: The ORCA job ran and finished, but produced no "FINAL SINGLE POINT
#: ENERGY" line -- the geometry optimization did not converge.
FAILURE_OPTIMIZATION_NOT_CONVERGED = "optimization_not_converged"
#: The ORCA job finished, but no `<provider_id>.scf_energy` descriptor
#: came back from the parsed output -- an energy this candidate's weight
#: could be computed from was never actually produced.
FAILURE_ENERGY_UNPARSEABLE = "energy_unparseable"
#: The QProcess itself crashed or errored (not a parse failure) -- see
#: `services/quantum_chemistry_service.py`'s `_report_job_failure`.
FAILURE_JOB_ERROR = "job_error"
#: The whole operation was cancelled before this candidate's job finished.
FAILURE_CANCELLED = "cancelled"


@dataclass(frozen=True)
class CandidateResult:
    """One candidate's outcome, win or lose -- every deduplicated
    candidate gets one of these, never only the successful ones (an
    omitted failed candidate would make the enumerated set look smaller
    than it was)."""

    fingerprint: str
    molblock: str
    status: CandidateStatus
    embedding_seed: int = 0
    absolute_energy_hartree: float | None = None
    failure_reason: str = ""
    failure_reason_code: str = ""
    #: What the result shows and labels this candidate with
    #: (`TautomerCandidate.display_molblock`). Empty falls back to `molblock`,
    #: the 3D start geometry.
    display_molblock: str = ""
    #: The unspecified tautomer this candidate is a stereo job of. Empty (a
    #: candidate built without one) means it is its own tautomer.
    tautomer_fingerprint: str = ""
    stereo: StereoStatus = field(default_factory=StereoStatus)
    rdkit_score: float | None = None
    conformer: ConformerStatus = field(default_factory=ConformerStatus)

    @property
    def tautomer_key(self) -> str:
        return self.tautomer_fingerprint or self.fingerprint

    @classmethod
    def for_candidate(
        cls, candidate: TautomerCandidate, molblock: str, status: CandidateStatus, **outcome
    ) -> CandidateResult:
        """The one place a candidate's identity and stereo facts are copied
        onto its result, so no construction site can forget one."""
        return cls(
            fingerprint=candidate.fingerprint,
            molblock=molblock,
            status=status,
            embedding_seed=candidate.embedding_seed,
            display_molblock=candidate.display_molblock,
            tautomer_fingerprint=candidate.tautomer_fingerprint,
            stereo=candidate.stereo,
            rdkit_score=candidate.rdkit_score,
            conformer=candidate.conformer,
            **outcome,
        )


class TautomerState(str, Enum):
    """Whether a TAUTOMER's energy is scientifically complete -- the sole
    authority on that, derived once in `build_outcome`. Never infer it from
    counts, and never from a candidate's own `SUCCEEDED`: the over-cap
    fallback is a successful optimization of an incomplete stereo search."""

    #: Every unique stereo candidate succeeded and the search was not truncated.
    COMPLETE = "complete"
    #: A stereo candidate failed, was not run or was dropped at embedding, or
    #: the search was truncated: the lowest successful stereoisomer is known
    #: but is not known to be the lowest stereoisomer.
    INCOMPLETE = "incomplete"
    #: No usable candidate.
    FAILED = "failed"


@dataclass(frozen=True)
class TautomerDistributionOutcome:
    """The result of Boltzmann-combining every successful tautomer's
    representative energy -- or the honest story when that is not possible.

    `relative_energy_kcal_mol` is keyed by candidate fingerprint and computed
    relative to the lowest SUCCESSFUL candidate's energy. **That baseline
    is only the true global minimum when `complete` is True** -- a failed
    candidate could have been lower still, which would shift every
    reported gap. Consumers MUST read `complete` (or `energy_reference`)
    before presenting this dict under an unqualified "ΔE" label; see
    `energy_label` below.

    `populations` (representative candidate fingerprint -> normalized weight,
    0..1) is `None` whenever `complete` is False, by construction -- a
    distribution normalized over only the survivors is a different, weaker
    claim than "the distribution," and this type makes that unrepresentable
    rather than merely undocumented. Populations are over TAUTOMERS (each by
    its lowest successful stereoisomer), never over stereo jobs.
    """

    candidates: tuple[CandidateResult, ...]
    complete: bool
    relative_energy_kcal_mol: dict[str, float] = field(default_factory=dict)
    populations: dict[str, float] | None = None
    temperature_k: float = STANDARD_TEMPERATURE_K
    #: tautomer key -> state, and tautomer key -> the fingerprint of its
    #: lowest successful candidate.
    tautomer_states: dict[str, TautomerState] = field(default_factory=dict)
    representatives: dict[str, str] = field(default_factory=dict)

    @property
    def tautomer_count(self) -> int:
        return len(self.tautomer_states)

    @property
    def truncated_tautomer_count(self) -> int:
        return len({c.tautomer_key for c in self.candidates if c.stereo.truncated})

    @property
    def has_conformer_search(self) -> bool:
        """Some candidate came from a conformer search, so each tautomer's energy
        is the lowest of what that search selected, not of one start geometry."""
        return any(c.conformer.search != SEARCH_SINGLE for c in self.candidates)

    @property
    def truncated_conformer_class_count(self) -> int:
        """Stereo classes whose conformer pool was cut at the cap (`full_orca`)."""
        return len({c.conformer.stereo_fingerprint for c in self.candidates if c.conformer.truncated})

    @property
    def has_stereo_search(self) -> bool:
        """Some tautomer was searched over more than one stereo candidate (or
        fell back), so the energies are lowest-of-several, not a single job."""
        return any(c.stereo.isomers_calculated > 1 or c.stereo.truncated for c in self.candidates)

    @property
    def energy_reference(self) -> str:
        """Machine-readable form of what the ΔE baseline is."""
        return "global_minimum" if self.complete else "lowest_successful_calculated"

    @property
    def energy_label(self) -> str:
        if self.has_conformer_search:
            # Never an unqualified "lowest-energy conformer": the search is sampled,
            # so this is the lowest of what the declared policy selected.
            if self.complete:
                return (
                    "ΔE (kcal/mol), lowest calculated conformer of each tautomer "
                    "(a sampled conformer search, not exhaustive)"
                )
            reason = (
                f"the conformer pool was truncated for {self.truncated_conformer_class_count} "
                "stereoisomer(s)"
                if self.truncated_conformer_class_count
                else "one or more candidates failed or were not searched"
            )
            return (
                "ΔE relative to the lowest successful calculated tautomer (kcal/mol) -- incomplete; "
                f"lowest calculated conformer found for each tautomer, {reason}"
            )
        if self.complete:
            if self.has_stereo_search:
                return "ΔE (kcal/mol), lowest-energy stereoisomer of each tautomer"
            return "ΔE (kcal/mol)"
        truncated = self.truncated_tautomer_count
        if truncated:
            return (
                "ΔE relative to the lowest successful calculated tautomer (kcal/mol) -- incomplete; "
                "lowest successful stereoisomer found for each tautomer, stereoisomer enumeration "
                f"was truncated for {truncated} tautomer(s)"
            )
        if self.has_stereo_search:
            return (
                "ΔE relative to the lowest successful calculated tautomer (kcal/mol) -- incomplete; "
                "lowest successful stereoisomer found for each tautomer, one or more candidates failed"
            )
        return (
            "ΔE relative to the lowest successful candidate (kcal/mol) "
            "-- incomplete, one or more candidates failed"
        )

    def rdkit_cross_check(self) -> dict:
        """RDKit's heuristic preference against ORCA, TAUTOMER by tautomer:
        each tautomer's ORCA energy is its representative's (lowest successful
        stereo job), never one stereo job against a tautomer's rank. See
        `chem.tautomer_ranking.cross_check` for the four verdicts."""
        by_fingerprint = {c.fingerprint: c for c in self.candidates}
        scores: dict[str, float | None] = {}
        for candidate in self.candidates:
            scores.setdefault(candidate.tautomer_key, candidate.rdkit_score)
        energies = {
            key: self.relative_energy_kcal_mol[fingerprint]
            for key, fingerprint in self.representatives.items()
            if fingerprint in self.relative_energy_kcal_mol and fingerprint in by_fingerprint
        }
        return cross_check(scores, energies, self.complete)

    @property
    def succeeded_count(self) -> int:
        return sum(1 for c in self.candidates if c.status is CandidateStatus.SUCCEEDED)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.candidates if c.status is CandidateStatus.FAILED)

    @property
    def not_run_count(self) -> int:
        return sum(1 for c in self.candidates if c.status is CandidateStatus.NOT_RUN)


def build_outcome(
    candidates: list[CandidateResult], temperature_k: float = STANDARD_TEMPERATURE_K
) -> TautomerDistributionOutcome:
    """Combines every candidate's own outcome into one auditable result.

    Candidates are grouped by tautomer. A tautomer is represented by its
    lowest SUCCESSFUL stereo candidate (ties broken by fingerprint, so the
    choice never depends on enumeration order) and is `COMPLETE` only when
    every one of its candidates succeeded AND its stereo search was neither
    truncated nor missing an embedding failure.

    Never renormalizes over only the survivors and calls it the
    distribution -- `populations` is populated only when EVERY tautomer is
    complete. A survivor-relative `relative_energy_kcal_mol` is still
    reported for an incomplete run, so the real, measured energies are not
    hidden just because the set isn't complete -- `energy_label` and
    `energy_reference` are how a consumer finds out which baseline it is
    reading.
    """
    groups: dict[str, list[CandidateResult]] = {}
    for candidate in candidates:
        groups.setdefault(candidate.tautomer_key, []).append(candidate)

    states: dict[str, TautomerState] = {}
    representatives: dict[str, str] = {}
    for key, members in sorted(groups.items()):
        succeeded_members = [m for m in members if m.status is CandidateStatus.SUCCEEDED]
        if not succeeded_members:
            states[key] = TautomerState.FAILED
            continue
        best = min(succeeded_members, key=lambda m: (m.absolute_energy_hartree, m.fingerprint))
        representatives[key] = best.fingerprint
        searched_fully = len(succeeded_members) == len(members) and not any(
            m.stereo.truncated or m.stereo.embedding_failed or m.conformer.truncated for m in members
        )
        states[key] = TautomerState.COMPLETE if searched_fully else TautomerState.INCOMPLETE

    complete = bool(states) and all(state is TautomerState.COMPLETE for state in states.values())
    succeeded = [c for c in candidates if c.status is CandidateStatus.SUCCEEDED]
    if not succeeded:
        return TautomerDistributionOutcome(
            candidates=tuple(candidates),
            complete=False,
            temperature_k=temperature_k,
            tautomer_states=states,
        )

    lowest = min(c.absolute_energy_hartree for c in succeeded)
    relative = {
        c.fingerprint: (c.absolute_energy_hartree - lowest) * HARTREE_TO_KCAL_PER_MOL for c in succeeded
    }

    populations: dict[str, float] | None = None
    if complete:
        by_fingerprint = {c.fingerprint: c for c in succeeded}
        representative_ids = [representatives[key] for key in sorted(representatives)]
        weights = boltzmann_weights(
            [by_fingerprint[f].absolute_energy_hartree for f in representative_ids],
            temperature_k=temperature_k,
        )
        populations = dict(zip(representative_ids, weights, strict=True))

    return TautomerDistributionOutcome(
        candidates=tuple(candidates),
        complete=complete,
        relative_energy_kcal_mol=relative,
        populations=populations,
        temperature_k=temperature_k,
        tautomer_states=states,
        representatives=representatives,
    )


def format_population_percent(population: float) -> str:
    """Display formatting only -- `population` itself must already be the
    full-precision, unrounded weight (`build_outcome` never rounds)."""
    if population < 0:
        raise ValueError(f"a population cannot be negative: {population!r}")
    if population < _SMALL_POPULATION_DISPLAY_FLOOR:
        return "<0.01%"
    return f"{population * 100:.2f}%"


#: `StructureSetResult.provenance.parameters["validation_branch"]`'s three
#: fixed values -- not incidental spellings chosen per call site.
#: `model_version` is the single string every other key here feeds into
#: (Design point 8/30): change any one of them and `model_version` changes
#: too, so a stale `validation_branch` can never silently keep authorizing
#: a percentage under a model that has since moved on.
#: No validation claim has been established yet -- not the same as
#: "validation was attempted and failed." The only branch this module
#: ships, until a real validation study runs.
VALIDATION_UNVALIDATED = "unvalidated"
#: The ranking gate passed but the quantitative gate didn't, or a
#: candidate in this specific run failed -- real relative energies are
#: shown, never a percentage built from them.
VALIDATION_RANKING_ONLY = "ranking_only"
#: Both gates passed under the exact frozen model this result's own
#: `model_version` names -- the only branch allowed to show a percentage.
VALIDATION_VALIDATED = "validated"


def model_version(
    method_basis: str,
    embedding_algorithm: str,
    temperature_k: float,
    policy: ModelPolicy = MODEL_POLICY,
) -> str:
    """One short, stable string identifying the exact scientific-computation
    semantics behind a result -- covers computation only, deliberately
    excluding presentation (a label or rounding-policy change must never
    change this, Design point 8). Changing any input here is, by
    definition, a different model: a stored `validation_branch` from a
    different `model_version` must never be trusted for the current one.

    Built from the revision, the structured `ModelPolicy` and the computation
    parameters -- never from `model_assumptions`' prose -- so each part stays
    recoverable from the result without diffing hashes."""
    return (
        f"tautomer-boltzmann-v{TAUTOMER_MODEL_REVISION}|{policy.canonical()}"
        f"|{method_basis}|{embedding_algorithm}|T={temperature_k:g}K"
    )


def build_structure_set_result(
    outcome: TautomerDistributionOutcome,
    molecule_uuid: str,
    method_basis: str,
    run_id: str,
    validation_branch: str = VALIDATION_UNVALIDATED,
    embedding_algorithm: str = "ETKDGv3",
    policy: ModelPolicy = MODEL_POLICY,
) -> StructureSetResult:
    """The user-facing result: one entry per deduplicated candidate
    (succeeded AND failed -- never only the survivors, which would make
    the enumerated set look smaller than it was), reusing the same
    `StructureSetResult`/`StructureEntry` shape and `StructureGridWidget`
    renderer `enumerate_tautomers`'s own result already uses. A tautomer with
    several stereo candidates has one entry each; the entry of its lowest
    successful candidate says so (`is_lowest_calculated_for_tautomer`), and
    only a COMPLETE tautomer's says it is the lowest stereoisomer.

    `StructureEntry.score` carries the normalized population (0..1, the
    field this project's own docstring already earmarks for "a relative
    weight") -- but **only once `validation_branch` is
    `VALIDATION_VALIDATED`**. `StructureGridWidget`'s shared caption
    renders any non-`None` `score` directly (`f"score {entry.score:.2f}"`)
    with no awareness of validation state, so this is the one place that
    gate has to be enforced -- an unvalidated or ranking-only result's
    real population is still computed (point 7) but is retained only in
    `metadata["population_unvalidated"]`, never in the field the shared
    grid actually displays, so nothing that looks like a percentage
    reaches the screen before it has been validated. `StructureEntry.energy`
    carries the relative energy in kcal/mol, labeled by `outcome.
    energy_label` at the result level so a reader knows whether it is the
    complete-set ΔE or a survivor-relative one (Design point 5's trap).
    """
    # The lowest successful candidate WITHIN each stereo class (a class is one
    # revision-3 candidate; under a conformer search it has several jobs).
    lowest_in_class: dict[str, str] = {}
    for candidate in sorted(
        (c for c in outcome.candidates if c.status is CandidateStatus.SUCCEEDED),
        key=lambda c: (c.absolute_energy_hartree, c.fingerprint),
    ):
        lowest_in_class.setdefault(candidate.conformer.stereo_fingerprint or candidate.fingerprint, candidate.fingerprint)
    entries: list[StructureEntry] = []
    for candidate in outcome.candidates:
        # The drawing chosen at generation (`generate_tautomer_candidates`),
        # never the 3D start geometry: reading chirality off embedded
        # coordinates invents a specific enantiomer for every centre the user
        # left unspecified (`_display_molblock`).
        shown = candidate.display_molblock or candidate.molblock
        mol = Chem.MolFromMolBlock(shown) if shown else None
        label = Chem.MolToSmiles(mol) if mol is not None else candidate.fingerprint[:12]
        stereo = candidate.stereo
        # Short on purpose: the grid caption wraps and clips in a small cell
        # (seen on screen). What a mark means is in the entry's metadata and
        # the result's "Stereochemistry" line, not in the caption.
        if stereo.fallback:
            label += " [fallback]"
        elif stereo.isomers_calculated > 1:
            label += f" [{stereo.index + 1} of {stereo.isomers_calculated}]"
        conformer = candidate.conformer
        if conformer.selected > 1:
            label += f" [conf {conformer.index + 1}/{conformer.selected}]"
        state = outcome.tautomer_states.get(candidate.tautomer_key, TautomerState.FAILED)
        metadata: dict = {
            "status": candidate.status.value,
            "fingerprint": candidate.fingerprint,
            "embedding_seed": candidate.embedding_seed,
            "tautomer_fingerprint": candidate.tautomer_key,
            "tautomer_state": state.value,
            # The lowest successful candidate AMONG THOSE CALCULATED. Only
            # when `tautomer_state` is "complete" is it also the lowest
            # stereoisomer; under a failure or truncation it is not known to be.
            "is_lowest_calculated_for_tautomer": (
                outcome.representatives.get(candidate.tautomer_key) == candidate.fingerprint
            ),
            "stereo_index": stereo.index,
            "stereo_isomers_total": stereo.isomers_total,
            "stereo_isomers_total_known": stereo.isomers_total_known,
            "stereo_isomers_calculated": stereo.isomers_calculated,
            "stereo_enantiomer_merged": stereo.enantiomer_merged,
            "stereo_fallback": stereo.fallback,
            "stereo_fallback_reason": stereo.fallback_reason,
            "rdkit_score": candidate.rdkit_score,
            "conformer_search": conformer.search,
            "conformer_index": conformer.index,
            "conformer_recipe_fingerprint": conformer.recipe_fingerprint,
            "stereo_fingerprint": conformer.stereo_fingerprint or candidate.fingerprint,
            "conformers_generated_for_stereo": conformer.generated,
            "conformers_distinct_for_stereo": conformer.distinct,
            "conformers_selected_for_stereo": conformer.selected,
            "conformers_truncated": conformer.truncated,
            "conformer_prefilter": conformer.prefilter,
            "conformer_prefilter_energy_kcal": conformer.prefilter_energy_kcal,
            # Lowest AMONG THOSE CALCULATED for this stereoisomer: never a claim of
            # the global conformer minimum.
            "is_lowest_calculated_for_stereo": (
                lowest_in_class.get(conformer.stereo_fingerprint or candidate.fingerprint)
                == candidate.fingerprint
            ),
        }
        if candidate.absolute_energy_hartree is not None:
            # The measurement behind the derived relative energy, kept so the
            # table can be audited and exported without recomputing anything.
            metadata["absolute_energy_hartree"] = candidate.absolute_energy_hartree
        if candidate.status is CandidateStatus.FAILED:
            metadata["failure_reason"] = candidate.failure_reason
            metadata["failure_reason_code"] = candidate.failure_reason_code
            label = f"{label} (failed: {candidate.failure_reason_code})"

        raw_population = None
        if outcome.populations is not None:
            raw_population = outcome.populations.get(candidate.fingerprint)
        # Computed and real, but withheld from the displayed `score` field
        # until the model is actually validated -- see the docstring above.
        population = raw_population if validation_branch == VALIDATION_VALIDATED else None
        if raw_population is not None:
            metadata["population_unvalidated"] = raw_population
        energy = outcome.relative_energy_kcal_mol.get(candidate.fingerprint)

        entries.append(
            StructureEntry(
                molblock=shown,
                label=label,
                score=population,
                energy=energy,
                metadata=metadata,
            )
        )

    # Ascending |E| with a stable fingerprint tie-break -- never by
    # RDKit's own "canonical" pick (a separate concept, see this module's
    # own docstring), and a failed candidate (energy=None) sorts after
    # every succeeded one rather than raising or landing arbitrarily.
    entries.sort(key=lambda e: (e.energy is None, e.energy if e.energy is not None else 0.0, e.metadata["fingerprint"]))

    version = model_version(method_basis, embedding_algorithm, outcome.temperature_k, policy)
    pools: dict[str, dict] = {}
    for candidate in outcome.candidates:
        c = candidate.conformer
        if c.search == SEARCH_SINGLE:
            continue
        pools.setdefault(
            c.stereo_fingerprint,
            {
                "stereo_fingerprint": c.stereo_fingerprint,
                "tautomer_fingerprint": candidate.tautomer_key,
                "seed": c.seed,
                "generated": c.generated,
                "prefilter_ok": c.prefilter_ok,
                "prefilter_failed": c.prefilter_failed,
                "distinct": c.distinct,
                "selected": c.selected,
                "truncated": c.truncated,
                "prefilter": c.prefilter,
                "retained_recipes": list(c.retained_recipes),
                "selected_recipes": list(c.selected_recipes),
            },
        )
    states = outcome.tautomer_states.values()
    provenance = Provenance(
        created_by="core",
        method="orca",
        parameters={
            "population_model": "electronic-energy-boltzmann",
            "temperature_k": outcome.temperature_k,
            "validation_branch": validation_branch,
            "model_version": version,
            "model_revision": TAUTOMER_MODEL_REVISION,
            "model_policy": asdict(policy),
            "model_assumptions": list(model_assumptions(policy)),
            "method_basis": method_basis,
            "embedding_algorithm": embedding_algorithm,
            # Jobs, not tautomers: one stereo candidate is one ORCA optimization.
            "candidate_count_expected": len(outcome.candidates),
            "candidate_count_succeeded": outcome.succeeded_count,
            "candidate_count_failed": outcome.failed_count,
            "candidate_count_not_run": outcome.not_run_count,
            "tautomer_count": outcome.tautomer_count,
            "tautomers_complete": sum(1 for s in states if s is TautomerState.COMPLETE),
            "tautomers_incomplete": sum(1 for s in states if s is TautomerState.INCOMPLETE),
            "tautomers_failed": sum(1 for s in states if s is TautomerState.FAILED),
            "parent_run_id": run_id,
            "complete": outcome.complete,
            "energy_label": outcome.energy_label,
            "energy_reference": outcome.energy_reference,
            "stereo_enumeration_cap": policy.stereo_cap,
            "conformer_search": policy.conformer_search,
            "conformer_pools": list(pools.values()),
            "conformer_pools_truncated": outcome.truncated_conformer_class_count,
            "stereo_enumeration_truncated": outcome.truncated_tautomer_count,
            "stereo_search": outcome.has_stereo_search,
            # RDKit's heuristic against ORCA: informational, never an input to
            # populations or validation. The verdict is four-valued and is
            # `indeterminate` for any incomplete result.
            "rdkit_cross_check": outcome.rdkit_cross_check(),
            "rdkit_version": RDKIT_VERSION,
        },
    )

    return StructureSetResult(
        # Matches the registered `calculator_id` ("orca.tautomer_distribution",
        # bootstrap.py) exactly -- `property_panel.py`'s own documented
        # invariant is that a generator's `set_id` equals its registered
        # calculator_id, which is also what `make_identity`/`result_id_of`
        # key off. A mismatch here would make `_category_of` file this
        # result under "other" instead of "quantum_chemistry".
        set_id="orca.tautomer_distribution",
        name=f"Tautomer distribution ({len(entries)})",
        method="orca",
        molecule_uuid=molecule_uuid,
        entries=entries,
        provenance=provenance,
    )


#: The columns of `tautomer_distribution_table`, in order.
TABLE_COLUMNS = (
    "Structure", "Status", "Tautomer state", "Lowest calculated for tautomer", "Stereo index",
    "Stereoisomers calculated", "Stereo fallback", "Conformer", "Conformers selected",
    "Lowest calculated for stereoisomer", "Conformer recipe fingerprint", "Absolute energy (Hartree)",
    "Relative energy (kcal/mol)", "Energy reference", "Population estimate",
    "RDKit heuristic score", "Failure", "Candidate fingerprint", "Tautomer fingerprint",
    "Validation branch", "Model version",
)


def tautomer_distribution_table(result: StructureSetResult) -> tuple[list[str], list[list[str]]]:
    """A tautomer-distribution result as `(headers, rows)`, one row per candidate,
    read from the result and never from the screen. Numbers are written at full
    precision.

    **EVERY ROW CARRIES WHAT QUALIFIES ITS ENERGY.** A relative energy is only
    "ΔE to the global minimum" when the result is complete, so each row names its
    `Energy reference`, validation branch and model version rather than leaving
    a reader to infer them from a file that has lost its dialog.

    **THE POPULATION COLUMN IS BLANK UNLESS THE MODEL IS VALIDATED.** It reads
    `entry.score`, which `build_structure_set_result` sets only for a validated
    result; the withheld `population_unvalidated` value is deliberately never
    exported, so no file can carry a percentage the screen was not allowed to show.
    """
    parameters = result.provenance.parameters if result.provenance else {}

    def number(value) -> str:
        return "" if value is None else repr(float(value))

    def conformer_cell(meta: dict) -> str:
        """1-based position among the selected conformers; blank without a search."""
        if meta.get("conformer_search", SEARCH_SINGLE) == SEARCH_SINGLE:
            return ""
        return str(int(meta.get("conformer_index", 0)) + 1)

    rows = []
    for entry in result.entries:
        meta = entry.metadata
        rows.append(
            [
                entry.label,
                str(meta.get("status", "")),
                str(meta.get("tautomer_state", "")),
                "yes" if meta.get("is_lowest_calculated_for_tautomer") else "no",
                str(meta.get("stereo_index", "")),
                str(meta.get("stereo_isomers_calculated", "")),
                "yes" if meta.get("stereo_fallback") else "no",
                conformer_cell(meta),
                str(meta.get("conformers_selected_for_stereo", "")) if meta.get("conformer_search") != SEARCH_SINGLE else "",
                "yes" if meta.get("is_lowest_calculated_for_stereo") else "no",
                str(meta.get("conformer_recipe_fingerprint", "")),
                number(meta.get("absolute_energy_hartree")),
                number(entry.energy),
                str(parameters.get("energy_reference", "")),
                number(entry.score),
                number(meta.get("rdkit_score")),
                str(meta.get("failure_reason_code", "")),
                str(meta.get("fingerprint", "")),
                str(meta.get("tautomer_fingerprint", "")),
                str(parameters.get("validation_branch", "")),
                str(parameters.get("model_version", "")),
            ]
        )
    return list(TABLE_COLUMNS), rows

