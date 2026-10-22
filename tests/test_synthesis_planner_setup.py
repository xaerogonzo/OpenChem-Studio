"""Locating and verifying the synthesis planner (`openchem.services.synthesis_planner_setup`, the runner's `inspect` request, `chem.aizynth_planner.inspect_environment` and the External Tools tab): each thing that can be wrong is named, nothing is downloaded or removed, and the planning service reads what the tab writes.

The planner's environment is replaced by stand-ins (a fake `yaml` and a fake `aizynthfinder` dist-info on the child's path) so these run anywhere; the last tests use the real environment where it is installed."""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from openchem.app.settings import Settings
from openchem.chem import aizynth_planner as host
from openchem.chem import aizynth_runner as runner
from openchem.domain.synthesis_route import RouteStatus, SearchLimits, TargetIdentity
from openchem.events.base import EventBus
from openchem.services import synthesis_planner_setup as setup
from openchem.services.tool_download_service import ToolVerificationError

TARGET = TargetIdentity(molecule_uuid="u", canonical_smiles="CCO", fingerprint="f")


# --- the runner's inspect request, with stand-in libraries --------------------------------------------------------------------------------------


@pytest.fixture
def fake_env(tmp_path):
    """A folder that makes the runner believe it is in the planner's environment: a dist-info for aizynthfinder and a `yaml` whose `safe_load` reads JSON (a subset of YAML)."""
    lib = tmp_path / "fakelib"
    (lib / "aizynthfinder-4.4.1.dist-info").mkdir(parents=True)
    (lib / "aizynthfinder-4.4.1.dist-info" / "METADATA").write_text("Metadata-Version: 2.1\nName: aizynthfinder\nVersion: 4.4.1\n", encoding="utf-8")
    (lib / "yaml.py").write_text("import json\n\ndef safe_load(stream):\n    return json.load(stream)\n", encoding="utf-8")
    return lib


def run_inspect(request: dict | bytes, lib: Path | None = None):
    payload = request if isinstance(request, bytes) else json.dumps(request).encode("utf-8")
    env = dict(os.environ, PYTHONPATH=str(lib) if lib else "", PYTHONIOENCODING="utf-8")
    done = subprocess.run([sys.executable, str(host.RUNNER_PATH)], input=payload, capture_output=True, env=env, timeout=120)
    lines = done.stdout.decode("utf-8").strip().splitlines()
    return done.returncode, json.loads(lines[-1]), lines


def write_config(folder: Path, config: dict, name: str = "config.yml") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_the_schemas_of_the_inspect_exchange_are_equal_in_both_halves():
    assert host.INSPECT_REQUEST_SCHEMA == runner.INSPECT_REQUEST_SCHEMA and host.INSPECT_SCHEMA == runner.INSPECT_SCHEMA


def test_inspect_reads_the_configuration_makes_relative_paths_absolute_and_lists_the_names(tmp_path, fake_env):
    folder = tmp_path / "caf\u00e9 data"  # a non-ASCII folder, read as UTF-8
    config = write_config(
        folder,
        {
            "expansion": {"uspto": ["uspto_model.onnx", "uspto_templates.csv.gz"], "ring": ["sub/ring.onnx", str(tmp_path / "abs.csv")]},
            "filter": {"uspto": "filter.onnx"},
            "stock": {"zinc": "zinc.hdf5", "mongo": {"type": "mongodb"}},
            "search": {"iteration_limit": 100},
        },
    )

    code, document, lines = run_inspect({"schema": runner.INSPECT_REQUEST_SCHEMA, "config_path": str(config)}, fake_env)

    assert code == 0 and len(lines) == 1 and document["schema"] == runner.INSPECT_SCHEMA and document["status"] == "ok"
    resolved = document["config"]
    assert resolved["expansion"]["uspto"] == [str(folder / "uspto_model.onnx"), str(folder / "uspto_templates.csv.gz")]
    assert resolved["expansion"]["ring"] == [str(folder / "sub" / "ring.onnx"), str(tmp_path / "abs.csv")]  # an absolute path is left alone
    assert resolved["filter"]["uspto"] == str(folder / "filter.onnx") and resolved["stock"]["zinc"] == str(folder / "zinc.hdf5")
    assert resolved["stock"]["mongo"] == {"type": "mongodb"} and resolved["search"] == {"iteration_limit": 100}  # what is not a path is not touched
    assert document["keys"] == {"expansion": ["ring", "uspto"], "filter": ["uspto"], "stock": ["mongo", "zinc"]}
    assert document["packages"]["aizynthfinder"] == "4.4.1" and document["packages"]["numpy"] is None or isinstance(document["packages"]["numpy"], str)


def test_inspect_without_the_planner_installed_says_so_and_names_nothing_else(tmp_path):
    config = write_config(tmp_path, {"stock": {}})
    code, document, _ = run_inspect({"schema": runner.INSPECT_REQUEST_SCHEMA, "config_path": str(config)})  # no fake dist-info on the path
    assert code == 1 and (document["status"], document["kind"]) == ("unavailable", "planner") and "not installed" in document["reason"]


def test_inspect_with_a_missing_file_or_no_yaml_or_a_bad_file_names_each(tmp_path, fake_env):
    code, document, _ = run_inspect({"schema": runner.INSPECT_REQUEST_SCHEMA, "config_path": str(tmp_path / "gone.yml")}, fake_env)
    assert (document["status"], document["kind"]) == ("unavailable", "config") and "not there" in document["reason"]

    config = write_config(tmp_path, {"stock": {}})
    no_yaml = tmp_path / "noyaml"
    (no_yaml / "aizynthfinder-4.4.1.dist-info").mkdir(parents=True)
    (no_yaml / "aizynthfinder-4.4.1.dist-info" / "METADATA").write_text("Metadata-Version: 2.1\nName: aizynthfinder\nVersion: 4.4.1\n", encoding="utf-8")
    _, document, _ = run_inspect({"schema": runner.INSPECT_REQUEST_SCHEMA, "config_path": str(config)}, no_yaml)
    assert (document["status"], document["kind"]) == ("failed", "yaml")

    broken = tmp_path / "broken.yml"
    broken.write_text("{not json", encoding="utf-8")
    _, document, _ = run_inspect({"schema": runner.INSPECT_REQUEST_SCHEMA, "config_path": str(broken)}, fake_env)
    assert (document["status"], document["kind"]) == ("failed", "config") and "JSONDecodeError" in document["reason"]

    listing = tmp_path / "list.yml"
    listing.write_text("[1, 2]", encoding="utf-8")
    _, document, _ = run_inspect({"schema": runner.INSPECT_REQUEST_SCHEMA, "config_path": str(listing)}, fake_env)
    assert (document["status"], document["kind"]) == ("failed", "config") and "not a mapping" in document["reason"]


def test_inspect_with_no_path_is_a_bad_request_and_the_exit_code_follows_the_status(tmp_path, fake_env):
    code, document, _ = run_inspect({"schema": runner.INSPECT_REQUEST_SCHEMA}, fake_env)
    assert code == 1 and (document["status"], document["kind"]) == ("failed", "bad_request")
    ok_config = write_config(tmp_path, {"expansion": {}})
    code, document, _ = run_inspect({"schema": runner.INSPECT_REQUEST_SCHEMA, "config_path": str(ok_config)}, fake_env)
    assert code == 0 and document["status"] == "ok"


def test_the_search_request_is_still_a_search_request(tmp_path):
    code, document, _ = run_inspect({"schema": runner.REQUEST_SCHEMA, "target_smiles": "CCO"})
    assert (document["schema"], document["kind"]) == (runner.RUN_SCHEMA, "bad_request")  # not mistaken for an inspection


# --- the host's call ---------------------------------------------------------------------------------------------------------------------


def stand_in(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "inspect_runner.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def ok_document(**over) -> dict:
    document = {"schema": host.INSPECT_SCHEMA, "status": "ok", "config": {"expansion": {"uspto": ["m", "t"]}, "stock": {"zinc": "s"}}, "keys": {"expansion": ["uspto"], "filter": [], "stock": ["zinc"]}, "packages": {"aizynthfinder": "4.4.1"}}
    document.update(over)
    return document


def inspect_with(tmp_path, body: str, **kw):
    return host.inspect_environment(sys.executable, "config.yml", runner=stand_in(tmp_path, body), **kw)


def printing(document) -> str:
    return f"import sys\nsys.stdin.buffer.read()\nsys.stdout.write({json.dumps(document)!r})\n"


def test_a_good_document_is_an_ok_inspection_with_keys_as_tuples_and_the_version(tmp_path):
    result = inspect_with(tmp_path, printing(ok_document()))
    assert result.ok and result.kind == "" and result.version == "4.4.1" and result.keys == {"expansion": ("uspto",), "filter": (), "stock": ("zinc",)}
    assert result.config["stock"] == {"zinc": "s"}


def test_each_way_the_child_can_answer_badly_is_a_kind(tmp_path):
    cases = {
        "planner": (printing({"schema": host.INSPECT_SCHEMA, "status": "unavailable", "kind": "planner", "reason": "aizynthfinder is not installed", "packages": {"aizynthfinder": None}}), "planner"),
        "config": (printing({"schema": host.INSPECT_SCHEMA, "status": "failed", "kind": "config", "reason": "bad file"}), "config"),
        "garbage": ("import sys\nsys.stdin.buffer.read()\nsys.stdout.write('not json')\n", "malformed"),
        "wrong schema": (printing({"schema": "other", "status": "ok"}), "malformed"),
        "no config": (printing({"schema": host.INSPECT_SCHEMA, "status": "ok", "keys": {}}), "malformed"),
        "not an object": ("import sys\nsys.stdin.buffer.read()\nsys.stdout.write('[1]')\n", "malformed"),
        "nothing": ("import sys\nsys.stdin.buffer.read()\nsys.stderr.write('ImportError: boom')\nsys.exit(3)\n", "failed"),
    }
    for name, (body, kind) in cases.items():
        result = inspect_with(tmp_path, body)
        assert not result.ok and result.kind == kind, name
    nothing = inspect_with(tmp_path, cases["nothing"][0])
    assert "exited with code 3" in nothing.reason and "ImportError: boom" in nothing.reason
    assert inspect_with(tmp_path, cases["planner"][0]).packages == {"aizynthfinder": None}


def test_a_python_that_is_not_there_a_runner_that_is_missing_and_a_hang_are_each_named(tmp_path):
    missing = host.inspect_environment(tmp_path / "no" / "python.exe", "c.yml")
    assert missing.kind == "python" and "was not found" in missing.reason
    blank = host.inspect_environment("", "c.yml")
    assert blank.kind == "python" and "was not found" in blank.reason  # named as missing, not as a program that would not start
    assert host.inspect_environment(sys.executable, "c.yml", runner=tmp_path / "gone.py").kind == "runner"
    began = time.monotonic()
    hung = inspect_with(tmp_path, "import sys, time\nsys.stdin.buffer.read()\ntime.sleep(60)\n", timeout=1.0)
    assert hung.kind == "timeout" and time.monotonic() - began < 20
    not_a_program = tmp_path / "python.exe"
    not_a_program.write_text("this is not an executable", encoding="utf-8")
    assert host.inspect_environment(not_a_program, "c.yml").kind == "python"


def test_the_request_is_an_argument_array_with_isolation_and_the_path_as_ascii_json(tmp_path, monkeypatch):
    seen = {}
    real = subprocess.run

    def spy(args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        return real(args, **kwargs)

    monkeypatch.setattr(host.subprocess, "run", spy)
    inspect_with(tmp_path, printing(ok_document()))
    # inspect_with passes 'config.yml'; use a non-ASCII one for the payload check
    host.inspect_environment(sys.executable, "D:\\caf\u00e9\\config.yml", runner=stand_in(tmp_path, printing(ok_document())))

    assert isinstance(seen["args"], list) and seen["args"][1] == "-I" and not seen["kwargs"].get("shell") and seen["kwargs"]["env"]["PYTHONUTF8"] == "1"
    sent = json.loads(seen["kwargs"]["input"].decode("ascii"))
    assert sent == {"schema": host.INSPECT_REQUEST_SCHEMA, "config_path": "D:\\caf\u00e9\\config.yml"}


# --- the status line ---------------------------------------------------------------------------------------------------------------------


def test_the_status_line_reads_two_paths_and_starts_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the status line started a program")))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the status line started a program")))
    python = tmp_path / "python.exe"
    python.write_text("x", encoding="utf-8")
    config = tmp_path / "config.yml"
    config.write_text("x", encoding="utf-8")

    assert setup.describe_status("", "") == "Not configured: set the Python of the environment AiZynthFinder is installed in"
    assert "Python not found at" in setup.describe_status(str(tmp_path / "gone.exe"), "")
    assert "now set the configuration file" in setup.describe_status(str(python), "")
    assert "Configuration file not found at" in setup.describe_status(str(python), str(tmp_path / "gone.yml"))
    assert setup.describe_status(str(python), str(config)).startswith("Configured:") and "use Test" in setup.describe_status(str(python), str(config))


# --- finding it ---------------------------------------------------------------------------------------------------------------------------


def test_the_config_finder_looks_in_the_folder_and_in_a_data_folder_beside_or_below_it(tmp_path):
    assert setup.find_config(tmp_path) is None
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "config.yaml").write_text("x", encoding="utf-8")
    assert setup.find_config(tmp_path) == tmp_path / "data" / "config.yaml"
    (tmp_path / "config.yml").write_text("x", encoding="utf-8")
    assert setup.find_config(tmp_path) == tmp_path / "config.yml"  # the folder itself wins


@pytest.mark.parametrize("relative", ["python.exe", "Scripts/python.exe", ".venv/Scripts/python.exe", "env/Scripts/python.exe", "bin/python"])
def test_the_python_finder_accepts_the_usual_layouts_but_only_a_python_that_has_the_planner(tmp_path, monkeypatch, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    monkeypatch.setattr(setup, "responds_as_planner", lambda p: False)
    assert setup.find_python(tmp_path) is None  # a Python without the planner is refused
    monkeypatch.setattr(setup, "responds_as_planner", lambda p: True)
    assert setup.find_python(tmp_path) == path
    assert setup.find_python(tmp_path / "nothing") is None


def test_locate_uses_aizynthcli_on_the_path_and_asks_the_python_beside_it(tmp_path, monkeypatch):
    scripts = tmp_path / "env" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "python.exe").write_text("x", encoding="utf-8")
    (scripts / "aizynthcli.exe").write_text("x", encoding="utf-8")
    monkeypatch.setattr(setup.shutil, "which", lambda name: str(scripts / "aizynthcli.exe") if name == "aizynthcli" else None)
    monkeypatch.setattr(setup, "responds_as_planner", lambda p: True)
    assert setup.locate() == scripts / "python.exe"
    monkeypatch.setattr(setup, "responds_as_planner", lambda p: False)
    assert setup.locate() is None
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    assert setup.locate() is None


def test_a_python_without_the_planner_does_not_respond_as_one_and_a_dead_path_does_not_either(tmp_path):
    assert setup.responds_as_planner(sys.executable) is False  # OpenChem's own interpreter has no aizynthfinder
    assert setup.responds_as_planner(tmp_path / "none.exe") is False


# --- what is chosen from the configuration -----------------------------------------------------------------------------------------------


class FakeSettings:
    def __init__(self, **values):
        self.values = {key.replace("__", "/"): value for key, value in values.items()}

    def get(self, key, default=""):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


def inspection(expansion=("uspto",), stock=("zinc",), filters=(), config=None, ok=True):
    return host.PlannerInspection(ok=ok, config=config or {}, keys={"expansion": tuple(expansion), "stock": tuple(stock), "filter": tuple(filters)}, packages={"aizynthfinder": "4.4.1"})


def test_the_defaults_prefer_uspto_and_zinc_take_the_first_otherwise_and_use_no_filter():
    assert setup.select_keys(inspection(), FakeSettings()) == ("uspto", "zinc", None, "")
    assert setup.select_keys(inspection(expansion=("ring", "uspto"), stock=("a", "zinc")), FakeSettings())[:3] == ("uspto", "zinc", None)
    assert setup.select_keys(inspection(expansion=("ring", "other"), stock=("a", "b")), FakeSettings())[:3] == ("ring", "a", None)
    assert setup.select_keys(inspection(filters=("uspto",)), FakeSettings())[2] is None  # a filter is never chosen for the user


def test_a_chosen_name_is_used_and_one_the_configuration_lacks_is_a_problem_not_a_fallback():
    chosen = FakeSettings(aizynthfinder__expansion="ring", aizynthfinder__stock="b", aizynthfinder__filter="uspto")
    assert setup.select_keys(inspection(expansion=("ring", "uspto"), stock=("a", "b"), filters=("uspto",)), chosen) == ("ring", "b", "uspto", "")
    for bad, fragment in ((FakeSettings(aizynthfinder__expansion="nope"), "no expansion named 'nope'"), (FakeSettings(aizynthfinder__stock="nope"), "no stock named 'nope'"), (FakeSettings(aizynthfinder__filter="nope"), "no filter named 'nope'")):
        result = setup.select_keys(inspection(), bad)
        assert result[:3] == (None, None, None) and fragment in result[3]
    assert setup.select_keys(inspection(expansion=()), FakeSettings())[3] == "the configuration has no expansion section"
    assert setup.select_keys(inspection(stock=()), FakeSettings())[3] == "the configuration has no stock section"


@pytest.mark.parametrize("value", ["", "none", "NONE", "  none "])
def test_blank_or_none_means_no_filter_whatever_the_filters_on_offer(value):
    # the whole answer, so "no filter" cannot be confused with the (None, None, None, problem) of a name that is not there
    assert setup.select_keys(inspection(filters=("uspto",)), FakeSettings(aizynthfinder__filter=value)) == ("uspto", "zinc", None, "")


def files(tmp_path):
    paths = {name: tmp_path / name for name in ("model.onnx", "templates.csv.gz", "filter.onnx", "stock.txt")}
    for path in paths.values():
        path.write_text("x", encoding="utf-8")
    config = {"expansion": {"uspto": [str(paths["model.onnx"]), str(paths["templates.csv.gz"])]}, "filter": {"uspto": str(paths["filter.onnx"])}, "stock": {"zinc": str(paths["stock.txt"])}}
    return paths, config


def test_each_file_the_selection_needs_is_checked_on_its_own_and_named(tmp_path):
    paths, config = files(tmp_path)
    look = lambda filter_name="uspto": setup.assets_problem(inspection(config=config, filters=("uspto",)), "uspto", "zinc", filter_name)  # noqa: E731
    assert look() is None and look(None) is None
    for name, kind in (("model.onnx", "model"), ("templates.csv.gz", "templates"), ("filter.onnx", "filter"), ("stock.txt", "stock")):
        paths[name].unlink()
        problem = look()
        assert problem is not None and problem[0] == kind and str(paths[name]) in problem[1], name
        paths[name].write_text("x", encoding="utf-8")
    assert look(None) is None
    paths["filter.onnx"].unlink()
    assert look(None) is None  # no filter chosen, so a missing filter model is not a problem
    assert setup.assets_problem(inspection(config={"expansion": {"uspto": ["only"]}, "stock": {}}), "uspto", "zinc", None)[0] == "config"
    assert setup.assets_problem(inspection(config={"expansion": config["expansion"], "stock": {"zinc": {"type": "mongodb"}}}), "uspto", "zinc", None)[0] == "stock"


# --- the Test button ----------------------------------------------------------------------------------------------------------------------


def good_inspector(config):
    return lambda python, config_path: inspection(config=config, filters=("uspto",))


def test_the_test_names_the_first_thing_wrong_in_order_and_runs_nothing_before_the_files_are_right(tmp_path):
    python = tmp_path / "python.exe"
    python.write_text("x", encoding="utf-8")
    config_file = tmp_path / "config.yml"
    config_file.write_text("x", encoding="utf-8")
    ran = []

    def never_inspect(*a, **k):
        raise AssertionError("inspected too early")

    for args, fragment in (
        (("", ""), "Set the Python"),
        ((str(tmp_path / "gone.exe"), ""), "No Python at"),
        ((str(python), ""), "Set the configuration file"),
        ((str(python), str(tmp_path / "gone.yml")), "No configuration file at"),
    ):
        with pytest.raises(ToolVerificationError, match=fragment):
            setup.verify(*args, inspector=never_inspect, runner=lambda *a, **k: ran.append(1))
    assert ran == []


def test_an_environment_without_the_planner_or_with_a_bad_configuration_is_explained(tmp_path):
    python = tmp_path / "python.exe"
    python.write_text("x", encoding="utf-8")
    config_file = tmp_path / "config.yml"
    config_file.write_text("x", encoding="utf-8")

    def failing(kind, reason):
        return lambda p, c: host.PlannerInspection(ok=False, kind=kind, reason=reason)

    with pytest.raises(ToolVerificationError, match=r"AiZynthFinder is not installed in .*Install it in that environment"):
        setup.verify(str(python), str(config_file), inspector=failing("planner", "x"))
    with pytest.raises(ToolVerificationError, match="the configuration file could not be read"):
        setup.verify(str(python), str(config_file), inspector=failing("config", "the configuration file could not be read (X)"))
    with pytest.raises(ToolVerificationError, match="did not answer within 60 seconds. Try again"):
        setup.verify(str(python), str(config_file), inspector=failing("timeout", "the planner's Python did not answer within 60 seconds"))


def test_a_missing_model_template_filter_or_stock_is_named_by_file_before_any_search_starts(tmp_path):
    python = tmp_path / "python.exe"
    python.write_text("x", encoding="utf-8")
    config_file = tmp_path / "config.yml"
    config_file.write_text("x", encoding="utf-8")
    paths, config = files(tmp_path)
    ran = []
    for name, fragment in (("model.onnx", "policy model file is not there"), ("templates.csv.gz", "template file is not there"), ("stock.txt", "stock file is not there")):
        paths[name].unlink()
        with pytest.raises(ToolVerificationError, match=fragment) as caught:
            setup.verify(str(python), str(config_file), inspector=good_inspector(config), runner=lambda *a, **k: ran.append(1))
        assert str(paths[name]) in str(caught.value) and str(caught.value).endswith(".")
        paths[name].write_text("x", encoding="utf-8")
    paths["filter.onnx"].unlink()
    with pytest.raises(ToolVerificationError, match="filter policy model file is not there"):
        setup.verify(str(python), str(config_file), FakeSettings(aizynthfinder__filter="uspto"), inspector=good_inspector(config), runner=lambda *a, **k: ran.append(1))
    with pytest.raises(ToolVerificationError, match="no stock named 'nope'"):
        setup.verify(str(python), str(config_file), FakeSettings(aizynthfinder__stock="nope"), inspector=good_inspector(config), runner=lambda *a, **k: ran.append(1))
    assert ran == []


def run_verify(tmp_path, result_for, settings=None):
    python = tmp_path / "python.exe"
    python.write_text("x", encoding="utf-8")
    config_file = tmp_path / "config.yml"
    config_file.write_text("x", encoding="utf-8")
    _, config = files(tmp_path)
    seen = {}

    def runner_stub(request, target, **kw):
        seen["request"], seen["target"], seen["kw"] = request, target, kw
        return result_for(request, target)

    message = setup.verify(str(python), str(config_file), settings, inspector=good_inspector(config), runner=runner_stub)
    return message, seen


def planner_identity(request):
    return host.PlannerSetup(python="p", config=request.config, stock=request.stock, expansion=request.expansion, filter=request.filter, limits=request.limits)


def test_the_test_runs_a_trivial_search_with_the_chosen_selection_and_reports_what_answered(tmp_path):
    from openchem.domain.synthesis_route import PlannerIdentity, RouteSet

    def result(request, target):
        return RouteSet(status=RouteStatus.NO_ROUTE, target=target, planner=PlannerIdentity(planner="AiZynthFinder", version="4.4.1", model_identity=request_selection(request), limits=request.limits))

    def request_selection(request):
        return (("expansion", request.expansion), ("stock", request.stock))

    message, seen = run_verify(tmp_path, result)

    assert seen["request"].target_smiles == setup.TEST_TARGET and seen["request"].limits == setup.TEST_LIMITS and seen["request"].filter is None and seen["request"].all_routes is True
    assert seen["target"].molecule_uuid == "external-tools-test" and "cancel" not in seen["kw"]
    assert message.startswith("AiZynthFinder 4.4.1") and "answered a trivial search (aspirin, 20 iterations" in message and "no route within it" in message and "no filter" in message
    assert "Expansion uspto, stock zinc" in message

    chosen = FakeSettings(aizynthfinder__filter="uspto")
    _, seen = run_verify(tmp_path, result, chosen)
    assert seen["request"].filter == "uspto"


@pytest.mark.parametrize("status,reason,fragment", [
    (RouteStatus.UNAVAILABLE, "stock: the stock file is not there: x", "the stock file is not there"),
    (RouteStatus.FAILED, "the planner exited with code 1 and wrote no result. Its last words: ImportError: pyarrow requires NumPy 2 or newer", 'pip install "pyarrow<21"'),
    (RouteStatus.FAILED, "ValueError: not enough values to unpack", "not enough values to unpack"),
])
def test_a_search_that_fails_is_reported_with_the_childs_words_and_the_known_fix(tmp_path, status, reason, fragment):
    from openchem.domain.synthesis_route import RouteSet

    with pytest.raises(ToolVerificationError, match=__import__("re").escape(fragment)):
        run_verify(tmp_path, lambda request, target: RouteSet(status=status, target=target, planner=host._unknown_identity(request), reason=reason, termination=host.SearchTermination.FAILED if status is RouteStatus.FAILED else host.SearchTermination.UNKNOWN))


def test_the_pyarrow_hint_is_only_given_for_that_failure(tmp_path):
    from openchem.domain.synthesis_route import RouteSet

    with pytest.raises(ToolVerificationError) as caught:
        run_verify(tmp_path, lambda r, t: RouteSet(status=RouteStatus.FAILED, target=t, planner=host._unknown_identity(r), reason="some other failure", termination=host.SearchTermination.FAILED))
    assert "pyarrow" not in str(caught.value)


def test_a_found_route_is_counted_in_the_message(tmp_path):
    from openchem.domain.synthesis_route import PlannerIdentity, Route, RouteMolecule, RouteSet, RouteStep

    route = Route(target_smiles="T", steps=(RouteStep(product="T", reactants=("A", "B")),), starting_materials=(RouteMolecule(smiles="A", in_stock=True), RouteMolecule(smiles="B", in_stock=True)), rank=1)
    message, _ = run_verify(tmp_path, lambda r, t: RouteSet(status=RouteStatus.FOUND, target=t, planner=PlannerIdentity(planner="AiZynthFinder", version="4.4.1"), routes=(route,)))
    assert "1 route within it" in message


# --- the setting the planning service reads ---------------------------------------------------------------------------------------------------


def configured(tmp_path, **extra):
    python = tmp_path / "python.exe"
    python.write_text("x", encoding="utf-8")
    config_file = tmp_path / "config.yml"
    config_file.write_text("x", encoding="utf-8")
    paths, config = files(tmp_path)
    settings = FakeSettings(**{"aizynthfinder__python_path": str(python), "aizynthfinder__config_path": str(config_file), **extra})
    return settings, paths, config


def test_the_provider_returns_none_until_both_paths_exist_and_the_environment_answers(tmp_path):
    calls = []
    provider = setup.SetupProvider(FakeSettings(), inspector=lambda *a: calls.append(a))
    assert provider() is None and calls == []
    settings, paths, config = configured(tmp_path)
    settings.set(setup.PYTHON_KEY, str(tmp_path / "gone.exe"))
    assert setup.SetupProvider(settings, inspector=lambda *a: calls.append(a))() is None and calls == []
    settings.set(setup.PYTHON_KEY, str(tmp_path / "python.exe"))
    settings.set(setup.CONFIG_KEY, str(tmp_path / "gone.yml"))
    assert setup.SetupProvider(settings, inspector=lambda *a: calls.append(a))() is None and calls == []
    settings.set(setup.CONFIG_KEY, str(tmp_path / "config.yml"))
    failing = setup.SetupProvider(settings, inspector=lambda p, c: host.PlannerInspection(ok=False, kind="planner", reason="x"))
    assert failing() is None


def test_the_provider_builds_the_setup_the_service_runs_with_the_benchmarks_limits(tmp_path):
    settings, paths, config = configured(tmp_path)
    provider = setup.SetupProvider(settings, inspector=good_inspector(config))

    result = provider()

    assert isinstance(result, host.PlannerSetup) and result.python == settings.get(setup.PYTHON_KEY) and result.config == config
    assert (result.expansion, result.stock, result.filter, result.all_routes) == ("uspto", "zinc", None, True)
    assert result.limits == SearchLimits(iteration_limit=500, time_limit_seconds=1800.0, max_transforms=10) == setup.DEFAULT_LIMITS


def test_the_provider_does_not_start_a_program_for_a_file_it_has_already_read(tmp_path):
    settings, paths, config = configured(tmp_path)
    calls = []

    def counting(python, config_path):
        calls.append(config_path)
        return inspection(config=config, filters=("uspto",))

    provider = setup.SetupProvider(settings, inspector=counting)
    provider()
    provider()
    settings.set(setup.FILTER_KEY, "uspto")  # a different choice from the same file needs no second reading
    assert provider().filter == "uspto"
    assert len(calls) == 1

    config_path = Path(settings.get(setup.CONFIG_KEY))
    stat = config_path.stat()
    os.utime(config_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    provider()
    assert len(calls) == 2  # the file changed, so it is read again


def test_a_failed_reading_is_not_kept_so_fixing_the_environment_needs_no_restart(tmp_path):
    settings, paths, config = configured(tmp_path)
    answers = [host.PlannerInspection(ok=False, kind="planner", reason="x"), inspection(config=config)]
    provider = setup.SetupProvider(settings, inspector=lambda p, c: answers.pop(0))
    assert provider() is None
    assert provider() is not None


def test_a_selection_or_a_file_that_is_not_right_is_none_and_the_test_says_which(tmp_path):
    settings, paths, config = configured(tmp_path, aizynthfinder__stock="nope")
    provider = setup.SetupProvider(settings, inspector=good_inspector(config))
    assert provider() is None
    settings.set(setup.STOCK_KEY, "")
    assert provider() is not None
    paths["stock.txt"].unlink()
    assert provider() is None


def test_the_container_reads_the_settings_the_tab_writes(qapp):
    from openchem.bootstrap import build_service_container

    service = build_service_container().synthesis_planning_service
    assert isinstance(service._setup_provider, setup.SetupProvider)


# --- the tab -----------------------------------------------------------------------------------------------------------------------------


def wait_for(qapp, condition, seconds=20.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError("the condition never became true")


def test_the_descriptor_is_locate_only_with_two_paths_and_no_way_to_obtain_or_remove(qapp):
    from openchem.ui.dialogs import external_tool_catalog as catalog

    descriptor = catalog.aizynthfinder()
    assert descriptor.key == "aizynthfinder" and descriptor.obtainable is False and descriptor.removable is False and descriptor.test_with_settings is True
    assert descriptor.setting_key == setup.PYTHON_KEY and [e.setting_key for e in descriptor.extra_paths] == [setup.CONFIG_KEY]
    assert [label for label, _ in descriptor.vendor_links] == ["Get AiZynthFinder...", "AiZynthFinder Documentation..."]
    with pytest.raises(RuntimeError, match="does not download or install"):
        descriptor.run(lambda _: None)


def test_the_dialog_tab_writes_both_paths_to_the_settings_and_shows_the_status(qapp, tmp_path):
    from openchem.ui.dialogs.external_tools_pages import ExternalToolsPages

    settings = Settings(EventBus())
    dialog = ExternalToolsPages(settings, focus="aizynthfinder")
    tab = dialog._tab_for("aizynthfinder")
    assert dialog.current_tool() == "aizynthfinder" and not tab.setup_button.isVisibleTo(tab) and not tab.remove_button.isVisibleTo(tab)
    assert tab.status_label.text().startswith("Not configured")

    python = tmp_path / "python.exe"
    python.write_text("x", encoding="utf-8")
    config_file = tmp_path / "config.yml"
    config_file.write_text("x", encoding="utf-8")
    dialog._aizynthfinder_path_edit.setText(str(python))
    tab.path_row.commit()
    assert settings.get(setup.PYTHON_KEY, "") == str(python) and "now set the configuration file" in tab.status_label.text()
    dialog._aizynthfinder_extra1_path_edit.setText(str(config_file).replace("\\", "/"))
    tab.extra_rows[0].commit()
    assert settings.get(setup.CONFIG_KEY, "") == str(config_file) and tab.status_label.text().startswith("Configured:")  # stored in native form, as every path row does
    dialog._aizynthfinder_extra1_path_edit.setText("")
    tab.extra_rows[0].commit()
    assert settings.get(setup.CONFIG_KEY, "x") == "" and "now set the configuration file" in tab.status_label.text()


def test_the_test_button_passes_both_paths_and_the_settings_and_shows_the_answer_or_the_refusal(qapp, tmp_path):
    from openchem.ui.dialogs import external_tool_catalog as catalog
    from openchem.ui.dialogs.external_tool_tabs import ManagedExecutableTab

    settings = Settings(EventBus())
    settings.set(setup.PYTHON_KEY, "P")
    settings.set(setup.CONFIG_KEY, "C")
    seen = []

    def fake_test(python, config, settings=None):
        seen.append((python, config, settings))
        if python == "FAIL":
            raise ToolVerificationError("the stock file is not there: x.")
        return "AiZynthFinder 4.4.1 answered a trivial search."

    descriptor = dataclasses.replace(catalog.aizynthfinder(), describe_test=fake_test)
    tab = ManagedExecutableTab(descriptor, None, settings=settings, remove_button_factory=lambda parent, key, label: __import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton(label, parent))

    tab.test_button.click()
    wait_for(qapp, lambda: tab.status_label.text().startswith("AiZynthFinder 4.4.1"))
    assert seen == [("P", "C", settings)] and tab.test_button.isEnabled()

    tab.path_row.edit.setText("FAIL")
    tab.test_button.click()
    wait_for(qapp, lambda: tab.status_label.text().startswith("Test failed"))
    assert tab.status_label.text() == "Test failed: the stock file is not there: x." and tab.test_button.isEnabled()


# --- the real planner, where it is installed ----------------------------------------------------------------------------------------------------


_PLANNER_PYTHON = Path("D:/_scratch/aizynth/env/Scripts/python.exe")
_PLANNER_CONFIG = Path("D:/_scratch/aizynth/data/config.yml")
_REAL = pytest.mark.skipif(not (_PLANNER_PYTHON.exists() and _PLANNER_CONFIG.exists()), reason="the planner environment is not on this machine")


@_REAL
def test_the_real_environment_is_read_and_its_python_answers_as_a_planner():
    result = host.inspect_environment(_PLANNER_PYTHON, _PLANNER_CONFIG)
    assert result.ok and result.version == "4.4.1" and "uspto" in result.keys["expansion"] and "zinc" in result.keys["stock"]
    assert all(os.path.isabs(item) for entry in result.config["expansion"].values() for item in entry)
    assert setup.responds_as_planner(_PLANNER_PYTHON) is True
    assert setup.find_python(_PLANNER_PYTHON.parent.parent) == _PLANNER_PYTHON and setup.find_config(_PLANNER_CONFIG.parent) == _PLANNER_CONFIG


@_REAL
def test_the_real_environment_with_the_wrong_python_or_a_missing_stock_is_named(tmp_path):
    wrong = host.inspect_environment(sys.executable, _PLANNER_CONFIG)
    assert not wrong.ok and wrong.kind == "planner"
    with pytest.raises(ToolVerificationError, match="not installed in"):
        setup.verify(sys.executable, str(_PLANNER_CONFIG))
    bad = tmp_path / "config.yml"
    bad.write_text("expansion:\n  uspto:\n    - " + str(_PLANNER_CONFIG.parent / "uspto_model.onnx") + "\n    - " + str(_PLANNER_CONFIG.parent / "uspto_templates.csv.gz") + "\nstock:\n  zinc: " + str(tmp_path / "missing_stock.hdf5") + "\n", encoding="utf-8")
    with pytest.raises(ToolVerificationError, match="stock file is not there"):
        setup.verify(str(_PLANNER_PYTHON), str(bad))


def test_the_tab_re_reads_both_paths_when_something_else_changed_them(qapp, tmp_path):
    from openchem.ui.dialogs.external_tools_pages import ExternalToolsPages

    settings = Settings(EventBus())
    dialog = ExternalToolsPages(settings, focus="aizynthfinder")
    tab = dialog._tab_for("aizynthfinder")
    python = tmp_path / "python.exe"
    python.write_text("x", encoding="utf-8")
    config_file = tmp_path / "config.yml"
    config_file.write_text("x", encoding="utf-8")

    settings.set(setup.PYTHON_KEY, str(python))  # a removal elsewhere, or a drive script, changed the settings under the open tab
    settings.set(setup.CONFIG_KEY, str(config_file))
    tab.refresh()

    assert tab.path_row.text() == str(python) and tab.extra_rows[0].text() == str(config_file) and tab.status_label.text().startswith("Configured:")
