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

from openchem.chem.nuclides import Nuclide, nuclide, _symbol_by_z

#: Charge change per beta step. Longest first when matching, so `2B-`
#: is never read as `2` followed by `B-`.
_BETA = {"2B-": 2, "2B+": -2, "EC+B+": -1, "B-": 1, "B+": -1, "EC": -1, "e+": -1}

#: (dZ, dA) removed per emitted light fragment.
_FRAGMENT = {"n": (0, 1), "p": (1, 1), "d": (1, 2), "t": (1, 3), "A": (2, 4)}

#: Modes with no single daughter. **Measured, not guessed**: these are
#: the only five of the 45 whose stoichiometry cannot be derived.
#: `SF` and its beta-delayed forms fission; the two `X+Y` expressions
#: report one summed branching for two different clusters, so neither
#: daughter can be attributed.
UNFOLLOWABLE = frozenset({"SF", "B-SF", "B+SF", "24Ne+26Ne", "28Mg+30Mg"})

#: Why a branch stops. **Three physical reasons and no fourth** -- a
#: `cycle` reason would be a bug wearing a leaf's clothes.
STABLE = "stable"
UNFOLLOWABLE_MODE = "unfollowable"
OFF_TABLE = "off_table"

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


def _z_by_symbol() -> dict[str, int]:
    return {symbol: z for z, symbol in _symbol_by_z().items()}


def delta_for(mode: str) -> tuple[int, int] | None:
    """(dZ, dA) for one decay mode, or None if it has no single daughter.

    Deterministic for every token sequence: the same string always gives
    the same pair, and an unrecognised one gives None rather than a
    partial answer.
    """
    if mode in UNFOLLOWABLE:
        return None

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
    return mode in UNFOLLOWABLE or delta_for(mode) is not None


def daughter(parent: Nuclide, mode: str) -> Nuclide | None:
    """What `parent` becomes, or None if that cannot be derived."""
    delta = delta_for(mode)
    if delta is None:
        return None
    return nuclide(parent.z + delta[0], parent.a + delta[1])


@dataclass(frozen=True)
class DecayEdge:
    """One decay path, drawn."""

    mode: str
    branching: float | None
    qualifier: str | None
    to: tuple[int, int] | None
    #: Set when `to` is None: why this branch stops here.
    leaf_reason: str = ""


@dataclass
class DecayTree:
    """The reachable ground states, and how they connect.

    A graph rather than a literal tree -- decay paths converge, and
    duplicating a shared daughter would draw uranium's chain several
    times. `edges` is keyed by (Z, A).
    """

    root: tuple[int, int]
    nodes: dict[tuple[int, int], Nuclide] = field(default_factory=dict)
    edges: dict[tuple[int, int], list[DecayEdge]] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.nodes)

    def leaves(self) -> dict[tuple[int, int], str]:
        """Every terminal node, and the physical reason it is terminal."""
        found: dict[tuple[int, int], str] = {}
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
    tree = DecayTree(root=(start.z, start.a))
    pending = [start]
    on_path: set[tuple[int, int]] = set()

    while pending:
        current = pending.pop()
        key = (current.z, current.a)
        if key in tree.nodes:
            continue
        tree.nodes[key] = current
        outgoing: list[DecayEdge] = []
        for decay in current.decays:
            child = daughter(current, decay.mode)
            if child is None:
                reason = (
                    UNFOLLOWABLE_MODE
                    if decay.mode in UNFOLLOWABLE or delta_for(decay.mode) is None
                    else OFF_TABLE
                )
                outgoing.append(
                    DecayEdge(decay.mode, decay.branching, decay.qualifier, None, reason)
                )
                continue
            child_key = (child.z, child.a)
            if child_key == key:
                raise DecayGraphError(
                    f"{current.name} decays to itself by {decay.mode}; "
                    "the daughter arithmetic is wrong"
                )
            outgoing.append(
                DecayEdge(decay.mode, decay.branching, decay.qualifier, child_key)
            )
            pending.append(child)
        tree.edges[key] = outgoing

    _refuse_cycles(tree)
    del on_path
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
    order = [tree.root] if tree.root in tree.nodes else list(tree.nodes)

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
    del order
