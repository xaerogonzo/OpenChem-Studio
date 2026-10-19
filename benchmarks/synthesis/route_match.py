"""Does a route the planner returned agree with a reference route? The matching rule of the synthesis benchmark (`PREREGISTRATION.md`), pure RDKit and tested before any run.

IDENTITY IS TAKEN FROM THE TREE, NOT FROM A REACTION STRING. A route is a tree of molecule nodes and reaction nodes (the planner's dictionary, and PaRoutes' reference routes, share that shape). Each reaction is identified by the molecule it makes and the molecules it consumes: `(canonical product, sorted canonical precursors)`, from the parent node and its child nodes. SMILES are canonicalised with RDKit, **stereo kept**, atom maps absent. This does not depend on which string the planner or the reference wrote for the reaction (the reference's reaction SMILES are mapped forward reactions, the planner's retro templates), and it does not depend on the order of the children.

THE RULE, FIXED:
  * A predicted route MATCHES the reference route when the SET of its reaction identities equals the reference's (the same reactions, in any order; two different intermediates are two different reactions).
  * A target is RECOVERED AT k when any of the first k routes the planner returned (its own order, never re-ranked here) matches.
  * Reported beside it and never decisive: the LEAF OVERLAP of a route with the reference (shared leaves over the larger leaf set, the paper's measure) and whether the first route is SHORTER than the reference.
A molecule that does not parse is kept as its raw string, so two unparseable nodes can only match each other exactly; nothing is repaired.
"""
from __future__ import annotations

from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")


def canonical(smiles: str) -> str:
    """Canonical isomeric SMILES with atom maps removed; the raw string if it does not parse."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return smiles
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(mol)


def reactions_of(route: dict) -> frozenset[tuple[str, tuple[str, ...]]]:
    """Every reaction of the tree as `(product, sorted precursors)`, canonicalised."""
    found: set[tuple[str, tuple[str, ...]]] = set()

    def visit(molecule: dict) -> None:
        for reaction in molecule.get("children") or []:
            precursors = [child for child in reaction.get("children") or [] if child.get("type") == "mol"]
            found.add((canonical(molecule["smiles"]), tuple(sorted(canonical(p["smiles"]) for p in precursors))))
            for precursor in precursors:
                visit(precursor)

    visit(route)
    return frozenset(found)


def leaves_of(route: dict) -> frozenset[str]:
    """The canonical SMILES of every terminal molecule (a molecule with no reaction below it); the bare target of a one-node tree is its own leaf."""
    leaves: set[str] = set()

    def visit(molecule: dict) -> None:
        reactions = molecule.get("children") or []
        if not reactions:
            leaves.add(canonical(molecule["smiles"]))
        for reaction in reactions:
            for child in reaction.get("children") or []:
                if child.get("type") == "mol":
                    visit(child)

    visit(route)
    return frozenset(leaves)


def matches(predicted: dict, reference: dict) -> bool:
    """Whether the predicted route has exactly the reference route's reactions. A tree with no reaction never matches (it is not a route)."""
    reference_reactions = reactions_of(reference)
    return bool(reference_reactions) and reactions_of(predicted) == reference_reactions


def recovered_at(predicted_routes: list[dict], reference: dict, k: int) -> bool:
    """Whether one of the first `k` returned routes matches the reference."""
    return any(matches(route, reference) for route in predicted_routes[:k])


def leaf_overlap(predicted: dict, reference: dict) -> float:
    """Shared leaves over the larger of the two leaf sets (1.0 = the same starting materials, in whatever reactions)."""
    a, b = leaves_of(predicted), leaves_of(reference)
    return len(a & b) / max(len(a), len(b)) if a or b else 0.0


def is_shorter(predicted: dict, reference: dict) -> bool:
    """Whether the predicted route has fewer reactions than the reference."""
    return len(reactions_of(predicted)) < len(reactions_of(reference))
