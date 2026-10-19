"""The route validator of the synthesis spike (`docs/SYNTHESIS_HELPER_DESIGN.md` 0d): what can and cannot be checked about one route the planner returned, as SEPARATE outcomes, never one pass/fail.

A route is the planner's own tree (AiZynthFinder's route dictionary as saved in `fixtures/`): molecule nodes (`type: "mol"`, `smiles`, `in_stock`) alternating with reaction nodes (`type: "reaction"`, `smiles`, `metadata.mapped_reaction_smiles`). The mapped reaction is written product >> reactants (a RETROsynthetic step): the left side is the molecule that is being made, the right side its precursors.

THE OUTCOMES (each its own field; `fully_validated` is derived from the first four and says nothing about the planner's chemistry being right):
  1. `molecules`: every molecule SMILES in the tree parses and sanitizes under RDKit.
  2. `reactions`: every reaction has a mapped reaction SMILES that parses, and its left side is the parent molecule node and its right side the child molecule nodes (compared as canonical SMILES with atom maps removed, stereo kept).
  3. `mapping`: per step `complete` (every heavy atom of the left side carries a map number, none repeated on a side), `partial`, or `absent`; the route is `complete` only if every step is.
  4. `conservation`: ASSESSED ONLY WHERE THE MAPPING IS COMPLETE, otherwise `not_assessable`, never a pass or a fail. Rule, fixed here: every mapped atom of the left side has exactly one atom with the same map number on the right side and the same element. Atoms on the right with no partner on the left (a leaving group's or a reagent's atoms) are PERMITTED and counted, not judged. Charge and hydrogen counts are not compared (a planner may write an acid and its salt).
  5. `stock`: every terminal precursor's `in_stock` flag: `all_in_stock` / `some_not_in_stock` / `not_provided`. A match against a catalogue snapshot, not availability.
  6. `missing`: what the planner did not supply, listed per field (policy probability, template, mapping, stock flags).
NOTHING IS INVENTED to make a route pass: no atom is added, no mapping is repaired, no reaction is balanced.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")

COMPLETE, PARTIAL, ABSENT = "complete", "partial", "absent"
PASS, FAIL, NOT_ASSESSABLE, NOT_PROVIDED = "pass", "fail", "not_assessable", "not_provided"
ALL_IN_STOCK, SOME_NOT_IN_STOCK = "all_in_stock", "some_not_in_stock"


@dataclass
class Validation:
    molecules: str = PASS
    reactions: str = PASS
    mapping: str = COMPLETE
    conservation: str = PASS
    stock: str = ALL_IN_STOCK
    steps: int = 0
    unmapped_right_atoms: int = 0
    diagnostics: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def fully_validated(self) -> bool:
        """Outcomes 1 to 4 all clean and the conservation actually assessed (never inferred from a route that could not be checked)."""
        return self.molecules == PASS and self.reactions == PASS and self.mapping == COMPLETE and self.conservation == PASS


def _canonical(smiles: str) -> str | None:
    """Canonical isomeric SMILES with atom maps removed, or None if it does not parse."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(mol)


def _side_molecules(side: str) -> list[Chem.Mol] | None:
    """The molecules of one side of a reaction SMILES (dot-separated), maps kept; None if any fails."""
    mols = []
    for part in side.split("."):
        mol = Chem.MolFromSmiles(part)
        if mol is None:
            return None
        mols.append(mol)
    return mols


def _map_numbers(mols: list[Chem.Mol]) -> list[int]:
    return [a.GetAtomMapNum() for m in mols for a in m.GetAtoms() if a.GetAtomMapNum() > 0]


def _heavy_atoms(mols: list[Chem.Mol]) -> list[Chem.Atom]:
    return [a for m in mols for a in m.GetAtoms() if a.GetAtomicNum() > 1]


def _step_mapping(left: list[Chem.Mol], right: list[Chem.Mol]) -> str:
    heavy = _heavy_atoms(left)
    mapped = [a for a in heavy if a.GetAtomMapNum() > 0]
    if not mapped:
        return ABSENT
    numbers = [a.GetAtomMapNum() for a in mapped]
    right_numbers = _map_numbers(right)
    if len(mapped) < len(heavy) or len(set(numbers)) < len(numbers) or len(set(right_numbers)) < len(right_numbers):
        return PARTIAL
    return COMPLETE


def _step_conservation(left: list[Chem.Mol], right: list[Chem.Mol]) -> tuple[bool, int, list[str]]:
    """(conserved, atoms on the right with no partner, reasons). Every mapped left atom needs one same-element right atom with its number."""
    right_by_number = {}
    for m in right:
        for a in m.GetAtoms():
            if a.GetAtomMapNum() > 0:
                right_by_number.setdefault(a.GetAtomMapNum(), []).append(a.GetAtomicNum())
    reasons = []
    left_numbers = set()
    for m in left:
        for a in m.GetAtoms():
            number = a.GetAtomMapNum()
            if number == 0:
                continue
            left_numbers.add(number)
            partners = right_by_number.get(number, [])
            if len(partners) != 1:
                reasons.append(f"map {number} ({a.GetSymbol()}) has {len(partners)} partners on the right")
            elif partners[0] != a.GetAtomicNum():
                reasons.append(f"map {number} changes element ({a.GetSymbol()} to atomic number {partners[0]})")
    extras = sum(1 for n in right_by_number if n not in left_numbers) + sum(1 for m in right for a in m.GetAtoms() if a.GetAtomMapNum() == 0 and a.GetAtomicNum() > 1)
    return (not reasons, extras, reasons)


def validate_route(route: dict) -> Validation:
    """The separate outcomes of one route tree; see the module docstring for what each means and does not."""
    result = Validation()
    leaves: list[dict] = []
    missing: set[str] = set()
    mapping_states: list[str] = []
    conserved_all, assessed_any = True, False

    def visit(node: dict) -> None:
        nonlocal conserved_all, assessed_any
        if node.get("type") == "mol":
            if _canonical(node.get("smiles", "")) is None:
                result.molecules = FAIL
                result.diagnostics.append(f"molecule does not parse: {node.get('smiles')!r}")
            children = node.get("children") or []
            if not children:
                leaves.append(node)
            for child in children:
                visit_reaction(node, child)
        else:
            result.diagnostics.append(f"unexpected node type {node.get('type')!r} where a molecule was expected")
            result.molecules = FAIL

    def visit_reaction(parent: dict, reaction: dict) -> None:
        nonlocal conserved_all, assessed_any
        result.steps += 1
        metadata = reaction.get("metadata") or {}
        for key in ("policy_probability", "template", "template_hash"):
            if key not in metadata:
                missing.add(f"reaction.metadata.{key}")
        mapped = metadata.get("mapped_reaction_smiles")
        children = reaction.get("children") or []
        if not mapped:
            missing.add("reaction.metadata.mapped_reaction_smiles")
            result.reactions = FAIL
            result.diagnostics.append("a reaction carries no mapped reaction SMILES")
            mapping_states.append(ABSENT)
        else:
            sides = mapped.split(">>")
            left = _side_molecules(sides[0]) if len(sides) == 2 else None
            right = _side_molecules(sides[1]) if len(sides) == 2 else None
            if left is None or right is None:
                result.reactions = FAIL
                result.diagnostics.append(f"mapped reaction SMILES does not parse: {mapped!r}")
                mapping_states.append(ABSENT)
            else:
                state = _step_mapping(left, right)
                mapping_states.append(state)
                parent_smiles = _canonical(parent.get("smiles", ""))
                left_smiles = sorted(_canonical(Chem.MolToSmiles(m)) or "" for m in left)
                right_smiles = sorted(_canonical(Chem.MolToSmiles(m)) or "" for m in right)
                child_smiles = sorted(_canonical(c.get("smiles", "")) or "" for c in children)
                if left_smiles != [parent_smiles] or right_smiles != child_smiles:
                    result.reactions = FAIL
                    result.diagnostics.append("a reaction's sides are not the molecule nodes it connects")
                if state == COMPLETE:
                    assessed_any = True
                    ok, extras, reasons = _step_conservation(left, right)
                    result.unmapped_right_atoms += extras
                    if not ok:
                        conserved_all = False
                        result.diagnostics.extend(reasons)
        for child in children:
            visit(child)

    visit(route)
    if not mapping_states:
        # a tree with no reaction (the target is itself in stock) has nothing to validate step by step
        result.mapping, result.conservation = ABSENT, NOT_ASSESSABLE
        result.diagnostics.append("the tree has no reaction")
    elif all(s == ABSENT for s in mapping_states):
        result.mapping, result.conservation = ABSENT, NOT_ASSESSABLE
    elif any(s != COMPLETE for s in mapping_states):
        result.mapping, result.conservation = PARTIAL, NOT_ASSESSABLE
    elif not conserved_all:
        result.conservation = FAIL
    flags = [leaf.get("in_stock") for leaf in leaves]
    if not leaves or any(flag is None for flag in flags):
        result.stock = NOT_PROVIDED
        missing.add("molecule.in_stock")
    elif all(flags):
        result.stock = ALL_IN_STOCK
    else:
        result.stock = SOME_NOT_IN_STOCK
    result.missing = sorted(missing)
    return result
