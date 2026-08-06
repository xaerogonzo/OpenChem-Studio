"""Valence checking, and the two places it deliberately disagrees.

The 2D canvas is vendored Ketcher, whose valence model lives inside
Indigo's compiled WASM. We cannot change what it draws red and this build
has no highlighting API, so this checker is not a replacement for it -- it
is a second opinion that can be read alongside it and, where the two
disagree, can say why.

Measured on this build before any of it was written:

| structure          | Ketcher | RDKit sanitize | here      |
|--------------------|---------|----------------|-----------|
| FeO, Fe2O3, Fe3O4  | flags   | accepts        | accepts   |
| I(CH3)6            | flags   | rejects        | ERROR     |
| IF7                | --      | **rejects**    | accepts   |
| IF5, PhI(OAc)2     | --      | accepts        | accepts   |
| ClO4-              | --      | accepts        | accepts   |

Both disagreements are on purpose. Iron is a transition metal: RDKit
reports its valence list as `[-1]`, meaning it has no defined valence at
all, and main-group octet arithmetic simply does not apply to it. IF7 is a
real, characterised compound that RDKit's valence list for iodine
(`[1, 3, 5]`) has no room for.

So this does its own arithmetic rather than reporting RDKit's verdict.
Reporting RDKit's verdict would inherit the IF7 bug, and reporting
Ketcher's is impossible.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from openchem.chem.structure_check import (
    PARSED_MOLECULE,
    Basis,
    Category,
    CheckContext,
    CheckerDefinition,
    Severity,
    StructureIssue,
)
from openchem.domain.common import Provenance

_RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "hypervalent_rules.json"

#: Elements whose halogen-to-carbon multiple bonds are called out. A
#: halogen forms one sigma bond; a drawn C=I or C=Br is nearly always
#: either a slip or an ylide that belongs in its charge-separated form
#: (I+ -- C-). Reported as a WARNING and not an ERROR because iodonium
#: ylides are genuinely drawn both ways in the literature, and this project
#: does not call a real convention impossible.
_HALOGENS = frozenset({"F", "Cl", "Br", "I"})


@lru_cache(maxsize=1)
def hypervalent_rules() -> dict[str, dict[str, Any]]:
    """The shipped exception table, keyed by element symbol.

    Keys beginning with an underscore are documentation for whoever opens
    the file and are dropped here.
    """
    data = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _effective_valence(atom: Any, outer_electrons: int) -> int:
    """Valence adjusted for formal charge.

    The direction of the adjustment flips across the middle of the period,
    which is not a subtlety that can be skipped: ammonium nitrogen (4
    bonds, +1) and borohydride boron (4 bonds, -1) are both perfectly
    ordinary, and a rule that adds the charge in both cases calls one of
    them impossible. Elements with four or more outer electrons subtract
    it; the electron-poor ones add it.
    """
    valence = atom.GetTotalValence()
    charge = atom.GetFormalCharge()
    if outer_electrons >= 4:
        return valence - charge
    return valence + charge


def _check_valence(context: CheckContext) -> list[StructureIssue]:
    from rdkit import Chem

    mol = context.mol
    table = Chem.GetPeriodicTable()
    rules = hypervalent_rules()
    issues: list[StructureIssue] = []

    # Needed before GetTotalValence() on a molecule that was parsed
    # without sanitization -- which is exactly the case this checker has
    # to handle, since a structure RDKit refuses is one we still want an
    # opinion about.
    mol.UpdatePropertyCache(strict=False)

    for atom in mol.GetAtoms():
        symbol = atom.GetSymbol()
        atomic_number = atom.GetAtomicNum()
        if atomic_number == 0:  # a query/dummy atom has no valence to check
            continue

        allowed = list(table.GetValenceList(atomic_number))
        if -1 in allowed:
            # No defined valence: every transition metal, plus the alkali
            # and alkaline-earth metals. This is the branch that stops
            # FeO and Fe2O3 being reported, and it is a statement about
            # the periodic table rather than a special case for iron.
            continue

        outer = table.GetNOuterElecs(atomic_number)
        valence = _effective_valence(atom, outer)
        if valence in allowed:
            continue

        index = atom.GetIdx()
        ligands = sorted({n.GetSymbol() for n in atom.GetNeighbors()})
        rule = rules.get(symbol)

        if valence > max(allowed):
            permitted = rule.get("permitted_valences", []) if rule else []
            allowed_ligands = set(rule.get("expanded_octet_requires_ligands", [])) if rule else set()
            maximum = rule.get("maximum_valence", 0) if rule else 0

            if rule and valence in permitted and valence <= maximum and set(ligands) <= allowed_ligands:
                issues.append(
                    StructureIssue(
                        checker_id="hypervalent_allowed",
                        category=Category.VALIDITY,
                        severity=Severity.INFO,
                        basis=Basis.DETERMINISTIC,
                        message=(
                            f"{symbol}{index + 1} has an expanded octet (valence {valence}). "
                            f"Accepted here: {rule['reference']}, stabilised by "
                            f"{'/'.join(sorted(allowed_ligands))} ligands "
                            f"(e.g. {rule['examples'][0]})."
                        ),
                        atom_indices=(index,),
                        explains_editor_warning=True,
                    )
                )
                continue

            issues.append(
                StructureIssue(
                    checker_id="valence",
                    category=Category.VALIDITY,
                    severity=Severity.ERROR,
                    basis=Basis.DETERMINISTIC,
                    message=_over_valence_message(symbol, index, valence, allowed, ligands, rule),
                    atom_indices=(index,),
                )
            )
            continue

        # Below the element's maximum but not one of its usual states --
        # a radical, a carbene, a nitrene, or a slip. Marvin's yellow, not
        # its red: these are all things somebody draws on purpose.
        issues.append(
            StructureIssue(
                checker_id="unusual_valence",
                category=Category.VALIDITY,
                severity=Severity.WARNING,
                basis=Basis.DETERMINISTIC,
                message=(
                    f"{symbol}{index + 1} has valence {valence}; "
                    f"{symbol} is normally {_join_or(allowed)}. "
                    "This is what a radical or a carbene looks like, so it may be deliberate."
                ),
                atom_indices=(index,),
            )
        )

    issues.extend(_halogen_multiple_bonds(mol))
    return issues


def _over_valence_message(
    symbol: str,
    index: int,
    valence: int,
    allowed: list[int],
    ligands: list[str],
    rule: dict[str, Any] | None,
) -> str:
    """Say which rule refused it, not just that something did.

    When an element HAS an expanded-octet rule and still failed it, the
    reason is the interesting part -- I(CH3)6 fails on both counts and
    saying so is what distinguishes it from IF7 in the reader's mind.
    """
    base = f"{symbol}{index + 1} has valence {valence}; {symbol} is normally {_join_or(allowed)}."
    if not rule:
        return base
    if valence not in rule.get("permitted_valences", []):
        return (
            f"{base} {symbol} does form expanded octets, but only at "
            f"{_join_or(rule['permitted_valences'])} "
            f"({rule['reference']}) -- ligands are added in pairs, so {valence} is not reachable."
        )
    unsupported = sorted(set(ligands) - set(rule.get("expanded_octet_requires_ligands", [])))
    return (
        f"{base} {symbol} reaches valence {valence} only with "
        f"{'/'.join(rule['expanded_octet_requires_ligands'])} ligands "
        f"(e.g. {rule['examples'][0]}); here it is bonded to {'/'.join(unsupported)}."
    )


def _halogen_multiple_bonds(mol: Any) -> list[StructureIssue]:
    """A halogen in a double or triple bond to carbon."""
    from rdkit import Chem

    issues: list[StructureIssue] = []
    for bond in mol.GetBonds():
        if bond.GetBondType() not in (Chem.BondType.DOUBLE, Chem.BondType.TRIPLE):
            continue
        begin, end = bond.GetBeginAtom(), bond.GetEndAtom()
        pairs = ((begin, end), (end, begin))
        for halogen, other in pairs:
            if halogen.GetSymbol() in _HALOGENS and other.GetSymbol() == "C":
                order = "double" if bond.GetBondType() == Chem.BondType.DOUBLE else "triple"
                issues.append(
                    StructureIssue(
                        checker_id="halogen_multiple_bond",
                        category=Category.VALIDITY,
                        severity=Severity.WARNING,
                        basis=Basis.DETERMINISTIC,
                        message=(
                            f"{halogen.GetSymbol()}{halogen.GetIdx() + 1} is drawn with a "
                            f"{order} bond to carbon. Halogens form one sigma bond; the "
                            f"ylide is normally written charge-separated "
                            f"({halogen.GetSymbol()}+ -- C-)."
                        ),
                        atom_indices=(halogen.GetIdx(), other.GetIdx()),
                        bond_indices=(bond.GetIdx(),),
                    )
                )
                break
    return issues


def _join_or(values: list[int]) -> str:
    numbers = [str(v) for v in values]
    if len(numbers) == 1:
        return numbers[0]
    return ", ".join(numbers[:-1]) + " or " + numbers[-1]


def _check_sanitizable(context: CheckContext) -> list[StructureIssue]:
    """Report RDKit's own refusal, when it refuses.

    Kept separate from the valence checker rather than folded into it,
    because the two answer different questions. This one says "the toolkit
    cannot work with this structure, so most other analysis is
    unavailable", which is true even when our own valence arithmetic is
    happy -- IF7 is exactly that case, and a reader deserves to know that
    descriptors will not run on it.
    """
    if context.has("sanitized_molecule"):
        return []
    return [
        StructureIssue(
            checker_id="sanitizable",
            category=Category.VALIDITY,
            severity=Severity.WARNING,
            basis=Basis.DETERMINISTIC,
            message=(
                "RDKit will not sanitize this structure, so descriptors, naming and "
                f"3D generation are unavailable for it. RDKit says: {context.sanitization_error}"
            ),
        )
    ]


def register(registry: Any) -> None:
    provenance = Provenance(
        created_by="core",
        method="own valence arithmetic + hypervalent_rules.json",
        parameters={"rules_file": _RULES_PATH.name},
    )
    registry.register(
        CheckerDefinition(
            checker_id="valence",
            display_name="Valence",
            category=Category.VALIDITY,
            run=_check_valence,
            requires=frozenset({PARSED_MOLECULE}),
            provenance=provenance,
            description=(
                "Atom valences against the periodic table, with expanded octets "
                "allowed where the ligands justify them."
            ),
        )
    )
    registry.register(
        CheckerDefinition(
            checker_id="sanitizable",
            display_name="RDKit compatibility",
            category=Category.VALIDITY,
            run=_check_sanitizable,
            requires=frozenset({PARSED_MOLECULE}),
            provenance=Provenance(created_by="core", method="RDKit sanitization"),
            description="Whether the rest of the toolkit can work with this structure.",
        )
    )
