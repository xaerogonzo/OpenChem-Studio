"""The window's side of the assistant's calculator bridge: the one place a model's request becomes a run.

Everything pure -- the cards, the validation, the turn snapshot, the run ledger -- lives in `domain/`.
This is the part that needs the window's session, the services and a thread boundary, and it is
deliberately thin: it decides nothing about chemistry and starts a calculation only through the
path a person's click takes (`DescriptorService.run_calculator`), so an AI-requested run is
recorded, fingerprinted and shown exactly like any other. See `docs/AI_CALCULATION_BRIDGE.md`.

**THREADS, BECAUSE THE TOOL LOOP RUNS ON A POOL WORKER.**

* `begin_turn` runs on the GUI thread, at Send, and reads the live project once. It is the only
  call that does.
* `catalog`, `describe`, `read_results` and `prepare` read the registry and the frozen
  `TurnContext` and may be called from any thread.
* `run` is called from a worker. It posts the request to this object's thread through a queued
  signal and waits on a future for a bounded time; the GUI thread is never blocked, and a worker is
  blocked only up to the wait. Calling it ON the GUI thread would wait for events the same thread
  must process, so it refuses.
* `approve` and `cancel` are GUI-thread calls for a person's button. They are not on the plugin's
  tool-facing handle.

**ONE START, ONE FUTURE.** `RunLedger.claim_dispatch` answers True to one caller, so two requests
for one run start one calculation; the second `run` waits on the same future and gets the same
outcome. A run that outlives its caller's wait is reported `TIMED_OUT` -- it is still running, its
result lands in Results by the ordinary path, and asking again returns the recorded outcome rather
than starting another.

**THE PLAN IS CHECKED AGAIN AT THE MOMENT OF STARTING.** The structure and the project the plan
was made against must still be the live ones, or the run is `INVALIDATED` and nothing starts. That
is what makes approving a stale preview impossible rather than merely unlikely.

**KNOWN LIMIT.** A completion is matched to its run by (calculator, molecule) and the result by its
parameter identity; the bus carries no run id. If a person runs the same calculator on the same
molecule with different settings in the same few milliseconds, the other run's "finished" can be
mistaken for this one's and the outcome reported as a failure. The result of the AI's own run is
still recorded normally, and a later read finds it; nothing is lost, only mis-described.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Protocol

from PySide6.QtCore import QObject, Qt, QThread, Signal

from openchem.app.session import SessionManager
from openchem.chem.quantum_run_request import (
    BOND_DISSOCIATION,
    PROTON_AFFINITY,
    TAUTOMER_DISTRIBUTION,
    TWO_PARTNERS_MESSAGE,
    PreparedBondDissociation,
    PreparedProtonAffinity,
    PreparedTautomers,
    RunChoice,
    RunRefusal,
    led_cost_of_smiles,
    prepare_bond_dissociation,
    prepare_proton_affinity,
    prepare_tautomers,
)
from openchem.domain import calculator_search
from openchem.domain import result_status as rs
from openchem.domain.calculation_bridge import (
    CalculatorCard,
    GoalCard,
    Problem,
    ProblemCode,
    Requirement,
    Route,
    ServicePreview,
    build_card,
    goal_cards,
    route_of,
    validate_parameters,
)
from openchem.domain.calculator import DRAWING, GEOMETRY, CalculationRequest
from openchem.domain.calculator_goals import GOALS
from openchem.domain.execution_plan import build_execution_plan
from openchem.domain.execution_policy import AiRun, ResourceClass, decide, policy_of
from openchem.domain.refusal_kinds import REFUSAL_KEY, REFUSAL_KIND_KEY, refusal_kind_of_result
from openchem.domain.result_store import StoredResult
from openchem.domain.run_lifecycle import (
    MAX_FINISHED_RUNS,
    Preparation,
    PrepareResult,
    RunLedger,
    RunOutcome,
    RunState,
)
from openchem.domain.score_definition import MAX_DEFINITIONS
from openchem.domain.score_proposal import (
    ProposalBook,
    ProposalOutcome,
    ProposalProblem,
    ProposalRefusal,
    ProposalState,
    Registered,
    ScoreProposal,
    check_request,
)
from openchem.domain.score_value import evaluate_score
from openchem.domain.quantum_dispatch import RUNS_ON_DRAWING, STARTABLE, calc_type_of
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus
from openchem.domain.quantum_run_snapshot import classify_runs
from openchem.domain.turn_snapshot import DEFAULT_READ_LIMIT, ResultsView, TurnContext, build_turn_context, read_results
from openchem.domain.common import CacheState
from openchem.events.events import CalculationFinished, QuantumChemistryJobStateChanged, QuantumChemistryRunCompleted, ResultRecorded
from openchem.services.container import ServiceContainer
from openchem.services.result_cache import parameters_key

logger = logging.getLogger("openchem.app")

#: How long `run` waits for a calculation, by the policy's measured cost class. Generous against
#: the measurements (instant is under a second, short under ten) because the GUI thread has to
#: pick the request up and the pool has to start it.
WAIT_SECONDS: dict[ResourceClass, float] = {
    ResourceClass.INSTANT: 15.0,
    ResourceClass.SHORT: 60.0,
    ResourceClass.LONG: 120.0,
}


class QuantumStarter(Protocol):
    """What the window gives the host so that a person's Approve can start an ORCA job: the Quantum Chemistry panel's own entry point.

    **THE HOST DECIDES NOTHING ABOUT AN ORCA JOB.** It hands the choice the card showed to the panel, which applies the Run button's rules to the molecule as it is now and keeps the bookkeeping its result
    handlers read (`QuantumChemistryPanel.start_assistant_run`). GUI thread.
    """

    def start_assistant_run(self, molecule_uuid: str, choice: RunChoice, input_fingerprint: str) -> str:
        """"" when the job was handed to the service, otherwise the sentence that says why nothing started."""
        ...


class _TurnMolecule:
    """The three attributes `build_execution_plan` reads, from a turn rather than a live model."""

    def __init__(self, turn: TurnContext) -> None:
        self.uuid = turn.molecule_uuid
        self.display_name = turn.display_name
        self.molblock = "x" if turn.has_structure else ""


class CalculationHost(QObject):
    """See the module docstring. Construct on the GUI thread and keep a reference to it."""

    #: A run reached a final state (including one voided before it started). For the panel.
    finished = Signal(object)

    #: A score the assistant proposed was decided: saved, cancelled, voided or refused when it was saved (a `ProposalOutcome`). For the panel.
    score_finished = Signal(object)

    _dispatch_requested = Signal(str)

    def __init__(self, services: ServiceContainer, session: SessionManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._services = services
        self._session = session
        self._ledger = RunLedger()
        self._lock = threading.RLock()
        #: Runs already announced as finished, so a repeated approve or cancel cannot announce one twice.
        self._settled: OrderedDict[str, None] = OrderedDict()
        #: run id -> the future its waiters share. Created by whoever first asks for the run.
        self._futures: dict[str, Future] = {}
        #: (calculator id, molecule uuid) -> the runs waiting on that completion, oldest first. A list
        #: because two previews of one calculator on one molecule can be approved back to back.
        self._inflight: dict[tuple[str, str], list[str]] = {}
        #: run id -> the result recorded for it, held until the matching "finished" arrives.
        self._recorded: dict[str, StoredResult] = {}
        #: The scores the assistant proposed that wait for a person. Nothing in it is stored: only `approve_score` makes a score, on the GUI thread, for a button.
        self._proposals = ProposalBook()
        #: The panel that starts an approved ORCA job; None until the window gives one (a headless run, a test), when those calculators stay "run it from its panel".
        self._quantum_starter: QuantumStarter | None = None
        #: molecule uuid -> (run id, conformer fingerprint, calculation type) of the approved ORCA job now running for it. One job per molecule, as the service allows.
        self._quantum_inflight: dict[str, tuple[str, str, str]] = {}
        #: While the starter is called: the molecule it is starting, and what the service said (a failed state is published from inside the call, before it returns).
        self._starting: str = ""
        self._start_failure: str = ""
        self._dispatch_requested.connect(self._on_dispatch_requested, Qt.ConnectionType.QueuedConnection)
        services.event_bus.subscribe(ResultRecorded, self._on_result_recorded)
        services.event_bus.subscribe(CalculationFinished, self._on_calculation_finished)
        services.event_bus.subscribe(QuantumChemistryJobStateChanged, self._on_quantum_state)
        services.event_bus.subscribe(QuantumChemistryRunCompleted, self._on_quantum_run_completed)

    def set_quantum_starter(self, starter: QuantumStarter | None) -> None:
        """Give the host the means to start an approved ORCA job. Until it has one, those calculators are described and not startable."""
        self._quantum_starter = starter

    def _startable(self) -> frozenset[str]:
        """The service-run calculators a person's Approve can start from here: all of `STARTABLE` once there is a panel to start them, none before."""
        return frozenset(STARTABLE) if self._quantum_starter is not None else frozenset()

    # --- the turn -------------------------------------------------------------------------------

    def _require_gui_thread(self, what: str) -> None:
        if QThread.currentThread() is not self.thread():
            raise RuntimeError(f"{what} must be called on the GUI thread")

    def begin_turn(self) -> TurnContext | None:
        """Freeze the selected molecule and everything stored about it. GUI thread, at Send.

        `None` when nothing is selected. A molecule with nothing drawn yet still gets a turn (so the
        assistant can say so); `has_structure` is False and no calculation can be prepared for it.
        """
        self._require_gui_thread("begin_turn")
        project = self._session.project
        self._void_stale_proposals(project.uuid if project is not None else "")
        molecule_uuid = self._session.selected_molecule_uuid
        if project is None or molecule_uuid is None:
            return None
        model = project.find_molecule(molecule_uuid)
        if model is None:
            return None
        engine = self._services.chemistry_engine
        has_structure = bool(model.molblock)
        heavy_atoms = 0
        if has_structure:
            try:
                heavy_atoms = engine.heavy_atom_count(model)
            except Exception:  # noqa: BLE001 - an unreadable drawing is "no structure", not a crash
                logger.debug("No readable structure for %s", model.uuid, exc_info=True)
                has_structure = False
        fingerprints: dict[str, str] = {}
        records: list[StoredResult] = []
        fresh: list[StoredResult] = []
        runs: tuple = ()
        results = self._services.result_store_service
        if results is not None and has_structure:
            try:
                fingerprints = results.fingerprints_for(model)
            except Exception:  # noqa: BLE001 - nothing can be vouched for without a fingerprint
                logger.debug("No fingerprints for %s", model.uuid, exc_info=True)
            records = results.store.all_results(model.uuid)
            fresh = results.store.fresh_results(model.uuid, fingerprints)
        if results is not None:
            # The ORCA runs are frozen with the results, and classified against the same fingerprints: a run on an earlier structure is historical. They are read even when nothing is drawn, since a run
            # outlives the structure it was made for and a person may ask what happened to it.
            runs = classify_runs(results.qc_runs.runs_for(model.uuid), fingerprints)
        return build_turn_context(
            project_uuid=project.uuid,
            molecule_uuid=model.uuid,
            display_name=model.display_name,
            canonical_smiles=model.canonical_smiles or "",
            heavy_atoms=heavy_atoms,
            has_structure=has_structure,
            conformer_count=len(model.conformers),
            fingerprints=fingerprints,
            records=records,
            fresh=fresh,
            scores=self._score_definitions(project),
            runs=runs,
        )

    def _score_definitions(self, project) -> tuple:
        """The project's score definitions, frozen into the turn with its results. None when the score service is not holding THIS project's."""
        service = getattr(self._services, "score_service", None)
        if service is None or service.project is None or service.project.uuid != project.uuid:
            return ()
        return tuple(service.store.definitions())

    # --- a score the assistant proposes, and a person approves --------------------------------------------

    def propose_score(self, turn: TurnContext, request: Any) -> Registered | ProposalRefusal:
        """Check a model's request for a score against every rule a typed definition meets, and hold it for a person. **Any thread. Stores nothing.**

        The preview in the proposal is what it gives for the turn's molecule from the turn's FROZEN results, so what the card says and what the model was told are one number.
        """
        service = getattr(self._services, "score_service", None)
        if service is None or service.project is None or service.project.uuid != turn.project_uuid:
            return ProposalRefusal(ProposalProblem.NO_PROJECT, "the open project cannot hold a score right now (none is open, or it is not the one this conversation began in)")
        if len(turn.scores) >= MAX_DEFINITIONS:
            return ProposalRefusal(ProposalProblem.PROJECT_FULL, f"the project already holds {len(turn.scores)} scores, the most one may")
        checked = check_request(request, service.reserved_names())
        if isinstance(checked, ProposalRefusal):
            return checked
        preview = evaluate_score(checked, turn.entries)
        proposal = ScoreProposal(ProposalBook.new_id(), turn.project_uuid, turn.molecule_uuid, turn.display_name, checked, preview)
        return self._proposals.register(proposal)

    def pending_scores(self) -> tuple[ScoreProposal, ...]:
        """The proposals waiting for a person, oldest first."""
        return self._proposals.pending()

    def approve_score(self, proposal_id: str) -> ProposalOutcome | None:
        """A person approved a proposed score: make it, through the same service the Derived Scores window uses. **GUI thread**, for a button.

        The score is exactly the definition that was proposed and shown (the model's request is not read again). It is refused, and says why, if the project is no longer the one it was
        proposed in or the rules now refuse it (a label that has since become too close to a name, a project that has filled). Returns what became of it; asking again about one that is
        decided returns the same outcome and does nothing.
        """
        self._require_gui_thread("approve_score")
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return self._proposals.outcome_of(proposal_id)
        service = getattr(self._services, "score_service", None)
        project = self._session.project
        if service is None or service.project is None or project is None or not (service.project.uuid == project.uuid == proposal.project_uuid):
            return self._settle_score(proposal_id, ProposalState.VOID, "the project is not the one this score was proposed in, so nothing was saved")
        definition = proposal.definition
        try:
            made = service.create(
                label=definition.label, formula=definition.formula, result_unit=definition.result_unit, inputs=list(definition.inputs),
                constants=list(definition.constants), owner=definition.owner, note=definition.note,
            )
        except ValueError as exc:
            # A rule that now refuses it (`FormulaError`, with the rule's own message) or a project with no room: either way nothing was saved, and a person is told why.
            return self._settle_score(proposal_id, ProposalState.FAILED, f"it could not be saved: {exc}")
        return self._settle_score(proposal_id, ProposalState.SAVED, f"saved as {made.score_id}", made.score_id)

    def cancel_score(self, proposal_id: str) -> bool:
        """A person declined a proposed score. Nothing is saved. **GUI thread.**"""
        self._require_gui_thread("cancel_score")
        return self._settle_score(proposal_id, ProposalState.CANCELLED, "cancelled by the user; nothing was saved") is not None

    def score_state_of(self, proposal_id: str) -> ProposalState | None:
        return self._proposals.state_of(proposal_id)

    def score_outcome_of(self, proposal_id: str) -> ProposalOutcome | None:
        return self._proposals.outcome_of(proposal_id)

    def _settle_score(self, proposal_id: str, state: ProposalState, message: str, score_id: str = "") -> ProposalOutcome | None:
        outcome = self._proposals.settle(proposal_id, state, message, score_id)
        if outcome is not None:
            self.score_finished.emit(outcome)
        return outcome

    def _void_stale_proposals(self, project_uuid: str) -> None:
        """At Send: a proposal made in another project (or when none is open) can never be saved, so it is decided now and its card goes."""
        for outcome in self._proposals.void_outside(project_uuid, "the project changed, so nothing was saved"):
            self.score_finished.emit(outcome)

    # --- discovery and reading (any thread) ---------------------------------------------------------

    def catalog(self, query: str = "", limit: int = 20) -> tuple[CalculatorCard, ...]:
        found = calculator_search.search(self._services.calculator_registry.definitions(), query, limit)
        startable = self._startable()
        return tuple(build_card(definition, startable) for definition in found)

    def describe(self, calculator_id: str) -> CalculatorCard | None:
        definition = self._services.calculator_registry.get(calculator_id)
        return build_card(definition, self._startable()) if definition is not None else None

    def goals(self) -> tuple[GoalCard, ...]:
        """The wizard's questions and the calculators that answer them, each entry's route read live.

        Read-only knowledge: nothing here starts a calculation, and `PropertyPanel.run_goal` is not
        reachable from it (it does not consult the execution policy).
        """
        return goal_cards(GOALS, self.describe)

    def read_results(
        self,
        turn: TurnContext,
        calculator_ids: list[str] | None = None,
        *,
        include_not_current: bool = False,
        limit: int = DEFAULT_READ_LIMIT,
    ) -> ResultsView:
        return read_results(turn, calculator_ids, include_not_current=include_not_current, limit=limit)

    # --- preparing (any thread) -----------------------------------------------------------------

    def _smiles_ok(self, smiles: str) -> bool:
        try:
            self._services.chemistry_engine.mol_from_smiles(smiles)
        except Exception:  # noqa: BLE001 - any failure to read it is "not a structure"
            return False
        return True

    def prepare(self, turn: TurnContext, calculator_id: str, parameters: dict[str, Any] | None = None) -> PrepareResult:
        """Validate a request against the definition and the turn, decide who may start it, record it.

        Starts nothing. An `AUTO` preparation is dispatched by `run`; one needing a person waits in
        the ledger for `approve`. A request that cannot go ahead returns every reason at once.
        """
        registry = self._services.calculator_registry
        definition = registry.get(calculator_id)
        if definition is None:
            return PrepareResult(problems=(Problem(
                ProblemCode.UNKNOWN_CALCULATOR,
                f"there is no calculator {calculator_id!r}; use the catalog to find one",
            ),))
        route, why = route_of(definition, self._startable())
        if route is Route.BLOCKED:
            return PrepareResult(problems=(Problem(ProblemCode.NOT_FOR_MOLECULES, why),))
        if calc_type_of(calculator_id) is not None and self._quantum_starter is not None:
            return self._prepare_quantum(definition, turn, parameters)
        if route is Route.PREVIEW_ONLY:
            return self._service_preview_result(definition, turn, parameters, why)
        if not turn.has_structure:
            return PrepareResult(problems=(Problem(
                ProblemCode.NO_STRUCTURE, f"{turn.display_name} has no drawn structure yet, so there is nothing to calculate"
            ),))
        validation = validate_parameters(definition, parameters, smiles_ok=self._smiles_ok)
        if not validation.ok:
            return PrepareResult(problems=validation.problems)
        calculation_input = definition.calculation_input
        fingerprint = turn.fingerprints.get(calculation_input)
        if not fingerprint:
            # GEOMETRY means "prefer real 3D coordinates", and falls back to the drawing, so a molecule
            # with no conformer still has a fingerprint: the calculators that need one refuse on their
            # own, with their own words, and that refusal is what a person would get too.
            return PrepareResult(problems=(Problem(
                ProblemCode.NO_STRUCTURE, f"{turn.display_name} has no {calculation_input} to fingerprint"
            ),))
        plan = build_execution_plan(
            molecules=[_TurnMolecule(turn)],
            calculator_ids=[calculator_id],
            chosen_parameters={calculator_id: dict(validation.parameters)},
            definition_of=registry.get,
        )
        if plan.is_empty:
            reasons = "; ".join(job.reason for job in plan.excluded) or "it cannot be run"
            return PrepareResult(problems=(Problem(ProblemCode.SERVICE_RUN, reasons),))
        policy = policy_of(definition)
        decision = decide(policy, validation.parameters, heavy_atoms=turn.heavy_atoms)
        route = Route.AUTO if decision.ai_run is AiRun.AUTO else Route.NEEDS_APPROVAL
        parameters_now = plan.parameters_for(calculator_id)
        preparation = Preparation(
            run_id=plan.run_id,
            turn_id=turn.turn_id,
            calculator_id=calculator_id,
            display_name=definition.display_name,
            molecule_uuid=turn.molecule_uuid,
            molecule_name=turn.display_name,
            project_uuid=turn.project_uuid,
            calculation_input=calculation_input,
            input_fingerprint=fingerprint,
            parameters=parameters_now,
            route=route,
            decision=decision,
            preview=_preview_lines(definition.display_name, turn, parameters_now, policy, decision.reason),
            adjustments=validation.adjustments,
            resource=policy.resource.value,
            external_tools=tuple(sorted(policy.external_tools)),
        )
        self._ledger.register(preparation)
        return PrepareResult(preparation=preparation)

    def _prepare_quantum(self, definition, turn: TurnContext, parameters) -> PrepareResult:
        """An ORCA job a person can approve: validated like any request, checked against what this computer has, and held as a preview. Starts nothing.

        **THE CARD IS DRAWN FROM THE TURN, THE RULES RUN AT APPROVE.** This runs on a worker, where the live molecule is not the thread's to read, so what is checked here is what the frozen turn and the
        registry can say (a structure, a conformer, the ORCA program, the settings, the cost of an interaction breakdown). The rules that need the molecule itself are the Run button's, and the panel
        applies them to the molecule as it is when Approve is pressed (`QuantumStarter`): a structure edited in between is `INVALIDATED`, never run.
        """
        if not turn.has_structure:
            return PrepareResult(problems=(Problem(
                ProblemCode.NO_STRUCTURE, f"{turn.display_name} has no drawn structure yet, so there is nothing to calculate"
            ),))
        validation = validate_parameters(definition, parameters, smiles_ok=self._smiles_ok)
        if not validation.ok:
            return PrepareResult(problems=validation.problems)
        missing = [r for r in self._service_requirements(definition, turn) if not r.ok]
        if missing:
            return PrepareResult(problems=tuple(
                Problem(ProblemCode.NOT_READY, f"{r.what} is missing" + (f": {r.how_to_fix}" if r.how_to_fix else "")) for r in missing
            ))
        # A fixed protocol and the tautomer distribution run on the drawing, every structure embedded fresh; the others on the conformer every calculation uses.
        on_drawing = definition.calculator_id in RUNS_ON_DRAWING
        calculation_input = DRAWING if on_drawing else GEOMETRY
        fingerprint = turn.fingerprints.get(calculation_input)
        if not fingerprint:
            return PrepareResult(problems=(Problem(ProblemCode.NO_STRUCTURE, f"{turn.display_name} has no {calculation_input} to fingerprint"),))
        calc_type = calc_type_of(definition.calculator_id)
        extra: list[str] = []
        if on_drawing:
            protocol = _PROTOCOLS[calc_type][0](turn.canonical_smiles)
            if isinstance(protocol, RunRefusal):
                return PrepareResult(problems=(Problem(ProblemCode.INVALID_STRUCTURE, protocol.message),))
            extra.append("What it would cost (approving accepts it): " + _protocol_cost(protocol))
        if calc_type == "led":
            refusal, cost = led_cost_of_smiles(turn.canonical_smiles)
            if refusal:
                return PrepareResult(problems=(Problem(ProblemCode.INVALID_STRUCTURE, refusal),))
            extra.append("What it would cost (approving accepts it): " + cost.replace("\n\n", " "))
        policy = policy_of(definition)
        decision = decide(policy, validation.parameters, heavy_atoms=turn.heavy_atoms)
        lines = list(_preview_lines(definition.display_name, turn, validation.parameters, policy, decision.reason))
        # Before the closing sentence: what the job will do, in the panel's terms, and what the person can still do about it.
        where = (
            "It runs on the drawing (every structure is embedded fresh), by the same rules as the Quantum Chemistry panel's " + (_PROTOCOLS[calc_type][1] if on_drawing else "") + " button"
            if on_drawing else "It runs on the conformer every calculation uses, by the same rules as the Quantum Chemistry panel's Run button"
        )
        lines[-1:] = [
            f"{where}, and shows in that panel while it runs, where it can be cancelled.",
            *extra,
            lines[-1],
        ]
        preparation = Preparation(
            run_id=uuid.uuid4().hex,
            turn_id=turn.turn_id,
            calculator_id=definition.calculator_id,
            display_name=definition.display_name,
            molecule_uuid=turn.molecule_uuid,
            molecule_name=turn.display_name,
            project_uuid=turn.project_uuid,
            calculation_input=calculation_input,
            input_fingerprint=fingerprint,
            parameters=dict(validation.parameters),
            route=Route.NEEDS_APPROVAL,
            decision=decision,
            preview=tuple(lines),
            adjustments=validation.adjustments,
            resource=policy.resource.value,
            external_tools=tuple(sorted(policy.external_tools)),
            drawing_fingerprint="" if on_drawing else turn.fingerprints.get(DRAWING, ""),
        )
        self._ledger.register(preparation)
        return PrepareResult(preparation=preparation)

    def _service_preview_result(self, definition, turn: TurnContext, parameters, why: str) -> PrepareResult:
        """What a service-run calculator would take, with nothing prepared and nothing started.

        The settings are validated exactly like a registry calculator's, so a model that names a method
        the service does not offer is told so. The requirements are read from the live application: the
        executable that is configured NOW, the conformer the molecule has NOW. See `ServicePreview`.
        """
        if not turn.has_structure:
            return PrepareResult(problems=(Problem(
                ProblemCode.NO_STRUCTURE, f"{turn.display_name} has no drawn structure yet, so there is nothing to calculate"
            ),))
        validation = validate_parameters(definition, parameters, smiles_ok=self._smiles_ok)
        if not validation.ok:
            return PrepareResult(problems=validation.problems)
        policy = policy_of(definition)
        preview = ServicePreview(
            calculator_id=definition.calculator_id,
            display_name=definition.display_name,
            panel_id=definition.execution.panel_id,
            panel_name=definition.execution.panel_name,
            summary=(
                (definition.description or "").strip()[:500],
                policy.why_confirm,
                "Settings it would run with: "
                + (", ".join(f"{k}={v!r}" for k, v in validation.parameters.items()) or "none") + ".",
            ),
            requirements=self._service_requirements(definition, turn),
            parameters=dict(validation.parameters),
            external_tools=tuple(sorted(policy.external_tools)),
        )
        return PrepareResult(problems=(Problem(ProblemCode.SERVICE_RUN, why),), service_preview=preview)

    def _service_requirements(self, definition, turn: TurnContext) -> tuple[Requirement, ...]:
        """What this service needs, checked against the application as it is now. Starts nothing.

        A requirement that is met carries no hint (see `Requirement`): the hint is only for what is missing.
        """

        def need(what: str, ok: bool, how_to_fix: str) -> Requirement:
            return Requirement(what, ok, "" if ok else how_to_fix)

        service = definition.execution.service_name
        requirements = [need(f"a drawn structure for {turn.display_name}", turn.has_structure, "draw or import one")]
        if definition.calculator_id not in _NO_CONFORMER_NEEDED:
            requirements.append(need(
                f"a 3D conformer for {turn.display_name}", turn.conformer_count > 0,
                "generate conformers first, from the Conformers tools",
            ))
        if service == "quantum_chemistry_service":
            requirements.append(need(
                "the ORCA executable", self._services.quantum_chemistry_service.orca_executable() is not None,
                "set its path in Tools > External Tools",
            ))
        elif service == "docking_service":
            project = self._session.project
            requirements.append(need(
                "a receptor macromolecule in the project", bool(project and project.macromolecules),
                "import one with Import Macromolecule",
            ))
            requirements.append(need(
                "AutoDock Vina", self._services.docking_service.is_available(),
                "set its path in Tools > External Tools",
            ))
        return tuple(requirements)

    # --- running (a worker thread) ---------------------------------------------------------------

    def run(self, turn: TurnContext, run_id: str, *, timeout: float | None = None) -> RunOutcome:
        """Start a prepared automatic run and wait for it, or report why it was not started.

        Never raises for anything a model could cause. Idempotent: a run already finished returns
        its recorded outcome; one still going is waited for, not started again.
        """
        if QThread.currentThread() is self.thread():
            raise RuntimeError("run waits for work the GUI thread must do; call it from a worker thread")
        preparation = self._ledger.get(run_id)
        if preparation is None:
            return _rejected(run_id, ProblemCode.NO_SUCH_RUN, "no run with that id was prepared; call prepare first")
        if preparation.turn_id != turn.turn_id:
            return _rejected(
                run_id, ProblemCode.WRONG_TURN, "that run was prepared in an earlier turn and cannot be started from this one",
                preparation.calculator_id,
            )
        state = self._ledger.state_of(run_id)
        if state is RunState.PREVIEWED:
            return RunOutcome(
                run_id, preparation.calculator_id, RunState.PREVIEWED,
                "this needs a person to approve it first; a preview is on screen. It has not started, and "
                "asking again will not start it.",
            )
        if state in (RunState.COMPLETED, RunState.REFUSED, RunState.FAILED, RunState.CANCELLED, RunState.INVALIDATED):
            return self._ledger.outcome_of(run_id) or _rejected(run_id, ProblemCode.NO_SUCH_RUN, "the run was forgotten")
        with self._lock:
            future = self._futures.get(run_id)
            first = future is None
            if first:
                future = self._futures[run_id] = Future()
        # The run may have finished between the state check above and the future existing, in which
        # case nothing will ever resolve this future: re-read the state now that one is registered.
        state = self._ledger.state_of(run_id)
        if state in (RunState.COMPLETED, RunState.REFUSED, RunState.FAILED, RunState.CANCELLED, RunState.INVALIDATED):
            return self._ledger.outcome_of(run_id) or _rejected(run_id, ProblemCode.NO_SUCH_RUN, "the run was forgotten")
        if first and state is RunState.PREPARED:
            self._dispatch_requested.emit(run_id)
        wait = timeout if timeout is not None else WAIT_SECONDS[ResourceClass(preparation.resource or "long")]
        try:
            return future.result(timeout=wait)
        except FutureTimeout:
            return RunOutcome(
                run_id, preparation.calculator_id, RunState.TIMED_OUT,
                "it is still running; its result will appear in Results when it finishes. Do not ask again: "
                "asking again waits for the same run.",
            )

    # --- approval (the GUI thread, for a person's button) -----------------------------------------

    def pending(self) -> tuple[Preparation, ...]:
        return self._ledger.pending()

    def approve(self, run_id: str) -> RunState | None:
        """A person approved a preview. Starts it if it is still valid; returns the run's state."""
        self._require_gui_thread("approve")
        if not self._ledger.approve(run_id):
            # `approve` itself withdraws a preview that sat too long; that is a final state to announce.
            # `_settle` announces a run once, so asking again about a finished one says nothing new.
            self._settle(run_id, self._ledger.outcome_of(run_id))
            return self._ledger.state_of(run_id)
        self._start(run_id)
        return self._ledger.state_of(run_id)

    def cancel(self, run_id: str) -> bool:
        self._require_gui_thread("cancel")
        if not self._ledger.cancel(run_id):
            return False
        outcome = self._ledger.outcome_of(run_id)
        if outcome is not None:
            self._settle(run_id, outcome)
        return True

    def state_of(self, run_id: str) -> RunState | None:
        return self._ledger.state_of(run_id)

    def outcome_of(self, run_id: str) -> RunOutcome | None:
        return self._ledger.outcome_of(run_id)

    # --- starting a run (the GUI thread) ------------------------------------------------------------

    def _on_dispatch_requested(self, run_id: str) -> None:
        self._start(run_id)

    def _model_for(self, preparation: Preparation):
        project = self._session.project
        if project is None or project.uuid != preparation.project_uuid:
            return None
        return project.find_molecule(preparation.molecule_uuid)

    def _why_void(self, preparation: Preparation, model) -> str:
        """Why a prepared run can no longer start, or "" when it still describes the live structure."""
        if model is None:
            return "the molecule is no longer in the open project, so the plan was withdrawn"
        results = self._services.result_store_service
        if results is None:
            return ""
        try:
            now = results.fingerprints_for(model)
        except Exception:  # noqa: BLE001 - an input that cannot be fingerprinted cannot be vouched for
            now = {}
        if now.get(preparation.calculation_input) != preparation.input_fingerprint:
            return "the structure changed after this was prepared, so the plan was withdrawn; prepare it again"
        if preparation.drawing_fingerprint and now.get(DRAWING) != preparation.drawing_fingerprint:
            return "the structure was edited after this was prepared, so the plan was withdrawn; prepare it again"
        return ""

    def _start(self, run_id: str) -> None:
        """Re-check the plan against the live molecule, claim the run once, and hand it to the service."""
        preparation = self._ledger.get(run_id)
        if preparation is None or self._ledger.state_of(run_id) not in (RunState.PREPARED, RunState.APPROVED):
            return
        model = self._model_for(preparation)
        reason = self._why_void(preparation, model)
        if reason:
            if self._ledger.invalidate(run_id, reason):
                self._settle(run_id, self._ledger.outcome_of(run_id))
            return
        if not self._ledger.claim_dispatch(run_id):
            return
        if calc_type_of(preparation.calculator_id) is not None:
            self._start_quantum(preparation)
            return
        key = (preparation.calculator_id, preparation.molecule_uuid)
        with self._lock:
            self._inflight.setdefault(key, []).append(run_id)
        try:
            self._services.descriptor_service.run_calculator(
                model,
                CalculationRequest(
                    calculator_id=preparation.calculator_id,
                    molecule_uuid=preparation.molecule_uuid,
                    parameters=dict(preparation.parameters),
                ),
            )
        except Exception as error:  # noqa: BLE001 - a service that cannot start the work is a failed run
            logger.exception("Could not start %s", preparation.calculator_id)
            with self._lock:
                self._forget_inflight(key, run_id)
            self._finish(run_id, RunState.FAILED, f"it could not be started: {error}")

    def _start_quantum(self, preparation: Preparation) -> None:
        """Hand an approved ORCA job to the Quantum Chemistry panel, which applies the Run button's rules to the molecule as it is now. The run is already claimed (RUNNING).

        A refusal (the panel's sentence) or a failure the service publishes from inside the call ends the run here. Otherwise it ends when ORCA's run record arrives (`_on_quantum_run_completed`),
        which can be minutes or hours later: nothing waits for it, and the person is told with the next message.
        """
        run_id, molecule_uuid = preparation.run_id, preparation.molecule_uuid
        starter = self._quantum_starter
        if starter is None:
            self._finish(run_id, RunState.FAILED, "the Quantum Chemistry panel is not available to start it")
            return
        parameters = preparation.parameters
        choice = RunChoice(
            calc_type=calc_type_of(preparation.calculator_id) or "",
            method_basis=str(parameters.get("method_basis", "")),
            charge=int(parameters.get("charge", 0)),
            multiplicity=int(parameters.get("multiplicity", 1)),
        )
        calc_type = choice.calc_type
        with self._lock:
            self._quantum_inflight[molecule_uuid] = (run_id, preparation.input_fingerprint, calc_type)
            self._starting, self._start_failure = molecule_uuid, ""
        try:
            refusal = starter.start_assistant_run(molecule_uuid, choice, preparation.input_fingerprint)
        except Exception as error:  # noqa: BLE001 - a panel that cannot start the work is a failed run
            logger.exception("Could not start %s", preparation.calculator_id)
            refusal = f"it could not be started: {error}"
        finally:
            with self._lock:
                failure, self._starting, self._start_failure = self._start_failure, "", ""
        if refusal or failure:
            with self._lock:
                self._quantum_inflight.pop(molecule_uuid, None)
            # A refusal is the panel's rule speaking (nothing was queued); a failure is the service's, said from inside the call.
            self._finish(run_id, RunState.REFUSED if refusal else RunState.FAILED, refusal or failure)

    # --- completion (the GUI thread, from the bus) ------------------------------------------------------

    def _on_quantum_state(self, event: QuantumChemistryJobStateChanged) -> None:
        """A job's state, read for one thing only: a failure said while the job was being handed over (no executable, a second job for the molecule), which has no run record to say it."""
        if event.state is CacheState.FAILED and event.molecule_uuid == self._starting:
            self._start_failure = event.message or "the job could not be started"

    def _on_quantum_run_completed(self, event: QuantumChemistryRunCompleted) -> None:
        """An ORCA run reached its final state: if it is the one a person approved for the assistant, the approval's run ends with it."""
        run = event.run
        with self._lock:
            held = self._quantum_inflight.get(run.molecule_uuid)
            if held is None or held[2] != run.calc_type or held[1] != run.input_fingerprint:
                return
            self._quantum_inflight.pop(run.molecule_uuid)
        state, message = _quantum_outcome(run)
        self._finish(held[0], state, message)

    def _forget_inflight(self, key: tuple[str, str], run_id: str) -> None:
        """Drop one run from the in-flight list (the caller holds the lock)."""
        waiting = self._inflight.get(key, [])
        if run_id in waiting:
            waiting.remove(run_id)
        if not waiting:
            self._inflight.pop(key, None)

    def _on_result_recorded(self, event: ResultRecorded) -> None:
        identity = event.stored.identity
        with self._lock:
            for run_id in self._inflight.get((identity.producer, identity.molecule_uuid), ()):
                preparation = self._ledger.get(run_id)
                # The same calculator run with other settings, by somebody else, is not this run's.
                if (
                    preparation is not None
                    and run_id not in self._recorded
                    and parameters_key(dict(preparation.parameters)) == identity.parameters_key
                ):
                    self._recorded[run_id] = event.stored
                    return

    def _on_calculation_finished(self, event: CalculationFinished) -> None:
        key = (event.calculator_id, event.molecule_uuid)
        with self._lock:
            waiting = self._inflight.get(key, [])
            # The oldest run that has its result recorded; failing that, the oldest (see the module
            # docstring's known limit).
            run_id = next((r for r in waiting if r in self._recorded), waiting[0] if waiting else None)
            if run_id is None:
                return
            self._forget_inflight(key, run_id)
            stored = self._recorded.pop(run_id, None)
        if stored is None:
            self._finish(run_id, RunState.FAILED, "it finished without recording a result")
            return
        status = rs.status_of(stored.result)
        if status in (rs.READY, rs.STALE):
            state, message = RunState.COMPLETED, "completed"
        elif status == rs.FAILED:
            state, message = RunState.FAILED, _failure_text(stored)
        else:
            state, message = RunState.REFUSED, _failure_text(stored)
        self._finish(run_id, state, message, status=status, stored=stored)

    def _finish(self, run_id: str, state: RunState, message: str, *, status: str = "", stored: StoredResult | None = None) -> None:
        preparation = self._ledger.get(run_id)
        if preparation is None:
            return
        outcome = RunOutcome(run_id, preparation.calculator_id, state, message, status=status, stored=stored)
        if self._ledger.finish(outcome):
            self._settle(run_id, outcome)

    def _settle(self, run_id: str, outcome: RunOutcome | None) -> None:
        """Release everyone waiting on a run and tell the panel it reached a final state."""
        if outcome is None:
            return
        with self._lock:
            if run_id in self._settled:
                return
            self._settled[run_id] = None
            while len(self._settled) > 2 * MAX_FINISHED_RUNS:
                self._settled.popitem(last=False)
            future = self._futures.get(run_id)
        if future is not None and not future.done():
            future.set_result(outcome)
        self.finished.emit(outcome)


def _rejected(run_id: str, code: ProblemCode, message: str, calculator_id: str = "") -> RunOutcome:
    return RunOutcome(run_id, calculator_id, RunState.REJECTED, message, problems=(Problem(code, message),))


#: Startable calculators that need no stored conformer: a fixed protocol embeds every structure fresh from the drawing, and these others say so of themselves ("no 3D conformer needed"),
#: as does the Lewis HSAB score, which is read from the drawing.
_NO_CONFORMER_NEEDED = frozenset({"lewis_hsab", "orca.proton_affinity", "orca.bond_dissociation_enthalpy", "orca.tautomer_distribution"})


#: The calculators that run on the drawing, by calculation type: what prepares their card's cost from the structure, and the Quantum Chemistry panel's button whose rules they follow.
_PROTOCOLS = {
    PROTON_AFFINITY: (prepare_proton_affinity, "Proton affinity"),
    BOND_DISSOCIATION: (prepare_bond_dissociation, "Bond dissociation"),
    TAUTOMER_DISTRIBUTION: (prepare_tautomers, "Tautomers"),
}


def _protocol_cost(protocol: PreparedProtonAffinity | PreparedBondDissociation | PreparedTautomers) -> str:
    return protocol.card_text().replace("\n\n", " ")


def _quantum_outcome(run: QuantumChemistryRun) -> tuple[RunState, str]:
    """How an approved ORCA job ended, in the words the model is told: the application's own, naming the run record that holds the rest (`read_quantum_runs`).

    Numbers are never in it: they are in the run, read with the tool that gives a run's freshness and caveats.
    """
    where = f"It is stored as ORCA run {run.run_id}; read how it ended, its warnings and its outputs with read_quantum_runs."
    if run.status is RunStatus.COMPLETED:
        return RunState.COMPLETED, f"ORCA finished the job. {where}"
    if run.status is RunStatus.COMPLETED_WITH_WARNINGS:
        return RunState.COMPLETED, f"ORCA finished the job and reported {len(run.warnings)} warning(s). {where}"
    if run.status is RunStatus.CANCELLED:
        return RunState.CANCELLED, f"The job was cancelled before it finished (in the Quantum Chemistry panel). It has no numbers. {where}"
    return RunState.FAILED, f"ORCA did not produce a result. It has no numbers. {where}"


def _failure_text(stored: StoredResult) -> str:
    """The calculator's own words for why it declined or failed, with its code and kind."""
    result = stored.result
    text = getattr(result, "error_summary", None) or getattr(result, "error", None) or "it did not produce a result"
    parameters = getattr(getattr(result, "provenance", None), "parameters", None) or {}
    bits = []
    if isinstance(parameters.get(REFUSAL_KEY), str):
        bits.append(f"code {parameters[REFUSAL_KEY]}")
    kind = refusal_kind_of_result(result)
    if kind is not None:
        bits.append(f"kind {kind.value}")
    return f"{text} ({', '.join(bits)})" if bits else str(text)


def _preview_lines(name: str, turn: TurnContext, parameters, policy, reason: str) -> tuple[str, ...]:
    settings = ", ".join(f"{key}={value!r}" for key, value in parameters.items()) or "no settings"
    lines = [f"Run {name} on {turn.display_name} ({turn.heavy_atoms} heavy atoms).", f"Settings: {settings}."]
    if policy.external_tools:
        lines.append(f"It starts: {', '.join(sorted(policy.external_tools))}.")
    if reason:
        # The reasons are written as clauses; the card puts a sentence after each, so end this one properly.
        lines.append(f"Why a person approves it: {reason}{'' if reason.endswith(('.', '!', '?')) else '.'}")
    lines.append("The result will be recorded in the project like one you run yourself.")
    return tuple(lines)
