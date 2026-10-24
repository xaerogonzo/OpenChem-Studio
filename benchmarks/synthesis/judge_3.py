"""The pure parts of protocol 3 (`PREREGISTRATION_3.md`): turning a transcribed reference into a route tree, the secondary matches, the by-depth comparison with protocol 2 and the intervals. No planner, no files; `run_quality_3.py` calls these and `tests/test_synthesis_protocol3.py` holds them.

The exact match, the ranking and M1/M2/M3 are NOT redefined here: they are `route_match.py` and `route_rank.py`, unchanged from protocols 1 and 2.
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")
HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


matching = _load("synthesis_quality_match_3", "route_match.py")
rank = _load("synthesis_quality_rank_3", "route_rank.py")

#: Protocol 2's M2 at 10 by the depth of the reference (the longest chain of reactions), under the exact rule: PREREGISTRATION_3.md, "The reading". Depth 2: 80 targets, depth 3: 136, depth 4: 50. Fixed text, not recomputed.
PROTOCOL2_M2_AT_10_BY_DEPTH = {2: 0.81, 3: 0.39, 4: 0.04}
#: A precursor of this many heavy atoms or fewer is dropped from BOTH sides of the lenient match (methyl iodide, formaldehyde, carbon disulfide).
SMALL_PRECURSOR_HEAVY_ATOMS = 3
#: The exact lower-tail probability below which the reading is LOWER.
LOWER_TAIL_LEVEL = 0.05
#: Two runs of one stock that differ by more than this in M2 at 10 are reported as a range.
NOISE_FLOOR = 0.06


def normalise(smiles: str) -> str:
    """Canonical SMILES of the largest fragment (a salt's counter-ion is not part of the structure compared), stereo kept, atom maps removed."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"does not parse: {smiles}")
    fragments = Chem.GetMolFrags(mol, asMols=True)
    mol = max(fragments, key=lambda m: m.GetNumHeavyAtoms()) if len(fragments) > 1 else mol
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(mol)


def inchikey(smiles: str) -> str:
    return Chem.MolToInchiKey(Chem.MolFromSmiles(normalise(smiles)))


def heavy_atoms(smiles: str) -> int:
    mol = Chem.MolFromSmiles(smiles)
    return mol.GetNumHeavyAtoms() if mol is not None else 0


# --- the reference as a route tree ---------------------------------------------------------------------------------------------


def reference_tree(document: dict) -> dict:
    """The reference (a `refs_out` JSON with decision `route`) as the planner's tree shape: molecule nodes and reaction nodes, SMILES normalised."""
    by_product = {normalise(r["product"]["smiles"]): r for r in document["reactions"]}

    def molecule(smiles: str) -> dict:
        canonical = normalise(smiles)
        node = {"type": "mol", "smiles": canonical, "children": []}
        reaction = by_product.get(canonical)
        if reaction is not None:
            node["children"] = [{"type": "reaction", "children": [molecule(r["smiles"]) for r in reaction["reactants"]]}]
        return node

    return molecule(document["target"]["smiles"])


def tree_depth(tree: dict) -> int:
    """The longest chain of reactions from the target down (protocol 2's `depth` of a reference)."""
    reactions = tree.get("children") or []
    if not reactions:
        return 0
    return 1 + max((tree_depth(child) for child in reactions[0].get("children") or [] if child.get("type") == "mol"), default=0)


def leaves_of(tree: dict) -> frozenset[str]:
    return matching.leaves_of(tree)


def intermediates_of(tree: dict) -> frozenset[str]:
    """Every molecule the route makes except its target."""
    found: set[str] = set()

    def visit(node: dict, is_target: bool) -> None:
        reactions = node.get("children") or []
        if reactions and not is_target:
            found.add(matching.canonical(node["smiles"]))
        for reaction in reactions:
            for child in reaction.get("children") or []:
                if child.get("type") == "mol":
                    visit(child, False)

    visit(tree, True)
    return frozenset(found)


# --- the secondary matches -----------------------------------------------------------------------------------------------------


def lenient_reactions_of(route: dict) -> frozenset[tuple[str, tuple[str, ...]]]:
    """The route's reaction identities with every precursor of 3 or fewer heavy atoms removed (the planner may or may not list a small reagent as a reactant)."""
    return frozenset((product, tuple(p for p in precursors if heavy_atoms(p) > SMALL_PRECURSOR_HEAVY_ATOMS)) for product, precursors in matching.reactions_of(route))


def lenient_match(predicted: dict, reference: dict) -> bool:
    ref = lenient_reactions_of(reference)
    return bool(ref) and lenient_reactions_of(predicted) == ref


def same_materials_route(predicted: dict, reference: dict) -> bool:
    """A route that is NOT an exact match but starts only from the reference's own starting materials (right materials, different chemistry)."""
    return not matching.matches(predicted, reference) and bool(matching.reactions_of(predicted)) and matching.leaves_of(predicted) <= matching.leaves_of(reference)


def reaction_recall(routes: list[dict], reference: dict) -> list[dict]:
    """For each reference reaction, in how many of the returned routes it appears (the diagnostic of WHY a route was missed)."""
    sets = [matching.reactions_of(route) for route in routes]
    out = []
    for product, precursors in sorted(matching.reactions_of(reference)):
        out.append({"product": product, "precursors": list(precursors), "routes_containing": sum(1 for s in sets if (product, precursors) in s)})
    return out


# --- intervals and the reading -------------------------------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """The Wilson score interval for k successes of n (95% by default)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def poisson_binomial_lower_tail(probabilities: list[float], k: int) -> float:
    """P(X <= k) where X is the number of successes of independent trials with the given probabilities (exact, by dynamic programming)."""
    distribution = [1.0]
    for p in probabilities:
        nxt = [0.0] * (len(distribution) + 1)
        for i, mass in enumerate(distribution):
            nxt[i] += mass * (1 - p)
            nxt[i + 1] += mass * p
        distribution = nxt
    return sum(distribution[: k + 1])


def reading(depths: list[int], recovered: list[bool]) -> dict:
    """The preregistered reading of the primary stock: the routes of depth 2 or more against protocol 2's rate at the same depths.

    LOWER when the probability of this many recoveries or fewer, under those rates, is below 0.05; otherwise NO EVIDENCE OF A DROP. A depth outside 2-4 uses the nearest protocol 2 rate (depth 5 or more: depth 4's), which is stated so nothing is silently chosen.
    """
    comparable = [(d, r) for d, r in zip(depths, recovered) if d >= 2]
    rates = [PROTOCOL2_M2_AT_10_BY_DEPTH[min(max(d, 2), 4)] for d, _ in comparable]
    k = sum(1 for _, r in comparable if r)
    n = len(comparable)
    p_low = poisson_binomial_lower_tail(rates, k)
    low, high = wilson(k, n)
    return {"routes": n, "recovered": k, "expected": round(sum(rates), 2), "expected_rate": round(sum(rates) / n, 3) if n else None,
            "observed_rate": round(k / n, 3) if n else None, "interval_95": [round(low, 3), round(high, 3)], "lower_tail_probability": round(p_low, 4),
            "reading": "LOWER" if p_low < LOWER_TAIL_LEVEL else "NO EVIDENCE OF A DROP"}
