"""What a nuclide decays into, and the tree that follows.

**A COMPOSITIONAL GRAMMAR, NOT A TABLE OF 45 MODES.** NUBASE2020 records
45 distinct decay modes among ground states, and a lookup table of them
would rot the first time an evaluation adds one. They decompose instead:
an optional beta step, then emitted fragments with multipliers.

    B-        Z+1        beta minus
    B+ EC e+  Z-1        the three ways of losing a proton's charge
    2B- 2B+   Z+-2       double beta
    n p d t A            neutron, proton, deuteron, triton, alpha
    14C 28Mg 34Si        cluster emission, any nuclide symbol
    2n 3p B-3n B+2p      multipliers, and combinations of the above

**AND THAT GRAMMAR ALREADY CAUGHT A BUG IN ITS OWN PROTOTYPE.** A first
parser tokenised `B+pA` as `B+` followed by the single symbol `pA`, found
no such fragment, and classified the mode unfollowable. It is beta-plus,
then a proton, then an alpha: Z-4 and A-5. Consuming fragments one at a
time gets it right, and the "no unrecognised modes" rule below is what
turned a silent dead branch into a build failure.

## Followable is about the stoichiometry, not about being a cluster

Single-cluster emission is perfectly derivable -- 14C from Ra-223 gives
Pb-209, Z-6 and A-14, like any other fragment. What cannot be followed is
a mode with no single daughter, which measured is exactly five of the 45.

## A cycle is an error, not a leaf

Returning a `cycle` leaf would make every tree terminate and every corpus
assertion pass while a broken daughter calculation hid behind the guard --
defeating the very mutation the corpus test exists to catch. So the walk
raises, and the corpus test asserts nothing raises. Measured on the
shipped table: **zero cycles**, so that error is unreachable today.

## Ground-state topology, not a complete decay network

Every nuclide here is a ground state; the table carries no isomers. A
real decay can populate an excited state which then decays differently,
so this is an educational topology rather than the full physics, and the
UI says so rather than leaving it in a docstring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple

from openchem.chem.nuclides import (
    Nuclide,
    NuclideKey,
    nuclide,
    nuclide_at,
    _symbol_by_z,
)

#: Charge change per beta step. Longest first when matching, so `2B-`
#: is never read as `2` followed by `B-`.
_BETA = {"2B-": 2, "2B+": -2, "EC+B+": -1, "B-": 1, "B+": -1, "EC": -1, "e+": -1}

#: (dZ, dA) removed per emitted light fragment.
_FRAGMENT = {"n": (0, 1), "p": (1, 1), "d": (1, 2), "t": (1, 3), "A": (2, 4)}

#: **THE ISOMERIC TRANSITION, WHICH IS NOT A (dZ, dA) AT ALL.** It moves
#: a nucleus DOWN in excitation at constant Z and A, so in `(Z, A)` space
#: it is a self-loop -- and giving it `(0, 0)` would make the walk cycle
#: and trip `_refuse_cycles`. In `(Z, A, state_index)` space it is a
#: strict descent, which is what makes the walk terminate.
#:
#: 1,471 rows carry it, and `is_recognised("IT")` was False before this
#: existed -- so the generator's zero-unrecognised-modes rule REFUSED to
#: build with isomers in the table rather than dropping those branches
#: silently. That is the fail-closed design doing its job.
ISOMERIC_TRANSITION = "IT"

#: Modes with no single daughter. **Measured, not guessed**: these are
#: the only five of the 45 whose stoichiometry cannot be derived.
#: `SF` and its beta-delayed forms fission; the two `X+Y` expressions
#: report one summed branching for two different clusters, so neither
#: daughter can be attributed.
UNFOLLOWABLE = frozenset({"SF", "B-SF", "B+SF", "24Ne+26Ne", "28Mg+30Mg"})

#: Modes whose daughter EXISTS but which the source does not pin down.
#: **A DIFFERENT CLAIM FROM `UNFOLLOWABLE`**, and conflating the two
#: would make the leaf reason a lie: there is one daughter here, and
#: NUBASE simply does not say which.
#:
#: **ONE ROW IN 5,684, and it arrived with the isomers.** Pd-126p writes
#: `B=72 8;IT=28 8` -- a beta decay with no sign, where the sign is
#: exactly what decides whether Z goes up or down. Its own ground state
#: is `B-=100`, and an isomer sits HIGHER in energy, so beta-minus is a
#: near-certain inference -- which is precisely why it is refused. This
#: application does not derive physics the source declined to state, and
#: NUBASE's own format header (columns 120-209, "Decay Modes and their
#: Intensities") documents no mode vocabulary to appeal to.
UNDERSPECIFIED = frozenset({"B"})

#: Why a branch stops. **Three physical reasons and no fourth** -- a
#: `cycle` reason would be a bug wearing a leaf's clothes.
STABLE = "stable"
UNFOLLOWABLE_MODE = "unfollowable"
OFF_TABLE = "off_table"
#: **THE FOURTH REASON, AND IT IS NOT A PHYSICAL ONE.** The three above
#: describe the nucleus; this one describes the DATA -- the mode is
#: named and its sign is not, so a daughter exists and cannot be
#: identified. Kept separate for that reason: folding it into
#: `unfollowable` would tell a reader no daughter exists.
UNDERSPECIFIED_MODE = "underspecified"

_TOKEN = re.compile(r"(\d*)([A-Z][a-z]?|[npdtA])")


class DecayGraphError(RuntimeError):
    """The decay graph did something it is not allowed to do.

    Raised for a cycle. Not a display state: a tree that quietly reported
    one would hide exactly the arithmetic error it was guarding against.
    """


#: How a mode is written for a reader. NUBASE's own tokens are compact
#: and cryptic -- `A` for alpha, `B-` for beta minus -- so the common ones
#: get their names and anything else falls through as written.
#:
#: **ASCII, deliberately.** This text is copied out of the isotope table
#: and the decay diagram, and this project has recorded three separate
#: `UnicodeEncodeError`s from result lines meeting a cp1252 console --
#: which has no Greek at all.
_MODE_NAMES = {
    "A": "alpha",
    # NUBASE writes ONE unsigned beta, on Pd-126p. The sign decides the
    # daughter, so it is named rather than guessed at -- see UNDERSPECIFIED.
    "B": "beta (sign not stated)",
    # **THE SECOND COMMONEST MODE IN THE TABLE, at 1,471 rows**, and it
    # shipped rendering as its raw token beside "beta+" and "electron
    # capture" -- exactly the cryptic-token problem this map exists for.
    # Found by magnifying the Isotopes tab, with the whole suite green.
    "IT": "isomeric transition",
    "B-": "beta-",
    "B+": "beta+",
    "2B-": "double beta-",
    "2B+": "double beta+",
    "EC": "electron capture",
    "EC+B+": "electron capture / beta+",
    "e+": "positron",
    "SF": "spontaneous fission",
    "B-SF": "beta- delayed fission",
    "B+SF": "beta+ delayed fission",
    "p": "proton",
    "2p": "2 protons",
    "n": "neutron",
    "2n": "2 neutrons",
    "B-n": "beta- delayed neutron",
    "B-2n": "beta- delayed 2 neutrons",
    "B+p": "beta+ delayed proton",
    "B-A": "beta- delayed alpha",
    "B+A": "beta+ delayed alpha",
}


def format_mode(mode: str) -> str:
    """A decay mode as words, falling back to the source's own token.

    A cluster emission like `14C` reads perfectly well as itself, and
    inventing a name for each of the thirteen would be a table to keep in
    step with NUBASE for no gain.
    """
    return _MODE_NAMES.get(mode, mode)


def format_branching(branching: float | None, qualifier: str | None) -> str:
    """A branching ratio, **carrying its qualifier**.

    `?` is the commonest of all -- 1,755 of them -- and means the mode is
    expected while nobody has measured how often. Rendered as a bare
    percentage it would read as a measurement; rendered as nothing at all
    the mode would look impossible.

    **A BRANCHING OF EXACTLY ZERO IS FAITHFUL, NOT A BUG.** Thirteen
    entries carry one -- Tc-98's `B+=0` among them -- and it is NUBASE
    saying the branch is known and negligible. It renders as `0%`.
    Turning that into `<0.01%` would be inventing a bound the source
    never gave.
    """
    if branching is None:
        return "unmeasured" if qualifier else ""
    if branching >= 1:
        number = f"{branching:g}%"
    else:
        number = f"{branching:.3g}%"
    if qualifier in ("<", ">", "~"):
        return f"{qualifier} {number}"
    if qualifier == "?":
        return f"{number} (unconfirmed)"
    return number


def mode_family(mode: str) -> str:
    """Which kind of decay this is, for colouring a chain.

    **DERIVED FROM `delta_for`, NEVER FROM A SECOND STRING TABLE.** The
    grammar already knows what a mode does; a parallel table keyed on the
    same 45 tokens is a second thing to keep in step with NUBASE, and
    this file's whole reason for having a grammar rather than a lookup is
    that a 45-entry table rots the first time a mode is added.

    Five families, chosen for what a reader needs off a chart rather than
    for taxonomic tidiness -- `other` is composites and nucleon emission,
    which move a nuclide in directions that do not group usefully.
    """
    if mode == ISOMERIC_TRANSITION:
        return "isomeric"
    delta = delta_for(mode)
    if delta is None:
        return "other"
    dz, da = delta
    if (dz, da) == (-2, -4):
        return "alpha"
    if da <= -5:
        return "cluster"
    if da == 0 and dz > 0:
        return "beta_minus"
    if da == 0 and dz < 0:
        return "beta_plus"
    return "other"


def _z_by_symbol() -> dict[str, int]:
    return {symbol: z for z, symbol in _symbol_by_z().items()}


def delta_for(mode: str) -> tuple[int, int] | None:
    """(dZ, dA) for one decay mode, or None if it has no single daughter.

    Deterministic for every token sequence: the same string always gives
    the same pair, and an unrecognised one gives None rather than a
    partial answer.

    **AN ISOMERIC TRANSITION IS (0, 0) HERE AND IS NOT A CYCLE**, because
    the state index it descends is not part of this pair. Callers that
    resolve a daughter must use `daughter()`, which carries the state;
    reading `delta_for("IT")` alone and following it in `(Z, A)` space
    would loop forever.
    """
    if mode in UNFOLLOWABLE or mode in UNDERSPECIFIED:
        return None
    if mode == ISOMERIC_TRANSITION:
        return (0, 0)

    rest = mode
    z = 0
    for name in sorted(_BETA, key=len, reverse=True):
        if rest.startswith(name):
            z = _BETA[name]
            rest = rest[len(name):]
            break

    a = 0
    symbols = _z_by_symbol()
    while rest:
        match = _TOKEN.match(rest)
        if match is None:
            return None
        count = int(match.group(1)) if match.group(1) else 1
        token = match.group(2)
        if token in _FRAGMENT and not match.group(1):
            dz, da = _FRAGMENT[token]
            z -= dz
            a -= da
        elif token in _FRAGMENT:
            dz, da = _FRAGMENT[token]
            z -= count * dz
            a -= count * da
        elif match.group(1) and token in symbols:
            # A cluster: the multiplier is its MASS NUMBER, not a count.
            z -= symbols[token]
            a -= count
        else:
            return None
        rest = rest[match.end():]
    return z, a


def is_recognised(mode: str) -> bool:
    """Does this mode parse, or is it explicitly unfollowable?

    **The third state must be impossible in shipped data.** A mode that is
    neither means NUBASE introduced a notation nobody anticipated, and the
    generator refuses rather than dropping the branch silently.
    """
    return (
        mode in UNFOLLOWABLE
        or mode in UNDERSPECIFIED
        or delta_for(mode) is not None
    )


class DaughterProvenance(str, Enum):
    """How a decay edge's daughter STATE was arrived at.

    **NUBASE NAMES NO DAUGHTER STATE.** Read off the raw rows, the whole
    of what the decay field carries is the mode and the branching --
    `B-=100`, `IT~100;B-=0.0037` -- so which state of Ru-99 a Tc-99m beta
    decay populates is simply not in the source.

    **THE ASSUMPTION IS BEING MADE ALREADY, INVISIBLY**, and that is the
    honest framing: today's uranium chain resolves U-238 to Th-234's
    ground state because ground states are all the table holds. Isomers do
    not create the assumption, they make it visible. So this is a VALUE
    that reaches the screen rather than a comment -- a diagram that looks
    like an exact NUBASE-derived chain while part of it is this
    application's guess is precisely the plausible-looking wrongness this
    project spends its time removing.

    A `str` enum so it can be compared, sorted and put in a diagnostic
    without a conversion, the same as the leaf reasons beside it.
    """

    #: The source determines it. **ONE CASE, AND IT IS REAL**: an
    #: isomeric transition from state index 1 has only the ground state
    #: below it, so there is nowhere else it can land. From index 2 or
    #: above it could reach any lower state and the source does not say.
    EXACT = "exact"
    #: NUBASE names no state populated, so the ground state was drawn.
    ASSUMED_GROUND_STATE = "assumed_ground_state"
    #: No single daughter exists to have a state -- fission, or a summed
    #: branching for two different clusters.
    UNFOLLOWABLE = "unfollowable"


class DaughterResolution(NamedTuple):
    """What a decay leads to, and how much of that the source determines."""

    nuclide: "Nuclide | None"
    provenance: DaughterProvenance


def daughter(parent: Nuclide, mode: str) -> DaughterResolution:
    """What `parent` becomes, and how its STATE was arrived at.

    **THE PROVENANCE COMES BACK WITH THE RESULT rather than being asked
    for.** A `DaughterStatePolicy` argument was considered and deferred:
    it would have exactly one caller and one value today, and a consumer
    wanting exact-only can filter on what it is already handed. The
    boundary is explicit either way; this is the version with less
    machinery.

    **AN ISOMERIC TRANSITION DESCENDS A STATE, IT DOES NOT MOVE.** In
    `(Z, A)` space it is a self-loop, which is why `delta_for` returning
    `(0, 0)` must never be followed on its own -- the state index is what
    makes the walk terminate, and it is resolved here.
    """
    if mode == ISOMERIC_TRANSITION:
        return _isomeric_daughter(parent)
    delta = delta_for(mode)
    if delta is None:
        return DaughterResolution(None, DaughterProvenance.UNFOLLOWABLE)
    return DaughterResolution(
        nuclide(parent.z + delta[0], parent.a + delta[1]),
        DaughterProvenance.ASSUMED_GROUND_STATE,
    )


def _isomeric_daughter(parent: Nuclide) -> DaughterResolution:
    """Which lower state an `IT` from `parent` reaches.

    From index 1 there is exactly one state below and the answer is
    EXACT. From index 2 or above the source does not say, so the ground
    state is drawn and the edge records that it was assumed.

    A ground state has nothing below it, so an `IT` on one is a
    contradiction in the data rather than a branch -- reported as
    unfollowable rather than resolved to itself, which would be the
    self-loop `_refuse_cycles` exists to catch.
    """
    if parent.is_ground_state:
        return DaughterResolution(None, DaughterProvenance.UNFOLLOWABLE)
    below = nuclide_at(NuclideKey(parent.z, parent.a))
    provenance = (
        DaughterProvenance.EXACT
        if parent.state_index == 1
        else DaughterProvenance.ASSUMED_GROUND_STATE
    )
    return DaughterResolution(below, provenance)


@dataclass(frozen=True)
class DecayEdge:
    """One decay path, drawn."""

    mode: str
    branching: float | None
    qualifier: str | None
    to: NuclideKey | None
    #: Set when `to` is None: why this branch stops here.
    leaf_reason: str = ""
    #: How the daughter's STATE was arrived at. **It reaches the screen**
    #: -- an assumed edge is marked on the chart and explained in the
    #: legend, because a provenance that exists while failing to protect
    #: interpretation is worse than none.
    provenance: DaughterProvenance = DaughterProvenance.ASSUMED_GROUND_STATE

    @property
    def is_assumed(self) -> bool:
        """Did this application choose the daughter's state?"""
        return self.provenance is DaughterProvenance.ASSUMED_GROUND_STATE


@dataclass
class DecayTree:
    """The reachable ground states, and how they connect.

    A graph rather than a literal tree -- decay paths converge, and
    duplicating a shared daughter would draw uranium's chain several
    times. `edges` is keyed by (Z, A).
    """

    root: NuclideKey
    nodes: dict[NuclideKey, Nuclide] = field(default_factory=dict)
    edges: dict[NuclideKey, list[DecayEdge]] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.nodes)

    def leaves(self) -> dict[NuclideKey, str]:
        """Every terminal node, and the physical reason it is terminal."""
        found: dict[NuclideKey, str] = {}
        for key, outgoing in self.edges.items():
            if any(edge.to is not None for edge in outgoing):
                continue
            if self.nodes[key].is_stable:
                found[key] = STABLE
            elif outgoing:
                found[key] = outgoing[0].leaf_reason or UNFOLLOWABLE_MODE
            else:
                found[key] = STABLE if self.nodes[key].is_stable else OFF_TABLE
        return found


def decay_tree(start: Nuclide) -> DecayTree:
    """Every ground state reachable from `start`, following all branches.

    **No threshold and no node cap**, because measured across all 3,557
    shipped nuclides the trees are bounded by the physics: median 8 nodes,
    mean 15, and 161 at the largest (Au-169). Chains converge on
    stability. A cap would be a constant somebody chose over a number
    nobody needed.
    """
    tree = DecayTree(root=start.key)
    pending = [start]

    while pending:
        current = pending.pop()
        key = current.key
        if key in tree.nodes:
            continue
        tree.nodes[key] = current
        outgoing: list[DecayEdge] = []
        for decay in current.decays:
            child, provenance = daughter(current, decay.mode)
            if child is None:
                if decay.mode in UNDERSPECIFIED:
                    reason = UNDERSPECIFIED_MODE
                elif provenance is DaughterProvenance.UNFOLLOWABLE:
                    reason = UNFOLLOWABLE_MODE
                else:
                    reason = OFF_TABLE
                outgoing.append(
                    DecayEdge(
                        decay.mode,
                        decay.branching,
                        decay.qualifier,
                        None,
                        reason,
                        provenance,
                    )
                )
                continue
            child_key = child.key
            if child_key == key:
                raise DecayGraphError(
                    f"{current.name} decays to itself by {decay.mode}; "
                    "the daughter arithmetic is wrong"
                )
            outgoing.append(
                DecayEdge(
                    decay.mode,
                    decay.branching,
                    decay.qualifier,
                    child_key,
                    "",
                    provenance,
                )
            )
            pending.append(child)
        tree.edges[key] = outgoing

    _refuse_cycles(tree)
    return tree


def _refuse_cycles(tree: DecayTree) -> None:
    """A cycle is an ERROR, and this is where it is refused.

    Not a leaf reason. A tree that reported one would terminate happily
    and satisfy every corpus assertion while a reversed daughter
    calculation hid inside it -- which is precisely the mutation the
    corpus test exists to catch.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(tree.nodes, WHITE)
    for start in list(tree.nodes):
        if colour[start] != WHITE:
            continue
        stack = [(start, iter(tree.edges.get(start, ())))]
        colour[start] = GREY
        while stack:
            node, edges = stack[-1]
            advanced = False
            for edge in edges:
                if edge.to is None or edge.to not in colour:
                    continue
                if colour[edge.to] == GREY:
                    raise DecayGraphError(
                        f"decay path cycles at {tree.nodes[edge.to].name}"
                    )
                if colour[edge.to] == WHITE:
                    colour[edge.to] = GREY
                    stack.append((edge.to, iter(tree.edges.get(edge.to, ()))))
                    advanced = True
                    break
            if not advanced:
                colour[node] = BLACK
                stack.pop()
