"""Numeric pKa via pkasolver, plus pH-dependent protonation via Dimorphite-DL.

HOW ACCURATE IT ACTUALLY IS, measured rather than assumed, because the
single acetic-acid number the setup dialog used to report made it look
worse than it is. Twenty-four compounds with standard literature values
in water at 25 C, run against the real installed sidecar:

    MAE 0.29 pKa units   median 0.14   22 of 24 within 1.0 unit
      bases  n=10  MAE 0.13   max 0.39
      acids  n=14  MAE 0.41   max 2.70

That is at or better than pkasolver's own published performance, and
better than the 0.5-1 unit a medicinal chemist would treat as usable.

ACETIC ACID IS ONE OF ITS WORSE CASES (-0.57, third worst of the 24),
which is exactly why the dialog now probes an acid, a phenol and a base
instead of that one compound.

THE REAL WEAKNESS IS ELECTRON-POOR PHENOLS, and it is worth knowing
before trusting a number:

    2,4-dinitrophenol   literature 4.09   predicted 6.79   +2.70
    4-nitrophenol       literature 7.15   predicted 8.19   +1.04

Both are strongly acidic phenols whose acidity comes from nitro-group
resonance stabilising the phenolate, and the model consistently
under-predicts that. Ordinary phenols are fine (phenol +0.04,
4-methylphenol -0.08). Treat a nitro-substituted phenol's predicted pKa
as an upper bound.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from rdkit import Chem

from openchem.chem.engine import InvalidStructureError

logger = logging.getLogger("openchem.chemistry")

#: Settings key holding the path to a Python interpreter that has pkasolver
#: installed. Configured via Tools -> External Tools, same as ORCA's and
#: Vina's executables.
PKASOLVER_PYTHON_SETTING = "pka/pkasolver_python_path"

#: The sidecar script `compute_pka` runs in the pkasolver interpreter. A
#: separate process because pkasolver pins its own torch and RDKit; a
#: separate FILE because an inline `-c` program cannot be linted or tested.
_RUNNER = Path(__file__).resolve().parent / "pka_runner.py"

#: A pkasolver call loads a 105 MB ensemble of models per invocation, so it
#: is slow but bounded -- generous enough not to fail a legitimate run on a
#: cold filesystem cache, short enough not to hang the UI forever.
_TIMEOUT_SECONDS = 300


#: Nitrogen whose lone pair is DELOCALISED into an adjacent electron sink,
#: written against the PROTONATED product: an N carrying four connections
#: and a positive charge, bonded to a carbonyl, a thiocarbonyl or a
#: sulfonyl. Such a nitrogen is not a base at any physiological pH -- the
#: lone pair is in the pi system rather than available to a proton -- and
#: an amide's conjugate acid sits around pKa -0.5, some eight units below
#: the pH this application asks about.
_OVERPROTONATED_N = Chem.MolFromSmarts(
    "[$([NX4+]-[CX3]=[OX1]),$([NX4+]-[CX3]=[SX1]),$([NX4+]-[SX4](=[OX1])=[OX1])]"
)


@dataclass(frozen=True)
class Microspecies:
    """The dominant ionization state at one pH, and what it took to get it.

    `corrected_atoms` is empty on the ordinary path. When it is not, this
    module overrode Dimorphite-DL on the atoms it names -- reported rather
    than applied silently, because a charge distribution that quietly
    disagrees with the library that produced it is the kind of number this
    project spends its time removing.
    """

    mol: Chem.Mol
    formal_charge: int
    corrected_atoms: tuple[int, ...] = ()


def dominant_microspecies(mol: Chem.Mol, ph: float) -> Microspecies:
    """The single dominant ionization state at `ph`.

    **`variants[0]` WAS NOT A RANKING, AND THE ORDER CAME FROM THE HASH
    SEED.** Dimorphite-DL ENUMERATES microspecies; it does not sort them.
    This module used to take the first and call it dominant. Measured on
    an isobutyrylfentanyl at pH 7.4, eight separate processes returned
    THREE different net charges for one molecule:

        chg  +1  +0  +1  +0  +1  +0  +2  +0

    Within one process twelve calls agreed, and `PYTHONHASHSEED=0` was
    stable across processes while varying seeds were not -- so the order
    is a set iteration escaping into a scientific answer. It reached six
    production consumers, and logD moved **1.68 to 4.38** on one molecule,
    a factor of 500 in partition coefficient.

    `precision=0.0` is the fix for that half: it collapses Dimorphite's
    window to the pKa itself, so exactly one state comes back and the
    answer no longer depends on anything but the chemistry. Measured, six
    processes, identical.

    **DETERMINISM IS NOT CORRECTNESS, WHICH IS THE SECOND HALF.**
    Dimorphite's `Amines_primary_secondary_tertiary` site is
    `[C:1]-[NX3+0:2]` with pKa 8.16 and NO exclusion for an adjacent
    carbonyl, while its `*Amide` rule requires an N-H. So a TERTIARY amide
    matches nothing amide-specific, falls through to the plain-amine rule,
    and is protonated at pH 7.4 because 7.4 < 8.16. Measured over fifteen
    drug-like molecules with literature charge states, five were wrong and
    every one was that class:

        DMF, DEET, N,N-dimethylacetamide, N-methylpyrrolidone   0 -> +1
        fentanyl                                               +1 -> +2

    Acetanilide and lidocaine are right because they HAVE an N-H, which is
    the tell. So the correction here is a statement about a class rather
    than a patch for one molecule, and it is textbook: an amide,
    thioamide or sulfonamide nitrogen is not protonated at physiological
    pH.

    **IT ONLY EVER REMOVES A PROTON DIMORPHITE ADDED**, never adds one.
    Overriding a library's chemistry is a claim, and this is the narrowest
    form of it -- anything the library does that is not this specific,
    well-understood error stands.

    **THE RETURNED MOLECULE IS IN THE INPUT'S ATOM ORDER.** The SMILES round
    trip used to hand back the library's canonical order, and every per-atom
    consumer numbered its values by that. On a four-atom O-O-C=N ring the
    pH 7.4 Gasteiger charges landed nitrogen's +0.00 on an oxygen. See
    `restore_heavy_atom_order` for the contract.
    """
    import dimorphite_dl

    smiles = Chem.MolToSmiles(mol)
    # precision=0.0: the dominant state, not the enumeration. See above --
    # without it this function is a coin flip.
    variants = dimorphite_dl.protonate_smiles(
        smiles, ph_min=ph, ph_max=ph, precision=0.0
    )
    if not variants:
        raise InvalidStructureError(
            f"Dimorphite-DL returned no protonation state for {smiles!r} at pH {ph}"
        )
    # SORTED, NEVER ARRIVAL ORDER, and this is the belt to precision=0.0's
    # braces. At precision 0 the library returns exactly one state on every
    # molecule measured -- but "measured on every input I tried" is not "no
    # input can", and the failure mode of being wrong here is silent and
    # irreproducible rather than loud. Sorting costs nothing and makes the
    # answer a function of the chemistry alone, which is the property that
    # can actually be tested: a fake returning the same states in two
    # different orders must give one answer.
    chosen = sorted(variants)[0]
    parsed = Chem.MolFromSmiles(chosen)
    if parsed is None:
        raise InvalidStructureError(f"Could not parse Dimorphite-DL output {chosen!r}")
    # Correspondence FIRST, chemistry second, and neither knows about the
    # other: which atom is which is a separate question from which formal
    # state that atom should carry.
    protonated = restore_heavy_atom_order(mol, parsed)

    corrected = _deprotonate_delocalised_nitrogen(protonated)
    return Microspecies(
        mol=protonated,
        formal_charge=Chem.GetFormalCharge(protonated),
        corrected_atoms=corrected,
    )


#: More candidate correspondences than this is refused rather than searched.
#: Only automorphisms produce extra candidates, and a drug-sized molecule has
#: tens (fentanyl's two phenyl flips and its piperidine); a count at the cap
#: means the search was truncated, which is not a uniqueness result.
_MAX_CORRESPONDENCES = 5000


def restore_heavy_atom_order(original: Chem.Mol, protonated: Chem.Mol) -> Chem.Mol:
    """`protonated`, renumbered into `original`'s atom order.

    **THE CONTRACT:** for every atom index i of `original`, atom i of the
    result is the same atom. A heavy atom carries the protonated state
    (charge, hydrogen count, aromaticity); a hydrogen `original` holds as an
    ATOM stays an atom at its own index, bonded to the same parent. Nothing
    else is guaranteed: this answers "which atom is which", never "which
    state is right" -- that is Dimorphite's answer and
    `_deprotonate_delocalised_nitrogen`'s correction.

    **WHY IT MATCHES THE SKELETON INSTEAD OF CARRYING ATOM MAPS.** Maps were
    the obvious route and they change the chemistry: measured over 111
    molecule/pH pairs, a mapped imidazole comes back with NO state at pH 7.4
    and 12 where the unmapped one returns an anion, and 4-nitrophenol's nitro
    oxygen loses its map. So Dimorphite is called exactly as before and the
    correspondence is recovered afterwards on element and adjacency alone --
    protonation changes charges, hydrogens, bond orders and aromaticity
    (the O-O-C=N ring comes back aromatic), and never the heavy-atom graph.

    **THE DRAWING BREAKS THE TIES THE SKELETON CANNOT.** With bond orders
    erased, a carboxylic acid's two oxygens are interchangeable, and the
    first version refused 60 of 126 molecule/pH pairs for exactly that --
    every acid. But the drawing says which oxygen held the proton. Dimorphite
    only moves protons, so the right correspondence is the one that departs
    LEAST from the drawing: `-OH -> -O-` changes one atom, where the swap
    also turns a single bond double and a double single.

    **AMBIGUITY THAT REMAINS REFUSES, UNLESS IT CANNOT MATTER.** Among the
    least-departing candidates, each is compared on what it would put at
    each index -- charge, hydrogens, aromaticity, bond orders. If they all
    agree, which one is used is unobservable (a phenyl ring flipped). If they
    disagree (one of two equivalent amines protonated), choosing would assign
    the proton to an atom nothing chose, so it raises `InvalidStructureError`.
    """
    heavy = [atom.GetIdx() for atom in original.GetAtoms() if atom.GetAtomicNum() != 1]
    if any(atom.GetAtomicNum() == 1 for atom in protonated.GetAtoms()):
        raise InvalidStructureError(
            "The protonated form holds hydrogen atoms; its correspondence to "
            "the drawing cannot be established"
        )
    if len(heavy) != protonated.GetNumAtoms():
        raise InvalidStructureError(
            f"The protonated form has {protonated.GetNumAtoms()} heavy atoms "
            f"where the drawing has {len(heavy)}"
        )

    query, heavy_bonds = _skeleton(original, heavy)
    target, _ = _skeleton(protonated, list(range(protonated.GetNumAtoms())))
    if len(heavy_bonds) != protonated.GetNumBonds():
        raise InvalidStructureError("The protonated form's bonding differs from the drawing")

    params = Chem.SubstructMatchParameters()
    params.uniquify = False
    params.maxMatches = _MAX_CORRESPONDENCES
    matches = target.GetSubstructMatches(query, params)
    if not matches:
        raise InvalidStructureError("The protonated form does not match the drawing")
    if len(matches) >= _MAX_CORRESPONDENCES:
        raise InvalidStructureError("Too many symmetric correspondences to establish atom identity")

    def signature(match):
        atoms = tuple(
            (
                protonated.GetAtomWithIdx(match[q]).GetFormalCharge(),
                protonated.GetAtomWithIdx(match[q]).GetTotalNumHs(),
                protonated.GetAtomWithIdx(match[q]).GetIsAromatic(),
            )
            for q in range(len(heavy))
        )
        bonds = tuple(
            protonated.GetBondBetweenAtoms(match[a], match[b]).GetBondType()
            for a, b in heavy_bonds
        )
        return atoms, bonds

    def departures(match):
        """Changes to the DRAWING this correspondence cannot explain.

        A proton event moves a hydrogen AND a unit of charge onto (or off)
        the same atom, so `(+1 H, +1 charge)` and `(-1 H, -1 charge)` are
        explained and cost nothing; anything else on an atom, and any bond
        whose order changed, is a departure. Returned as (unexplained,
        total) so the explained count still separates candidates that tie
        on the first.
        """
        unexplained = total = 0
        for q, index in enumerate(heavy):
            drawn = original.GetAtomWithIdx(index)
            made = protonated.GetAtomWithIdx(match[q])
            change = (
                made.GetTotalNumHs() - drawn.GetTotalNumHs(),
                made.GetFormalCharge() - drawn.GetFormalCharge(),
            )
            total += (change[0] != 0) + (change[1] != 0)
            unexplained += change not in ((0, 0), (1, 1), (-1, -1))
        for a, b in heavy_bonds:
            drawn = original.GetBondBetweenAtoms(heavy[a], heavy[b])
            made = protonated.GetBondBetweenAtoms(match[a], match[b])
            changed = drawn.GetBondType() != made.GetBondType()
            unexplained += changed
            total += changed
        return unexplained, total

    scored = [(departures(match), match) for match in matches]
    fewest = min(score for score, _ in scored)
    best = [match for score, match in scored if score == fewest]
    first = signature(best[0])
    if any(signature(match) != first for match in best[1:]):
        raise InvalidStructureError(
            "Symmetry-equivalent atoms receive different protonation states, so "
            "which drawn atom carries the change cannot be established"
        )
    return _rebuild_in_original_order(original, protonated, heavy, best[0])


def _skeleton(mol: Chem.Mol, keep: list[int]) -> tuple[Chem.Mol, list[tuple[int, int]]]:
    """Element and adjacency only, over the atoms in `keep`, renumbered 0..n.

    Returns the skeleton and its bonds as position pairs. Everything
    protonation may legitimately change is erased, so substructure matching
    between two skeletons of equal size is graph isomorphism.
    """
    position = {index: p for p, index in enumerate(keep)}
    skeleton = Chem.RWMol()
    for index in keep:
        atom = Chem.Atom(mol.GetAtomWithIdx(index).GetAtomicNum())
        atom.SetNoImplicit(True)
        skeleton.AddAtom(atom)
    bonds = []
    for bond in mol.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if a in position and b in position:
            skeleton.AddBond(position[a], position[b], Chem.BondType.SINGLE)
            bonds.append((position[a], position[b]))
    skeleton.UpdatePropertyCache(strict=False)
    return skeleton.GetMol(), bonds


def _rebuild_in_original_order(
    original: Chem.Mol, protonated: Chem.Mol, heavy: list[int], match: tuple[int, ...]
) -> Chem.Mol:
    """Atoms added in `original`'s order, bonds in `original`'s bond order.

    Bond order is kept deliberately: an atom's chiral tag is a parity over the
    order its bonds were added, so rebuilding in the drawing's bond order is
    what lets the drawing's own tag stay valid.
    """
    to_protonated = {index: match[p] for p, index in enumerate(heavy)}
    drawn_h = {index: 0 for index in heavy}
    for atom in original.GetAtoms():
        if atom.GetAtomicNum() == 1:
            for neighbour in atom.GetNeighbors():
                if neighbour.GetIdx() in drawn_h:
                    drawn_h[neighbour.GetIdx()] += 1

    rebuilt = Chem.RWMol()
    for atom in original.GetAtoms():
        index = atom.GetIdx()
        if index not in to_protonated:
            rebuilt.AddAtom(Chem.Atom(atom))
            continue
        source = protonated.GetAtomWithIdx(to_protonated[index])
        hydrogens = source.GetTotalNumHs() - drawn_h[index]
        if hydrogens < 0:
            raise InvalidStructureError(
                f"Atom {index + 1} is drawn with a hydrogen the protonated form removes"
            )
        new = Chem.Atom(source.GetAtomicNum())
        new.SetFormalCharge(source.GetFormalCharge())
        new.SetNumRadicalElectrons(source.GetNumRadicalElectrons())
        new.SetIsAromatic(source.GetIsAromatic())
        new.SetIsotope(atom.GetIsotope())
        new.SetChiralTag(atom.GetChiralTag())
        new.SetNumExplicitHs(hydrogens)
        new.SetNoImplicit(True)
        rebuilt.AddAtom(new)

    stereo = []
    for bond in original.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if a in to_protonated and b in to_protonated:
            source = protonated.GetBondBetweenAtoms(to_protonated[a], to_protonated[b])
            rebuilt.AddBond(a, b, source.GetBondType())
            rebuilt.GetBondBetweenAtoms(a, b).SetIsAromatic(source.GetIsAromatic())
            if source.GetBondType() == Chem.BondType.DOUBLE and len(bond.GetStereoAtoms()) == 2:
                stereo.append((a, b, tuple(bond.GetStereoAtoms()), bond.GetStereo()))
        else:
            rebuilt.AddBond(a, b, Chem.BondType.SINGLE)
    # AFTER every bond exists: a stereo atom must already be bonded to its
    # end of the double bond, and it may be a later bond in the drawing.
    for a, b, atoms, kind in stereo:
        new_bond = rebuilt.GetBondBetweenAtoms(a, b)
        new_bond.SetStereoAtoms(*atoms)
        new_bond.SetStereo(kind)

    result = rebuilt.GetMol()
    try:
        Chem.SanitizeMol(result)
    except Exception as exc:  # noqa: BLE001 - a rebuild that does not sanitize is a refusal
        raise InvalidStructureError(f"The renumbered protonated form is not valid ({exc})") from exc
    # cleanIt=False: the double-bond stereo copied above has no directional
    # bonds behind it, and a cleaning pass reads that as "unspecified" and
    # erases it -- measured on crotonic acid, where E vanished.
    Chem.AssignStereochemistry(result, cleanIt=False, force=True)
    return result


def _deprotonate_delocalised_nitrogen(mol: Chem.Mol) -> tuple[int, ...]:
    """Undo, IN PLACE, any protonation of an amide-like nitrogen.

    Returns the atom indices corrected, so a caller can say what happened
    rather than presenting a silently-edited molecule.
    """
    matches = mol.GetSubstructMatches(_OVERPROTONATED_N)
    if not matches:
        return ()
    corrected = []
    for (index,) in matches:
        atom = mol.GetAtomWithIdx(index)
        atom.SetFormalCharge(0)
        # The proton Dimorphite added is explicit on the parsed product, so
        # the charge alone is not enough -- leaving it would be a neutral
        # nitrogen with five bonds, which does not sanitize.
        if atom.GetNumExplicitHs():
            atom.SetNumExplicitHs(atom.GetNumExplicitHs() - 1)
        atom.SetNoImplicit(False)
        corrected.append(index)
    Chem.SanitizeMol(mol)
    return tuple(corrected)


def protonate_at_ph(mol: Chem.Mol, ph: float) -> Chem.Mol:
    """The dominant ionization microspecies at `ph`, as a new Mol.

    The thin form of `dominant_microspecies`, kept because six production
    consumers want only the structure. Read that function's docstring
    before changing anything here: what looks like a one-line call into a
    library is the fix for a non-deterministic scientific answer.
    """
    return dominant_microspecies(mol, ph).mol


class PKaStatus(Enum):
    """Why a pKa lookup produced what it did.

    **FOUR STATES, BECAUSE COLLAPSING THEM LOSES THE ONE THAT MATTERS.**
    `compute_pka` returns `None` for "not installed" and its own docstring
    has to warn that this is not "no ionizable atoms found" -- a warning
    only load-bearing because the two were indistinguishable in the return
    type. They are not here.

    The distinction is user-visible, not academic. "Caffeine has no
    ionizable centre" is a fact about caffeine and a perfectly good answer;
    "pkasolver crashed" is a fault the user can fix. Rendering both as a
    failed calculation tells the caffeine user their software is broken.
    """

    FOUND = "found"
    NO_IONIZABLE_CENTRES = "no_ionizable_centres"
    UNAVAILABLE = "unavailable"  # no environment configured
    FAILED = "failed"  # configured, but the run errored


@dataclass(frozen=True)
class PKaResolution:
    """What a pKa lookup found, and where it came from.

    Carries no policy. What a caller DOES about `NO_IONIZABLE_CENTRES`
    differs by property -- logD says "nothing varies with pH" and declines,
    solubility draws a perfectly meaningful flat line -- so the decision
    belongs to each caller rather than to the resolver. A helper that is
    right for one caller and wrong for another is carrying policy it
    should have handed back.
    """

    status: PKaStatus
    values: tuple[float, ...] = ()
    #: "manual" when the user typed them, "pkasolver" when predicted.
    source: str = ""
    method: str = ""
    #: Why, when the status is not FOUND. Shown to the user verbatim.
    reason: str = ""
    #: Exactly what the user typed, before parsing, so "4.8, 9.4" and
    #: "4.80,9.40" stay distinguishable when a stored result is reopened.
    input_text: str = ""


def pka_predictor_available(interpreter_path: str | None) -> bool:
    """Whether a usable pkasolver environment is configured.

    pkasolver runs OUT OF PROCESS, in its own virtual environment, for a
    concrete reason established by a real install spike (Phase 23): it
    requires `numpy<2` and `scipy<1.14`, while this project runs numpy 2.x,
    and it is not pip-installable at all on Python 3.12 (its setup.py uses
    `versioneer`, which calls the `configparser.SafeConfigParser` removed
    in 3.12). Running it as an external tool -- exactly how this app
    already treats ORCA and Vina -- keeps those pins, ~105 MB of model
    weights, and all of torch out of this project's dependency tree.

    Only checks that the interpreter exists; whether pkasolver actually
    imports there is answered by running it (see `describe_pka_status`),
    since a stale or half-built environment should surface as a real error
    message rather than a silent False.
    """
    if not interpreter_path:
        return False
    return Path(interpreter_path).is_file()


def _connectivity_skeleton(mol: Chem.Mol) -> tuple[Chem.Mol, list[int]]:
    """A heavy-atom, element-and-connectivity-only copy, plus the original
    atom index of each of its atoms.

    Every one of formal charge, hydrogen count, bond order and aromatic
    perception can differ between a molecule and its own conjugate base --
    a carboxylic acid and a carboxylate differ in all four at once -- so a
    match that respects any of them can fail on exactly the atoms that
    matter. Reducing both sides to "which elements, bonded to which" leaves
    a graph that protonation cannot change.

    Hydrogens are dropped rather than matched, since they are the thing
    being added and taken away. They are dropped by FILTERING rather than
    by `RemoveHs`, so that the returned index list can carry the original
    numbering back: one side of this match is a molecule the caller holds,
    and an answer in some intermediate numbering would just be the bug
    again in a new place.
    """
    heavy = [atom for atom in mol.GetAtoms() if atom.GetAtomicNum() > 1]
    original_index = [atom.GetIdx() for atom in heavy]
    skeleton_index = {idx: position for position, idx in enumerate(original_index)}

    skeleton = Chem.RWMol()
    for atom in heavy:
        fresh = Chem.Atom(atom.GetAtomicNum())
        fresh.SetNoImplicit(True)  # or RDKit re-derives H counts from valence
        skeleton.AddAtom(fresh)
    for bond in mol.GetBonds():
        begin = skeleton_index.get(bond.GetBeginAtomIdx())
        end = skeleton_index.get(bond.GetEndAtomIdx())
        if begin is not None and end is not None:
            skeleton.AddBond(begin, end, Chem.BondType.SINGLE)

    built = skeleton.GetMol()
    # Substructure matching needs ring membership, which normally arrives
    # via sanitization -- and sanitizing this deliberately wrong-valence
    # graph would fail. FastFindRings supplies just that one piece.
    Chem.FastFindRings(built)
    return built, original_index


def map_site_atom(site_smiles: str, site_atom_index: int, target: Chem.Mol) -> int | None:
    """Translate one of pkasolver's reaction-centre indices onto `target`'s
    own atom numbering, or None when it cannot be done honestly.

    `site_smiles` is the microstate the index belongs to, tagged by
    `pka_runner._indexed_smiles` with atom map numbers recording pkasolver's
    numbering (RDKit renumbers on every SMILES round trip, so the tags are
    what survives).

    A None return means the caller must not claim an atom. That is the
    behaviour worth protecting: the bug this replaces did not fail, it
    pointed confidently at a ring carbon.

    On a symmetric molecule several matches are equally valid and an
    arbitrary one is taken. That is not a defect -- the alternatives are
    the same atom by symmetry, so any of them labels the same chemistry.
    """
    if not site_smiles or site_atom_index < 0:
        return None
    site = Chem.MolFromSmiles(site_smiles)
    if site is None:
        return None

    # Atom map number n was written for pkasolver index n-1.
    parsed_for_site_index = {
        atom.GetAtomMapNum() - 1: atom.GetIdx()
        for atom in site.GetAtoms()
        if atom.GetAtomMapNum() > 0
    }
    parsed_index = parsed_for_site_index.get(site_atom_index)
    if parsed_index is None:
        return None

    site_skeleton, site_originals = _connectivity_skeleton(site)
    target_skeleton, target_originals = _connectivity_skeleton(target)
    if site_skeleton.GetNumAtoms() != target_skeleton.GetNumAtoms():
        return None
    try:
        site_position = site_originals.index(parsed_index)
    except ValueError:
        return None  # the reaction centre came back as a hydrogen

    match = target_skeleton.GetSubstructMatch(site_skeleton, useChirality=False)
    if not match or site_position >= len(match):
        return None
    return int(target_originals[match[site_position]])


@dataclass(frozen=True)
class PkaPrediction:
    """One predicted pKa, with the model's own spread on it.

    A dataclass rather than the (index, value) tuple this used to be,
    because `stddev` is the third thing and a three-wide tuple would have
    every caller remembering which slot is which -- the same call
    `CrossPeak` and `StructureEntry` already made here.

    `stddev` is the spread across pkasolver's 50-model ensemble, which the
    runner has always parsed and this layer used to discard. It is REAL
    reported uncertainty, not a number this project invented, which makes
    it worth carrying: it is the honest confidence signal that naming and
    NMR predictions were repeatedly unable to offer.

    IT IS A SPREAD, NOT A CALIBRATED CONFIDENCE INTERVAL -- but measured
    against the 24-compound set in this module's docstring it earns its
    place, which is more than was assumed:

        Pearson r(spread, |error|)      +0.66
        spread <= 0.30  (n=19)          mean |error| 0.15
        spread >  0.30  (n= 5)          mean |error| 0.84

    So a tight ensemble really does go with a better answer, by roughly
    5x. Useful as a triage signal.

    It is NOT a bound, and the failure that proves it is the same
    nitrophenol case above: 2,4-dinitrophenol is 2.70 units wrong at a
    spread of only 0.68, understating its own error four-fold. Fifty
    models sharing training data can agree closely and be wrong together,
    which is exactly what electron-poor phenols make them do. Read a wide
    spread as a warning; do not read a narrow one as a guarantee.

    Re-check with `benchmarks/pka/score_pka.py`, which reports these
    numbers at the end of its run.
    """

    #: The ionizable atom, in the CALLER's numbering, or None when the
    #: mapping could not be established. None is not "atom 0" and must not
    #: be rendered as an atom -- the defect this replaced did exactly that,
    #: pointing confidently at whichever atom happened to share the index.
    atom_index: int | None
    value: float
    stddev: float = 0.0


def compute_pka(mol: Chem.Mol, interpreter_path: str | None) -> list[PkaPrediction] | None:
    """Returns a `PkaPrediction` per ionizable centre pkasolver found, or
    `None` if no pkasolver environment is configured -- callers must treat
    `None` as "not installed," not "no ionizable atoms found."

    `atom_index` is in `mol`'s OWN numbering, or None where that could not
    be established. It used to be neither: pkasolver's raw
    `reaction_center_idx` indexes the pH-7 microstate Dimorphite-DL built
    by round-tripping the molecule through SMILES, so it silently named a
    different atom.

    Measured on the real sidecar, 2026-08-05, index against what it
    selects in each molecule:

        4-aminobenzoic acid  pKa 5.38  idx 7   ours: C     microstate: O
        ibuprofen            pKa 4.82  idx 12  ours: C     microstate: O
        acetic acid          pKa 4.19  idx  3  ours: O     microstate: O
        aniline              pKa 4.99  idx  0  ours: N     microstate: N

    The last two are the reason this went unnoticed for so long -- on a
    small molecule the two numberings often coincide, so the index looks
    right until the molecule is big enough to reorder. (An earlier revision
    of this docstring cited aniline as a failing case. It is not one; the
    measurement above is what the sidecar actually reports.)

    `map_site_atom` does the translation, against the microstate the runner
    now sends alongside each value.

    Raises `RuntimeError` when a pkasolver environment IS configured but
    the run fails, so a broken install is reported rather than silently
    degrading to the same state as "not installed."
    """
    if not pka_predictor_available(interpreter_path):
        return None

    smiles = Chem.MolToSmiles(mol)
    try:
        completed = subprocess.run(
            [str(interpreter_path), str(_RUNNER), smiles],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"pkasolver timed out after {_TIMEOUT_SECONDS}s") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not run the configured pkasolver interpreter: {exc}") from exc

    payload = _parse_runner_output(completed.stdout, completed.stderr, completed.returncode)
    return [
        PkaPrediction(
            # A runner predating `site_smiles` sends no microstate, so the
            # index cannot be mapped and None is the only honest answer --
            # NOT the raw index, which is what used to mislabel atoms.
            atom_index=map_site_atom(
                str(entry.get("site_smiles", "")), int(entry["atom_idx"]), mol
            ),
            value=float(entry["pka"]),
            # Older payloads predate the field; absent is not zero-spread,
            # but 0.0 is the only honest default that cannot overstate
            # confidence downstream (see how the pKa calculator prints it).
            stddev=float(entry.get("stddev", 0.0)),
        )
        for entry in payload["pkas"]
    ]


def _parse_runner_output(stdout: str, stderr: str, returncode: int) -> dict:
    # pkasolver's dependencies print progress/citation banners to stdout,
    # so the JSON payload is the LAST line rather than the whole stream.
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "error" in payload:
            raise RuntimeError(f"pkasolver failed: {payload['error']}")
        if "pkas" in payload:
            return payload
    raise RuntimeError(
        f"pkasolver produced no usable output (exit {returncode}). "
        f"stderr: {stderr.strip()[:400] or '<empty>'}"
    )


def describe_pka_status(interpreter_path: str) -> str:
    """One-line human-readable status for the External Tools dialog --
    mirrors `tool_download_service.describe_vina_status`. Actually runs a
    tiny prediction rather than just checking the path, since a configured
    but broken environment is the failure mode worth surfacing here.
    """
    # Checked before running anything: a path that is not an interpreter
    # produces an OS error naming neither the path nor the problem, and
    # the app knows where it installed the real one.
    from openchem.services.pkasolver_setup import default_install_root
    from openchem.services.sidecar_env import interpreter_problem, recovery_hint

    if interpreter_path and interpreter_path.strip():
        problem = interpreter_problem(interpreter_path)
        if problem is not None:
            return f"Not usable: {problem}{recovery_hint(default_install_root())}"
    if not pka_predictor_available(interpreter_path):
        return "Not configured — numeric pKa unavailable (ionizable-group detection still works)"
    # Three probes, not one. This used to report acetic acid alone, whose
    # -0.57 error is the third worst of the 24 compounds benchmarked below
    # -- so the single number a user saw was close to the model's worst
    # advert, and read as "inaccurate" when the measured MAE is 0.29.
    # An acid, a phenol and a base together show the real spread.
    probes = (("acetic acid", "CC(=O)O", 4.76), ("phenol", "Oc1ccccc1", 9.99),
              ("benzylamine", "NCc1ccccc1", 9.34))
    parts, errors = [], []
    for name, smiles, literature in probes:
        try:
            pkas = compute_pka(Chem.MolFromSmiles(smiles), interpreter_path)
        except RuntimeError as exc:
            return f"Configured but not working: {exc}"
        if not pkas:
            return f"Configured, but returned no pKa for {name} — check the install"
        nearest = min((p.value for p in pkas), key=lambda v: abs(v - literature))
        errors.append(abs(nearest - literature))
        parts.append(f"{name} {nearest:.2f} (lit {literature:.2f})")
    return (
        "Found: pkasolver — "
        + "; ".join(parts)
        + f". Off by {sum(errors)/len(errors):.2f} on average here; "
        "0.29 over the 24-compound check in this module's docstring."
    )
