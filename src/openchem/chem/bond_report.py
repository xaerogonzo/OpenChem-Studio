"""Collectors for `BondReport` -- everything already known about one bond.

Same shape as `chem/atom_report.py` and for the same reasons: one function
per source, each free to return nothing, each isolated so that a source
which dislikes an exotic structure costs its own facts and no others.

**Nothing here computes chemistry.** Every fact is read off the molecule,
off a conformer that already exists, or out of results that arrived by
event. Opening a report must stay free.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from rdkit import Chem
from rdkit.Chem import BRICS, Lipinski

from openchem.domain.bond_report import BondReport
from openchem.domain.report import Detail, Fact, FactCategory, FactLink
from openchem.domain.structure_issue import Basis

_ASSUMPTIONS: tuple[str, ...] = (
    "Read from the structure as drawn. Nothing here re-perceives the "
    "molecule or recomputes a property.",
)

#: How RDKit spells a bond order, and how a person does.
_ORDER_NAMES = {
    Chem.BondType.SINGLE: "single",
    Chem.BondType.DOUBLE: "double",
    Chem.BondType.TRIPLE: "triple",
    Chem.BondType.AROMATIC: "aromatic",
    Chem.BondType.DATIVE: "dative",
}
_ORDER_GLYPHS = {
    Chem.BondType.SINGLE: "-",
    Chem.BondType.DOUBLE: "=",
    Chem.BondType.TRIPLE: "#",
    Chem.BondType.AROMATIC: ":",
    Chem.BondType.DATIVE: "->",
}


def _fact(
    category: FactCategory,
    label: str,
    value: Any,
    display: str,
    source: str,
    basis: Basis = Basis.DETERMINISTIC,
    evidence: tuple[str, ...] = (),
    limitations: tuple[str, ...] = (),
    link: FactLink | None = None,
    units: str = "",
    detail: Detail = Detail.STANDARD,
) -> Fact:
    return Fact(
        category=category,
        label=label,
        value=value,
        display_value=display,
        source=source,
        basis=basis,
        evidence=evidence,
        limitations=limitations,
        link=link,
        units=units,
        detail=detail,
    )


def bond_label(mol: Any, bond_index: int) -> str:
    """"C3=O4" -- element, 1-based index, and the order as a glyph.

    1-based because every other user-facing index in this application is,
    and because the structure checker's own messages already say "atoms 3
    and 4" for what RDKit calls 2 and 3.
    """
    bond = mol.GetBondWithIdx(bond_index)
    begin, end = bond.GetBeginAtom(), bond.GetEndAtom()
    glyph = _ORDER_GLYPHS.get(bond.GetBondType(), "-")
    return (
        f"{begin.GetSymbol()}{begin.GetIdx() + 1}"
        f"{glyph}"
        f"{end.GetSymbol()}{end.GetIdx() + 1}"
    )


def collect_intrinsic(mol: Any, index: int, _context: dict) -> list[Fact]:
    """What RDKit knows without being asked to compute anything."""
    bond = mol.GetBondWithIdx(index)
    begin, end = bond.GetBeginAtom(), bond.GetEndAtom()
    facts = [
        _fact(
            FactCategory.IDENTITY, "Bond", bond_label(mol, index),
            bond_label(mol, index), "RDKit",
        ),
        _fact(
            FactCategory.IDENTITY, "Order",
            _ORDER_NAMES.get(bond.GetBondType(), str(bond.GetBondType())),
            _ORDER_NAMES.get(bond.GetBondType(), str(bond.GetBondType())),
            "RDKit",
        ),
    ]
    # Each end links to its own atom report, which is the whole point of a
    # bond view sitting beside an atom view.
    for role, atom in (("From", begin), ("To", end)):
        facts.append(
            _fact(
                FactCategory.IDENTITY, role,
                atom.GetIdx(),
                f"{atom.GetSymbol()}{atom.GetIdx() + 1}",
                "RDKit",
                link=FactLink(
                    target="atom_report",
                    params={"atom_index": atom.GetIdx()},
                    label=f"Inspect {atom.GetSymbol()}{atom.GetIdx() + 1}",
                ),
            )
        )
    facts.append(
        _fact(FactCategory.STRUCTURE, "Aromatic", bond.GetIsAromatic(),
              "yes" if bond.GetIsAromatic() else "no", "RDKit")
    )
    facts.append(
        _fact(
            FactCategory.ELECTRONIC, "Conjugated", bond.GetIsConjugated(),
            "yes" if bond.GetIsConjugated() else "no", "RDKit",
            limitations=(
                "Conjugation raises the barrier to rotation but does not "
                "forbid it -- biphenyl's central bond is conjugated and "
                "still rotates.",
            ) if bond.GetIsConjugated() else (),
        )
    )
    stereo = str(bond.GetStereo()).replace("STEREO", "")
    if stereo and stereo != "NONE":
        facts.append(
            _fact(FactCategory.STRUCTURE, "Stereochemistry", stereo, stereo, "RDKit")
        )
    return facts


def collect_ring_membership(mol: Any, index: int, _context: dict) -> list[Fact]:
    ring_info = mol.GetRingInfo()
    count = ring_info.NumBondRings(index)
    if not count:
        return [_fact(FactCategory.TOPOLOGY, "In a ring", False, "no", "RDKit")]
    sizes = sorted(len(ring) for ring in ring_info.BondRings() if index in ring)
    facts = [
        _fact(FactCategory.TOPOLOGY, "In a ring", True,
              f"yes, in {count} ring{'s' if count > 1 else ''}", "RDKit"),
        _fact(FactCategory.TOPOLOGY, "Ring size", sizes,
              ", ".join(str(s) for s in sizes), "RDKit"),
    ]
    if count > 1:
        # A bond shared by two rings is where they are fused, and that is
        # a real structural statement rather than a restatement of the
        # count above.
        facts.append(
            _fact(FactCategory.TOPOLOGY, "Ring fusion", True,
                  "this bond is shared between rings", "RDKit")
        )
    return facts


def collect_geometry(mol: Any, index: int, _context: dict) -> list[Fact]:
    """Bond length, and ONLY from a genuinely 3D conformer.

    A 2D depiction has coordinates too, and they are drawing units: every
    bond in a layout is about the same length whatever its order. Reporting
    "1.50 A" from one would be a fabricated measurement, so a 2D conformer
    produces no length fact at all rather than a wrong one. Measured on
    aspirin: the 2D C=O reads 1.5 "units" against a real 1.264 A.
    """
    if mol.GetNumConformers() == 0:
        return []
    conformer = mol.GetConformer()
    if not conformer.Is3D():
        return []
    bond = mol.GetBondWithIdx(index)
    begin = conformer.GetAtomPosition(bond.GetBeginAtomIdx())
    end = conformer.GetAtomPosition(bond.GetEndAtomIdx())
    length = begin.Distance(end)
    return [
        _fact(FactCategory.GEOMETRY, "Length", length, f"{length:.3f}", "conformer",
              units="Å")
    ]


def collect_flexibility(mol: Any, index: int, _context: dict) -> list[Fact]:
    """Whether the bond is single, acyclic and between non-terminal atoms.

    **Deliberately not called "rotatable".** That word has a specific
    meaning set by `CalcNumRotatableBonds`, and this is not it: the
    molecule-level count uses a stricter definition that excludes amide and
    ester bonds among others. Two plausible reconstructions of it were
    tried and both failed -- excluding amides leaves aspirin at 3 against
    RDKit's 2, and excluding all conjugated bonds drops biphenyl's central
    bond, which RDKit does count. So this reports the structural fact it
    can stand behind and names the gap rather than guessing.
    """
    bond = mol.GetBondWithIdx(index)
    pairs = {
        frozenset(pair) for pair in mol.GetSubstructMatches(Lipinski.RotatableBondSmarts)
    }
    free = frozenset((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())) in pairs
    return [
        _fact(
            FactCategory.STRUCTURE, "Single, acyclic, non-terminal", free,
            "yes" if free else "no", "RDKit",
            basis=Basis.DETERMINISTIC,
            evidence=(f"SMARTS {Chem.MolToSmarts(Lipinski.RotatableBondSmarts)}",),
            limitations=(
                "This is the loose definition. The molecule-level rotatable-bond "
                "count uses a strict definition that also excludes amide and "
                "ester bonds, so the bonds flagged here outnumber it.",
            ),
        )
    ]


def collect_retrosynthesis(mol: Any, index: int, _context: dict) -> list[Fact]:
    """Whether BRICS would cut here, and into what environments.

    BRICS is a retrosynthetic fragmentation scheme: a bond it names is one
    that a known reaction class could plausibly form. That is a synthesis
    statement, not a stability one -- it does not mean the bond is weak.
    """
    bond = mol.GetBondWithIdx(index)
    ends = frozenset((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))
    for pair, environments in BRICS.FindBRICSBonds(mol):
        if frozenset(pair) == ends:
            return [
                _fact(
                    FactCategory.STRUCTURE, "Retrosynthetic disconnection", True,
                    f"BRICS bond, environments {environments[0]}/{environments[1]}",
                    "BRICS",
                    basis=Basis.HEURISTIC,
                    limitations=(
                        "BRICS describes where a known reaction class could "
                        "form this bond. It says nothing about how strong or "
                        "reactive the bond is.",
                    ),
                )
            ]
    return []


def collect_structure_issues(mol: Any, index: int, context: dict) -> list[Fact]:
    """Structure-check findings that name this bond.

    Keyed on `bond_indices`, which `StructureIssue` already carries -- the
    valence and geometry checkers populate it, so nothing had to change for
    a bond to find its own issues.
    """
    facts: list[Fact] = []
    for issue in context.get("issues", ()) or ():
        if index not in getattr(issue, "bond_indices", ()) or ():
            continue
        facts.append(
            _fact(
                FactCategory.STRUCTURE,
                getattr(issue, "checker_id", "issue"),
                issue,
                getattr(issue, "message", ""),
                "StructureCheck",
                basis=getattr(issue, "basis", Basis.HEURISTIC),
                link=FactLink(
                    target="structure_check",
                    params={"checker_id": getattr(issue, "checker_id", "")},
                    label="Open Structure Check",
                ),
            )
        )
    return facts


def collect_lewis(mol: Any, index: int, _context: dict) -> list[Fact]:
    """A Lewis role on either end, reported as a property of the bond.

    A sigma* acceptor is a property of a POLARISED BOND -- donation goes
    into the antibonding orbital of one -- so it belongs on the bond view
    as much as on the atom's. The analysis keys on atoms, so this reports
    which end carries the role rather than inventing a bond-level one.
    """
    from openchem.chem.lewis import analyse

    analysis = analyse(mol)
    bond = mol.GetBondWithIdx(index)
    ends = {bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()}
    facts: list[Fact] = []
    for site in getattr(analysis, "sites", ()):
        if site.atom_index not in ends:
            continue
        facts.append(
            _fact(
                FactCategory.ELECTRONIC,
                f"Lewis role at {site.symbol}{site.atom_index + 1}",
                site.role,
                str(getattr(site.role, "value", site.role)),
                "LewisAnalysis",
                basis=Basis.HEURISTIC,
                evidence=tuple(e.rule for e in site.evidence),
                link=FactLink(target="interactions", params={}, label="Open Interactions"),
            )
        )
    return facts


#: Where the conventional descriptions change, on the Pauling scale.
#: **These are a CONVENTION, not a measurement**, and different textbooks
#: draw them differently -- 1.7 and 2.0 are both in common use for the
#: ionic boundary. They are named here rather than buried so a reader can
#: disagree with the wording without doubting the number it came from.
_POLARITY_BANDS: tuple[tuple[float, str], ...] = (
    (0.4, "essentially non-polar"),
    (1.7, "polar covalent"),
    (float("inf"), "usually described as ionic"),
)


def _polarity_band(delta: float) -> str:
    return next(word for threshold, word in _POLARITY_BANDS if delta < threshold)


def collect_polarity(mol: Any, index: int, _context: dict) -> list[Fact]:
    """Electronegativity difference across the bond, and which end is
    negative.

    **Reported as Δχ, never as a percentage of ionic character.** The
    Pauling transform 1 - exp(-(Δχ)²/4) exists and would turn 0.9 into
    "18.3%", which is two digits of precision nobody measured on a
    quantity that is not observable. The formula is named in the fact's
    limitations so a reader who wants it knows exactly what is being
    withheld and why, rather than finding a suspiciously precise number.

    The DIRECTION is worth more than the magnitude for most purposes --
    "which end is δ-" is what somebody predicting a reaction actually
    needs -- so it is its own fact rather than something to infer.
    """
    from openchem.chem.oxidation_states import electronegativity_table

    table = electronegativity_table()
    bond = mol.GetBondWithIdx(index)
    begin, end = bond.GetBeginAtom(), bond.GetEndAtom()
    left = table.get(begin.GetSymbol(), {}).get("pauling")
    right = table.get(end.GetSymbol(), {}).get("pauling")
    if left is None or right is None:
        # A query atom, or an element with no accepted value. Saying so
        # beats an absent row, which reads as "this bond has no polarity".
        missing = sorted(
            {
                atom.GetSymbol()
                for atom, value in ((begin, left), (end, right))
                if value is None
            }
        )
        return [
            _fact(
                FactCategory.ELECTRONIC,
                "Electronegativity difference",
                None,
                f"No accepted Pauling value for {', '.join(missing)}",
                "Pauling",
                basis=Basis.DETERMINISTIC,
            )
        ]

    delta = abs(left - right)
    facts = [
        _fact(
            FactCategory.ELECTRONIC,
            "Electronegativity difference",
            round(delta, 2),
            f"{delta:.2f}",
            "Pauling",
            evidence=(
                f"{begin.GetSymbol()} {left:.2f}, {end.GetSymbol()} {right:.2f} "
                "on the Pauling scale",
            ),
            limitations=(
                "This is a difference of tabulated atomic values, not a property "
                "measured on this bond. It says nothing about the actual charge "
                "separation, which depends on everything else attached.",
                "No percentage of ionic character is given. The Pauling transform "
                "1 - exp(-(dX)^2/4) would render this as a two-decimal percentage, "
                "and that precision is not something anybody measured.",
            ),
        )
    ]

    if delta == 0:
        facts.append(
            _fact(
                FactCategory.ELECTRONIC,
                "Bond polarity",
                "none",
                # A homonuclear bond is non-polar for a REASON that a
                # threshold does not capture, so it is not run through the
                # bands: the two atoms are the same element.
                "Non-polar -- both atoms are the same element",
                "Pauling",
            )
        )
        return facts

    negative, positive = (end, begin) if right > left else (begin, end)
    facts.append(
        _fact(
            FactCategory.ELECTRONIC,
            "Bond polarity",
            f"{negative.GetSymbol()}{negative.GetIdx() + 1}",
            f"{positive.GetSymbol()}{positive.GetIdx() + 1}(d+) -> "
            f"{negative.GetSymbol()}{negative.GetIdx() + 1}(d-)",
            "Pauling",
            evidence=(
                f"{negative.GetSymbol()} is the more electronegative of the two",
            ),
        )
    )
    facts.append(
        _fact(
            FactCategory.ELECTRONIC,
            "Polarity description",
            _polarity_band(delta),
            _polarity_band(delta),
            "Pauling",
            basis=Basis.HEURISTIC,
            evidence=(
                f"dX = {delta:.2f}; the conventional boundaries used here are "
                f"{_POLARITY_BANDS[0][0]} and {_POLARITY_BANDS[1][0]}",
            ),
            limitations=(
                "A wording convention, not a result. Textbooks place the ionic "
                "boundary at 1.7 or at 2.0, so a bond near it will be described "
                "differently by different sources.",
            ),
            detail=Detail.ADVANCED,
        )
    )
    return facts


_COLLECTORS: tuple[Callable[[Any, int, dict], list[Fact]], ...] = (
    collect_intrinsic,
    collect_ring_membership,
    collect_geometry,
    collect_flexibility,
    collect_retrosynthesis,
    collect_structure_issues,
    collect_lewis,
    collect_polarity,
)


def build_bond_report(
    mol: Any,
    bond_index: int,
    *,
    molecule_uuid: str = "",
    structure_version: int = 0,
    context: dict | None = None,
    providers: Iterable[Any] = (),
) -> BondReport:
    """Everything known about one bond.

    A collector that raises is SKIPPED rather than allowed to take the
    whole report down -- one plugin, or one analysis that dislikes an
    exotic structure, should cost its own facts and nothing else.
    """
    mol.UpdatePropertyCache(strict=False)
    context = context or {}
    facts: list[Fact] = []

    for collector in _COLLECTORS:
        try:
            facts.extend(collector(mol, bond_index, context))
        except Exception:  # noqa: BLE001 - a failing source costs its own facts only
            continue

    for provider in providers:
        try:
            facts.extend(provider.collect_bond_facts(mol, bond_index, context))
        except Exception:  # noqa: BLE001 - a plugin must not break the report
            continue

    bond = mol.GetBondWithIdx(bond_index)
    return BondReport(
        molecule_uuid=molecule_uuid,
        bond_index=bond_index,
        begin_atom_index=bond.GetBeginAtomIdx(),
        end_atom_index=bond.GetEndAtomIdx(),
        label=bond_label(mol, bond_index),
        structure_version=structure_version,
        facts=tuple(facts),
        assumptions=_ASSUMPTIONS,
        limitations=_limitations(facts),
    )


def _limitations(facts: list[Fact]) -> tuple[str, ...]:
    """Each source's own limitations, once each."""
    limitations: list[str] = []
    for fact in facts:
        for text in fact.limitations:
            if text not in limitations:
                limitations.append(text)
    return tuple(limitations)
