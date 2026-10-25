"""What can and cannot be checked about one planned route, as SEPARATE outcomes and never one pass/fail (`docs/SYNTHESIS_HELPER_DESIGN.md` 0d, moved here from the spike in Stage 1 slice 6).

A `Route` carries the planner's own bookkeeping twice: the molecules of each step (`product`, `reactants`) and, when the planner supplied it, the mapped reaction of the real molecules (`reaction_smiles`, written product first, as the planner writes a retrosynthetic step). This module reads the two against each other. It says nothing about the chemistry being right: `ValidationReport.fully_validated` means the route's own books are clean.

THE OUTCOMES, each its own field of the `ValidationReport`:
  1. `molecules`: every molecule of the route (target, intermediates, starting materials) parses and sanitizes under RDKit.
  2. `reactions`: every step's reaction parses and ITS SIDES ARE THE MOLECULES THE STEP CONNECTS (the left side is the step's product, the right side its reactants, compared as canonical SMILES with atom maps removed and stereo kept). A step with no reaction SMILES at all is `not_assessable` (the planner did not give enough to check), not a failure; one that is present and does not parse, or whose sides are not its molecules, is a failure.
  3. `mapping`: per step `complete` (every heavy atom of the left side carries a map number, none repeated on a side), `partial` or `absent`; the route is `complete` only if every step is, `absent` only if every step is.
  4. `conservation`: ASSESSED ONLY WHERE THE MAPPING IS COMPLETE, otherwise `not_assessable`, never a pass or a fail. The rule is fixed: every mapped atom of the left side has exactly one atom with the same map number on the right and the same element. Atoms on the right with no partner on the left (a leaving group's or a reagent's atoms) are PERMITTED and counted in `unmapped_right_atoms`, not judged. Charge and hydrogen counts are not compared (a planner may write an acid and its salt).
  5. `stock`: the starting materials' `in_stock` flags: `all_in_stock`, `some_not_in_stock` or `not_provided` (any flag missing, which outranks a False). A match against a catalogue snapshot, not availability, and not a validity outcome.
  6. `missing`: what the planner did not supply, field by field.

NOTHING IS INVENTED to make a route pass: no atom is added, no mapping repaired, no reaction balanced. Never raises for anything in a route: a molecule or reaction RDKit cannot read is an outcome.
"""

from __future__ import annotations

from rdkit import Chem, rdBase

from openchem.domain.synthesis_route import Check, MappingStatus, Route, RouteStep, StockStatus, ValidationReport, route_molecules


def _parse(smiles: str) -> Chem.Mol | None:
    with rdBase.BlockLogs():
        return Chem.MolFromSmiles(smiles)


def _canonical(smiles: str) -> str | None:
    """Canonical isomeric SMILES with atom maps removed, or None if it does not parse."""
    mol = _parse(smiles)
    if mol is None:
        return None
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(mol)


def _side(text: str) -> list[Chem.Mol] | None:
    """The molecules of one side of a reaction SMILES (dot-separated), maps kept; None if any does not parse."""
    mols = []
    for part in text.split("."):
        mol = _parse(part)
        if mol is None:
            return None
        mols.append(mol)
    return mols


def _heavy(mols: list[Chem.Mol]) -> list[Chem.Atom]:
    return [a for m in mols for a in m.GetAtoms() if a.GetAtomicNum() > 1]


def _numbers(mols: list[Chem.Mol]) -> list[int]:
    return [a.GetAtomMapNum() for m in mols for a in m.GetAtoms() if a.GetAtomMapNum() > 0]


def _step_mapping(left: list[Chem.Mol], right: list[Chem.Mol]) -> MappingStatus:
    heavy = _heavy(left)
    mapped = [a for a in heavy if a.GetAtomMapNum() > 0]
    if not mapped:
        return MappingStatus.ABSENT
    numbers = [a.GetAtomMapNum() for a in mapped]
    right_numbers = _numbers(right)
    if len(mapped) < len(heavy) or len(set(numbers)) < len(numbers) or len(set(right_numbers)) < len(right_numbers):
        return MappingStatus.PARTIAL
    return MappingStatus.COMPLETE


def _step_conservation(left: list[Chem.Mol], right: list[Chem.Mol]) -> tuple[int, list[str]]:
    """(atoms on the right with no partner on the left, reasons the step does not conserve). Every mapped left atom needs one same-element right atom with its number."""
    right_by_number: dict[int, list[int]] = {}
    for mol in right:
        for atom in mol.GetAtoms():
            if atom.GetAtomMapNum() > 0:
                right_by_number.setdefault(atom.GetAtomMapNum(), []).append(atom.GetAtomicNum())
    reasons: list[str] = []
    left_numbers: set[int] = set()
    for mol in left:
        for atom in mol.GetAtoms():
            number = atom.GetAtomMapNum()
            if number == 0:
                continue
            left_numbers.add(number)
            partners = right_by_number.get(number, [])
            if not partners:  # a number repeated on the right was caught earlier, as a partial mapping
                reasons.append(f"map {number} ({atom.GetSymbol()}) has 0 partners on the right")
            elif partners[0] != atom.GetAtomicNum():
                reasons.append(f"map {number} changes element ({atom.GetSymbol()} to atomic number {partners[0]})")
    extras = sum(1 for number in right_by_number if number not in left_numbers) + sum(1 for m in right for a in m.GetAtoms() if a.GetAtomMapNum() == 0 and a.GetAtomicNum() > 1)
    return extras, reasons


def _missing(step: RouteStep) -> list[str]:
    fields = {"reaction_smiles": step.reaction_smiles, "policy_probability": step.policy_probability, "template_id": step.template_id, "policy_name": step.policy_name}
    return [f"step.{name}" for name, value in fields.items() if value is None]


def validate_route(route: Route) -> ValidationReport:
    """The separate outcomes of checking one route; see the module docstring for what each means and does not."""
    diagnostics: list[str] = []
    missing: set[str] = set()

    molecules = Check.PASS
    for smiles in route_molecules(route):
        if _canonical(smiles) is None:
            molecules = Check.FAIL
            diagnostics.append(f"molecule does not parse: {smiles!r}")

    reactions_failed = reactions_unassessable = False
    mappings: list[MappingStatus] = []
    conserved = True
    unmapped_right = 0
    for number, step in enumerate(route.steps, start=1):
        missing.update(_missing(step))
        if step.reaction_smiles is None:
            reactions_unassessable = True
            mappings.append(MappingStatus.ABSENT)
            diagnostics.append(f"step {number}: the planner gave no reaction SMILES")
            continue
        sides = step.reaction_smiles.split(">>")
        left = _side(sides[0]) if len(sides) == 2 else None
        right = _side(sides[1]) if len(sides) == 2 else None
        if left is None or right is None:
            reactions_failed = True
            mappings.append(MappingStatus.ABSENT)
            diagnostics.append(f"step {number}: the reaction SMILES does not parse: {step.reaction_smiles!r}")
            continue
        state = _step_mapping(left, right)
        mappings.append(state)
        wanted_left = [_canonical(step.product)]
        wanted_right = sorted(_canonical(r) or "" for r in step.reactants)
        left_smiles = sorted(_canonical(Chem.MolToSmiles(m)) or "" for m in left)
        right_smiles = sorted(_canonical(Chem.MolToSmiles(m)) or "" for m in right)
        if left_smiles != wanted_left or right_smiles != wanted_right:
            reactions_failed = True
            diagnostics.append(f"step {number}: the reaction's sides are not the molecules the step connects")
        if state is MappingStatus.COMPLETE:
            extras, reasons = _step_conservation(left, right)
            unmapped_right += extras
            if reasons:
                conserved = False
                diagnostics.extend(f"step {number}: {reason}" for reason in reasons)

    reactions = Check.FAIL if reactions_failed else Check.NOT_ASSESSABLE if reactions_unassessable else Check.PASS
    if all(state is MappingStatus.ABSENT for state in mappings):
        mapping, conservation = MappingStatus.ABSENT, Check.NOT_ASSESSABLE
    elif any(state is not MappingStatus.COMPLETE for state in mappings):
        mapping, conservation = MappingStatus.PARTIAL, Check.NOT_ASSESSABLE
    else:
        mapping, conservation = MappingStatus.COMPLETE, (Check.PASS if conserved else Check.FAIL)

    flags = [material.in_stock for material in route.starting_materials]
    if not flags or any(flag is None for flag in flags):
        stock = StockStatus.NOT_PROVIDED
        missing.add("molecule.in_stock")
    elif all(flags):
        stock = StockStatus.ALL_IN_STOCK
    else:
        stock = StockStatus.SOME_NOT_IN_STOCK
    return ValidationReport(
        molecules=molecules,
        reactions=reactions,
        mapping=mapping,
        conservation=conservation,
        stock=stock,
        unmapped_right_atoms=unmapped_right,
        diagnostics=tuple(diagnostics),
        missing=tuple(sorted(missing)),
    )
