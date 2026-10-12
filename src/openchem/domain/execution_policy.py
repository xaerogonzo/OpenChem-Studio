"""May a calculator run because a model asked, or does a person approve it first.

**FOUR QUESTIONS THAT LOOK LIKE ONE, AND A `cheap` FLAG WOULD ANSWER THEM ALL WITH THE SAME
WORD.** How long it takes, which external program it starts, whether it leaves anything behind
besides a stored result, and whether it is safe to start unattended are different facts:

* a calculator can be quick and still start a Java process and reach the network
  (`iupac_name`);
* one can be slow and be exactly what the person asked for (Docking), once they have seen what
  it will do;
* one can be instant at its defaults and 100 times slower at a setting the model chose
  (`hbond_vs_ph` at a 0.01 pH step).

So the policy holds each separately, and `ai_run` -- the only field a decision reads -- is
derived from them by a guard, never from a hand-set word that drifts from the others.

**MEASURED, NOT ESTIMATED.** An `AUTO` policy must say how it was measured (`measured`). The
numbers behind the shipped table are in `benchmarks/calculator_cost/` and the guard in
`tests/test_execution_policy.py` re-reads the declared ceilings against each parameter's own
bounds. Costs are labelled on a three-step scale rather than in seconds, because a second on
this machine is not a second on Alex's laptop; the scale's boundaries are fixed here.

**THE DEFAULT IS THE CAUTIOUS ONE, FOR THE REASON `CalculatorDefinition.applies_to`'S IS.** A
calculator nobody classified -- a plugin's, a test double, a built-in added without a thought --
needs approval. Auto-running is an opt-in somebody had to measure and mean.

**A POLICY GOVERNS THE CALCULATOR AS SHIPPED, AND IS ATTACHED BY THE COMPOSITION ROOT.**
`bootstrap` puts a built-in's policy on its definition; a plugin that registers an id a built-in
also uses does not inherit it, because nothing here looks policies up by id.

Pure: no Qt, no RDKit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ResourceClass(str, Enum):
    """What running it costs, in the worst case MEASURED on the calculator census panel.

    The boundaries are part of the contract: a calculator is `INSTANT` only if no run on the
    panel (a 3-heavy-atom, a 13-heavy-atom and a 41-heavy-atom molecule) took a second, so the
    class describes the biggest drug-like molecule the panel holds rather than ethanol.
    """

    #: Under a second.
    INSTANT = "instant"
    #: Under ten seconds, or under ten at the ceilings its policy sets.
    SHORT = "short"
    #: Ten seconds or more, unbounded by any parameter, or NOT MEASURED. "Not measured" is
    #: deliberately filed here: an unknown cost is not a small one.
    LONG = "long"


class AiRun(str, Enum):
    """Whether a request from the assistant may start this without a person approving it."""

    #: Runs when asked, subject to the policy's ceilings and floors.
    AUTO = "auto"
    #: Prepared as a preview; only a person pressing Confirm starts it.
    CONFIRM = "confirm"


#: Names of the external programs a calculator can start. Closed, so a typo cannot quietly
#: read as "starts nothing". A plugin declaring a program not listed here is a validation
#: error until this set grows, which is the point of keeping it small and reviewed.
EXTERNAL_TOOLS = frozenset({
    "pkasolver",    # the pKa sidecar interpreter (Tools > External Tools)
    "admet_ai",     # the ADMET-AI sidecar interpreter
    "opsin_java",   # OPSIN through Java, for name -> structure
    "network",      # an outbound HTTP request
    "orca",         # ORCA quantum chemistry
    "vina",         # AutoDock Vina
})

#: Programs that run for as long as the job asks and write files of their own. A policy that
#: names one of these cannot be `AUTO`, whatever else it says.
HEAVY_TOOLS = frozenset({"orca", "vina"})

#: The largest molecule an `AUTO` run is allowed on, in heavy atoms. **It is the census panel's
#: biggest molecule (atorvastatin, 41), and not a round number above it**, because every measured
#: figure stands for a molecule up to that size and a larger one is outside what was measured. It
#: is a ceiling on the evidence, not on the chemistry: raise it by measuring a bigger panel, never
#: by editing the number. `alignment_3d` shows why a size matters: the same 41-heavy-atom molecule
#: took 0.6 s aligned to a 13-heavy-atom reference and 31 s aligned to a 28-heavy-atom one.
AUTO_MAX_HEAVY_ATOMS = 41

#: `(parameter name, minimum or None, maximum or None)`. A request whose value for the
#: parameter falls outside is not refused: it becomes a `CONFIRM`, with the reason.
Bound = tuple[str, float | None, float | None]

#: `(parameter name, values that disqualify automatic running)`, for a choice whose setting
#: changes what the calculator does rather than how much of it (`conformer_policy`).
Exclusion = tuple[str, frozenset[str]]


@dataclass(frozen=True)
class ExecutionPolicy:
    """How one calculator may be started on behalf of a model."""

    resource: ResourceClass
    ai_run: AiRun
    #: Programs it starts, from `EXTERNAL_TOOLS`. Empty means it runs in this process.
    external_tools: frozenset[str] = frozenset()
    #: True when a run leaves anything behind besides a stored result: files, a network request,
    #: a pose on disk. A stored result is not an effect -- recording it is the point.
    writes_outside_results: bool = False
    #: Parameter ranges inside which `AUTO` holds. Outside, the request needs approval.
    auto_bounds: tuple[Bound, ...] = ()
    #: Choice values that need approval, whatever the numbers say.
    auto_excluded: tuple[Exclusion, ...] = ()
    #: How the cost was established: what was run, on what, where the figures are. Required for
    #: `AUTO`, because "it is fast" with no measurement is how this was a guess before.
    measured: str = ""
    #: Why a person approves it first. Required for `CONFIRM`, and shown beside the preview.
    why_confirm: str = ""

    def __post_init__(self) -> None:
        unknown = self.external_tools - EXTERNAL_TOOLS
        if unknown:
            raise ValueError(f"unknown external tool(s) {sorted(unknown)}; expected from {sorted(EXTERNAL_TOOLS)}")
        if self.ai_run is AiRun.AUTO:
            if self.resource is ResourceClass.LONG:
                raise ValueError("a LONG calculator cannot run automatically")
            heavy = self.external_tools & HEAVY_TOOLS
            if heavy:
                raise ValueError(f"a calculator that starts {sorted(heavy)} cannot run automatically")
            if self.writes_outside_results:
                raise ValueError("a calculator that writes outside the result store cannot run automatically")
            if not self.measured.strip():
                raise ValueError("an AUTO policy must say how its cost was measured")
        else:
            if self.auto_bounds or self.auto_excluded:
                raise ValueError("auto bounds and exclusions belong to an AUTO policy only")
            if not self.why_confirm.strip():
                raise ValueError("a CONFIRM policy must say why a person approves it first")
        for name, low, high in self.auto_bounds:
            if low is None and high is None:
                raise ValueError(f"auto bound on {name!r} limits nothing")
            if low is not None and high is not None and low > high:
                raise ValueError(f"auto bound on {name!r}: minimum {low} is above maximum {high}")


#: Nobody has classified it, so a person approves it. Not a statement about the calculator.
UNCLASSIFIED = ExecutionPolicy(
    ResourceClass.LONG,
    AiRun.CONFIRM,
    why_confirm="Nobody has measured what this costs or what it starts, so a person approves it first.",
)


def policy_of(definition: Any) -> ExecutionPolicy:
    """The policy a definition declares, or the cautious one."""
    return getattr(definition, "execution_policy", None) or UNCLASSIFIED


@dataclass(frozen=True)
class RunDecision:
    """Whether THIS request, with these parameters, may start without approval."""

    ai_run: AiRun
    #: Why it needs approval, for the preview; "" when it runs automatically.
    reason: str = ""


def decide(
    policy: ExecutionPolicy, parameters: dict[str, Any] | None = None, heavy_atoms: int | None = None
) -> RunDecision:
    """`AUTO` for a request inside the policy's bounds, `CONFIRM` with the reason otherwise.

    A parameter the request does not set is not tested: the calculator's default applies, and
    the policy was measured at the defaults. A value that is not a number where a bound exists
    is treated as outside it -- a bound on a number cannot vouch for something else.

    `heavy_atoms` is the size of the molecule the run would be handed. **UNKNOWN IS NOT SMALL:**
    `None` means the caller could not say, and an `AUTO` policy then still holds only because
    the host always knows the size it is handing over; a caller that passes `None` for a
    molecule it has is leaving the check out, which is why the host passes it and a test pins
    that it does.
    """
    if policy.ai_run is AiRun.CONFIRM:
        return RunDecision(AiRun.CONFIRM, policy.why_confirm)
    if heavy_atoms is not None and heavy_atoms > AUTO_MAX_HEAVY_ATOMS:
        return RunDecision(
            AiRun.CONFIRM,
            f"the molecule has {heavy_atoms} heavy atoms; the cost was measured on molecules of up to "
            f"{AUTO_MAX_HEAVY_ATOMS}, and larger ones can take far longer",
        )
    values = parameters or {}
    for name, low, high in policy.auto_bounds:
        if name not in values:
            continue
        value = values[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return RunDecision(AiRun.CONFIRM, f"{name} is {value!r}, which is not a number the cost was measured for")
        if low is not None and value < low:
            return RunDecision(AiRun.CONFIRM, f"{name} {value:g} is below {low:g}, the smallest value measured to stay quick")
        if high is not None and value > high:
            return RunDecision(AiRun.CONFIRM, f"{name} {value:g} is above {high:g}, the largest value measured to stay quick")
    for name, excluded in policy.auto_excluded:
        if name in values and str(values[name]) in excluded:
            return RunDecision(AiRun.CONFIRM, f"{name}={values[name]!s} does much more work than the default")
    return RunDecision(AiRun.AUTO)
