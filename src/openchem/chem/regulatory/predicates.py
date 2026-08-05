"""A small declarative language for "what does this regulation describe".

WHY A LANGUAGE AND NOT JUST SMARTS. Regulations routinely constrain things
SMARTS cannot express. CWC Schedule 1.A.1 is "O-Alkyl (**<=C10**, incl.
cycloalkyl) alkyl-phosphonofluoridates": the connectivity is a SMARTS
question and the carbon count is not. Bolting a special case onto the
matcher for each such clause would produce a matcher nobody can audit, so
the conditions are data instead, and a new regulation becomes a JSON file
rather than a code change.

NOTHING SHORT-CIRCUITS, and that is the point rather than an inefficiency.
An `all` evaluates every child even once one has failed, because the
failures ARE the product: they are what lets the engine answer "nearest
rule, failed on one predicate -- missing the P-C bond" instead of
returning silence. A screen that can only say "no match" leaves a
legitimate user unable to see where the boundary runs, which is the
question they most often have.

REUSABLE ON PURPOSE. The same evaluator serves substructure search,
Markush handling and batch filtering; the regulatory engine is its first
consumer, not its only possible one.

An expression is a dict with an `op`, and either combines others
(`all`/`any`/`not`) or tests the molecule directly. Every leaf carries an
optional `label` so a failure reads as chemistry rather than as syntax.
"""

from __future__ import annotations

from typing import Any, Callable

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors

from openchem.chem.regulatory.types import PredicateOutcome


class PredicateError(ValueError):
    """A malformed expression.

    Raised rather than silently failing closed: a rule that cannot be
    evaluated must be visible at build time, because a regulation silently
    matching nothing is the worst outcome this system has.
    """


def evaluate(expression: Any, mol: Chem.Mol) -> tuple[bool, list[PredicateOutcome]]:
    """Evaluate `expression` against `mol`.

    Returns whether it held, and EVERY condition's outcome including the
    ones that failed.
    """
    if mol is None:
        raise PredicateError("No molecule to evaluate against.")
    if isinstance(expression, str):
        # A bare SMARTS is the common case and is accepted directly, so a
        # simple rule need not carry ceremony it does not use.
        expression = {"op": "contains", "smarts": expression}
    if not isinstance(expression, dict):
        raise PredicateError(f"Expression must be a dict or SMARTS, got {type(expression)!r}")

    op = str(expression.get("op", "")).strip().lower()
    if not op:
        raise PredicateError(f"Expression has no 'op': {expression!r}")

    if op in _COMBINATORS:
        return _COMBINATORS[op](expression, mol)
    if op not in _LEAVES:
        raise PredicateError(f"Unknown predicate op {op!r}")

    outcome = _LEAVES[op](expression, mol)
    return outcome.passed, [outcome]


# --- Combinators --------------------------------------------------------


def _op_all(expression: dict, mol: Chem.Mol) -> tuple[bool, list[PredicateOutcome]]:
    """Every child must hold -- and every child is EVALUATED regardless.

    Short-circuiting here would be a small speed win and would destroy the
    near-miss report, which needs to know that four conditions passed and
    one did not.
    """
    outcomes: list[PredicateOutcome] = []
    passed = True
    for child in _children(expression):
        child_passed, child_outcomes = evaluate(child, mol)
        outcomes.extend(child_outcomes)
        passed = passed and child_passed
    return passed, outcomes


def _op_any(expression: dict, mol: Chem.Mol) -> tuple[bool, list[PredicateOutcome]]:
    """One outcome for the GROUP, not one per alternative.

    An `any` is a single condition -- "the P-alkyl is methyl, ethyl,
    n-propyl or isopropyl" -- and reporting its branches individually is
    wrong twice over. Measured on the real CWC Schedule 1.A.1 rule:

      * SARIN MATCHED AND REPORTED THREE FAILURES, because it is
        P-methyl and so the ethyl, n-propyl and isopropyl branches did
        not fire. A successful match displaying three failed conditions
        is nonsense to read.
      * DFP's near-miss distance went from 1 to 4, pushing it past the
        threshold so the one case the explainer exists for stopped being
        reported at all.

    Every branch is still EVALUATED -- nothing short-circuits -- and which
    one fired is kept in `detail`, so no information is lost. What changes
    is that the group counts once toward the distance, which is what makes
    the distance mean anything.
    """
    # Two lists, not one. Conflating them produced "matched bromine,
    # fluorine" for a molecule containing no bromine -- the failing branch
    # was being recorded as if it had matched, because both were appended
    # to the same list and only the wording differed at the end.
    matched: list[str] = []
    tried: list[str] = []
    atoms: set[int] = set()
    passed = False

    for child in _children(expression):
        child_passed, child_outcomes = evaluate(child, mol)
        for outcome in child_outcomes:
            if outcome.label:
                tried.append(outcome.label)
        if child_passed:
            passed = True
            for outcome in child_outcomes:
                if outcome.passed:
                    atoms.update(outcome.atoms)
                    if outcome.label:
                        matched.append(outcome.label)

    label = expression.get("label") or "one of several alternatives"
    if passed:
        detail = f"matched {', '.join(matched)}" if matched else ""
    else:
        detail = f"none of: {', '.join(tried)}" if tried else ""
    return passed, [
        PredicateOutcome(
            label=label, passed=passed, detail=detail, atoms=frozenset(atoms)
        )
    ]


def _op_not(expression: dict, mol: Chem.Mol) -> tuple[bool, list[PredicateOutcome]]:
    children = _children(expression)
    if len(children) != 1:
        raise PredicateError("'not' takes exactly one child expression.")
    child_passed, child_outcomes = evaluate(children[0], mol)
    label = expression.get("label") or "must not match"
    # The child's own outcomes are kept alongside the negation, because
    # "this failed BECAUSE the excluded group was present" is the useful
    # reading and the bare inverted boolean is not.
    return (not child_passed), [
        PredicateOutcome(label=label, passed=not child_passed),
        *child_outcomes,
    ]


def _children(expression: dict) -> list[Any]:
    children = expression.get("of") or expression.get("children") or []
    if not isinstance(children, list) or not children:
        raise PredicateError(f"{expression.get('op')!r} needs a non-empty 'of' list.")
    return children


# --- Leaves -------------------------------------------------------------


def _smarts(expression: dict) -> Chem.Mol:
    pattern = expression.get("smarts", "")
    if not pattern:
        raise PredicateError("A structural predicate needs 'smarts'.")
    query = Chem.MolFromSmarts(pattern)
    if query is None:
        raise PredicateError(f"Invalid SMARTS: {pattern!r}")
    return query


def _leaf_contains(expression: dict, mol: Chem.Mol) -> PredicateOutcome:
    query = _smarts(expression)
    matches = mol.GetSubstructMatches(query)
    minimum = int(expression.get("min", 1))
    atoms = frozenset(i for match in matches for i in match)
    label = expression.get("label") or f"contains {expression['smarts']}"
    passed = len(matches) >= minimum
    detail = "" if passed else f"found {len(matches)}, needs {minimum}"
    return PredicateOutcome(label=label, passed=passed, detail=detail, atoms=atoms)


def _leaf_absent(expression: dict, mol: Chem.Mol) -> PredicateOutcome:
    query = _smarts(expression)
    matches = mol.GetSubstructMatches(query)
    label = expression.get("label") or f"lacks {expression['smarts']}"
    atoms = frozenset(i for match in matches for i in match)
    return PredicateOutcome(
        label=label,
        passed=not matches,
        detail="" if not matches else f"found {len(matches)}",
        atoms=atoms,
    )


def _leaf_count(expression: dict, mol: Chem.Mol) -> PredicateOutcome:
    query = _smarts(expression)
    found = len(mol.GetSubstructMatches(query))
    return _range_outcome(expression, found, f"count of {expression['smarts']}")


def _leaf_element_count(expression: dict, mol: Chem.Mol) -> PredicateOutcome:
    """Atoms of one element, in a range.

    The workhorse for CWC-style size limits: "alkyl of <=10 carbons" is a
    carbon count, and there is no SMARTS that says it.
    """
    symbol = str(expression.get("element", "C")).strip()
    found = sum(1 for atom in mol.GetAtoms() if atom.GetSymbol() == symbol)
    return _range_outcome(expression, found, f"{symbol} count")


def _leaf_ring_count(expression: dict, mol: Chem.Mol) -> PredicateOutcome:
    found = mol.GetRingInfo().NumRings()
    return _range_outcome(expression, found, "ring count")


def _leaf_hetero_count(expression: dict, mol: Chem.Mol) -> PredicateOutcome:
    found = sum(
        1 for atom in mol.GetAtoms() if atom.GetSymbol() not in ("C", "H")
    )
    return _range_outcome(expression, found, "heteroatom count")


def _leaf_charge(expression: dict, mol: Chem.Mol) -> PredicateOutcome:
    found = Chem.GetFormalCharge(mol)
    return _range_outcome(expression, found, "formal charge")


def _leaf_mw(expression: dict, mol: Chem.Mol) -> PredicateOutcome:
    return _range_outcome(expression, Descriptors.MolWt(mol), "molecular weight")


def _leaf_logp(expression: dict, mol: Chem.Mol) -> PredicateOutcome:
    return _range_outcome(expression, Crippen.MolLogP(mol), "cLogP")


def _leaf_fragment_count(expression: dict, mol: Chem.Mol) -> PredicateOutcome:
    """Disconnected components -- how a salt differs from its parent."""
    found = len(Chem.GetMolFrags(mol))
    return _range_outcome(expression, found, "fragment count")


def _leaf_has_stereo(expression: dict, mol: Chem.Mol) -> PredicateOutcome:
    """Whether any stereocentre is SPECIFIED.

    Regulations often reach "its isomers", so a rule may need to say that
    stereochemistry is or is not drawn. Unassigned centres do not count --
    an undrawn wedge is not a stereochemical claim.
    """
    centres = Chem.FindMolChiralCenters(
        mol, includeUnassigned=False, useLegacyImplementation=False
    )
    want = bool(expression.get("value", True))
    found = bool(centres)
    label = expression.get("label") or (
        "stereochemistry specified" if want else "no stereochemistry specified"
    )
    return PredicateOutcome(
        label=label,
        passed=found == want,
        detail="" if found == want else f"{len(centres)} specified centre(s)",
        atoms=frozenset(idx for idx, _ in centres),
    )


def _leaf_isotope(expression: dict, mol: Chem.Mol) -> PredicateOutcome:
    labelled = [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetIsotope()]
    want = bool(expression.get("value", True))
    found = bool(labelled)
    label = expression.get("label") or (
        "isotopically labelled" if want else "not isotopically labelled"
    )
    return PredicateOutcome(
        label=label, passed=found == want, atoms=frozenset(labelled)
    )


def _range_outcome(expression: dict, found: float, what: str) -> PredicateOutcome:
    """Shared min/max handling, so every numeric predicate reads alike."""
    minimum = expression.get("min")
    maximum = expression.get("max")
    exact = expression.get("equals")
    if minimum is None and maximum is None and exact is None:
        raise PredicateError(f"{what} needs one of 'min', 'max' or 'equals'.")

    passed = True
    if exact is not None:
        passed = found == exact
    if minimum is not None:
        passed = passed and found >= minimum
    if maximum is not None:
        passed = passed and found <= maximum

    bounds = []
    if exact is not None:
        bounds.append(f"= {exact}")
    if minimum is not None:
        bounds.append(f">= {minimum}")
    if maximum is not None:
        bounds.append(f"<= {maximum}")
    label = expression.get("label") or f"{what} {' and '.join(bounds)}"
    detail = "" if passed else f"found {found:g}"
    return PredicateOutcome(label=label, passed=passed, detail=detail)


_COMBINATORS: dict[str, Callable[[dict, Chem.Mol], tuple[bool, list[PredicateOutcome]]]] = {
    "all": _op_all,
    "any": _op_any,
    "not": _op_not,
}

_LEAVES: dict[str, Callable[[dict, Chem.Mol], PredicateOutcome]] = {
    "contains": _leaf_contains,
    "absent": _leaf_absent,
    "count": _leaf_count,
    "element_count": _leaf_element_count,
    "ring_count": _leaf_ring_count,
    "hetero_count": _leaf_hetero_count,
    "charge": _leaf_charge,
    "mw": _leaf_mw,
    "logp": _leaf_logp,
    "fragment_count": _leaf_fragment_count,
    "has_stereo": _leaf_has_stereo,
    "isotope": _leaf_isotope,
}

#: Every op a ruleset may use. Exposed so the build step can validate a
#: ruleset before it ships rather than discovering a typo at screening
#: time, when the symptom is a regulation that silently matches nothing.
SUPPORTED_OPS: frozenset[str] = frozenset(_COMBINATORS) | frozenset(_LEAVES)
