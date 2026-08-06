"""Lewis acid/base site analysis — offline, from the structure alone.

pKa answers "does it give up a proton", which is the wrong question for
most of inorganic and organometallic chemistry. Carbon monoxide is a
negligible Brønsted base and still forms an isolable adduct with borane
(H3B·CO, Burg & Schlesinger 1937). Nothing in this application, or in
Marvin, could say anything about that.

**An acceptor is an atom with an accessible low-energy acceptor orbital,
not an atom with an empty p orbital.** The empty-p reading fits BF3 and
AlCl3 and then fails on Fe(III), Zn(II), TiCl4, SO3, protonated carbonyls
and essentially all of coordination chemistry. Each way of accepting is a
named `AcceptorMechanism` with its own detector, and every detector emits
`LewisEvidence` saying which rule fired -- because "why is this atom
highlighted" is the question people actually ask, and several rules
routinely agree on one atom.

**What this module cannot do, measured rather than assumed.** Lone-pair
counting on carbon monoxide finds one pair on carbon and one on oxygen and
cannot say which donates. The answer -- carbon, despite oxygen being more
electronegative -- comes from the HOMO being carbon-localised, which needs
a wavefunction. Two candidate donor sites are reported and neither is
guessed at.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from openchem.chem.calculator_options import apply_microspecies, microspecies_note
from openchem.chem.electronic_properties import JENSEN_POLARIZABILITY
from openchem.chem.oxidation_states import classical_bonding_refusal, electronegativity_table
from openchem.domain.common import CacheState, Provenance
from openchem.domain.lewis import (
    AcceptorMechanism,
    LewisAnalysis,
    LewisEvidence,
    LewisRole,
    LewisSite,
    LewisStrength,
)
from openchem.domain.scientific_result import AlertResult
from openchem.domain.structure_issue import Basis

METHOD = "Lewis site analysis (structural rules)"

#: A filled valence shell, for the octet-deficiency arithmetic below.
_OCTET = 8

#: Hydrogen and helium fill at two, not eight.
_DUET_ELEMENTS = frozenset({"H", "He"})

_ASSUMPTIONS = (
    "Roles come from the structure as drawn -- connectivity, formal charge "
    "and lone-pair count -- not from a wavefunction.",
    "A lone pair is counted as an available donor pair. Whether it actually "
    "donates depends on which orbital it occupies, which needs a QM run.",
    "Strength is left unknown offline. Nothing here can rank two donors "
    "against each other, and a made-up ordering would be worse than none.",
)


def lone_pairs(atom: Any) -> int | None:
    """Non-bonding pairs, or None when the arithmetic does not apply.

    `outer electrons - bonds - formal charge`, halved.

    **Metals return None, and that is not a gap.** RDKit reports iron's
    valence list as `[-1]`, meaning no defined valence -- the same signal
    the valence checker and the oxidation-state module already act on.
    Running the arithmetic anyway gives Fe(III) "two lone pairs" when it is
    d5 with five UNPAIRED electrons, which is not a donor pair at all.
    Measured on the real thing before this guard was written.
    """
    from rdkit import Chem

    atomic_number = atom.GetAtomicNum()
    if atomic_number <= 0:
        return None
    table = Chem.GetPeriodicTable()
    if -1 in list(table.GetValenceList(atomic_number)):
        return None

    free = table.GetNOuterElecs(atomic_number) - atom.GetTotalValence() - atom.GetFormalCharge()
    return free // 2 if free >= 0 else None


def _shell_capacity(symbol: str) -> int:
    return 2 if symbol in _DUET_ELEMENTS else _OCTET


def octet_deficiency(atom: Any) -> int | None:
    """Electrons short of a filled valence shell, or None if not applicable.

    `capacity - 2*(bonds + lone pairs)`. Boron in BF3 has three bonds and
    no lone pair, so six electrons and a deficiency of two. Nitrogen in
    ammonia has three bonds and one pair -- eight, deficiency zero. A
    singlet carbene has two bonds and one pair, so six: deficient AND
    carrying a donor pair, which is exactly why it is ambiphilic.
    """
    pairs = lone_pairs(atom)
    if pairs is None:
        return None
    around = 2 * (int(atom.GetTotalValence()) + pairs)
    return max(0, _shell_capacity(atom.GetSymbol()) - around)


# --- acceptor detectors, one per mechanism ----------------------------------


def _empty_orbital_sites(mol: Any) -> dict[int, LewisEvidence]:
    """A main-group atom short of a filled shell has somewhere to put a pair."""
    found: dict[int, LewisEvidence] = {}
    for atom in mol.GetAtoms():
        deficiency = octet_deficiency(atom)
        if not deficiency:
            continue
        found[atom.GetIdx()] = LewisEvidence(
            rule="empty valence orbital",
            basis=Basis.DETERMINISTIC,
            mechanism=AcceptorMechanism.EMPTY_ORBITAL,
            supporting={
                "octet_deficiency": float(deficiency),
                "bonds": float(atom.GetTotalValence()),
            },
            note=(
                f"{atom.GetSymbol()}{atom.GetIdx() + 1} carries "
                f"{2 * (int(atom.GetTotalValence()) + (lone_pairs(atom) or 0))} valence "
                f"electrons, {deficiency} short of a filled shell."
            ),
        )
    return found


def _vacant_coordination_sites(mol: Any) -> dict[int, LewisEvidence]:
    """A metal centre with room in its coordination sphere.

    HEURISTIC, and deliberately loose: a bare cation such as Fe(3+) or
    Zn(2+) has an entirely empty sphere, and a four-coordinate d0 centre
    such as TiCl4 reaches six routinely. What counts as "room" depends on
    the metal, its oxidation state and the ligands, none of which this can
    see -- so it reports the opportunity rather than a coordination number.
    """
    table = electronegativity_table()
    metal_categories = {
        "alkali", "alkaline_earth", "transition", "post_transition",
        "lanthanide", "actinide",
    }
    found: dict[int, LewisEvidence] = {}
    for atom in mol.GetAtoms():
        entry = table.get(atom.GetSymbol())
        if entry is None or entry.get("category") not in metal_categories:
            continue
        coordination = atom.GetDegree()
        if coordination >= 6:
            continue
        found[atom.GetIdx()] = LewisEvidence(
            rule="vacant coordination site",
            basis=Basis.HEURISTIC,
            mechanism=AcceptorMechanism.VACANT_COORDINATION_SITE,
            supporting={
                "coordination_number": float(coordination),
                "formal_charge": float(atom.GetFormalCharge()),
            },
            note=(
                f"{atom.GetSymbol()}{atom.GetIdx() + 1} is a metal centre with "
                f"{coordination} bonded neighbours; a ligand pair can add to it."
            ),
        )
    return found


#: (SMARTS, index of the accepting atom within the match, description).
#: Kept as data so a new acceptor motif is one line rather than a branch.
_PI_STAR_PATTERNS: tuple[tuple[str, int, str], ...] = (
    ("[CX3]=[OX1]", 0, "carbonyl carbon"),
    ("[CX3]=[NX2]", 0, "imine carbon"),
    ("[CX2]#[NX1]", 0, "nitrile carbon"),
    ("[CX3]=[CX3][CX3]=[OX1]", 0, "Michael acceptor beta carbon"),
    ("[SX3](=[OX1])(=[OX1])=[OX1]", 0, "sulfur trioxide"),
    # Carbon monoxide and the isocyanides: a terminal carbon triple-bonded
    # to a more electronegative partner. These are THE textbook pi-acceptor
    # ligands, and without this rule carbon monoxide reads as a pure donor
    # -- which is the half of its behaviour that made this whole feature
    # worth building.
    ("[CX1-]#[OX1+]", 0, "carbon monoxide carbon"),
    ("[CX1-]#[NX2+]", 0, "isocyanide carbon"),
)


def _motif_sites(
    mol: Any,
    patterns: tuple[tuple[str, int, str], ...],
    rule: str,
    mechanism: AcceptorMechanism,
    tail: str,
) -> dict[int, LewisEvidence]:
    """Atoms matching any of `patterns`, at the pattern's marked position.

    `uniquify=False` is load-bearing rather than a default nobody thought
    about. RDKit's uniquifying collapses matches that cover the same ATOM
    SET, so on carbon tetrabromide -- where the four bromines are
    symmetry-equivalent and every one carries a sigma hole -- it returned
    four matches whose marked position happened to land on only two
    distinct bromines. Two identical atoms were flagged and two were not,
    which reads as a chemistry judgement and is really match ordering.
    """
    from rdkit import Chem

    found: dict[int, LewisEvidence] = {}
    for smarts, position, description in patterns:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is None:
            continue
        for match in mol.GetSubstructMatches(pattern, uniquify=False):
            index = match[position]
            if index in found:
                continue
            found[index] = LewisEvidence(
                rule=rule,
                basis=Basis.HEURISTIC,
                mechanism=mechanism,
                note=f"{description}; {tail}",
            )
    return found


def _pi_star_sites(mol: Any) -> dict[int, LewisEvidence]:
    """A low-lying pi* orbital accepts a pair without any empty orbital.

    HEURISTIC and motif-driven. Sulfur in SO3 has a filled shell by the
    valence arithmetic above and is still one of the strongest Lewis acids
    in common use, so structural electron counting alone cannot find these.
    """
    return _motif_sites(
        mol,
        _PI_STAR_PATTERNS,
        "low-lying pi* orbital",
        AcceptorMechanism.LOW_LYING_PI_STAR,
        "accepts into pi* rather than into an empty orbital.",
    )


#: A halogen or chalcogen bonded to an electron-withdrawing partner carries
#: a sigma hole opposite that bond.
_SIGMA_HOLE_PATTERNS: tuple[tuple[str, int, str], ...] = (
    ("[Cl,Br,I][CX4]([F,Cl,Br,I])([F,Cl,Br,I])", 0, "halogen on a polyhalogenated carbon"),
    ("[Br,I][c]", 0, "halogen on an aromatic ring"),
)


def _sigma_star_sites(mol: Any) -> dict[int, LewisEvidence]:
    """The sigma hole behind a polarised single bond -- halogen bonding.

    A halogen that also carries lone pairs comes out AMBIPHILIC, and that
    is the right answer rather than a rule collision: iodine in
    iodobenzene is a halogen-bond donor along the C-I axis and a
    nucleophile perpendicular to it, simultaneously.
    """
    return _motif_sites(
        mol,
        _SIGMA_HOLE_PATTERNS,
        "sigma hole",
        AcceptorMechanism.LOW_LYING_SIGMA_STAR,
        "accepts along the extension of its sigma bond.",
    )


_ACCEPTOR_DETECTORS = (
    _empty_orbital_sites,
    _vacant_coordination_sites,
    _pi_star_sites,
    _sigma_star_sites,
)


# --- donors -----------------------------------------------------------------


def _donor_evidence(atom: Any) -> LewisEvidence | None:
    pairs = lone_pairs(atom)
    if not pairs:
        return None
    supporting = {"lone_pairs": float(pairs)}
    polarizability = JENSEN_POLARIZABILITY.get(atom.GetSymbol())
    if polarizability is not None:
        # Polarizability is the physical basis of softness -- a soft donor
        # is a polarizable one. Reported as the measured quantity rather
        # than converted into a "softness" nobody defined.
        supporting["atomic_polarizability_A3"] = polarizability
    entry = electronegativity_table().get(atom.GetSymbol())
    if entry is not None:
        supporting["electronegativity"] = entry["pauling"]
    return LewisEvidence(
        rule="lone pair available",
        basis=Basis.DETERMINISTIC,
        supporting=supporting,
        note=f"{atom.GetSymbol()}{atom.GetIdx() + 1} carries {pairs} non-bonding pair"
        f"{'' if pairs == 1 else 's'}.",
    )


# --- the analysis ------------------------------------------------------------


def _refuse(molecule_uuid: str, reason: str) -> LewisAnalysis:
    return LewisAnalysis(
        molecule_uuid=molecule_uuid,
        refused=True,
        reason=reason,
        summary=f"Not assigned. {reason}",
        assumptions=_ASSUMPTIONS,
    )


def analyse(mol: Any, molecule_uuid: str = "") -> LewisAnalysis:
    """Donor and acceptor sites, or one reason why not."""
    from rdkit import Chem

    mol.UpdatePropertyCache(strict=False)

    if any(atom.GetAtomicNum() == 0 for atom in mol.GetAtoms()):
        return _refuse(
            molecule_uuid,
            "This structure contains query or R-group atoms, which have no element and "
            "therefore no donor or acceptor character.",
        )

    # The shared definition of "a two-centre bonding model does not apply
    # here" -- 3c-2e bridges, metal clusters, transition-metal-carbon
    # bonds. It lives in `oxidation_states` because that is where it was
    # first measured; defining it twice would let the two drift apart.
    bonding = classical_bonding_refusal(mol)
    if bonding is not None:
        return _refuse(molecule_uuid, bonding.reason)

    # Unpaired electrons break the PAIR arithmetic -- but only where that
    # arithmetic runs. `lone_pairs` already returns None for a metal, and
    # high-spin Fe(III) has five unpaired d electrons while being a
    # textbook hard Lewis acid. Refusing on it would have thrown away the
    # single most common acceptor class in coordination chemistry.
    # Measured: an earlier version did exactly that.
    radicals = [
        a.GetIdx()
        for a in mol.GetAtoms()
        if a.GetNumRadicalElectrons() and lone_pairs(a) is not None
    ]
    if radicals:
        return _refuse(
            molecule_uuid,
            "This structure carries unpaired electrons on a main-group atom. Donor and "
            "acceptor roles here are built on electron PAIRS, and an odd-electron centre "
            "is neither. A carbene drawn without its spin state lands here: the singlet "
            "has a donor pair and an empty orbital, the triplet has neither.",
        )

    acceptor_evidence: dict[int, list[LewisEvidence]] = {}
    for detector in _ACCEPTOR_DETECTORS:
        for index, evidence in detector(mol).items():
            acceptor_evidence.setdefault(index, []).append(evidence)

    sites: list[LewisSite] = []
    for atom in mol.GetAtoms():
        index = atom.GetIdx()
        donor = _donor_evidence(atom)
        accepts = acceptor_evidence.get(index, [])
        if donor is None and not accepts:
            continue
        if donor is not None and accepts:
            role = LewisRole.AMBIPHILIC
        elif donor is not None:
            role = LewisRole.DONOR
        else:
            role = LewisRole.ACCEPTOR
        sites.append(
            LewisSite(
                atom_index=index,
                symbol=atom.GetSymbol(),
                role=role,
                # Left UNKNOWN deliberately: see `_ASSUMPTIONS`.
                strength=LewisStrength.UNKNOWN,
                lone_pairs=lone_pairs(atom),
                evidence=tuple(([donor] if donor else []) + accepts),
            )
        )

    return LewisAnalysis(
        molecule_uuid=molecule_uuid,
        sites=tuple(sites),
        summary=_summarise(sites),
        assumptions=_ASSUMPTIONS,
        limitations=_limitations(sites),
    )


def _summarise(sites: list[LewisSite]) -> str:
    donors = [s for s in sites if s.role in (LewisRole.DONOR, LewisRole.AMBIPHILIC)]
    acceptors = [s for s in sites if s.role in (LewisRole.ACCEPTOR, LewisRole.AMBIPHILIC)]
    if not donors and not acceptors:
        return "No Lewis donor or acceptor sites found."
    parts = []
    if donors:
        parts.append(
            f"{len(donors)} donor site{'' if len(donors) == 1 else 's'} "
            f"({', '.join(f'{s.symbol}{s.atom_index + 1}' for s in donors[:6])})"
        )
    if acceptors:
        mechanisms = sorted({m.value for s in acceptors for m in s.mechanisms})
        parts.append(
            f"{len(acceptors)} acceptor site{'' if len(acceptors) == 1 else 's'} "
            f"via {', '.join(m.replace('_', ' ') for m in mechanisms)}"
        )
    return "; ".join(parts) + "."


def _describe(site: LewisSite) -> str:
    label = f"{site.symbol}{site.atom_index + 1}"
    reasons = "; ".join(f"{e.rule} [{e.basis.value}]" for e in site.evidence)
    return f"  {label}: {site.role.value} -- {reasons}"


def _without_heuristics(analysis: LewisAnalysis) -> LewisAnalysis:
    """Only what the arithmetic supports, re-deriving each role.

    Dropping the heuristic evidence is not enough on its own: an atom that
    was AMBIPHILIC because a motif matched alongside its lone pair is a
    plain donor once the motif is gone, and leaving the old label would be
    worse than not offering the option.
    """
    kept: list[LewisSite] = []
    for site in analysis.sites:
        evidence = tuple(e for e in site.evidence if e.basis is Basis.DETERMINISTIC)
        if not evidence:
            continue
        donates = any(e.mechanism is None for e in evidence)
        accepts = any(e.mechanism is not None for e in evidence)
        role = (
            LewisRole.AMBIPHILIC
            if donates and accepts
            else LewisRole.DONOR
            if donates
            else LewisRole.ACCEPTOR
        )
        kept.append(
            LewisSite(
                atom_index=site.atom_index,
                symbol=site.symbol,
                role=role,
                strength=site.strength,
                lone_pairs=site.lone_pairs,
                evidence=evidence,
            )
        )
    return replace(
        analysis,
        sites=tuple(kept),
        summary=_summarise(kept),
        limitations=_limitations(kept),
    )


def compute_lewis_sites(
    mol: Any, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> AlertResult:
    """The "lewis" category's site calculator."""
    parameters = parameters or {}
    # Protonation state is not a cosmetic setting here. An ammonium ion has
    # no lone pair and is not a donor at all, so the donor set at pH 2 and
    # at pH 10 are different answers rather than the same answer restated.
    target = apply_microspecies(mol, parameters)
    analysis = analyse(target, molecule_uuid)
    if not parameters.get("include_heuristic", True) and not analysis.refused:
        analysis = _without_heuristics(analysis)
    provenance = Provenance(created_by="core", method="lewis_sites")

    if analysis.refused:
        return AlertResult(
            alert_id="lewis_sites",
            name="Lewis Sites",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="lewis",
            cache_state=CacheState.FAILED,
            error=analysis.reason,
            provenance=provenance,
        )

    # Ambiphilic sites get their own heading rather than appearing under
    # both of the others. `donors()` and `acceptors()` each include them --
    # correct for a caller asking "can this donate", and duplicated noise
    # when read top to bottom.
    lines = [analysis.summary]
    groups = (
        ("Donor sites:", LewisRole.DONOR),
        ("Acceptor sites:", LewisRole.ACCEPTOR),
        ("Ambiphilic sites (both donor and acceptor):", LewisRole.AMBIPHILIC),
    )
    for heading, role in groups:
        matching = [site for site in analysis.sites if site.role is role]
        if matching:
            lines.append(heading)
            lines.extend(_describe(site) for site in matching)
    lines.extend(microspecies_note(parameters))
    lines.extend(f"Assumption: {text}" for text in analysis.assumptions)
    lines.extend(f"Limitation: {text}" for text in analysis.limitations)

    return AlertResult(
        alert_id="lewis_sites",
        name="Lewis Sites",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="lewis",
        provenance=provenance,
    )


def _limitations(sites: list[LewisSite]) -> tuple[str, ...]:
    limitations = [
        "Which lone pair actually donates depends on orbital energy and symmetry, "
        "which this cannot see. Carbon monoxide reports two candidate donors and "
        "donates through carbon.",
    ]
    if any(e.basis is Basis.HEURISTIC for s in sites for e in s.evidence):
        limitations.append(
            "Some sites here were found by structural motif rather than by "
            "arithmetic, and a motif can match a structure that does not behave "
            "the way the motif usually does."
        )
    return tuple(limitations)
