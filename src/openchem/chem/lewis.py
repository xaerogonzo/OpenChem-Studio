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
from openchem.domain.report import ReportResult
from openchem.chem.report_adapter import report_fields
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
    found: dict[int, LewisEvidence] = {}
    for atom in mol.GetAtoms():
        entry = table.get(atom.GetSymbol())
        if entry is None or entry.get("category") not in _METAL_CATEGORIES:
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
    # Sulfur dioxide keeps a lone pair, so the octet arithmetic calls it
    # complete and the expandable-shell rule skips it -- yet it forms
    # isolable adducts with amines. It comes out AMBIPHILIC, which is
    # right: it donates through that lone pair too.
    ("[SX2](=[OX1])=[OX1]", 0, "sulfur dioxide"),
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


#: Handled by `_vacant_coordination_sites`, which says the same thing with
#: a better note. The expandable-shell rule below defers to it rather than
#: firing alongside it -- aluminium in AlCl3 was collecting three pieces of
#: evidence for what is really two facts.
_METAL_CATEGORIES = frozenset(
    {"alkali", "alkaline_earth", "transition", "post_transition", "lanthanide", "actinide"}
)

#: Highest atomic number in each period, for "can this expand its shell".
_PERIOD_LIMITS = (2, 10, 18, 36, 54, 86)


def _period(atomic_number: int) -> int:
    return next(
        (index + 1 for index, limit in enumerate(_PERIOD_LIMITS) if atomic_number <= limit),
        7,
    )


def _hydrogen_bond_donor_sites(mol: Any) -> dict[int, LewisEvidence]:
    """An X-H bond accepts a lone pair into its sigma* orbital.

    **This is the same mechanism as a halogen bond, not a separate kind of
    thing.** A hydrogen bond and a halogen bond are both donation into the
    sigma* of a polarised single bond; only the identity of the heavy atom
    differs. Sharing `LOW_LYING_SIGMA_STAR` between them is the honest
    description rather than a convenience.

    Found because the adduct engine refused fourteen of the twenty-four
    acids in its OWN Drago-Wayland table -- phenol, the alcohols, pyrrole,
    chloroform. Those are hydrogen-bond donors, and Drago's calorimetry
    treats them as acids because they are.

    An alcohol comes out AMBIPHILIC: its oxygen donates lone pairs and its
    O-H accepts. Water is the textbook case of exactly that.

    The site is the HEAVY atom, not the hydrogen. RDKit hydrogens are
    usually implicit and have no index to report, and a highlight on the
    oxygen is what a reader is looking for anyway.
    """
    from rdkit import Chem

    found: dict[int, LewisEvidence] = {}
    # An H on carbon only counts when the carbon is polarised by halogens
    # -- chloroform is a real hydrogen-bond donor and methane is not.
    patterns = (
        # NX2 as well as NX3: isocyanic acid's nitrogen has one heavy
        # neighbour and one hydrogen, and SMARTS X counts hydrogens.
        ("[$([OX2,NX2,NX3,SX2,nX3;!H0])]", "electronegative atom"),
        ("[$([CX4;!H0]([F,Cl,Br,I])[F,Cl,Br,I])]", "polyhalogenated carbon"),
    )
    for smarts, description in patterns:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is None:
            continue
        for (index,) in mol.GetSubstructMatches(pattern, uniquify=False):
            if index in found:
                continue
            atom = mol.GetAtomWithIdx(index)
            found[index] = LewisEvidence(
                rule="hydrogen-bond donor",
                basis=Basis.HEURISTIC,
                mechanism=AcceptorMechanism.LOW_LYING_SIGMA_STAR,
                supporting={"hydrogens": float(atom.GetTotalNumHs())},
                note=(
                    f"{atom.GetSymbol()}{index + 1} is a {description} carrying "
                    "hydrogen; a lone pair is accepted into the X-H sigma*, the "
                    "same mechanism as a halogen bond."
                ),
            )
    return found


def _dihalogen_sites(mol: Any) -> dict[int, LewisEvidence]:
    """The sigma hole in a halogen-halogen bond.

    Molecular iodine is THE textbook halogen-bond acceptor -- most of the
    Drago-Wayland calorimetry is iodine adducts -- and the carbon-bound
    patterns miss it entirely, because there is no carbon. Found when the
    adduct engine refused I2 + benzene, which is a pair in its own
    validation set.

    **The hole is on the LESS electronegative halogen**, so this is not a
    symmetric SMARTS. In iodine monochloride the iodine is the acceptor
    end and the chlorine is the donor end; flagging both would invert the
    chemistry of every interhalogen while looking right for I2.
    """
    table = electronegativity_table()
    found: dict[int, LewisEvidence] = {}
    for bond in mol.GetBonds():
        begin, end = bond.GetBeginAtom(), bond.GetEndAtom()
        entries = [table.get(a.GetSymbol()) for a in (begin, end)]
        if any(e is None or e.get("category") != "halogen" for e in entries):
            continue
        first, second = entries[0]["pauling"], entries[1]["pauling"]
        if first < second:
            holes = [begin]
        elif second < first:
            holes = [end]
        else:
            holes = [begin, end]
        for atom in holes:
            partner = end if atom is begin else begin
            found[atom.GetIdx()] = LewisEvidence(
                rule="sigma hole",
                basis=Basis.HEURISTIC,
                mechanism=AcceptorMechanism.LOW_LYING_SIGMA_STAR,
                note=(
                    f"{atom.GetSymbol()}{atom.GetIdx() + 1} is the less "
                    f"electronegative end of a {atom.GetSymbol()}-{partner.GetSymbol()} "
                    "bond; it accepts along the extension of that bond."
                ),
            )
    return found


def _expandable_shell_sites(mol: Any) -> dict[int, LewisEvidence]:
    """A heavy main-group centre that can hold more than eight electrons.

    Antimony pentachloride takes a chloride to give SbCl6-, and it is one
    of the strongest acids in the Drago table; phosphorus pentafluoride
    gives PF6-, silicon tetrafluoride gives SiF6(2-). None of them is
    octet-deficient, none is a metal, and none has a pi* -- so every
    other detector here misses them, which is how this one came to be
    written.

    Period 3 or below is the load-bearing condition: it is what makes
    d orbitals and an expanded shell available at all. Carbon
    tetrafluoride has the same electron count as silicon tetrafluoride
    and cannot do this, and the period test is the only thing separating
    them.
    """
    table = electronegativity_table()
    found: dict[int, LewisEvidence] = {}
    for atom in mol.GetAtoms():
        if _period(atom.GetAtomicNum()) < 3:
            continue
        entry = table.get(atom.GetSymbol())
        if entry is not None and entry.get("category") in _METAL_CATEGORIES:
            continue  # `_vacant_coordination_sites` owns these.
        pairs = lone_pairs(atom)
        # None means a metal, which `_vacant_coordination_sites` owns.
        # A remaining lone pair means the atom is a donor, not an acceptor
        # -- triphenylphosphine has one and must not land here.
        if pairs is None or pairs != 0:
            continue
        degree = atom.GetDegree()
        if degree < 2 or degree >= 6:
            continue
        found[atom.GetIdx()] = LewisEvidence(
            rule="expandable valence shell",
            basis=Basis.HEURISTIC,
            mechanism=AcceptorMechanism.VACANT_COORDINATION_SITE,
            supporting={"coordination_number": float(degree)},
            note=(
                f"{atom.GetSymbol()}{atom.GetIdx() + 1} is a period-"
                f"{_period(atom.GetAtomicNum())} main-group centre with no lone "
                f"pair and {degree} bonds; it can hold more than eight electrons."
            ),
        )
    return found


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
    _expandable_shell_sites,
    _pi_star_sites,
    _sigma_star_sites,
    _dihalogen_sites,
    _hydrogen_bond_donor_sites,
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


def pi_donor_atoms(mol: Any) -> tuple[int, ...]:
    """Atoms carrying a pi system that can donate to an acceptor.

    **Deliberately NOT reported as `LewisSite`s**, and the reason is the
    whole design of this module. Benzene really is a pi donor -- its
    iodine adduct is measured at 1.4 kcal/mol, the weakest entry in the
    Drago table -- but listing every aromatic carbon as a donor site
    would put a dozen sites on every drug-like molecule and bury the
    lone-pair donors that anybody actually wants to see.

    So the two questions are separated. "Which atoms are donor sites"
    means lone pairs, and stays clean enough to read. "Can this molecule
    act as a base at all" includes pi donation, and is what the adduct
    engine asks before refusing a pair.

    That split is also why `test_a_saturated_hydrocarbon_has_no_lewis_site_at_all`
    still holds for benzene: it has no lone pair, and that test is the
    control stopping a rule that flags everything.
    """
    donors: set[int] = set()
    for bond in mol.GetBonds():
        from rdkit import Chem

        aromatic = bond.GetIsAromatic()
        multiple = bond.GetBondType() in (
            Chem.BondType.DOUBLE,
            Chem.BondType.TRIPLE,
        )
        if not (aromatic or multiple):
            continue
        begin, end = bond.GetBeginAtom(), bond.GetEndAtom()
        # Carbon-carbon only. A C=O pi bond is polarised the other way --
        # the carbon is the ACCEPTOR there, which `_pi_star_sites`
        # already reports, and calling the same bond a donor would be
        # saying both things about one thing.
        if {begin.GetSymbol(), end.GetSymbol()} != {"C"}:
            continue
        donors.update((begin.GetIdx(), end.GetIdx()))
    return tuple(sorted(donors))


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
) -> ReportResult:
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
        return _report(
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
    lines.extend(_gutmann_lines(target))
    lines.extend(microspecies_note(parameters))
    lines.extend(f"Assumption: {text}" for text in analysis.assumptions)
    lines.extend(f"Limitation: {text}" for text in analysis.limitations)

    return _report(
        alert_id="lewis_sites",
        name="Lewis Sites",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="lewis",
        provenance=provenance,
    )


def _gutmann_lines(mol: Any) -> list[str]:
    """Measured donicity, when the drawn structure IS one of the 68 liquids.

    `domain/lewis.py` was written with room for exactly this: "The shape
    also has room for what is coming -- donor and acceptor numbers".

    **A MEASURED NUMBER BESIDE A PERCEIVED ROLE, NOT INSTEAD OF ONE.** The
    sites above are perceived from the structure; these are what somebody
    measured for this liquid, and the two answer different questions. A
    reader deciding whether THF really donates has the experiment right
    there.

    **DN AND AN ARE TWO LINES, ALWAYS.** `chem/gutmann.py` records why: a
    solvent can be high in both (water 18.0/54.8) or high in one and
    nearly zero in the other (HMPA 38.8/10.6), so "the Gutmann number" is
    not a well-formed question. Folding them into one field would erase
    that without breaking any numeric test -- which is what
    `tests/test_gutmann_bridge.py` asserts against, on the parsed facts
    rather than on the prose.
    """
    from openchem.chem.gutmann import donicity_for_structure

    record = donicity_for_structure(mol)
    if record is None:
        return []

    lines = [f"Measured as a solvent ({record.name}), Gutmann 1976:"]
    if record.donor_number is not None:
        lines.append(f"Gutmann donor number (DN): {record.donor_number:.1f} kcal/mol")
    if record.bulk_donicity is not None:
        lines.append(f"Gutmann bulk donicity: {record.bulk_donicity:.1f} kcal/mol")
    if record.acceptor_number is not None:
        lines.append(f"Gutmann acceptor number (AN): {record.acceptor_number:.1f}")
    lines.append(
        "Limitation: DN and AN are separate scales, not two ends of one -- DN is "
        "-dH against SbCl5 in kcal/mol, AN is a dimensionless 31P shift between "
        "hexane at 0 and SbCl5 at 100."
    )
    return lines


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


def _report(**fields) -> ReportResult:
    """One `AlertResult(...)` call site, as a `ReportResult`.

    The keyword names are unchanged -- `alert_id`, `name`, `matched`,
    `category` -- so the call sites above read as they always did and the
    diff stays small. `report_fields` does the translation and turns each
    line into a `Fact`; see `chem/report_adapter.py` for what a string can
    and cannot carry.

    A calculator that wants real units, evidence or limitations on a fact
    builds `Fact`s directly instead, as `geometry_analysis` now does.
    """
    return ReportResult(**report_fields(**fields))
