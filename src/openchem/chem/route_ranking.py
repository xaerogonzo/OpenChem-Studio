"""The order routes are shown in: the PaRoutes route score, as protocol 2 of the synthesis quality benchmark ranked them (`benchmarks/synthesis/route_rank.py`, `RESULT_2.md`).

THE SCORE replicates `route_distances.utils.routes.route_score` (MolecularAI/route-distances, MIT), the function PaRoutes' own scripts rank with: a molecule with no reaction below it costs 1 if the planner marks it in stock and 10 if not; a molecule made by a reaction costs `1.0 + sum(precursor cost / 0.8)`. Lower is better. It reads only a route's SHAPE and which starting materials are in stock, so many routes tie.

THE ORDER is M2's, the one the benchmark measured as "the reference route is among the first 10 shown" (0.417): routes sorted by their DENSE RANK of that score (scores closer than 1e-8 share a rank, so two routes of one shape that differ in the last float digit still tie), then by the planner's own state score, higher first, then by the order the planner returned them. The last two keys matter: a tie of ranks is common (a median of 37 routes sat inside the first ten ranks), and the planner's order among them is otherwise arbitrary.

WHAT THE BENCHMARK DID AND DID NOT SHOW (`docs/SYNTHESIS_HELPER_DESIGN.md`, "Protocol 2 result"): ranking this way beat the planner's own order by 3 targets of 300 (125 against 122; 8 gained, 5 lost), which is inside the noise. It is used because the order is DETERMINISTIC from a route's shape and stock flags and can be explained ("fewer steps and more starting materials in stock first"), NOT because it finds the known route more often. A better rank says nothing about whether a route would work.

Pure: no RDKit, no I/O. It reads the planner's route trees (the dictionaries of the planner's own output) and returns positions, so the caller keeps whatever it built from them.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

#: What one reaction adds to the cost of the molecule it makes (the library's default).
REACTION_COST = 1.0
#: The yield each precursor's cost is divided by (the library's default; the paper's text says 1, the code the scripts ran says 0.8).
AVERAGE_YIELD = 0.8
#: The cost of a starting material the planner flags as in stock.
LEAF_IN_STOCK = 1.0
#: The cost of a starting material that is not in stock, so a route that needs one ranks far below one that does not.
LEAF_NOT_IN_STOCK = 10.0
#: Scores closer than this share a rank (the library's own tolerance).
TIE_TOLERANCE = 1e-8
#: The key the planner writes its own score under.
STATE_SCORE_KEY = "state score"


def route_cost(node: dict) -> float:
    """The PaRoutes route score of one route tree (lower is better).

    A molecule with no reaction below it is a leaf: 1 if it is flagged in stock, 10 if it is not. A molecule with no `in_stock` flag counts as in stock, as the library does (the caller keeps only routes whose every starting material is flagged, so it does not arise in practice). Only the first reaction under a molecule is read, as the library does; a route has one.
    """
    reactions = [child for child in node.get("children") or [] if isinstance(child, dict) and child.get("type") == "reaction"]
    if not reactions:
        return LEAF_IN_STOCK if node.get("in_stock", True) else LEAF_NOT_IN_STOCK
    precursors = [child for child in reactions[0].get("children") or [] if isinstance(child, dict) and child.get("type") == "mol"]
    return REACTION_COST + sum(route_cost(child) / AVERAGE_YIELD for child in precursors)


def dense_ranks(sorted_scores: Sequence[float]) -> list[int]:
    """Ranks of scores already sorted ascending: the first is 1, a score within `TIE_TOLERANCE` of the one before shares its rank, any other is the previous rank plus one."""
    ranks: list[int] = []
    for index, score in enumerate(sorted_scores):
        if index == 0:
            ranks.append(1)
        elif abs(score - sorted_scores[index - 1]) < TIE_TOLERANCE:
            ranks.append(ranks[-1])
        else:
            ranks.append(ranks[-1] + 1)
    return ranks


def state_score(tree: dict) -> float:
    """The planner's own score of a route, or 0 when it is not a finite number (so a missing score sorts below a given one)."""
    scores = tree.get("scores") if isinstance(tree.get("scores"), dict) else {}
    value = scores.get(STATE_SCORE_KEY)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return 0.0
    return float(value)


def shown_order(trees: Sequence[dict]) -> list[int]:
    """The positions of `trees` in the order they are shown: by dense rank of the route score, then the planner's state score (higher first), then the order given."""
    costs = [route_cost(tree) for tree in trees]
    by_cost = sorted(range(len(trees)), key=lambda i: costs[i])
    rank_of = dict(zip(by_cost, dense_ranks([costs[i] for i in by_cost])))
    return sorted(range(len(trees)), key=lambda i: (rank_of[i], -state_score(trees[i]), i))
