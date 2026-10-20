"""How routes are ranked and counted in protocol 2 of the synthesis benchmark (`PREREGISTRATION_2.md`): the PaRoutes route score, dense ranks that give equal scores the same rank, and the three ways of asking "is the reference among the first 10". Pure; the matching itself is `route_match.py`.

THE SCORE replicates `route_distances.utils.routes.route_score` (MolecularAI/route-distances, MIT, read 2026-10-20), the function PaRoutes' own `analysis/route_quality.py` ranks with: a terminal molecule costs 1 if the planner marks it `in_stock` and 10 if not; a molecule with a reaction below it costs `1.0 + sum(child cost / 0.8)` over that reaction's precursors; lower is better. It depends only on a route's shape and on which leaves are in stock, so many routes tie. (The paper's text says a fixed reaction cost of 10 and a yield of 1; the code the scripts ran uses these defaults, and the preregistration records that the choice changes the values, not which routes tie.)

THE RANK is dense and shared: routes sorted by score ascending; a route has its predecessor's rank when the two scores differ by less than 1e-8 and one more otherwise (`route_ranks`). PaRoutes counts "top-k" as every route whose rank is at most k, so **a published top-10 is the first ten score LEVELS, however many routes they hold**.

THE THREE COUNTS (all use the exact reaction-set match of `route_match.matches`):
  * M1, the PaRoutes top-k: any route with rank <= k matches the reference. The measure the thresholds were set against.
  * M2, the user-facing top-k: routes ordered by (rank ascending, state score descending, the planner's order) and any of the first k matches. What a person shown k routes sees; the one product wording must quote.
  * M3, the planner's own order: any of the first k routes in the order the planner returned them matches. The consistency check against protocol 1.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _sibling(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


matching = _sibling("synthesis_rank_match", "route_match.py")

REACTION_COST = 1.0
AVERAGE_YIELD = 0.8
LEAF_IN_STOCK = 1.0
LEAF_NOT_IN_STOCK = 10.0
#: Scores closer than this share a rank (the library's own tolerance).
TIE_TOLERANCE = 1e-8
STATE_SCORE_KEY = "state score"


def route_cost(route: dict) -> float:
    """The PaRoutes route score of one route tree (lower is better). A molecule with no reaction is a leaf; a node with no `in_stock` flag counts as in stock, as the library does."""
    reactions = route.get("children") or []
    if not reactions:
        return LEAF_IN_STOCK if route.get("in_stock", True) else LEAF_NOT_IN_STOCK
    # Only the first reaction under a molecule is read, as the library does (a route has one).
    return REACTION_COST + sum(route_cost(child) / AVERAGE_YIELD for child in reactions[0]["children"])


def dense_ranks(sorted_scores: list[float]) -> list[int]:
    """Ranks of scores already sorted ascending: starts at 1, equal scores (within `TIE_TOLERANCE`) share a rank, a new score is the previous rank plus one."""
    ranks: list[int] = []
    for index, score in enumerate(sorted_scores):
        if index == 0:
            ranks.append(1)
        elif abs(score - sorted_scores[index - 1]) < TIE_TOLERANCE:
            ranks.append(ranks[-1])
        else:
            ranks.append(ranks[-1] + 1)
    return ranks


def state_score(route: dict) -> float:
    """The planner's own score of a route (the key the planner writes); 0 when it is not there."""
    return float((route.get("scores") or {}).get(STATE_SCORE_KEY, 0.0))


@dataclass(frozen=True)
class Analysis:
    """Everything protocol 2 asks of one target's routes, computed once. Indices are positions in the planner's own order."""

    hits: tuple[bool, ...]
    costs: tuple[float, ...]
    cost_order: tuple[int, ...]
    cost_ranks: tuple[int, ...]  # rank of cost_order[i]
    user_order: tuple[int, ...]

    @property
    def count(self) -> int:
        return len(self.hits)

    def m1(self, k: int) -> bool:
        """The PaRoutes top-k: a match among every route whose dense rank is at most k."""
        return any(self.hits[i] for i, rank in zip(self.cost_order, self.cost_ranks) if rank <= k)

    def m2(self, k: int) -> bool:
        """The first k routes in the user-facing order."""
        return any(self.hits[i] for i in self.user_order[:k])

    def m3(self, k: int) -> bool:
        """The first k routes in the planner's own order."""
        return any(self.hits[:k])

    def pool(self) -> bool:
        """A match anywhere among the returned routes: the ceiling for any ranking."""
        return any(self.hits)

    def routes_within_rank(self, k: int) -> int:
        """How many routes the PaRoutes top-k holds (ties included)."""
        return sum(1 for rank in self.cost_ranks if rank <= k)

    def distinct_ranks(self) -> int:
        return self.cost_ranks[-1] if self.cost_ranks else 0

    def first_hit_rank(self) -> int | None:
        """The dense rank of the best-ranked matching route, or None when none matches."""
        ranks = [rank for i, rank in zip(self.cost_order, self.cost_ranks) if self.hits[i]]
        return min(ranks) if ranks else None


def analyse(routes: list[dict], reference: dict) -> Analysis:
    """Match every route to the reference once and rank them by cost. An empty reference (no reaction) matches nothing, as in `route_match.matches`."""
    reference_reactions = matching.reactions_of(reference)
    hits = tuple(bool(reference_reactions) and matching.reactions_of(route) == reference_reactions for route in routes)
    costs = tuple(route_cost(route) for route in routes)
    cost_order = tuple(sorted(range(len(routes)), key=lambda i: costs[i]))
    ranks = tuple(dense_ranks([costs[i] for i in cost_order]))
    rank_of = {i: rank for i, rank in zip(cost_order, ranks)}
    # By rank, not by the raw cost: two routes of one shape can differ in the last float digit and must still tie.
    user_order = tuple(sorted(range(len(routes)), key=lambda i: (rank_of[i], -state_score(routes[i]), i)))
    return Analysis(hits=hits, costs=costs, cost_order=cost_order, cost_ranks=ranks, user_order=user_order)
