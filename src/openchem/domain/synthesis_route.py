"""What a synthesis planner's answer looks like to the rest of the application (`docs/SYNTHESIS_HELPER_DESIGN.md`, Stage 1 slice 1).

PURE AND TOOL-FREE: frozen dataclasses of strings and numbers, no RDKit, no process, no planner. A route is built by a
parser from a planner's own output (a later slice), checked here for the shape a route must have, and read by every
surface from this one type, so no surface can leave out what the planner did not say.

THE RULES THIS TYPE ENFORCES, each one a thing the Stage 0 spike measured:

* **A field the planner did not supply is `None`, never a default number or an empty string.** The AiZynthFinder fixtures
  carry a mapped reaction, a template and a policy probability on every step seen, and no conditions, yields or reagents
  at all; a planner that gives less must read as "not provided", and `shown` (below) is the one place the words come from.
* **"No route found" is a statement about a search, not about chemistry.** The status text says "within the configured
  search limits" and never "no route exists"; a search that stopped at a limit says so, because the ranked set it
  returned is then not exhaustive. The planner has NO field that says why it stopped, so `read_termination` reads it
  from the limits and the counters and answers `UNKNOWN` when they do not say.
* **A route is a hypothesis.** The planner's policy probability is the planner's number, not the chance a reaction works;
  its route score ranks states of a search; "in stock" is a match to a catalogue snapshot, not a supplier. These sentences
  travel with every `RouteSet` as `limitations`, and a `RouteSet` that leaves one out cannot be built.
* **A route is a tree with one root, listed in the order it would be run.** Steps are in forward order (a step's
  precursors that another step makes come earlier), the target is the product of the last step and of no other, and every
  other step's product is consumed by a later one. A route that is not that is refused at construction, so the display's
  "step 1, step 2" is never ambiguous.
* **Only a successful search carries routes.** `refused`, `failed`, `cancelled`, `unavailable` and `unscreened` carry a
  reason and no route; `no_route` carries neither.
* **An alert on a molecule is a screening of that molecule, and an absent screening is not "no alert".** `RouteSet.node_screenings`
  holds one `NodeScreening` for every distinct molecule of every route once the wider regulatory rulesets have been asked, each
  saying whether it was screened; an empty tuple means they have not been asked (a limitation says so), never that nothing matched.

Nothing here knows whose planner it is: `PlannerIdentity` says. There is no seed field because the planner has none; the
repeatability a user can expect is the one the benchmark measured (the solved flag, not the tree).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from openchem.domain.synthesis_gate import NodeScreening

#: The version of this structure, written with every plan kept in a project file (`domain/synthesis_route_codec.py`) so a later build can tell what it is reading.
SYNTHESIS_ROUTE_FORMAT = 1

#: How the sentence about routes a planner returned and the parser left out begins. It is the one added sentence a plan read from a project file keeps (every other is re-derived by the build that reads it), so the codec has to recognise it.
LEFT_OUT_PREFIX = "Routes the planner returned that are not shown: "

#: What a field reads as when the planner did not supply it.
NOT_PROVIDED = "not provided"

#: The sentences every `RouteSet` carries. Each is true of ANY planner whose model was trained on published reactions and
#: whose stock is a catalogue snapshot; a planner-specific figure (the benchmark's recovery rate, a model's training set)
#: is added by the provider that knows it, never assumed here.
STANDARD_LIMITATIONS: tuple[str, ...] = (
    "A route is a hypothesis from a program, not a validated or feasible synthesis: nobody has run these reactions.",
    "The planner gives no reaction conditions, reagents, solvents, yields or selectivity.",
    "A policy probability is the planner's own number, not the chance that a reaction works, and a route score ranks the "
    "planner's search states, it does not measure feasibility.",
    "\"In stock\" means a match to a catalogue snapshot, not that anyone sells the compound today or that it may be "
    "bought.",
    "Stereochemistry in a route is the planner's and is often incomplete or dropped.",
)

#: Added to a result whose routes have not been screened against the wider regulatory rulesets: no alert is shown, and that is not "nothing matched".
ALERTS_NOT_CHECKED = "The molecules of these routes have not been checked against the regulatory rulesets, so the absence of an alert here means nothing."

#: Added to a result in which some molecule could not be screened: its row says why, and no empty list of alerts stands for "nothing matched".
SOME_NOT_SCREENED = "Some molecules of these routes could not be screened against the regulatory rulesets; each says why."

#: Added to a result whose search stopped at a limit: the routes are the ones found so far, not all of them.
LIMITS_NOT_EXHAUSTIVE = (
    "The search stopped at a limit, so these routes are the ones found so far and not every route there is."
)


class RouteStatus(StrEnum):
    """How a planning request ended. Closed: a surface that meets a value it does not know must say so, not guess."""

    FOUND = "found"
    NO_ROUTE = "no_route"
    REFUSED = "refused"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"
    #: The regulatory gate could not tell (a ruleset missing or broken, the screen raised), so nothing was started.
    UNSCREENED = "unscreened"


class SearchTermination(StrEnum):
    """Why a search stopped, as far as anyone can say. `UNKNOWN` is a real answer."""

    COMPLETED = "completed"
    ITERATION_LIMIT = "iteration_limit"
    TIME_LIMIT = "time_limit"
    DEPTH_LIMIT = "depth_limit"
    CANCELLED = "cancelled"
    FAILED = "failed"
    UNKNOWN = "unknown"


#: Statuses that carry a reason in words, and say why nothing was planned or the plan did not finish.
_NEEDS_REASON = frozenset(
    {RouteStatus.REFUSED, RouteStatus.FAILED, RouteStatus.CANCELLED, RouteStatus.UNAVAILABLE, RouteStatus.UNSCREENED}
)

#: The ways of stopping that mean the search was cut off rather than finished.
_LIMIT_TERMINATIONS = frozenset({SearchTermination.ITERATION_LIMIT, SearchTermination.TIME_LIMIT, SearchTermination.DEPTH_LIMIT})


class Check(StrEnum):
    """One validation outcome. `NOT_ASSESSABLE` is neither a pass nor a fail: it is "the planner did not give enough"."""

    PASS = "pass"
    FAIL = "fail"
    NOT_ASSESSABLE = "not_assessable"


class MappingStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    ABSENT = "absent"


class StockStatus(StrEnum):
    ALL_IN_STOCK = "all_in_stock"
    SOME_NOT_IN_STOCK = "some_not_in_stock"
    NOT_PROVIDED = "not_provided"


@dataclass(frozen=True, kw_only=True)
class SearchLimits:
    """The limits a search was given. A limit the planner was not given is `None`."""

    iteration_limit: int | None = None
    time_limit_seconds: float | None = None
    max_transforms: int | None = None

    def __post_init__(self) -> None:
        _positive_int_or_none("iteration_limit", self.iteration_limit)
        _positive_int_or_none("max_transforms", self.max_transforms)
        if self.time_limit_seconds is not None and not (math.isfinite(self.time_limit_seconds) and self.time_limit_seconds > 0):
            raise ValueError("time_limit_seconds must be a positive finite number or None")


@dataclass(frozen=True, kw_only=True)
class SearchStatistics:
    """What the planner reported about the search, each `None` when it did not."""

    iterations: int | None = None
    search_seconds: float | None = None
    first_solution_iteration: int | None = None
    nodes: int | None = None
    routes_returned: int | None = None
    solved_routes: int | None = None

    def __post_init__(self) -> None:
        for name in ("iterations", "first_solution_iteration", "nodes", "routes_returned", "solved_routes"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if self.search_seconds is not None and not (math.isfinite(self.search_seconds) and self.search_seconds >= 0):
            raise ValueError("search_seconds must be a non-negative finite number or None")


@dataclass(frozen=True, kw_only=True)
class PlannerIdentity:
    """Which planner, which models and stock, and the configuration, so two results are comparable or visibly not.

    `model_identity` holds the names of what was selected (expansion policy, filter policy, stock), not paths: a path is
    the user's machine and says nothing about the model. `config_sha256` is the hash of the configuration the planner
    actually ran.
    """

    planner: str
    version: str
    model_identity: tuple[tuple[str, str], ...] = ()
    config_sha256: str | None = None
    limits: SearchLimits = field(default_factory=SearchLimits)

    def __post_init__(self) -> None:
        _nonblank("planner", self.planner)
        _nonblank("version", self.version)
        for key, value in self.model_identity:
            _nonblank("model_identity key", key)
            _nonblank("model_identity value", value)

    def label(self) -> str:
        """`planner version`, with the model names after it: what a person is shown, never an installation path."""
        models = ", ".join(f"{k}: {v}" for k, v in self.model_identity)
        return f"{self.planner} {self.version}" + (f" ({models})" if models else "")


@dataclass(frozen=True, kw_only=True)
class TargetIdentity:
    """The molecule a plan was requested for, captured BEFORE the planner starts and carried on the result.

    A result is shown against its own target. The fingerprint is whatever the caller uses to say "this is still the same
    structure" (the application's own structure fingerprint); this type does not compute it.
    """

    molecule_uuid: str
    canonical_smiles: str
    fingerprint: str

    def __post_init__(self) -> None:
        _nonblank("molecule_uuid", self.molecule_uuid)
        _nonblank("canonical_smiles", self.canonical_smiles)
        _nonblank("fingerprint", self.fingerprint)


@dataclass(frozen=True, kw_only=True)
class ValidationReport:
    """The separate outcomes of checking one route (the spike's 0d), diagnostics and not a single pass/fail.

    `fully_validated` says the route's own bookkeeping is clean (molecules and reactions parse, the mapping is complete,
    atoms are conserved where the mapping allows it); it says nothing about the chemistry being right.
    """

    molecules: Check
    reactions: Check
    mapping: MappingStatus
    conservation: Check
    stock: StockStatus
    unmapped_right_atoms: int = 0
    diagnostics: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.unmapped_right_atoms < 0:
            raise ValueError("unmapped_right_atoms cannot be negative")
        if self.conservation is not Check.NOT_ASSESSABLE and self.mapping is not MappingStatus.COMPLETE:
            # The rule the spike fixed: conservation is asserted only where the mapping is complete.
            raise ValueError("conservation can only be assessed when the mapping is complete")

    @property
    def fully_validated(self) -> bool:
        return (
            self.molecules is Check.PASS
            and self.reactions is Check.PASS
            and self.mapping is MappingStatus.COMPLETE
            and self.conservation is Check.PASS
        )


@dataclass(frozen=True, kw_only=True)
class RouteMolecule:
    """A starting material (a terminal precursor) of a route, with the planner's stock flag (`None` = not supplied)."""

    smiles: str
    in_stock: bool | None = None

    def __post_init__(self) -> None:
        _nonblank("smiles", self.smiles)


@dataclass(frozen=True, kw_only=True)
class RouteStep:
    """One reaction of a route: the molecule it makes and the molecules it consumes, as the planner wrote them.

    `reaction_smiles` is the whole reaction of the real molecules (product first, as a retrosynthetic step is written by
    the planner) when it supplied one, with its atom maps as given; nothing is mapped or balanced here.
    """

    product: str
    reactants: tuple[str, ...]
    reaction_smiles: str | None = None
    template_id: str | None = None
    policy_name: str | None = None
    policy_probability: float | None = None

    def __post_init__(self) -> None:
        _nonblank("product", self.product)
        if not self.reactants:
            raise ValueError("a step consumes at least one molecule")
        for reactant in self.reactants:
            _nonblank("reactant", reactant)
        for name in ("reaction_smiles", "template_id", "policy_name"):
            value = getattr(self, name)
            if value is not None:
                _nonblank(name, value)
        p = self.policy_probability
        if p is not None and not (isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(p) and 0.0 <= p <= 1.0):
            raise ValueError("policy_probability must be a number from 0 to 1, or None")


@dataclass(frozen=True, kw_only=True)
class Route:
    """One route to the target: steps in the order they would be run, and the starting materials they begin from.

    `target_smiles` is the planner's own string for the molecule the route makes, which need not be the user's canonical
    SMILES (that is `TargetIdentity`'s). `score` is the planner's ranking quantity and `rank` this route's place in the
    planner's order (1 = first); neither says the route would work.
    """

    target_smiles: str
    steps: tuple[RouteStep, ...]
    starting_materials: tuple[RouteMolecule, ...]
    rank: int
    score: float | None = None
    validation: ValidationReport | None = None

    def __post_init__(self) -> None:
        _nonblank("target_smiles", self.target_smiles)
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError("rank starts at 1")
        if self.score is not None and not math.isfinite(self.score):
            raise ValueError("score must be finite or None")
        if not self.steps:
            raise ValueError("a route has at least one step; a target with no reaction is 'no route'")
        _check_tree(self.target_smiles, self.steps, self.starting_materials)

    @property
    def length(self) -> int:
        return len(self.steps)


@dataclass(frozen=True, kw_only=True)
class RouteSet:
    """Everything a planning request produced: the routes, how it ended, who ran it, and what must be said beside it."""

    status: RouteStatus
    target: TargetIdentity
    planner: PlannerIdentity
    routes: tuple[Route, ...] = ()
    termination: SearchTermination = SearchTermination.UNKNOWN
    statistics: SearchStatistics = field(default_factory=SearchStatistics)
    reason: str = ""
    limitations: tuple[str, ...] = STANDARD_LIMITATIONS
    #: One screening per distinct molecule of the routes, or empty when the routes have not been screened (see the module docstring).
    node_screenings: tuple[NodeScreening, ...] = ()
    format: int = SYNTHESIS_ROUTE_FORMAT

    def __post_init__(self) -> None:
        if self.status is RouteStatus.FOUND:
            if not self.routes:
                raise ValueError("status 'found' needs at least one route")
        elif self.routes:
            raise ValueError(f"status '{self.status}' carries no routes")
        if self.status in _NEEDS_REASON and not self.reason.strip():
            raise ValueError(f"status '{self.status}' needs a reason")
        if self.status is RouteStatus.CANCELLED and self.termination not in (SearchTermination.CANCELLED, SearchTermination.UNKNOWN):
            raise ValueError("a cancelled request cannot report another way of stopping")
        ranks = [r.rank for r in self.routes]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("routes are kept in the planner's order and ranked 1, 2, 3 ...")
        missing = [s for s in STANDARD_LIMITATIONS if s not in self.limitations]
        if missing:
            raise ValueError("limitations must include every standard sentence")
        if self.node_screenings:
            if self.status is not RouteStatus.FOUND:
                raise ValueError(f"status '{self.status}' carries no routes to screen")
            screened = [s.smiles for s in self.node_screenings]
            expected = {smiles for route in self.routes for smiles in route_molecules(route)}
            if len(set(screened)) != len(screened) or set(screened) != expected:
                raise ValueError("node screenings must be exactly the molecules of the routes, each once")

    @property
    def stopped_at_a_limit(self) -> bool:
        return self.termination in _LIMIT_TERMINATIONS

    def all_limitations(self) -> tuple[str, ...]:
        """The standing sentences plus the ones this particular result adds. Always at least `STANDARD_LIMITATIONS`."""
        extra: list[str] = []
        if self.status is RouteStatus.FOUND and self.stopped_at_a_limit:
            extra.append(LIMITS_NOT_EXHAUSTIVE)
        if self.status is RouteStatus.FOUND and not self.node_screenings:
            extra.append(ALERTS_NOT_CHECKED)
        elif any(not s.screened for s in self.node_screenings):
            extra.append(SOME_NOT_SCREENED)
        if self.status is RouteStatus.FOUND and any(r.validation is None for r in self.routes):
            extra.append("Some routes have not been checked for internal consistency.")
        elif self.status is RouteStatus.FOUND and any(not r.validation.fully_validated for r in self.routes):
            extra.append("Some routes could not be fully validated; each says which check was not possible.")
        return tuple(dict.fromkeys(self.limitations + tuple(extra)))

    def screenings_for(self, route: Route) -> tuple[NodeScreening, ...]:
        """The screenings of this route's molecules (target, intermediates, starting materials), in the order `route_molecules` gives them. Empty if the set has not been screened."""
        by_smiles = {s.smiles: s for s in self.node_screenings}
        return tuple(by_smiles[smiles] for smiles in route_molecules(route) if smiles in by_smiles)

    def alert_count(self, route: Route) -> int:
        """How many of this route's molecules matched a rule. Zero says nothing about molecules that were not screened: ask `screenings_for`."""
        return sum(1 for s in self.screenings_for(route) if s.has_alert)

    def message(self) -> str:
        """The one-line status a surface shows. Never says a route does not exist, only that none was found."""
        status = self.status
        if status is RouteStatus.FOUND:
            n = len(self.routes)
            text = f"{n} route{'s' if n != 1 else ''} found."
            if self.stopped_at_a_limit:
                text += " The search stopped at its " + _LIMIT_WORDS[self.termination] + "; there may be others."
            return text
        if status is RouteStatus.NO_ROUTE:
            text = "No route found within the configured search limits."
            return text + " This does not mean none exists."
        label = {
            RouteStatus.REFUSED: "Not planned",
            RouteStatus.FAILED: "The search failed",
            RouteStatus.CANCELLED: "Cancelled",
            RouteStatus.UNAVAILABLE: "The planner is not available",
            RouteStatus.UNSCREENED: "Not planned: the target could not be screened",
        }[status]
        return f"{label}: {self.reason.strip()}"


#: How each limit is named in the status line.
_LIMIT_WORDS = {
    SearchTermination.ITERATION_LIMIT: "iteration limit",
    SearchTermination.TIME_LIMIT: "time limit",
    SearchTermination.DEPTH_LIMIT: "depth limit",
}


def read_termination(limits: SearchLimits, statistics: SearchStatistics) -> SearchTermination:
    """Why a search stopped, read from its limits and counters, because the planner does not say.

    `ITERATION_LIMIT` when the iterations reached the limit, `TIME_LIMIT` when the search seconds reached the limit (the
    iteration limit is checked first, so a search that reached both is read as the iteration limit), and `UNKNOWN`
    otherwise. **Fewer iterations than the limit is not read as "completed"**: a tree that ran out of nodes to expand
    looks identical to one a stop signal cut short, and a claim that the search was exhaustive is one the planner never
    made.
    """
    if limits.iteration_limit is not None and statistics.iterations is not None and statistics.iterations >= limits.iteration_limit:
        return SearchTermination.ITERATION_LIMIT
    if limits.time_limit_seconds is not None and statistics.search_seconds is not None and statistics.search_seconds >= limits.time_limit_seconds:
        return SearchTermination.TIME_LIMIT
    return SearchTermination.UNKNOWN


def route_molecules(route: Route) -> tuple[str, ...]:
    """Every distinct molecule of a route as the planner wrote it, target first, then each step's product and reactants in the order the steps are run, then the starting materials."""
    found: list[str] = [route.target_smiles]
    for step in route.steps:
        found.append(step.product)
        found.extend(step.reactants)
    found.extend(material.smiles for material in route.starting_materials)
    return tuple(dict.fromkeys(found))


def shown(value: object) -> str:
    """A field as it is displayed: `None` as "not provided", never an empty cell or a zero."""
    if value is None:
        return NOT_PROVIDED
    return str(value)


def forward_order(steps: Sequence[RouteStep], target_smiles: str) -> tuple[RouteStep, ...]:
    """The steps in the order they would be run: a step comes after every step that makes one of its reactants.

    Ordered by distance from the target, farthest first (ties keep the planner's order), so the last step is the one that
    makes the target. Raises `ValueError` if the steps do not form a tree (or a DAG) rooted at `target_smiles`.
    """
    depth = _depths(target_smiles, steps)
    order = sorted(range(len(steps)), key=lambda i: (-depth[i], i))
    return tuple(steps[i] for i in order)


def _depths(target_smiles: str, steps: Sequence[RouteStep]) -> dict[int, int]:
    """Longest distance of each step (by index) from the step that makes the target, which is 0.

    Longest, not shortest: a molecule two later steps both consume (an intermediate used twice) must come before both. A
    cycle, a second step making the target's molecule, or a step the target does not lead to is a `ValueError`.
    """
    makers: dict[str, int] = {}
    for i, step in enumerate(steps):
        if step.product in makers:
            raise ValueError("two steps make the same molecule")
        makers[step.product] = i
    if target_smiles not in makers:
        raise ValueError("no step makes the target")
    depth: dict[int, int] = {}

    def visit(i: int, d: int, path: frozenset[int]) -> None:
        if i in path:
            raise ValueError("the steps contain a cycle")
        if depth.get(i, -1) >= d:
            return
        depth[i] = d
        for reactant in dict.fromkeys(steps[i].reactants):
            if reactant in makers:
                visit(makers[reactant], d + 1, path | {i})

    visit(makers[target_smiles], 0, frozenset())
    if len(depth) != len(steps):
        raise ValueError("every step must lead to the target; some make nothing the route uses")
    return depth


def _check_tree(target_smiles: str, steps: tuple[RouteStep, ...], starting: tuple[RouteMolecule, ...]) -> None:
    products = [s.product for s in steps]
    _depths(target_smiles, steps)  # one maker per molecule, no cycle, every step reachable from the target
    if products[-1] != target_smiles:
        raise ValueError("steps must be in forward order: the last step makes the target")
    made_so_far: set[str] = set()
    for step in steps:
        for reactant in step.reactants:
            if reactant in products and reactant not in made_so_far:
                raise ValueError("steps must be in forward order: a step is listed before the step that makes its reactant")
        made_so_far.add(step.product)
    expected = {r for s in steps for r in s.reactants if r not in set(products)}
    given = [m.smiles for m in starting]
    if len(set(given)) != len(given) or set(given) != expected:
        raise ValueError("starting materials must be exactly the molecules the steps consume and no step makes, each once")


def _nonblank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} cannot be blank")


def _positive_int_or_none(name: str, value: int | None) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
        raise ValueError(f"{name} must be a positive integer or None")
