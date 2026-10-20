"""`context.synthesis` and `context.synthesis_requests`: what a plugin may do with the synthesis planner (`docs/SYNTHESIS_HELPER_DESIGN.md`, Stage 1 slice 8), and nothing else.

A plugin never receives the planning service, the setting provider or the window (`PluginContext` hides all of them on purpose). The synthesis panel needs to read the selected molecule, ask what the
planner's configuration offers, start and stop a plan and read its result; this is exactly that, as calls that take and return plain values.

**THE READING HANDLE CANNOT START ANYTHING.** `PluginSynthesis` reads and draws; starting a plan, stopping one and choosing the policy, stock or filter are on `PluginSynthesisRequests`, a different object, which
a plugin's PANEL is given for its buttons and a plugin's TOOLS are not (the split `context.calculations` / `context.calculation_approvals` already makes). That a model's tool cannot start a search is
therefore a fact about which object it was handed. THE REGULATORY GATE DOES NOT DEPEND ON THIS SPLIT: it is enforced inside `SynthesisPlanningService.request_plan`, which every start goes through.

**A CONTEXT BUILT WITHOUT A HOST IS NOT AN ERROR.** A headless run or a test has none; every read then answers "nothing" and every request is `REJECTED`, the behaviour a plugin gets for any capability the
host did not provide.

THREADS: `target`, `request_plan`, `cancel`, `choose` and `result_for` are GUI-thread calls (they read the live project, or start a job that must be announced there). `options` can start the planner's
Python (about 1.6 s the first time) and is for a worker; `setup_is_warm` says whether that wait is over. `depict` is pure drawing and may be called from any thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from openchem.domain.synthesis_route import RouteStep
from openchem.services.synthesis_planner_setup import PlannerOptions
from openchem.services.synthesis_planning_service import BoundResult, RequestOutcome

#: The three choices a person can make about the planner, as the section of the configuration each one names.
CHOICES = ("expansion", "stock", "filter")

#: The answer to "what does the configuration offer" when the application did not provide a planner to this plugin.
_NO_HOST = PlannerOptions(ok=False, problem="The application did not provide the synthesis planner to this plugin (a headless run or a test).")


@dataclass(frozen=True)
class SynthesisTarget:
    """The molecule a plan would be for, as it is drawn now."""

    molecule_uuid: str
    display_name: str
    canonical_smiles: str


class SynthesisHost(Protocol):
    """What the window provides. Structural, so a test double needs no base class."""

    def target(self) -> SynthesisTarget | None: ...

    def result_for(self, molecule_uuid: str) -> BoundResult | None: ...

    def is_planning(self, molecule_uuid: str) -> bool: ...

    def setup_is_warm(self) -> bool: ...

    def options(self) -> PlannerOptions: ...

    def depict(self, step: RouteStep) -> str: ...

    def request_plan(self, molecule_uuid: str, requested_by: str) -> RequestOutcome: ...

    def cancel(self, molecule_uuid: str) -> bool: ...

    def choose(self, section: str, name: str | None) -> None: ...


class PluginSynthesis:
    """The reading face. See the module docstring."""

    def __init__(self, host: SynthesisHost | None) -> None:
        self._host = host

    @property
    def available(self) -> bool:
        return self._host is not None

    def target(self) -> SynthesisTarget | None:
        """The selected molecule, or None when nothing is selected, it has no structure, or no host is present. GUI thread."""
        return self._host.target() if self._host is not None else None

    def result_for(self, molecule_uuid: str) -> BoundResult | None:
        """The stored plan for that molecule, bound to the structure it was made for (`BoundResult.is_current`), or None. GUI thread."""
        return self._host.result_for(molecule_uuid) if self._host is not None else None

    def is_planning(self, molecule_uuid: str) -> bool:
        """True while a search for that molecule is queued or running. Any thread."""
        return self._host.is_planning(molecule_uuid) if self._host is not None else False

    def setup_is_warm(self) -> bool:
        """True when the planner's configuration has been read, so a request will not wait for it. Starts nothing."""
        return self._host.setup_is_warm() if self._host is not None else False

    def options(self) -> PlannerOptions:
        """What the configuration offers and what is chosen. May take about 1.6 s the first time: call it from a worker."""
        return self._host.options() if self._host is not None else _NO_HOST

    def depict(self, step: RouteStep) -> str:
        """The step as an SVG, or raises `chem.reaction_depiction.DepictionError` when a molecule of it cannot be read. Any thread."""
        if self._host is None:
            raise LookupError("the application did not provide drawing to this plugin")
        return self._host.depict(step)


class PluginSynthesisRequests:
    """What starts, stops and configures a plan. **For a panel's buttons, never for a tool.**"""

    def __init__(self, host: SynthesisHost | None) -> None:
        self._host = host

    def request_plan(self, molecule_uuid: str, requested_by: str = "the user") -> RequestOutcome:
        """Ask for a plan for that molecule. The regulatory gate decides first, inside the service, whoever asks. GUI thread."""
        if self._host is None:
            return RequestOutcome.REJECTED
        return self._host.request_plan(molecule_uuid, requested_by)

    def cancel(self, molecule_uuid: str) -> bool:
        """Stop that molecule's search, or take it out of the queue. False when none is running."""
        return self._host.cancel(molecule_uuid) if self._host is not None else False

    def choose(self, section: str, name: str | None) -> None:
        """Choose the expansion policy, the stock or the filter by the name the configuration gives it (None for no filter). Takes effect on the next plan; a plan under way keeps the choice it started with."""
        if section not in CHOICES:
            raise ValueError(f"there is nothing to choose in {section!r}; the choices are {', '.join(CHOICES)}")
        if section != "filter" and not name:
            raise ValueError(f"a {section} must be named")
        if self._host is not None:
            self._host.choose(section, name)


__all__ = ["CHOICES", "PluginSynthesis", "PluginSynthesisRequests", "SynthesisHost", "SynthesisTarget"]
