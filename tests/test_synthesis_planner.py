"""The AiZynthFinder runner and parser (`openchem.chem.aizynth_planner`, `openchem.chem.aizynth_runner`): the planner's real saved output becomes a `RouteSet`, every way the child can go wrong is a typed result, and a cancelled or overrunning child is gone. The child is a stand-in script for the process tests and the real planner, where it is installed, for the integration tests (skipped where it is not)."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from openchem.chem import aizynth_planner as host
from openchem.chem import aizynth_runner as runner
from openchem.domain.synthesis_route import (
    STANDARD_LIMITATIONS,
    RouteSet,
    RouteStatus,
    SearchLimits,
    SearchTermination,
    TargetIdentity,
)

_FIXTURES = Path(__file__).parent.parent / "benchmarks" / "synthesis" / "fixtures"
TARGET = TargetIdentity(molecule_uuid="u-1", canonical_smiles="CC(=O)Oc1ccccc1C(=O)O", fingerprint="fp")


def fixture(name: str) -> dict:
    """A saved real planner output, converted to the runner's response shape (the spike's runner wrote an earlier schema with the same fields)."""
    document = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    document["schema"] = host.RUN_SCHEMA
    document["limits"].setdefault("all_routes", False)
    document.pop("route_count", None)
    return document


def request_for(document: dict, **kw) -> host.PlanRequest:
    limits = document["limits"]
    return host.PlanRequest(
        **{
            "target_smiles": document["target"],
            "config": {"expansion": {"uspto": ["m.onnx", "t.csv.gz"]}, "stock": {"zinc": "s.hdf5"}},
            "stock": document["identity"]["selection"]["stock"],
            "expansion": "uspto",
            "filter": None if document["identity"]["selection"]["filter"] == "none" else document["identity"]["selection"]["filter"],
            "limits": SearchLimits(iteration_limit=limits["iteration_limit"], time_limit_seconds=limits["time_limit"], max_transforms=limits["max_transforms"]),
            **kw,
        }
    )


def parse(name: str, **kw) -> RouteSet:
    document = fixture(name)
    return host.parse_document(document, request_for(document), TARGET)


def parse_doc(document: dict, **kw) -> RouteSet:
    return host.parse_document(document, request_for(document, **kw), TARGET)


# --- the request ----------------------------------------------------------------------------------------------------------------------


def test_the_schemas_of_the_two_halves_are_equal_because_neither_can_import_the_other():
    assert host.REQUEST_SCHEMA == runner.REQUEST_SCHEMA and host.RUN_SCHEMA == runner.RUN_SCHEMA


def test_a_request_needs_every_limit_and_a_target_a_stock_an_expansion_and_a_configuration():
    document = fixture("aspirin_it100")
    good = request_for(document)
    assert good.document()["iteration_limit"] == 100 and good.document()["schema"] == host.REQUEST_SCHEMA
    for bad in ({"target_smiles": " "}, {"stock": ""}, {"expansion": ""}, {"config": {}}, {"filter": "  "}):
        with pytest.raises(ValueError):
            request_for(document, **bad)
    for limits in (SearchLimits(), SearchLimits(iteration_limit=10), SearchLimits(iteration_limit=10, time_limit_seconds=5)):
        with pytest.raises(ValueError, match="must all be set"):
            request_for(document, limits=limits)


def test_the_selection_is_names_not_paths_and_a_missing_filter_reads_none():
    request = request_for(fixture("paroutes_n1_t2_it500_nofilter"))
    assert request.selection() == (("expansion", "uspto"), ("filter", "none"), ("stock", "n1"))
    assert request.document()["filter"] is None


# --- the parser, on the planner's real output ---------------------------------------------------------------------------------------------


def test_a_solved_search_becomes_found_routes_in_the_planners_order_with_its_identity_and_termination():
    result = parse("aspirin_it100")

    assert result.status is RouteStatus.FOUND and result.routes and [r.rank for r in result.routes] == list(range(1, len(result.routes) + 1))
    assert result.planner.planner == "AiZynthFinder" and result.planner.version == "4.4.1" and ("stock", "zinc") in result.planner.model_identity
    assert result.planner.limits.iteration_limit == 100 and result.planner.config_sha256
    assert result.termination is SearchTermination.ITERATION_LIMIT and result.stopped_at_a_limit
    assert result.statistics.iterations == 100 and result.statistics.nodes and result.statistics.solved_routes
    assert set(STANDARD_LIMITATIONS) <= set(result.limitations)


def test_every_step_carries_what_the_planner_gave_and_nothing_else():
    route = parse("aspirin_it100").routes[0]
    step = route.steps[-1]
    assert step.product == route.target_smiles and step.reaction_smiles and step.template_id and step.policy_name == "uspto" and 0 < step.policy_probability <= 1
    assert all(m.in_stock is True for m in route.starting_materials)
    assert route.score and 0 < route.score <= 1  # the planner's ranking number
    assert route.validation is not None and route.validation.fully_validated  # every kept route is checked against its own bookkeeping (slice 6)


def test_a_three_step_route_is_in_the_order_it_would_be_run():
    route = max(parse("sildenafil_it100").routes, key=lambda r: r.length)
    assert route.length >= 3
    made: set[str] = set()
    products = {s.product for s in route.steps}
    for step in route.steps:
        assert all(r not in products or r in made for r in step.reactants)
        made.add(step.product)
    assert route.steps[-1].product == route.target_smiles


def test_an_unsolved_search_is_no_route_and_says_what_was_left_out():
    result = parse("strychnine_it100")  # five routes returned: the bare target and four one-step routes into a precursor that is not in stock

    assert result.status is RouteStatus.NO_ROUTE and result.routes == ()
    assert "No route found within the configured search limits" in result.message()
    left_out = [s for s in result.limitations if s.startswith("Routes the planner returned that are not shown")]
    assert len(left_out) == 1 and "4 had a starting material that is not in the stock" in left_out[0] and "1 had no reaction" in left_out[0]


def test_a_search_with_some_solved_routes_keeps_only_those_and_counts_the_rest():
    document = fixture("sildenafil_it100")
    total = len(document["routes"])
    result = parse_doc(document)
    solved = len(result.routes)
    assert 0 < solved < total
    assert f"{total - solved} had a starting material" in result.limitations[-1]


def test_every_saved_planner_output_parses_without_error_and_keeps_its_invariants():
    for path in sorted(_FIXTURES.glob("*.json")):
        document = fixture(path.stem)
        result = host.parse_document(document, request_for(document), TARGET)
        assert result.status in (RouteStatus.FOUND, RouteStatus.NO_ROUTE), path.name
        for route in result.routes:
            assert route.steps[-1].product == route.target_smiles and all(m.in_stock for m in route.starting_materials), path.name


def test_the_planner_identity_does_not_carry_paths():
    result = parse("aspirin_it100")
    assert not any(os.sep in value or "/" in value for _, value in result.planner.model_identity)
    assert "hdf5" not in result.planner.label()


# --- malformed and unusual documents --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("document", [None, [], "text", 7])
def test_a_document_that_is_not_an_object_is_failed(document):
    request = request_for(fixture("aspirin_it100"))
    result = host.parse_document(document, request, TARGET)
    assert result.status is RouteStatus.FAILED and "not a JSON object" in result.reason


def test_an_unsupported_or_missing_schema_is_failed_naming_both():
    for schema in ("aizynth-run-0", None, 3):
        document = fixture("aspirin_it100")
        document["schema"] = schema
        result = parse_doc(document)
        assert result.status is RouteStatus.FAILED and "unsupported schema" in result.reason and host.RUN_SCHEMA in result.reason


def test_the_statuses_the_runner_can_report_map_to_typed_results():
    base = {"schema": host.RUN_SCHEMA}
    request = request_for(fixture("aspirin_it100"))
    unavailable = host.parse_document({**base, "status": "unavailable", "kind": "stock", "reason": "the stock file is not there: x"}, request, TARGET)
    failed = host.parse_document({**base, "status": "failed", "kind": "error", "reason": "ValueError: boom"}, request, TARGET)
    unknown = host.parse_document({**base, "status": "melting"}, request, TARGET)
    assert (unavailable.status, failed.status, unknown.status) == (RouteStatus.UNAVAILABLE, RouteStatus.FAILED, RouteStatus.FAILED)
    assert "stock: the stock file is not there" in unavailable.reason and "boom" in failed.reason and "unknown status" in unknown.reason
    assert failed.termination is SearchTermination.FAILED and unavailable.planner.version == "unknown"


@pytest.mark.parametrize("damage", ["no_identity", "no_packages", "no_limits", "no_statistics", "routes_not_a_list", "negative_count", "bool_count"])
def test_a_completed_document_with_the_wrong_shape_is_failed_as_malformed(damage):
    document = fixture("aspirin_it100")
    request = request_for(document)  # built from the document as it was, before it is damaged
    if damage == "no_identity":
        del document["identity"]
    elif damage == "no_packages":
        document["identity"]["packages"] = None
    elif damage == "no_limits":
        del document["limits"]
    elif damage == "no_statistics":
        del document["statistics"]
    elif damage == "routes_not_a_list":
        document["routes"] = {"a": 1}
    elif damage == "negative_count":
        document["statistics"]["number_of_nodes"] = -4
    else:
        document["statistics"]["number_of_nodes"] = True
    result = host.parse_document(document, request, TARGET)
    assert result.status is RouteStatus.FAILED and "malformed" in result.reason


def test_limits_that_differ_from_the_ones_asked_for_are_failed_not_trusted():
    document = fixture("aspirin_it100")
    request = request_for(document)
    document["limits"]["iteration_limit"] = 5
    result = host.parse_document(document, request, TARGET)
    assert result.status is RouteStatus.FAILED and "different limits" in result.reason


def _one_route_document():
    document = fixture("aspirin_it100")
    document["routes"] = [document["routes"][0]]
    return document


def _first_reaction(tree):
    return next(c for c in tree["children"] if c["type"] == "reaction")


def test_metadata_that_is_missing_or_wrong_is_not_provided_never_invented():
    document = _one_route_document()
    metadata = _first_reaction(document["routes"][0])["metadata"]
    for key in ("mapped_reaction_smiles", "template_hash", "policy_name"):
        metadata[key] = "  "
    metadata["policy_probability"] = 1.7
    step = parse_doc(document).routes[0].steps[0]
    assert (step.reaction_smiles, step.template_id, step.policy_name, step.policy_probability) == (None, None, None, None)
    document = _one_route_document()
    del _first_reaction(document["routes"][0])["metadata"]
    step = parse_doc(document).routes[0].steps[0]
    assert step.reaction_smiles is None and step.policy_probability is None


@pytest.mark.parametrize("value,expected", [("0.25", 0.25), (0, 0.0), (1, 1.0), (True, None), ("x", None), (-0.1, None), (float("nan"), None), (None, None), ([0.5], None)])
def test_the_policy_probability_is_a_number_from_zero_to_one_or_nothing(value, expected):
    assert host._probability(value) == expected


def test_a_leaf_whose_stock_status_is_missing_or_false_means_the_route_is_not_shown():
    for flag in (None, False, "yes"):
        document = _one_route_document()
        leaf = next(c for c in _first_reaction(document["routes"][0])["children"] if c["type"] == "mol")
        if flag is None:
            del leaf["in_stock"]
        else:
            leaf["in_stock"] = flag
        result = parse_doc(document)
        assert result.status is RouteStatus.NO_ROUTE and "1 had a starting material" in result.limitations[-1]


def test_a_route_the_domain_cannot_hold_is_left_out_and_said_not_dropped_silently():
    # one molecule with two reactions below it
    document = _one_route_document()
    document["routes"][0]["children"].append(copy.deepcopy(_first_reaction(document["routes"][0])))
    result = parse_doc(document)
    assert result.status is RouteStatus.NO_ROUTE and "1 could not be represented (a molecule with more than one reaction below it)" in result.limitations[-1]
    # a reaction with no precursors
    document = _one_route_document()
    _first_reaction(document["routes"][0])["children"] = []
    assert "a reaction with no precursors" in parse_doc(document).limitations[-1]
    # a molecule with no structure
    document = _one_route_document()
    document["routes"][0]["smiles"] = " "
    assert parse_doc(document).status is RouteStatus.NO_ROUTE
    # not an object at all
    document = _one_route_document()
    document["routes"].append("garbage")
    result = parse_doc(document)
    assert result.status is RouteStatus.FOUND and "1 could not be represented (not a route object)" in result.limitations[-1]


def test_the_same_intermediate_made_the_same_way_twice_is_one_step_and_made_two_ways_is_unrepresentable():
    leaf_a = {"type": "mol", "smiles": "CC(=O)OC(C)=O", "in_stock": True}

    def reaction(*kids, template="h1"):
        return {"type": "reaction", "smiles": "", "metadata": {"template_hash": template}, "children": list(kids)}

    def inter(template):
        return {"type": "mol", "smiles": "CCO", "in_stock": False, "children": [reaction(copy.deepcopy(leaf_a), template=template)]}

    def tree(first, second):
        return {"type": "mol", "smiles": "CCCC", "in_stock": False, "children": [reaction(first, second)], "scores": {"state score": 0.5}}

    twice_same = host.route_from_tree(tree(inter("h1"), inter("h1")), 1)
    assert twice_same.length == 2  # CCO made once, CCCC once
    with pytest.raises(host._Unrepresentable, match="two different reactions"):
        host.route_from_tree(tree(inter("h1"), inter("h2")), 1)


def test_a_cycle_in_a_route_is_unrepresentable():
    cyc = {"type": "mol", "smiles": "A", "children": [{"type": "reaction", "metadata": {}, "children": [{"type": "mol", "smiles": "B", "children": [{"type": "reaction", "metadata": {}, "children": [{"type": "mol", "smiles": "A", "in_stock": True}]}]}]}]}
    with pytest.raises(host._Unrepresentable):
        host.route_from_tree(cyc, 1)


def test_a_search_that_stopped_short_of_its_limits_reports_unknown_not_completed():
    document = fixture("aspirin_it100")
    document["statistics"]["profiling"]["iterations"] = 40
    assert parse_doc(document).termination is SearchTermination.UNKNOWN
    document["statistics"]["profiling"]["iterations"] = 100
    assert parse_doc(document).termination is SearchTermination.ITERATION_LIMIT
    document["statistics"]["profiling"]["iterations"] = 40
    document["statistics"]["search_time"] = 10_000.0
    assert parse_doc(document).termination is SearchTermination.TIME_LIMIT


def test_a_planner_that_gives_no_scores_leaves_the_score_not_provided():
    document = _one_route_document()
    del document["routes"][0]["scores"]
    assert parse_doc(document).routes[0].score is None


def test_routes_are_ranked_one_two_three_in_the_planners_order_even_when_unsolved_ones_come_first():
    document = _one_route_document()
    solved = document["routes"][0]
    unsolved = copy.deepcopy(solved)
    next(c for c in _first_reaction(unsolved)["children"] if c["type"] == "mol")["in_stock"] = False
    bare = {"type": "mol", "smiles": solved["smiles"], "in_stock": False, "children": []}
    document["routes"] = [bare, unsolved, copy.deepcopy(solved), unsolved, copy.deepcopy(solved)]

    result = parse_doc(document)

    assert [r.rank for r in result.routes] == [1, 2] and len(result.routes) == 2
    assert "2 had a starting material" in result.limitations[-1] and "1 had no reaction" in result.limitations[-1]


@pytest.mark.parametrize("score,expected", [(True, None), (False, None), ("0.9", None), (float("nan"), None), (float("inf"), None), (0.5, 0.5), (1, 1.0)])
def test_the_planners_score_is_a_finite_number_or_not_provided(score, expected):
    document = _one_route_document()
    document["routes"][0]["scores"] = {"state score": score}
    assert parse_doc(document).routes[0].score == expected


# --- the child process --------------------------------------------------------------------------------------------------------------------


def pid_alive(pid: int) -> bool:
    try:
        import psutil

        return psutil.pid_exists(pid)
    except ImportError:
        pass
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def stand_in(tmp_path: Path, body: str) -> Path:
    """A planner stand-in: a script the host runs exactly as it would run the real runner (stdlib only, so `-I` is fine)."""
    path = tmp_path / "fake_runner.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def run_with(tmp_path, body: str, document: dict | None = None, **kw):
    document = document or fixture("aspirin_it100")
    script = stand_in(tmp_path, body)
    return host.run_planner(request_for(document), TARGET, python=sys.executable, runner=script, **kw)


def emit(document: dict, tmp_path: Path, then: str = "") -> str:
    """A stand-in body that reads the request, writes `document`, and then runs `then` (one statement)."""
    (tmp_path / "doc.json").write_text(json.dumps(document), encoding="utf-8")
    return f"""
        import sys
        sys.stdin.buffer.read()
        sys.stdout.write(open({str(tmp_path / 'doc.json')!r}, encoding='utf-8').read() + chr(10))
        sys.stdout.flush()
        {then}
    """


def test_a_child_that_writes_a_good_document_gives_routes(tmp_path):
    document = fixture("aspirin_it100")
    result = run_with(tmp_path, emit(document, tmp_path), document)
    assert result.status is RouteStatus.FOUND and result.routes


def test_the_request_reaches_the_child_on_stdin_intact_including_a_non_ascii_path(tmp_path):
    document = fixture("aspirin_it100")
    out = tmp_path / "received.json"
    body = f"""
        import sys
        data = sys.stdin.buffer.read()
        open({str(out)!r}, 'wb').write(data)
        sys.stdout.write(open({str(tmp_path / 'doc.json')!r}, encoding='utf-8').read() + chr(10))
    """
    (tmp_path / "doc.json").write_text(json.dumps(document), encoding="utf-8")
    config = {"expansion": {"uspto": ["D:\\caf\u00e9 mod\u00e8les\\m.onnx", "t.csv.gz"]}, "stock": {"zinc": "s.hdf5"}}
    request = request_for(document, config=config)

    host.run_planner(request, TARGET, python=sys.executable, runner=stand_in(tmp_path, body))

    received = json.loads(out.read_bytes().decode("utf-8"))
    assert received == request.document() and received["config"]["expansion"]["uspto"][0] == "D:\\caf\u00e9 mod\u00e8les\\m.onnx"
    assert b"\\u00e9" in out.read_bytes()  # sent as ASCII escapes, so no codec can mangle it


def test_the_child_is_started_with_an_argument_array_no_shell_and_isolated_mode(tmp_path, monkeypatch):
    seen = {}
    real = subprocess.Popen

    def spy(args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        return real(args, **kwargs)

    monkeypatch.setattr(host.subprocess, "Popen", spy)
    document = fixture("aspirin_it100")
    run_with(tmp_path, emit(document, tmp_path), document)

    assert isinstance(seen["args"], list) and seen["args"][1] == "-I" and not seen["kwargs"].get("shell")
    assert seen["kwargs"]["stdin"] == subprocess.PIPE and seen["kwargs"]["env"]["PYTHONUTF8"] == "1"
    assert not any("aspirin" in part.lower() or "CC(=O)" in part for part in seen["args"])  # no data on the command line


def test_stderr_noise_does_not_disturb_the_result(tmp_path):
    document = fixture("aspirin_it100")
    body = emit(document, tmp_path, then="sys.stderr.write('warning ' * 50000)")
    assert run_with(tmp_path, body, document).status is RouteStatus.FOUND


def test_library_chatter_on_stdout_before_the_document_is_not_a_document(tmp_path):
    body = """
        import sys
        sys.stdin.buffer.read()
        print('hello from a library')
        print('{"schema": "aizynth-run-1"}')
    """
    result = run_with(tmp_path, body)
    assert result.status is RouteStatus.FAILED and "not a JSON document" in result.reason


def test_a_child_that_exits_without_a_result_is_failed_with_its_last_words(tmp_path):
    result = run_with(tmp_path, "import sys\nsys.stdin.buffer.read()\nsys.stderr.write('Traceback: ImportError: pyarrow requires NumPy 2')\nsys.exit(3)\n")
    assert result.status is RouteStatus.FAILED and "exited with code 3 and wrote no result" in result.reason and "pyarrow requires NumPy 2" in result.reason


def test_a_child_that_writes_garbage_is_failed(tmp_path):
    result = run_with(tmp_path, "import sys\nsys.stdin.buffer.read()\nsys.stdout.write('not json at all')\n")
    assert result.status is RouteStatus.FAILED and "not a JSON document" in result.reason


def test_a_completed_document_with_a_non_zero_exit_is_failed_not_believed(tmp_path):
    document = fixture("aspirin_it100")
    result = run_with(tmp_path, emit(document, tmp_path, then="sys.exit(1)"), document)
    assert result.status is RouteStatus.FAILED and "reported a result but exited with code 1" in result.reason


def test_a_failed_document_with_a_non_zero_exit_keeps_the_childs_own_reason(tmp_path):
    body = """
        import sys
        sys.stdin.buffer.read()
        sys.stdout.write('{"schema": "aizynth-run-1", "status": "failed", "kind": "error", "reason": "ValueError: not enough values to unpack"}')
        sys.exit(1)
    """
    result = run_with(tmp_path, body)
    assert result.status is RouteStatus.FAILED and "not enough values to unpack" in result.reason


def test_an_unsupported_schema_from_the_child_is_failed(tmp_path):
    result = run_with(tmp_path, "import sys\nsys.stdin.buffer.read()\nsys.stdout.write('{\"schema\": \"aizynth-run-9\", \"status\": \"completed\"}')\n")
    assert result.status is RouteStatus.FAILED and "unsupported schema" in result.reason


def test_output_past_the_bound_kills_the_child_and_is_failed(tmp_path):
    pid_file = tmp_path / "pid"
    body = f"""
        import os, sys, time
        open({str(pid_file)!r}, 'w').write(str(os.getpid()))
        sys.stdin.buffer.read()
        for _ in range(100):
            sys.stdout.write('x' * 100000)
            sys.stdout.flush()
        time.sleep(60)
    """
    result = run_with(tmp_path, body, max_output_bytes=500_000)
    assert result.status is RouteStatus.FAILED and "wrote more than 500000 bytes" in result.reason
    time.sleep(0.5)
    assert not pid_alive(int(pid_file.read_text()))


def test_a_child_that_overruns_the_wall_clock_is_killed_and_is_failed(tmp_path):
    pid_file = tmp_path / "pid"
    body = f"""
        import os, sys, time
        open({str(pid_file)!r}, 'w').write(str(os.getpid()))
        sys.stdin.buffer.read()
        time.sleep(60)
    """
    began = time.monotonic()
    result = run_with(tmp_path, body, wall_clock_seconds=1.0)
    assert time.monotonic() - began < 15
    assert result.status is RouteStatus.FAILED and "did not finish within 1 seconds" in result.reason and result.termination is SearchTermination.FAILED
    time.sleep(0.5)
    assert not pid_alive(int(pid_file.read_text()))


def test_cancelling_kills_the_child_promptly_and_leaves_no_process(tmp_path):
    pid_file = tmp_path / "pid"
    body = f"""
        import os, sys, time
        open({str(pid_file)!r}, 'w').write(str(os.getpid()))
        sys.stdin.buffer.read()
        time.sleep(120)
    """
    cancel = threading.Event()
    threading.Timer(0.8, cancel.set).start()
    began = time.monotonic()

    result = run_with(tmp_path, body, cancel=cancel)

    assert time.monotonic() - began < 15
    assert result.status is RouteStatus.CANCELLED and result.termination is SearchTermination.CANCELLED and result.routes == ()
    time.sleep(0.5)
    assert not pid_alive(int(pid_file.read_text()))


def test_the_wall_clock_is_the_planners_time_limit_plus_the_margin(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "WALL_CLOCK_MARGIN_SECONDS", 0.5)
    document = fixture("aspirin_it100")
    document["limits"]["time_limit"] = 0.5
    began = time.monotonic()

    result = run_with(tmp_path, "import sys, time\nsys.stdin.buffer.read()\ntime.sleep(60)\n", document)

    assert result.status is RouteStatus.FAILED and "did not finish within 1 seconds" in result.reason  # 0.5 + 0.5, not the time limit alone
    assert time.monotonic() - began < 15


def test_a_cancel_that_is_already_set_stops_the_search_at_once(tmp_path):
    cancel = threading.Event()
    cancel.set()
    result = run_with(tmp_path, "import sys, time\nsys.stdin.buffer.read()\ntime.sleep(60)\n", cancel=cancel)
    assert result.status is RouteStatus.CANCELLED


def test_a_planner_python_that_is_not_there_is_unavailable_and_says_which(tmp_path):
    document = fixture("aspirin_it100")
    result = host.run_planner(request_for(document), TARGET, python=tmp_path / "no" / "python.exe")
    assert result.status is RouteStatus.UNAVAILABLE and "planner's Python was not found" in result.reason


def test_a_missing_runner_script_is_unavailable(tmp_path):
    document = fixture("aspirin_it100")
    result = host.run_planner(request_for(document), TARGET, python=sys.executable, runner=tmp_path / "gone.py")
    assert result.status is RouteStatus.UNAVAILABLE and "runner script is missing" in result.reason


def test_a_python_that_cannot_be_started_is_unavailable(tmp_path):
    not_a_program = tmp_path / "python.exe"
    not_a_program.write_text("this is not an executable", encoding="utf-8")
    result = host.run_planner(request_for(fixture("aspirin_it100")), TARGET, python=not_a_program, runner=host.RUNNER_PATH)
    assert result.status is RouteStatus.UNAVAILABLE and "could not be started" in result.reason


def test_the_real_runner_script_is_where_the_host_looks_for_it():
    assert host.RUNNER_PATH.is_file() and host.RUNNER_PATH.name == "aizynth_runner.py"


# --- the runner script itself, with a stand-in library ---------------------------------------------------------------------------------------------


@pytest.fixture
def fake_library(tmp_path):
    """A `aizynthfinder` package that records what the runner did and prints to stdout as a chatty library may."""
    package = tmp_path / "fakelib" / "aizynthfinder"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "aizynthfinder.py").write_text(
        textwrap.dedent(
            """
            import json, os, types

            class _Sel:
                def __init__(self, log, name): self.log, self.name = log, name
                def select(self, key, *a): self.log.append((self.name, key))

            class AiZynthFinder:
                def __init__(self, configdict=None, configfile=None):
                    print("a library banner on stdout")
                    self.log = []
                    configdict.pop("stock", None)   # the real library consumes the dictionary it is given
                    self.stock, self.expansion_policy, self.filter_policy = (_Sel(self.log, n) for n in ("stock", "expansion", "filter"))
                    self.config = types.SimpleNamespace(search=types.SimpleNamespace(), post_processing=types.SimpleNamespace(all_routes=False))
                def prepare_tree(self): pass
                def tree_search(self):
                    if os.environ.get("FAKE_EXPLODE"): raise RuntimeError("tree exploded")
                def build_routes(self):
                    target = self.target_smiles

                    class Routes:
                        def __len__(self): return 1
                        def dict_with_scores(self): return [{"type": "mol", "smiles": target, "children": [], "scores": {"state score": 0.5}}]

                    self.routes = Routes()
                def extract_statistics(self):
                    return {"is_solved": False, "all_routes": self.config.post_processing.all_routes, "limits": [self.config.search.iteration_limit, self.config.search.time_limit, self.config.search.max_transforms], "selected": self.log}
            """
        ),
        encoding="utf-8",
    )
    return tmp_path / "fakelib"


def files(tmp_path):
    names = {"model": "m.onnx", "templates": "t.csv.gz", "filter": "f.onnx", "stock": "s.txt"}
    for value in names.values():
        (tmp_path / value).write_text("x", encoding="utf-8")
    return {key: str(tmp_path / value) for key, value in names.items()}


def runner_request(tmp_path, **override):
    paths = files(tmp_path)
    request = {
        "schema": runner.REQUEST_SCHEMA,
        "target_smiles": "CCO",
        "config": {"expansion": {"uspto": [paths["model"], paths["templates"]]}, "filter": {"uspto": paths["filter"]}, "stock": {"zinc": paths["stock"]}},
        "stock": "zinc", "expansion": "uspto", "filter": "uspto", "iteration_limit": 7, "time_limit": 9.5, "max_transforms": 4, "all_routes": False,
    }
    request.update(override)
    return request


def run_script(request, library=None, env_extra=None):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=str(library) if library else "")
    env.update(env_extra or {})
    done = subprocess.run([sys.executable, str(host.RUNNER_PATH)], input=json.dumps(request).encode("utf-8"), capture_output=True, env=env, timeout=120)
    lines = done.stdout.decode("utf-8").strip().splitlines()
    return done.returncode, json.loads(lines[-1]) if lines else None, lines, done.stderr.decode("utf-8", errors="replace")


def test_the_runner_runs_a_search_selects_what_it_was_told_and_writes_one_document(tmp_path, fake_library):
    code, document, lines, stderr = run_script(runner_request(tmp_path), fake_library)

    assert code == 0 and len(lines) == 1 and document["schema"] == runner.RUN_SCHEMA and document["status"] == "completed"  # the banner went to stderr, not stdout
    assert "a library banner" in stderr
    assert document["limits"] == {"iteration_limit": 7, "time_limit": 9.5, "max_transforms": 4, "all_routes": False}
    stats = document["statistics"]
    assert stats["limits"] == [7, 9.5, 4] and ["stock", "zinc"] in stats["selected"] and ["expansion", "uspto"] in stats["selected"] and ["filter", "uspto"] in stats["selected"]
    assert document["identity"]["selection"] == {"stock": "zinc", "expansion": "uspto", "filter": "uspto"}
    import hashlib

    request = runner_request(tmp_path)
    expected = hashlib.sha256(json.dumps(request["config"], sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()
    assert document["identity"]["config_sha256"] == expected  # the hash of the configuration that was SENT, though the library consumed its copy
    assert document["routes"] == [{"type": "mol", "smiles": "CCO", "children": [], "scores": {"state score": 0.5}}]


def test_the_all_routes_flag_reaches_the_library_and_a_missing_filter_is_not_selected(tmp_path, fake_library):
    _, document, _, _ = run_script(runner_request(tmp_path, all_routes=True, filter=None), fake_library)
    assert document["statistics"]["all_routes"] is True and document["limits"]["all_routes"] is True
    assert not any(name == "filter" for name, _ in document["statistics"]["selected"]) and document["identity"]["selection"]["filter"] == "none"


@pytest.mark.parametrize(
    "mutate,kind",
    [
        (lambda r, p: r["config"]["expansion"]["uspto"].__setitem__(0, str(p / "gone.onnx")), "model"),
        (lambda r, p: r["config"]["expansion"]["uspto"].__setitem__(1, str(p / "gone.csv.gz")), "templates"),
        (lambda r, p: r["config"]["filter"].__setitem__("uspto", str(p / "gone.onnx")), "filter"),
        (lambda r, p: r["config"]["stock"].__setitem__("zinc", str(p / "gone.txt")), "stock"),
        (lambda r, p: r.__setitem__("expansion", "nope"), "config"),
        (lambda r, p: r.__setitem__("stock", "nope"), "config"),
        (lambda r, p: r.__setitem__("filter", "nope"), "config"),
        (lambda r, p: r["config"]["expansion"].__setitem__("uspto", ["only-one.onnx"]), "config"),
    ],
)
def test_a_missing_asset_is_unavailable_and_names_the_file_before_the_library_is_even_loaded(tmp_path, mutate, kind):
    request = runner_request(tmp_path)
    mutate(request, tmp_path)

    code, document, _, _ = run_script(request)  # no fake library on the path: the library must not be needed to say this

    assert code == 1 and document["status"] == "unavailable" and document["kind"] == kind and document["reason"]


def test_a_target_that_does_not_parse_is_invalid_target_not_the_librarys_attribute_error(tmp_path, fake_library):
    code, document, _, stderr = run_script(runner_request(tmp_path, target_smiles="C(C"), fake_library)
    assert code == 1 and (document["status"], document["kind"]) == ("failed", "invalid_target") and "could not be read" in document["reason"] and "SMILES Parse Error" not in stderr


@pytest.mark.parametrize(
    "override",
    [{"schema": "other"}, {"target_smiles": ""}, {"iteration_limit": 0}, {"iteration_limit": True}, {"max_transforms": "6"}, {"time_limit": -1}, {"time_limit": True}, {"all_routes": "yes"}, {"filter": 5}, {"config": []}],
)
def test_a_bad_request_is_failed_bad_request(tmp_path, override):
    code, document, _, _ = run_script(runner_request(tmp_path, **override))
    assert code == 1 and (document["status"], document["kind"]) == ("failed", "bad_request")


def test_the_runners_document_is_ascii_so_no_output_codec_can_break_it(tmp_path):
    request = runner_request(tmp_path)
    request["config"]["stock"]["zinc"] = str(tmp_path / "caf\u00e9 gone.txt")  # a non-ASCII path in an error message

    code, document, _, _ = run_script(request, env_extra={"PYTHONIOENCODING": "ascii", "PYTHONUTF8": "0"})

    assert code == 1 and document["status"] == "unavailable" and "caf\u00e9 gone.txt" in document["reason"]


def test_a_request_that_is_not_json_is_failed_bad_request():
    done = subprocess.run([sys.executable, str(host.RUNNER_PATH)], input=b"{not json", capture_output=True, timeout=60)
    document = json.loads(done.stdout.decode("utf-8").strip().splitlines()[-1])
    assert done.returncode == 1 and (document["status"], document["kind"]) == ("failed", "bad_request")


def test_a_fault_inside_the_search_is_failed_error_with_the_message_and_a_traceback(tmp_path, fake_library):
    code, document, lines, _ = run_script(runner_request(tmp_path), fake_library, {"FAKE_EXPLODE": "1"})
    assert code == 1 and len(lines) == 1 and (document["status"], document["kind"]) == ("failed", "error")
    assert document["reason"] == "RuntimeError: tree exploded" and "tree_search" in document["traceback"]


def test_the_runner_and_the_host_agree_on_a_whole_exchange(tmp_path, fake_library):
    """The runner's own document, parsed by the host: the one test that fails if the two halves drift apart."""
    request = runner_request(tmp_path)
    _, document, _, _ = run_script(request, fake_library)
    host_request = host.PlanRequest(
        target_smiles="CCO", config=request["config"], stock="zinc", expansion="uspto", filter="uspto", limits=SearchLimits(iteration_limit=7, time_limit_seconds=9.5, max_transforms=4)
    )
    result = host.parse_document(document, host_request, TARGET)
    assert result.status is RouteStatus.NO_ROUTE and result.planner.limits.iteration_limit == 7  # the stand-in returns a bare target: no reaction, so no route


# --- the real planner, where it is installed ---------------------------------------------------------------------------------------------------------


_PLANNER_PYTHON = Path("D:/_scratch/aizynth/env/Scripts/python.exe")
_PLANNER_DATA = Path("D:/_scratch/aizynth/data")
# The reference stock the benchmark ran on, as the InChI keys the planner reads. It is protocol 2's, committed with its records: protocol 1 never kept its copy, and these tests pointed at that missing file and skipped silently on every machine (found 2026-10-22).
_STOCK_KEYS = Path(__file__).parent.parent / "benchmarks" / "synthesis" / "artifacts_protocol2" / "stock_n1_inchikeys.txt"
_REAL = pytest.mark.skipif(not (_PLANNER_PYTHON.exists() and (_PLANNER_DATA / "uspto_model.onnx").exists() and _STOCK_KEYS.exists()), reason="the planner environment and the reference stock are not on this machine")


def test_the_stock_file_the_real_planner_tests_need_is_committed_so_they_cannot_skip_for_want_of_it():
    """A skip is silent. The real-planner tests skip when the planner is not installed, which is honest; they must never skip because the stock they read is not in the repository."""
    assert _STOCK_KEYS.is_file() and _STOCK_KEYS.stat().st_size > 100_000, "the benchmark's reference stock (13,414 InChI keys) is missing"
    keys = _STOCK_KEYS.read_text(encoding="utf-8").split()
    assert len(set(keys)) == 13414 and all(len(key) == 27 for key in keys)


def _real_request(iterations=30, target="CC(=O)Oc1ccccc1C(=O)O", **kw):
    config = {"expansion": {"uspto": [str(_PLANNER_DATA / "uspto_model.onnx"), str(_PLANNER_DATA / "uspto_templates.csv.gz")]}, "stock": {"n1": str(_STOCK_KEYS)}}
    # (the default target is aspirin: the exchange is checked, not the chemistry)
    return host.PlanRequest(target_smiles=target, config=config, stock="n1", expansion="uspto", limits=SearchLimits(iteration_limit=iterations, time_limit_seconds=300, max_transforms=6), **kw)


@_REAL
def test_the_real_planner_answers_through_the_real_runner():
    result = host.run_planner(_real_request(), TARGET, python=_PLANNER_PYTHON)

    assert result.status in (RouteStatus.FOUND, RouteStatus.NO_ROUTE), result.reason
    assert result.planner.version == "4.4.1" and result.planner.limits.iteration_limit == 30 and result.statistics.iterations == 30
    assert result.termination is SearchTermination.ITERATION_LIMIT


@_REAL
def test_a_real_search_asks_for_every_solved_route_and_keeps_ten_ranked_and_validated_and_says_how_many_it_left_out():
    """Paracetamol at 200 iterations returned 145 routes (86 with every starting material in stock) when measured on 2026-10-22; the count varies, the shape of the answer does not."""
    target = TargetIdentity(molecule_uuid="u-2", canonical_smiles="CC(=O)Nc1ccc(O)cc1", fingerprint="fp2")
    request = _real_request(iterations=200, target=target.canonical_smiles)
    assert request.all_routes is True

    result = host.run_planner(request, target, python=_PLANNER_PYTHON)

    assert result.status is RouteStatus.FOUND, result.reason
    assert len(result.routes) == host.ROUTES_SHOWN and [r.rank for r in result.routes] == list(range(1, host.ROUTES_SHOWN + 1))
    assert all(r.validation is not None and r.validation.fully_validated for r in result.routes)
    assert all(m.in_stock is True for r in result.routes for m in r.starting_materials)
    left_out = [s for s in result.limitations if s.startswith("Routes the planner returned that are not shown: ")]
    assert len(left_out) == 1 and "more solved routes ranked below the 10 shown" in left_out[0], result.limitations
    assert host.BENCHMARK_FINDING in result.limitations


@_REAL
def test_the_real_planner_reports_a_missing_stock_as_unavailable_without_loading_the_library():
    request = _real_request()
    request.config["stock"]["n1"] = str(_STOCK_KEYS) + ".gone"
    began = time.monotonic()
    result = host.run_planner(request, TARGET, python=_PLANNER_PYTHON)
    assert result.status is RouteStatus.UNAVAILABLE and "stock: the stock file is not there" in result.reason and time.monotonic() - began < 30


def runner_processes() -> set[int] | None:
    """The pids of every process whose command line names the runner script, or None where this machine cannot say. The launcher and the real interpreter both carry that command line, so a leaked one of either shows."""
    if os.name != "nt":
        out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout
        return {int(line.split()[0]) for line in out.splitlines()[1:] if "aizynth_runner.py" in line and "ps -eo" not in line}
    command = "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*aizynth_runner.py*' -and $_.CommandLine -notlike '*Get-CimInstance*' } | Select-Object -ExpandProperty ProcessId"
    done = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=120)
    return {int(token) for token in done.stdout.split() if token.isdigit()} if done.returncode == 0 else None


@_REAL
def test_cancelling_the_real_planner_leaves_no_process_that_is_running_the_runner():
    before = runner_processes()
    if before is None:
        pytest.skip("this machine cannot list processes by command line")
    cancel = threading.Event()
    midway: set[int] = set()

    def cancel_once_the_child_has_been_seen() -> None:
        # Cancel only after the listing has actually shown the running child (a fixed delay raced a slow PowerShell under load), and never later than 60 s.
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not midway:
            midway.update((runner_processes() or set()) - before)
        cancel.set()

    threading.Thread(target=cancel_once_the_child_has_been_seen, daemon=True).start()
    began = time.monotonic()

    result = host.run_planner(_real_request(iterations=100000), TARGET, python=_PLANNER_PYTHON, cancel=cancel)

    assert result.status is RouteStatus.CANCELLED and time.monotonic() - began < 60
    assert midway - before, "the process listing never saw the running child, so 'none left' below would prove nothing"
    time.sleep(2.0)
    assert runner_processes() - before == set()


def test_every_plan_carries_what_was_measured_about_the_planner_beside_the_standing_limitations():
    for name in ("aspirin_it100", "caffeine_it100"):
        result = parse(name)
        assert result.limitations[: len(STANDARD_LIMITATIONS)] == STANDARD_LIMITATIONS and host.BENCHMARK_FINDING in result.limitations, name
        assert host.BENCHMARK_FINDING in result.all_limitations()


def test_the_benchmark_finding_says_only_what_the_result_files_say():
    """The sentence is typed by hand, so each figure is held to the rows of the result file it comes from, which a re-run would change: protocol 3 (`RESULT_3.md`, routes after the model's training data, the figure to quote) and protocol 2 (`RESULT_2.md`, patent targets the model probably saw, whose M2 is the count of the first 10 routes shown)."""
    bench = Path(__file__).parent.parent / "benchmarks" / "synthesis"
    result_3 = (bench / "RESULT_3.md").read_text(encoding="utf-8")
    result_2 = (bench / "RESULT_2.md").read_text(encoding="utf-8")
    finding = host.BENCHMARK_FINDING
    # protocol 3: (the figure as the sentence writes it, the figure as the file writes it)
    for sentence, in_file in (
        ("13 of 51 targets, 25.5% (95% interval 15.5% to 38.9%)", "13 of 51 = 0.255 (95% 0.155 to 0.389)"),
        ("5 of 15 where", "| 1 | 15 | 5 (0.33) |"),
        ("6 of 10 at 2 steps", "| 2 | 10 | 6 (0.60) |"),
        ("2 of 14 at 3", "| 3 | 14 | 2 (0.14) |"),
        ("0 of 12 at 4", "| 4 | 12 | 0 |"),
        ("17 of the 51 targets", "| 13 | 13 | 15 | 15 | 17 | 43 |"),  # the primary stock's row: exact, lenient, M1, pool, a same-materials route in the first 10, solved
    ):
        assert sentence in finding and in_file in result_3, sentence
    assert "LOWER" in result_3.splitlines()[0] and "lower than the planner's rate on patent routes" in finding, "the reading was LOWER than protocol 2's depth-matched rates and the sentence says so"
    # protocol 2: the same rows as before, now the patent-target figure
    for sentence, in_file in (("96.7%", "**0.967** (290)"), ("41.7%", "**0.417 (125 of 300)**"), ("54.7%", "| 0.547 |")):
        assert sentence in finding and in_file in result_2, sentence
    # the depth figures are the file's table row by row: reference depth 2, 3 and 4, in the order M1 / M2 / pool
    for sentence, row in (("81%", "**0.86 / 0.81 / 0.86**"), ("39%", "**0.54 / 0.39 / 0.55**"), ("4% at 4", "**0.20 / 0.04 / 0.24**")):
        assert sentence in finding and row in result_2, sentence
    assert "51%" in finding and "the first route is shorter than the reference in 51%" in result_2
    assert "37.3%" not in finding and "53.3%" not in finding, "protocol 1's figure is superseded and the PaRoutes count is not the one quoted"
    assert "first 10 routes it showed" in finding, "the figure is about the list a person is shown"
    # the larger figure is never quoted alone, and the caveats stay
    assert finding.index("13 of 51") < finding.index("41.7%"), "protocol 3's figure comes first"
    assert "probably trained on those same reactions" in finding and "41.7% is not a figure for a molecule the model has not seen" in finding, "the contamination caveat is not dropped"
    assert "not evidence that a plan is wrong" in finding and "normal outcome, not a fault" in finding, "a different or missing route is not a fault"
    assert "feasibility was not measured" in finding and "not as known routes" in finding
    assert "known routes" in finding and "valid" not in finding.replace("internally consistent", ""), "never says a route is valid or feasible"