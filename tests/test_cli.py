"""The headless command line: its contract, its boundaries, and its agreement with the app.

What is pinned here, and why each is a thing that fails silently otherwise:

* **No toolkit comes with it.** The suite's conftest imports Qt for every test, so this
  runs a clean interpreter -- anything weaker would pass whatever the CLI imported.
* **The CLI path equals the application's path.** `cli.calculation` reproduces what
  `_CalculationTask._run` does around `registry.compute`; the real task is run beside
  it, on the same model, and what each produced is compared. Without this the two are
  the same only until somebody changes one.
* **"pure_read" is measured.** Every runnable calculator is run with file writes,
  subprocesses, sockets and temp files recorded, and the one exception is the one the
  CLI refuses by name.
* **One envelope on stdout, whatever happens** -- including a calculator that prints and
  a run that passes its deadline.
* **Status is the application's own word.** `needs_setup` and `needs_input` are not
  failures and not successes; a returned value is not a pass.
"""

from __future__ import annotations

import builtins
import json
import re
import socket
import subprocess
import sys
import tempfile
import time

import pytest

from openchem.cli import calculation, commands
from openchem.cli.commands import EXIT_FAILED, EXIT_OK, EXIT_PREREQUISITE, EXIT_USAGE, main
from openchem.cli.serialise import result_payload, to_plain

ETHANOL = "CCO"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


def run(capsys, *argv: str) -> tuple[int, dict]:
    """One in-process invocation. Asserts the stdout contract on the way."""
    code = main(list(argv))
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 1, f"stdout must be exactly one envelope, got {lines!r}"
    envelope = json.loads(lines[0])
    assert envelope["ok"] == (code == EXIT_OK)
    return code, envelope


def calculate(capsys, smiles: str, calculator: str, *extra: str) -> tuple[int, dict]:
    return run(capsys, "calculate", "--smiles", smiles, "--calculator", calculator,
               *extra, "--json")


# -- boundaries ---------------------------------------------------------------


def _clean_interpreter(code: str) -> str:
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          timeout=180)
    assert done.returncode == 0, done.stderr[-2000:]
    return done.stdout.strip()


def test_the_command_line_loads_no_toolkit_even_after_running_a_calculator():
    out = _clean_interpreter(
        "import io, sys\n"
        "from openchem.cli.commands import main\n"
        "real, sys.stdout = sys.stdout, io.StringIO()\n"
        "code = main(['calculate', '--smiles', 'CCO', '--calculator', 'logd', '--json'])\n"
        "sys.stdout = real\n"
        "bad = sorted({m.split('.')[0] for m in sys.modules} & {'PySide6', 'shiboken6'})\n"
        "print(code, bad)\n"
    )
    assert out == "0 []", f"expected a clean run with no toolkit, got {out}"


def test_the_command_line_does_not_reach_the_application_or_the_widgets():
    out = _clean_interpreter(
        "import sys\n"
        "import openchem.cli.commands\n"
        "print(sorted(m for m in sys.modules if m.startswith(('openchem.app', 'openchem.ui'))))\n"
    )
    assert out == "[]"


# -- the manifest ---------------------------------------------------------------


def test_the_manifest_names_the_tool_and_is_self_scoped(capsys):
    _, envelope = run(capsys, "commands", "--json")
    data = envelope["data"]
    assert data["tool"]["name"] == "openchem-cli"
    assert data["tool"]["scope"] == "self"
    assert data["tool"]["schema_version"] == commands.SCHEMA_VERSION
    assert [c["cli"] for c in data["commands"]] == [c.name for c in commands.COMMANDS]
    assert {c["side_effect"] for c in data["commands"]} == {"pure_read"}
    assert all(i["unattended_safe"] for i in data["invocation"].values())


def test_the_manifest_is_read_from_the_parser_not_restated(capsys):
    _, envelope = run(capsys, "commands", "--json")
    flags = {a["flag"]: a for a in envelope["data"]["invocation"]["calculate"]["args"]}
    assert flags["--smiles"]["required"] is True
    assert flags["--param"]["multiple"] is True
    assert flags["--timeout"]["kind"] == "number"
    assert flags["--conformer"]["kind"] == "flag"
    assert "--help" not in flags


# -- the calculators list ---------------------------------------------------------


def test_every_registered_calculator_is_listed_and_the_refused_one_says_why(capsys):
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    _, envelope = run(capsys, "calculators", "--json")
    rows = envelope["data"]["calculators"]
    assert [r["id"] for r in rows] == [d.calculator_id for d in CALCULATOR_DEFINITIONS]
    refused = {r["id"]: r["cli_reason"] for r in rows if not r["cli_runnable"]}
    assert set(refused) == set(calculation.EXTERNAL_EFFECT_CALCULATORS)
    assert all(refused.values())
    assert all(r["support"]["stage"] for r in rows)


def test_a_calculator_can_be_asked_for_by_id_and_an_unknown_one_is_refused(capsys):
    _, envelope = run(capsys, "calculators", "--id", "logd", "--json")
    (row,) = envelope["data"]["calculators"]
    assert [p["name"] for p in row["parameters"]][0] == "pH"
    code, envelope = run(capsys, "calculators", "--id", "nope", "--json")
    assert code == EXIT_USAGE


def test_every_name_on_the_refusal_list_is_a_registered_calculator():
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    registered = {d.calculator_id for d in CALCULATOR_DEFINITIONS}
    assert set(calculation.EXTERNAL_EFFECT_CALCULATORS) <= registered


# -- statuses and exit codes ---------------------------------------------------------


def test_a_ready_calculation_reports_the_result_and_what_it_was_run_on(capsys):
    code, envelope = calculate(capsys, ETHANOL, "elemental_analysis")
    assert code == EXIT_OK
    data = envelope["data"]
    assert data["status"] == "ready"
    assert data["input"]["canonical_smiles"] == "CCO"
    assert data["input"]["calculation_input"] == "drawing"
    assert data["input"]["input_fingerprint"]
    assert data["result"]["kind"] == "ReportResult"
    assert "C2H6O" in json.dumps(data["result"]["payload"])
    # What it was run with travels in the result, so it can be replayed.
    assert "input_parameters" in data["result"]["payload"]["provenance"]["parameters"]


@pytest.mark.parametrize("calculator, status, exit_code", [
    ("lewis_adduct", "needs_input", EXIT_USAGE),
    ("pka", "needs_setup", EXIT_PREREQUISITE),
    ("griffin_hlb", "inapplicable", EXIT_FAILED),
])
def test_a_refusal_keeps_its_kind_and_maps_to_its_own_exit_code(capsys, calculator, status, exit_code):
    """None of these is a success and none is a crash: the application's own kind
    says what the person has to do, and the exit code carries it."""
    code, envelope = calculate(capsys, ETHANOL, calculator)
    assert (code, envelope["data"]["status"]) == (exit_code, status)
    assert envelope["error"]
    assert envelope["data"]["result"] is None or envelope["data"]["refusal"] is None


def test_a_calculator_that_needs_geometry_says_so_and_then_runs_with_a_conformer(capsys):
    code, envelope = calculate(capsys, ASPIRIN, "dipole_moment")
    assert (code, envelope["data"]["status"]) == (EXIT_FAILED, "failed")
    assert "2D" in envelope["error"]

    code, envelope = calculate(capsys, ASPIRIN, "dipole_moment", "--conformer")
    assert (code, envelope["data"]["status"]) == (EXIT_OK, "ready")
    conformer = envelope["data"]["input"]["conformer"]
    assert conformer == {"requested": True, "generated": True, "optimized": False,
                         "seed": calculation.DEFAULT_CONFORMER_SEED, "error": ""}
    assert any("unoptimised" in w for w in envelope["warnings"])


def test_the_same_question_gives_the_same_document(capsys):
    """Everything is repeatable except the two timestamps the result stamps itself with
    -- measured over twelve runs: those, and `payload_bytes`, which moves by a byte
    because a timestamp's decimal form has a varying number of digits. Nothing else."""
    def document() -> str:
        _, envelope = calculate(capsys, ASPIRIN, "dipole_moment", "--conformer")
        text = json.dumps(envelope)
        text = re.sub(r'"timestamp": [0-9.e+-]+', '"timestamp": 0', text)
        return re.sub(r'"payload_bytes": \d+', '"payload_bytes": 0', text)

    assert document() == document()


def test_a_different_conformer_seed_is_a_different_geometry(capsys):
    def fingerprint(seed: str) -> str:
        _, envelope = calculate(capsys, ASPIRIN, "dipole_moment", "--conformer",
                                "--conformer-seed", seed)
        return envelope["data"]["input"]["input_fingerprint"]

    assert fingerprint("1") != fingerprint("2")


# -- usage -------------------------------------------------------------------------


@pytest.mark.parametrize("argv, fragment", [
    (("--smiles", ETHANOL, "--calculator", "nope"), "no calculator"),
    (("--smiles", ETHANOL, "--calculator", "iupac_name"), "Java"),
    (("--smiles", "not a smiles", "--calculator", "logd"), "parse"),
    (("--smiles", ETHANOL, "--calculator", "logd", "--param", "bogus=1"), "bogus"),
    (("--smiles", ETHANOL, "--calculator", "logd", "--param", "pH=abc"), "number"),
    (("--smiles", ETHANOL, "--calculator", "logd", "--param", "pH"), "name=value"),
    (("--smiles", ETHANOL, "--calculator", "logd", "--timeout", "0"), "positive"),
])
def test_an_invocation_that_cannot_run_is_an_envelope_with_a_usage_exit(capsys, argv, fragment):
    code, envelope = run(capsys, "calculate", *argv, "--json")
    assert code == EXIT_USAGE
    assert fragment in envelope["error"]
    assert envelope["data"] == {}


def test_a_misspelt_parameter_is_refused_because_the_registry_would_pass_it_through():
    """`active_parameters` hands keys no parameter declares straight to the
    calculator, so a typo would otherwise be a silently different calculation."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    definition = next(d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "logd")
    with pytest.raises(commands.UsageProblem):
        commands._parameters(definition, ["ph=7"])
    assert commands._parameters(definition, ["pH=3"])["pH"] == 3.0


def test_parameters_are_coerced_to_their_declared_kind_and_range():
    from openchem.domain.calculator import CalculatorParameter

    def parameter(kind, **extra):
        return CalculatorParameter(name="x", label="x", kind=kind, default=extra.pop("default", 0), **extra)

    assert commands._coerce("c", parameter("int"), "3") == 3
    assert commands._coerce("c", parameter("float", minimum=0.0, maximum=14.0), "7.4") == 7.4
    assert commands._coerce("c", parameter("bool", default=False), "Yes") is True
    assert commands._coerce("c", parameter("bool", default=False), "off") is False
    assert commands._coerce("c", parameter("choice", choices=["a", "b"], default="a"), "b") == "b"
    for kind, bad in (("int", "3.5"), ("float", "nan"), ("float", "inf"), ("bool", "maybe"),
                      ("choice", "c")):
        with pytest.raises(commands.UsageProblem):
            commands._coerce("c", parameter(kind, choices=["a", "b"], default="a"), bad)
    with pytest.raises(commands.UsageProblem):
        commands._coerce("c", parameter("float", minimum=0.0, maximum=14.0), "15")
    with pytest.raises(commands.UsageProblem):
        commands._coerce("c", parameter("float", minimum=0.0, maximum=14.0), "-1")


# -- agreement with the application ----------------------------------------------


class _Bus:
    """The only part of the event bus the task uses."""

    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


def _without_timestamps(value):
    if isinstance(value, dict):
        return {k: _without_timestamps(v) for k, v in value.items() if k != "timestamp"}
    if isinstance(value, list):
        return [_without_timestamps(v) for v in value]
    return value


def _the_application_ran(registry, engine, model, calculator_id, parameters):
    """The real `_CalculationTask`, synchronously, and the result it recorded."""
    from openchem.domain.calculator import CalculationRequest
    from openchem.events.events import ResultRecorded
    from openchem.services.descriptor_service import _CalculationTask

    bus = _Bus()
    _CalculationTask(
        registry, engine, model,
        CalculationRequest(calculator_id=calculator_id, molecule_uuid=model.uuid,
                           parameters=parameters),
        bus,
    ).run()
    recorded = [e.stored.result for e in bus.events if isinstance(e, ResultRecorded)]
    assert len(recorded) == 1, f"{calculator_id}: expected one recorded result"
    return recorded[0]


#: (smiles, calculator, with a conformer). Chosen to cover every status, a refusal that
#: is raised and one that is returned, and four result shapes.
PARITY = (
    (ETHANOL, "elemental_analysis", False),     # ReportResult, ready
    (ETHANOL, "crippen_logp_contrib", False),   # PerAtomDataset, ready
    (ETHANOL, "tautomers", False),              # StructureSetResult, ready
    (ETHANOL, "lewis_adduct", False),           # needs_input
    (ETHANOL, "pka", False),                    # needs_setup
    (ETHANOL, "griffin_hlb", False),            # inapplicable
    (ETHANOL, "detonation", False),             # a raised refusal
    (ASPIRIN, "dipole_moment", False),          # returned failure: no 3D
    (ASPIRIN, "dipole_moment", True),           # geometry, ready
    (ASPIRIN, "geometry_analysis", True),       # geometry report
)


@pytest.mark.parametrize("smiles, calculator, conformer", PARITY)
def test_the_cli_path_agrees_with_the_application_path(smiles, calculator, conformer):
    """What `DescriptorService` would have produced for this calculator, on this
    molecule, with this conformer -- compared with what the command line produced.

    A returned result is compared whole (provenance included, timestamps aside); a
    refusal is compared by the status the application reads back from it, and by its
    code."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain import result_status as rs
    from openchem.domain.refusal_kinds import REFUSAL_KEY

    registry = calculation.build_registry()
    engine = ChemistryEngine()
    model, _ = calculation.build_model(engine, smiles, conformer=conformer, seed=1)
    definition = next(d for d in CALCULATOR_DEFINITIONS if d.calculator_id == calculator)
    parameters = {p.name: p.default for p in definition.parameters}

    ours = calculation.run_calculator(registry, engine, model, calculator, parameters)
    theirs = _the_application_ran(registry, engine, model, calculator, parameters)

    assert ours.status == rs.status_of(theirs)
    if ours.result is not None:
        assert _without_timestamps(to_plain(ours.result, [])) == _without_timestamps(
            to_plain(theirs, []))
    elif ours.refusal is not None:
        assert ours.refusal["code"] == theirs.provenance.parameters[REFUSAL_KEY]


def test_the_parity_cases_cover_every_status_the_application_has_for_a_calculator():
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.chem.engine import ChemistryEngine

    registry = calculation.build_registry()
    engine = ChemistryEngine()
    seen = set()
    for smiles, calculator, conformer in PARITY:
        model, _ = calculation.build_model(engine, smiles, conformer=conformer, seed=1)
        definition = next(d for d in CALCULATOR_DEFINITIONS if d.calculator_id == calculator)
        seen.add(calculation.run_calculator(
            registry, engine, model, calculator,
            {p.name: p.default for p in definition.parameters}).status)
    assert {"ready", "needs_input", "needs_setup", "inapplicable", "failed"} <= seen


# -- pure_read, measured ------------------------------------------------------------


def test_no_other_calculator_has_a_side_effect(monkeypatch):
    """Every calculator the command line will run, on a molecule with a conformer so the
    geometry ones actually compute, with the ways a calculator can reach outside the
    process recorded. The measurement the `pure_read` label rests on: today exactly one
    calculator (`iupac_name`) did, and it is the one refused by name.

    Python-level writes, subprocesses, sockets and temp files. It cannot see a C
    extension that writes on its own, and says so rather than implying more."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.chem.engine import ChemistryEngine

    registry = calculation.build_registry()
    engine = ChemistryEngine()
    model, info = calculation.build_model(engine, ASPIRIN, conformer=True, seed=1)
    assert info["generated"]

    seen: list[str] = []
    real_open = builtins.open

    def recording_open(file, mode="r", *args, **kwargs):
        if any(flag in str(mode) for flag in "wax+"):
            seen.append(f"write {file}")
        return real_open(file, mode, *args, **kwargs)

    real_popen = subprocess.Popen.__init__

    def recording_popen(self, args, *a, **k):
        seen.append(f"subprocess {args}")
        return real_popen(self, args, *a, **k)

    real_connect = socket.socket.connect

    def recording_connect(self, address):
        seen.append(f"network {address}")
        return real_connect(self, address)

    monkeypatch.setattr(builtins, "open", recording_open)
    monkeypatch.setattr(subprocess.Popen, "__init__", recording_popen)
    monkeypatch.setattr(socket.socket, "connect", recording_connect)
    for name in ("mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryDirectory"):
        original = getattr(tempfile, name)
        monkeypatch.setattr(
            tempfile, name,
            (lambda o, n: lambda *a, **k: (seen.append(f"tempfile {n}"), o(*a, **k))[1])(original, name))

    for definition in CALCULATOR_DEFINITIONS:
        if calculation.runnable_reason(definition):
            continue
        before = len(seen)
        calculation.run_calculator(
            registry, engine, model, definition.calculator_id,
            {p.name: p.default for p in definition.parameters})
        assert len(seen) == before, f"{definition.calculator_id} touched {seen[before:]}"


# -- the envelope under pressure ----------------------------------------------------


def test_a_calculator_that_prints_cannot_corrupt_stdout(capsys, monkeypatch):
    real = calculation.run_calculator

    def noisy(*args, **kwargs):
        print("a stray line from a calculator")
        return real(*args, **kwargs)

    monkeypatch.setattr(calculation, "run_calculator", noisy)
    out_before = capsys.readouterr()
    code = main(["calculate", "--smiles", ETHANOL, "--calculator", "logd", "--json"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert [json.loads(line) for line in captured.out.splitlines() if line.strip()][0]["ok"]
    assert "stray line" not in captured.out and "stray line" in captured.err


def test_a_run_past_its_deadline_writes_one_envelope_and_ends_the_process(capsys, monkeypatch):
    exits = []
    real = calculation.run_calculator

    def slow(*args, **kwargs):
        time.sleep(0.6)
        return real(*args, **kwargs)

    monkeypatch.setattr(calculation, "run_calculator", slow)
    code = main(["calculate", "--smiles", ETHANOL, "--calculator", "logd", "--timeout", "0.1",
                 "--json"], _exit=exits.append)
    out = capsys.readouterr().out
    envelopes = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert len(envelopes) == 1, "the late result must not write a second envelope"
    assert envelopes[0]["ok"] is False and "timed out" in envelopes[0]["error"]
    assert exits == [EXIT_FAILED]
    assert code == EXIT_FAILED


def test_a_crash_inside_a_calculator_is_an_envelope_not_a_traceback(capsys, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("a calculator broke")

    monkeypatch.setattr(calculation.CalculatorRegistry, "compute", boom)
    code, envelope = calculate(capsys, ETHANOL, "logd")
    assert code == EXIT_FAILED
    assert envelope["data"]["status"] == "failed"
    assert "a calculator broke" in envelope["error"]


# -- the serialiser ----------------------------------------------------------------


def test_serialising_is_generic_and_never_guesses():
    from dataclasses import dataclass
    from enum import Enum

    class Colour(Enum):
        RED = "red"

    @dataclass
    class Inner:
        shade: Colour
        pair: tuple

    notes: list[str] = []
    plain = to_plain({"inner": Inner(Colour.RED, (1, 2)), "set": {3, 1, 2}, 5: float("nan"),
                      "odd": object()}, notes)
    assert plain["inner"] == {"shade": "red", "pair": [1, 2]}
    assert plain["set"] == [1, 2, 3]
    assert plain["5"] is None
    assert plain["odd"] == {"unserialisable": "object"}
    assert len(notes) == 2
    json.dumps(plain, allow_nan=False)


def test_a_payload_over_the_limit_is_withheld_whole_not_cut():
    shown = result_payload({"values": list(range(1000))}, max_bytes=10_000_000)
    assert shown["payload"] is not None and shown["truncated"] is False

    withheld = result_payload({"values": list(range(1000))}, max_bytes=100)
    assert withheld["payload"] is None and withheld["truncated"] is True
    assert withheld["payload_bytes"] > 100
    assert any("withheld" in note for note in withheld["notes"])


def test_a_withheld_result_says_so_through_the_whole_command(capsys):
    code, envelope = calculate(capsys, ETHANOL, "elemental_analysis", "--max-bytes", "100")
    assert code == EXIT_OK
    result = envelope["data"]["result"]
    assert result["payload"] is None and result["truncated"] is True
    assert any("withheld" in w for w in envelope["warnings"])


# -- the entry-surface declaration ---------------------------------------------------


def test_the_declared_console_script_is_really_in_pyproject():
    """Every module in `cli/` tells the reachability guard it is entered by a console
    script. That is only true while pyproject.toml actually declares the script, so the
    declaration is checked against the thing it claims."""
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    scripts = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts.get("openchem-cli") == "openchem.cli.commands:main"
    modules = sorted((root / "src" / "openchem" / "cli").glob("*.py"))
    assert len(modules) == 5
    for path in modules:
        assert re.search(r'REACHED_BY = \(\s*"console_script:', path.read_text(encoding="utf-8")), path.name
