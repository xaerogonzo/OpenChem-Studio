"""The OpenChem side of the AiZynthFinder runner (`docs/SYNTHESIS_HELPER_DESIGN.md`, Stage 1 slice 3): the request, a run of the planner's own interpreter as a child process, and the parser that turns its one JSON document into a `RouteSet`. The child is `chem/aizynth_runner.py`; the types are `domain/synthesis_route.py`.

AIZYNTHFINDER IS NEVER IMPORTED INTO THIS PROCESS. It needs Python 3.10 to 3.12, `numpy<2` and onnxruntime, none of which OpenChem's interpreter shares, so the user's planner environment is run as a separate program and talks over one JSON document each way (the `pka_runner` pattern).

THE PROCESS CONTRACT, each point a failure with a typed `RouteSet` and never an exception:
* argument ARRAYS and no shell; the child is started with `-I` (isolated: no user site, no `PYTHON*` variables, no current directory on the path); the request goes on stdin, so no data is on a command line and a non-ASCII path in the configuration survives;
* the response is bounded (`max_output_bytes`) and the search is bounded by a wall clock (`wall_clock_seconds`, by default the time limit plus a margin for the 16 to 18 s start-up measured in the spike); either bound being passed kills the child;
* `cancel` (a `threading.Event`) kills the child. A killed Windows launcher takes the real interpreter with it (a job object; measured, `docs/SYNTHESIS_HELPER_DESIGN.md` 0b), and the tests check that no process is left;
* a child that exits without a document, with a document that is not JSON, with an unsupported schema, or with a non-zero code beside a `completed` document is `failed` with the child's last words (the tail of its stderr) in the reason;
* a named asset that is not there (the planner's Python, the policy model, the templates, the filter, the stock) is `unavailable` and says which;
* NOTHING RETRIES, and no limit is ever changed to make a search succeed.

WHICH OF THE PLANNER'S ROUTES BECOME ROUTES (decided here, because the planner returns more than solved routes: a strychnine search at 100 iterations returns the bare target and four one-step routes into a precursor that is not in stock). A route is kept only if it has at least one reaction and EVERY starting material carries an `in_stock` flag that is true, so "a route was returned" means what the benchmark's "solved" meant. The rest are counted and said (a limitation on the set), never silently dropped: a search that returned only unsolved routes is `no_route`. THE ORDER IS THE PLANNER'S, unchanged; re-ranking (the PaRoutes route score) is a decision for after protocol 2 of the quality benchmark, and `PlanRequest.all_routes` (every solved route instead of the default 5 to 25) is the other half of it.
"""
from __future__ import annotations

import collections
import json
import math
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from openchem.domain.synthesis_route import (
    STANDARD_LIMITATIONS,
    PlannerIdentity,
    Route,
    RouteMolecule,
    RouteSet,
    RouteStatus,
    RouteStep,
    SearchLimits,
    SearchStatistics,
    SearchTermination,
    TargetIdentity,
    forward_order,
    read_termination,
)

#: The request the runner reads (`chem/aizynth_runner.py` keeps its own copy; a test holds the two equal).
REQUEST_SCHEMA = "aizynth-request-1"
#: The response the runner writes.
RUN_SCHEMA = "aizynth-run-1"
#: The request that asks the runner to read a configuration file (`chem/aizynth_runner.py` keeps its own copy; a test holds them equal).
INSPECT_REQUEST_SCHEMA = "aizynth-inspect-request-1"
#: The runner's response to it (its own copy is held equal by a test).
INSPECT_SCHEMA = "aizynth-inspect-1"
#: The longest an inspection may take: it starts a Python and reads a file (0.2 s measured), so this bounds a hang, not a budget.
INSPECT_TIMEOUT_SECONDS = 60.0
#: The planner's name as every `PlannerIdentity` carries it.
PLANNER_NAME = "AiZynthFinder"
#: The runner script the planner's interpreter is handed as a path.
RUNNER_PATH = Path(__file__).resolve().parent / "aizynth_runner.py"
#: Seconds added to the planner's own time limit for the wall clock: the spike measured 16 to 18 s before any search (import, model and stock load) and the stock load alone peaked at 5.3 GB with the ZINC stock, so the margin is generous and is a bound on a hung child, not a budget.
WALL_CLOCK_MARGIN_SECONDS = 600.0
#: The most stdout read before the child is killed. A protocol 2 search that returned every solved route was 4.1 MB for 341 routes; this allows far more than any route set a person reads.
MAX_OUTPUT_BYTES = 256 * 1024 * 1024
#: How much of the end of stderr is kept to explain a crash.
STDERR_TAIL_BYTES = 4000
#: How often the parent looks at the cancel flag and the clock.
POLL_SECONDS = 0.1
#: The longest reason copied out of a child's words into a `RouteSet`.
REASON_CHARS = 400
#: Windows only: no console window for the child. `0` elsewhere, because `Popen` rejects the flag off Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True, kw_only=True)
class PlanRequest:
    """One search. `config` is the planner's configuration as a dictionary (policy models, template files, stock files); `stock`, `expansion` and `filter` select from it.

    All three limits are required: a limit left to the planner's default would be a limit nobody wrote down.
    """

    target_smiles: str
    config: dict = field(compare=False)
    stock: str
    expansion: str
    limits: SearchLimits
    filter: str | None = None
    #: Ask for every solved route instead of the planner's default of at least 5 and at most 25.
    all_routes: bool = False

    def __post_init__(self) -> None:
        for name in ("target_smiles", "stock", "expansion"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be blank")
        if not isinstance(self.config, dict) or not self.config:
            raise ValueError("config must be the planner's configuration dictionary")
        if self.filter is not None and not self.filter.strip():
            raise ValueError("filter must be a name or None")
        if self.limits.iteration_limit is None or self.limits.time_limit_seconds is None or self.limits.max_transforms is None:
            raise ValueError("the iteration limit, the time limit and max_transforms must all be set")

    def document(self) -> dict:
        return {
            "schema": REQUEST_SCHEMA,
            "target_smiles": self.target_smiles,
            "config": self.config,
            "stock": self.stock,
            "expansion": self.expansion,
            "filter": self.filter,
            "iteration_limit": self.limits.iteration_limit,
            "time_limit": self.limits.time_limit_seconds,
            "max_transforms": self.limits.max_transforms,
            "all_routes": self.all_routes,
        }

    def selection(self) -> tuple[tuple[str, str], ...]:
        """The names of what was selected, which is what an identity carries instead of paths."""
        return (("expansion", self.expansion), ("filter", self.filter or "none"), ("stock", self.stock))


@dataclass(frozen=True, kw_only=True)
class PlannerSetup:
    """Everything about HOW the planner is run that does not depend on the target: the user's planner Python, its configuration, what to select from it and the limits.

    Captured by the caller BEFORE a search starts and carried with it, so a change to the setting while a search runs cannot reroute
    it. Where it comes from (the External Tools tab) is a later slice; this is only its shape.
    """

    python: str
    config: dict = field(compare=False)
    stock: str
    expansion: str
    limits: SearchLimits
    filter: str | None = None
    all_routes: bool = False

    def request_for(self, target_smiles: str) -> PlanRequest:
        return PlanRequest(target_smiles=target_smiles, config=self.config, stock=self.stock, expansion=self.expansion, limits=self.limits, filter=self.filter, all_routes=self.all_routes)

    def selection(self) -> tuple[tuple[str, str], ...]:
        return (("expansion", self.expansion), ("filter", self.filter or "none"), ("stock", self.stock))


@dataclass(frozen=True)
class PlannerInspection:
    """What reading the planner's configuration found, or why it could not.

    `kind` is "" when `ok`; otherwise one of `python` (the interpreter is not there or will not start), `runner` (this installation's script is missing),
    `planner` (aizynthfinder is not installed in that environment), `yaml`, `config` (missing, unreadable or not a mapping), `timeout`, `failed` or `malformed`.
    """

    ok: bool
    kind: str = ""
    reason: str = ""
    #: The configuration with every policy, filter and stock path made absolute.
    config: dict = field(default_factory=dict, compare=False)
    #: The names the configuration offers, by section.
    keys: dict = field(default_factory=dict, compare=False)
    #: The versions installed in that environment (None = not installed).
    packages: dict = field(default_factory=dict, compare=False)

    @property
    def version(self) -> str | None:
        return self.packages.get("aizynthfinder")


def _bad(kind: str, reason: str, packages: dict | None = None) -> PlannerInspection:
    return PlannerInspection(ok=False, kind=kind, reason=_reason(reason), packages=packages or {})


def inspect_environment(python: str | os.PathLike[str], config_path: str | os.PathLike[str], *, runner: str | os.PathLike[str] = RUNNER_PATH, timeout: float = INSPECT_TIMEOUT_SECONDS) -> PlannerInspection:
    """Ask the planner's own Python to read its configuration file. Never raises; every failure is a `PlannerInspection` with a kind."""
    if not str(python).strip() or not Path(python).is_file():
        return _bad("python", f"the planner's Python was not found: {python}")
    if not Path(runner).is_file():
        return _bad("runner", f"the planner runner script is missing from this installation: {runner}")
    payload = json.dumps({"schema": INSPECT_REQUEST_SCHEMA, "config_path": str(config_path)}, ensure_ascii=True).encode("utf-8")
    try:
        done = subprocess.run([str(python), "-I", str(runner)], input=payload, capture_output=True, timeout=timeout, env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"), creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return _bad("timeout", f"the planner's Python did not answer within {timeout:g} seconds")
    except OSError as error:
        return _bad("python", f"the planner's Python could not be started: {error}")
    text = done.stdout.decode("utf-8", errors="replace").strip()
    if not text:
        tail = done.stderr.decode("utf-8", errors="replace")[-STDERR_TAIL_BYTES:]
        return _bad("failed", f"the planner's Python exited with code {done.returncode} and wrote nothing. Its last words: {tail}" if tail.strip() else f"the planner's Python exited with code {done.returncode} and wrote nothing")
    try:
        document = json.loads(text)
    except ValueError:
        return _bad("malformed", "the planner's output was not a JSON document")
    if not isinstance(document, dict) or document.get("schema") != INSPECT_SCHEMA:
        return _bad("malformed", f"the planner's output has an unsupported schema ({_reason(document.get('schema') if isinstance(document, dict) else document)}); expected {INSPECT_SCHEMA}")
    packages = document.get("packages") if isinstance(document.get("packages"), dict) else {}
    if document.get("status") != "ok":
        return _bad(str(document.get("kind") or "failed"), document.get("reason") or "no reason was given", packages)
    config, keys = document.get("config"), document.get("keys")
    if not isinstance(config, dict) or not isinstance(keys, dict):
        return _bad("malformed", "the planner's document is missing the configuration or its keys", packages)
    return PlannerInspection(ok=True, config=config, keys={k: tuple(v) for k, v in keys.items() if isinstance(v, list)}, packages=packages)


# --- turning the child's document into a RouteSet ---------------------------------------------------------------------------------------


def _reason(text: object) -> str:
    return " ".join(str(text).split())[:REASON_CHARS] or "no reason was given"


def _unknown_identity(request: PlanRequest) -> PlannerIdentity:
    return PlannerIdentity(planner=PLANNER_NAME, version="unknown", model_identity=request.selection(), limits=request.limits)


def _failure(status: RouteStatus, request: PlanRequest, target: TargetIdentity, reason: str, *, identity: PlannerIdentity | None = None, termination: SearchTermination | None = None) -> RouteSet:
    if termination is None:
        termination = SearchTermination.CANCELLED if status is RouteStatus.CANCELLED else SearchTermination.FAILED if status is RouteStatus.FAILED else SearchTermination.UNKNOWN
    return RouteSet(status=status, target=target, planner=identity or _unknown_identity(request), reason=_reason(reason), termination=termination)


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _probability(value: object) -> float | None:
    """The planner's policy probability, or None when it is not a number from 0 to 1 (never clamped or guessed)."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) and 0.0 <= number <= 1.0 else None


class _Unrepresentable(Exception):
    """A route the planner returned that `Route` cannot hold, with the reason."""


def _collect(node: dict, steps: dict[str, RouteStep], leaves: dict[str, RouteMolecule]) -> None:
    """Walk a route tree into steps (one per molecule that is made) and starting materials."""
    smiles = _text(node.get("smiles"))
    if smiles is None:
        raise _Unrepresentable("a molecule with no structure")
    reactions = [child for child in node.get("children") or [] if isinstance(child, dict) and child.get("type") == "reaction"]
    if not reactions:
        flag = node.get("in_stock")
        leaves.setdefault(smiles, RouteMolecule(smiles=smiles, in_stock=flag if isinstance(flag, bool) else None))
        return
    if len(reactions) > 1:
        raise _Unrepresentable("a molecule with more than one reaction below it")
    reaction = reactions[0]
    precursors = [child for child in reaction.get("children") or [] if isinstance(child, dict) and child.get("type") == "mol"]
    if not precursors:
        raise _Unrepresentable("a reaction with no precursors")
    metadata = reaction.get("metadata") if isinstance(reaction.get("metadata"), dict) else {}
    try:
        step = RouteStep(
            product=smiles,
            reactants=tuple(_text(p.get("smiles")) or "" for p in precursors),
            reaction_smiles=_text(metadata.get("mapped_reaction_smiles")),
            template_id=_text(metadata.get("template_hash")),
            policy_name=_text(metadata.get("policy_name")),
            policy_probability=_probability(metadata.get("policy_probability")),
        )
    except ValueError as error:
        raise _Unrepresentable(str(error)) from error
    if smiles in steps and steps[smiles] != step:
        raise _Unrepresentable("one molecule made by two different reactions")
    steps.setdefault(smiles, step)
    for precursor in precursors:
        _collect(precursor, steps, leaves)


def route_from_tree(tree: dict, rank: int) -> Route:
    """One of the planner's route trees as a `Route`, or `_Unrepresentable` with why not. The steps are put in the order they would be run."""
    root = _text(tree.get("smiles"))
    if root is None:
        raise _Unrepresentable("a route with no target")
    steps: dict[str, RouteStep] = {}
    leaves: dict[str, RouteMolecule] = {}
    _collect(tree, steps, leaves)
    if not steps:
        raise _Unrepresentable("no reaction")
    scores = tree.get("scores") if isinstance(tree.get("scores"), dict) else {}
    score = scores.get("state score")
    try:
        ordered = forward_order(list(steps.values()), root)
        return Route(
            target_smiles=root,
            steps=ordered,
            starting_materials=tuple(leaves.values()),
            rank=rank,
            score=float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score) else None,
        )
    except ValueError as error:
        raise _Unrepresentable(str(error)) from error


def _identity(document: dict, request: PlanRequest) -> PlannerIdentity:
    raw = document["identity"]
    packages = raw["packages"]
    version = _text(packages.get("aizynthfinder")) or "unknown"
    selection = raw.get("selection") or {}
    models = tuple((key, str(selection[key])) for key in ("expansion", "filter", "stock") if selection.get(key))
    return PlannerIdentity(planner=PLANNER_NAME, version=version, model_identity=models, config_sha256=_text(raw.get("config_sha256")), limits=request.limits)


def _int(value: object, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} is not a count")
    return value


def _statistics(raw: dict) -> SearchStatistics:
    profiling = raw.get("profiling") if isinstance(raw.get("profiling"), dict) else {}
    seconds = raw.get("search_time")
    return SearchStatistics(
        iterations=_int(profiling.get("iterations"), "iterations"),
        search_seconds=float(seconds) if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) else None,
        first_solution_iteration=_int(raw.get("first_solution_iteration"), "first_solution_iteration"),
        nodes=_int(raw.get("number_of_nodes"), "number_of_nodes"),
        routes_returned=_int(raw.get("number_of_routes"), "number_of_routes"),
        solved_routes=_int(raw.get("number_of_solved_routes"), "number_of_solved_routes"),
    )


def _left_out(counts: collections.Counter, reasons: set[str]) -> str:
    """The sentence that says how many of the planner's routes are not shown and why, so none is dropped silently."""
    parts = []
    if counts["unsolved"]:
        parts.append(f"{counts['unsolved']} had a starting material that is not in the stock or whose stock status was not given")
    if counts["no reaction"]:
        parts.append(f"{counts['no reaction']} had no reaction")
    if counts["other"]:
        parts.append(f"{counts['other']} could not be represented ({'; '.join(sorted(reasons))})")
    return "Routes the planner returned that are not shown: " + "; ".join(parts) + "."


def parse_document(document: object, request: PlanRequest, target: TargetIdentity) -> RouteSet:
    """The planner's response as a `RouteSet`. Never raises: anything wrong with the document is a `failed` set with the reason."""
    if not isinstance(document, dict):
        return _failure(RouteStatus.FAILED, request, target, "the planner's output was not a JSON object")
    if document.get("schema") != RUN_SCHEMA:
        return _failure(RouteStatus.FAILED, request, target, f"the planner's output has an unsupported schema ({_reason(document.get('schema'))}); expected {RUN_SCHEMA}")
    status = document.get("status")
    if status == "unavailable":
        return _failure(RouteStatus.UNAVAILABLE, request, target, f"{document.get('kind', 'asset')}: {_reason(document.get('reason'))}")
    if status == "failed":
        return _failure(RouteStatus.FAILED, request, target, _reason(document.get("reason")))
    if status != "completed":
        return _failure(RouteStatus.FAILED, request, target, f"the planner reported an unknown status ({_reason(status)})")
    try:
        identity = _identity(document, request)
        echoed = document["limits"]
        if (echoed.get("iteration_limit"), echoed.get("time_limit"), echoed.get("max_transforms")) != (request.limits.iteration_limit, request.limits.time_limit_seconds, request.limits.max_transforms):
            return _failure(RouteStatus.FAILED, request, target, "the planner ran with different limits from the ones asked for", identity=identity)
        statistics = _statistics(document["statistics"])
        trees = document["routes"]
        if not isinstance(trees, list):
            raise ValueError("routes is not a list")
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        return _failure(RouteStatus.FAILED, request, target, f"the planner's document is malformed ({type(error).__name__}: {error})")

    kept: list[Route] = []
    counts: collections.Counter = collections.Counter()
    reasons: set[str] = set()
    for tree in trees:
        if not isinstance(tree, dict):
            counts["other"] += 1
            reasons.add("not a route object")
            continue
        try:
            route = route_from_tree(tree, rank=len(kept) + 1)
        except _Unrepresentable as error:
            if str(error) == "no reaction":
                counts["no reaction"] += 1
            else:
                counts["other"] += 1
                reasons.add(str(error))
            continue
        if not all(m.in_stock is True for m in route.starting_materials):
            counts["unsolved"] += 1
            continue
        kept.append(route)

    termination = read_termination(identity.limits, statistics)
    limitations = STANDARD_LIMITATIONS + ((_left_out(counts, reasons),) if sum(counts.values()) else ())
    status_ = RouteStatus.FOUND if kept else RouteStatus.NO_ROUTE
    return RouteSet(status=status_, target=target, planner=identity, routes=tuple(kept), termination=termination, statistics=statistics, limitations=limitations)


# --- the child process -------------------------------------------------------------------------------------------------------------------


def _interpret(stdout: bytes, stderr_tail: str, returncode: int, request: PlanRequest, target: TargetIdentity) -> RouteSet:
    text = stdout.decode("utf-8", errors="replace").strip()
    last_words = f" Its last words: {_reason(stderr_tail)}" if stderr_tail.strip() else ""
    if not text:
        return _failure(RouteStatus.FAILED, request, target, f"the planner exited with code {returncode} and wrote no result.{last_words}")
    try:
        document = json.loads(text)
    except ValueError:
        return _failure(RouteStatus.FAILED, request, target, f"the planner's output was not a JSON document (exit code {returncode}).{last_words}")
    result = parse_document(document, request, target)
    if returncode != 0 and result.status in (RouteStatus.FOUND, RouteStatus.NO_ROUTE):
        return _failure(RouteStatus.FAILED, request, target, f"the planner reported a result but exited with code {returncode}.{last_words}", identity=result.planner)
    return result


def run_planner(
    request: PlanRequest,
    target: TargetIdentity,
    *,
    python: str | os.PathLike[str],
    cancel: threading.Event | None = None,
    wall_clock_seconds: float | None = None,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
    runner: str | os.PathLike[str] = RUNNER_PATH,
) -> RouteSet:
    """Run one search in the planner's own interpreter and return what it produced. Blocking: run it on a worker thread. Never raises for anything the child or its environment does."""
    if not Path(python).is_file():
        return _failure(RouteStatus.UNAVAILABLE, request, target, f"the planner's Python was not found: {python}")
    if not Path(runner).is_file():
        return _failure(RouteStatus.UNAVAILABLE, request, target, f"the planner runner script is missing from this installation: {runner}")
    limit = (request.limits.time_limit_seconds or 0) + WALL_CLOCK_MARGIN_SECONDS if wall_clock_seconds is None else wall_clock_seconds
    environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        proc = subprocess.Popen(
            [str(python), "-I", str(runner)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            creationflags=_NO_WINDOW,
        )
    except OSError as error:
        return _failure(RouteStatus.UNAVAILABLE, request, target, f"the planner's Python could not be started: {error}")

    out_chunks: list[bytes] = []
    out_size = [0]
    overflow = threading.Event()
    err_tail: collections.deque[bytes] = collections.deque()
    err_size = [0]

    def pump_stdout() -> None:
        try:
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    return
                out_size[0] += len(chunk)
                if out_size[0] > max_output_bytes:
                    overflow.set()
                    return
                out_chunks.append(chunk)
        except (OSError, ValueError):
            return

    def pump_stderr() -> None:
        try:
            while True:
                chunk = proc.stderr.read(8192)
                if not chunk:
                    return
                err_tail.append(chunk)
                err_size[0] += len(chunk)
                while err_size[0] - len(err_tail[0]) >= STDERR_TAIL_BYTES:
                    err_size[0] -= len(err_tail.popleft())
        except (OSError, ValueError):
            return

    def feed() -> None:
        try:
            proc.stdin.write(json.dumps(request.document(), ensure_ascii=True).encode("utf-8"))
            proc.stdin.close()
        except (OSError, ValueError):
            return  # the child went away before reading; its exit is what reports it

    threads = [threading.Thread(target=fn, daemon=True) for fn in (pump_stdout, pump_stderr, feed)]
    for thread in threads:
        thread.start()

    outcome = "exited"
    deadline = time.monotonic() + limit
    try:
        while True:
            try:
                proc.wait(timeout=POLL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                pass
            if cancel is not None and cancel.is_set():
                outcome = "cancelled"
            elif overflow.is_set():
                outcome = "overflow"
            elif time.monotonic() > deadline:
                outcome = "timeout"
            else:
                continue
            break
    finally:
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        for thread in threads:
            thread.join(timeout=5)
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            try:
                pipe.close()
            except (OSError, ValueError):
                pass

    if outcome == "cancelled":
        return _failure(RouteStatus.CANCELLED, request, target, "the search was cancelled and the planner process was stopped")
    if outcome == "overflow":
        return _failure(RouteStatus.FAILED, request, target, f"the planner wrote more than {max_output_bytes} bytes and was stopped")
    if outcome == "timeout":
        return _failure(RouteStatus.FAILED, request, target, f"the planner did not finish within {limit:g} seconds and was stopped")
    tail = b"".join(err_tail)[-STDERR_TAIL_BYTES:].decode("utf-8", errors="replace")
    return _interpret(b"".join(out_chunks), tail, proc.returncode if proc.returncode is not None else -1, request, target)


__all__ = ["INSPECT_REQUEST_SCHEMA", "INSPECT_SCHEMA", "PLANNER_NAME", "PlanRequest", "PlannerInspection", "PlannerSetup", "inspect_environment", "RUN_SCHEMA", "REQUEST_SCHEMA", "RUNNER_PATH", "parse_document", "route_from_tree", "run_planner"]
