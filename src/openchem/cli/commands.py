"""The command table, its handlers, and `main`.

**The contract** (TokenSave Manager's `docs/AGENT_TOOL_CONTRACT.md`):

  stdout   exactly one JSON envelope, and nothing else, ever
  stderr   human diagnostics only
  exit     0 ready - 1 ran, no answer (a limit of the method, or a fault)
           2 the invocation cannot run as given (bad usage, or a required input
           is missing) - 3 a prerequisite is missing (a sidecar is not configured)

This tool is **self-scoped**: it answers questions about OpenChem's own chemistry, so
there is no `--project`. Every command is `pure_read`: it reads its arguments,
computes, and prints. Nothing is written, nothing is retained, and the person's
settings store is never opened. One calculator that would break that promise
(`iupac_name`: Java, the network, temporary files) is refused by name.

**A returned value is not a pass.** Status is `domain.result_status.status_of` --
the application's own word -- and never "it did not raise". Measured: with no sidecar
configured, `admet_ml` returns an `AlertResult` and `pka` a `ReportResult`, both
saying "not configured"; reading either as success is the failure this exists to
prevent.

**One table, three consumers.** `COMMANDS` feeds the parser, the dispatch and
`commands --json`; the manifest's flags are read from the parser, so a flag added to a
subcommand appears there without a second list.

**stdout is the envelope's alone.** A calculator that prints would corrupt it, so
`sys.stdout` is pointed at stderr while a command runs, and the envelope is written to
the stream that was stdout when `main` started.
"""

from __future__ import annotations

#: What `tests/test_calculator_reachability.py` accepts in place of an import: nothing
#: imports this module, because the real entry is the `openchem-cli` script. The guard
#: checks the claim (the script really is declared in pyproject.toml) rather than
#: trusting the string. See `chem/admet_runner.py` for the mechanism.
REACHED_BY = (
    "console_script: entered by the `openchem-cli` script in pyproject.toml "
    "([project.scripts] -> openchem.cli.commands:main) or `python -m openchem.cli`, "
    "never by an import from openchem.main"
)

import argparse
import contextlib
import json
import os
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from openchem.domain import result_status as rs
from openchem.domain.calculator import GEOMETRY

from openchem.cli.serialise import DEFAULT_MAX_BYTES, to_plain, result_payload

#: The version of the JSON envelope every command prints, in its `schema_version`
#: field, so a consumer can tell which shape it is reading.
SCHEMA_VERSION = 1

#: Exit 0: the command ran and has an answer (`ready`, or a `stale` one).
EXIT_OK = 0
#: Exit 1: it ran and has no answer to give, a limit of the method or a fault.
EXIT_FAILED = 1
#: Exit 2: the invocation cannot run as given, bad usage or a required input missing.
EXIT_USAGE = 2
#: Exit 3: a prerequisite is missing, such as a sidecar that is not configured.
EXIT_PREREQUISITE = 3

#: The side-effect class of a command that changes nothing: the one every command here
#: declares, in the agent-tool contract's vocabulary.
PURE_READ = "pure_read"
#: What each declared side-effect class means, printed in the manifest so a caller need
#: not guess.
SIDE_EFFECT_MEANING = {
    PURE_READ: "No filesystem, project or database mutation. "
               "(Python's own bytecode cache is excluded.)",
}

#: How long one calculation may take before the process gives up, in seconds. A
#: calculator is a synchronous call that cannot be interrupted from inside, so the
#: only honest bound is to end the process -- after writing the one envelope.
DEFAULT_TIMEOUT_SECONDS = 120.0

#: Exit code by status. `needs_input` is a usage problem (supply the value);
#: `needs_setup` is a prerequisite (configure the sidecar); the rest ran and have no
#: answer to give.
STATUS_EXIT = {
    rs.READY: EXIT_OK,
    rs.STALE: EXIT_OK,
    rs.INAPPLICABLE: EXIT_FAILED,
    rs.FAILED: EXIT_FAILED,
    rs.NEEDS_INPUT: EXIT_USAGE,
    rs.NEEDS_SETUP: EXIT_PREREQUISITE,
}


class UsageProblem(Exception):
    """The invocation cannot run as given. Maps to `EXIT_USAGE`."""


class Result:
    """What a handler returns, before it becomes an envelope."""

    def __init__(self, code: int = EXIT_OK, data: dict | None = None,
                 warnings: list | None = None, error: str = "", human: str = ""):
        self.code = code
        self.data = data or {}
        self.warnings = warnings or []
        self.error = error
        self.human = human


@dataclass(frozen=True)
class Command:
    """One operation, named once for the parser, the dispatch and the manifest."""

    name: str
    summary: str
    side_effect: str
    handler: Callable[[argparse.Namespace], Result]
    configure: Callable[[argparse.ArgumentParser], None]


# -- parameters --------------------------------------------------------------

#: The spellings a boolean `--param` reads as true, lower-cased.
_TRUE = frozenset({"true", "1", "yes", "on"})
#: The spellings it reads as false. Anything in neither set is refused (`_coerce`), so
#: a misspelt value is never quietly taken for false.
_FALSE = frozenset({"false", "0", "no", "off"})


def _coerce(calculator_id: str, parameter, text: str) -> Any:
    """`text` as the parameter's declared kind, refused when it does not fit."""
    name, kind = parameter.name, parameter.kind
    where = f"{calculator_id} --param {name}"
    if kind in ("float", "int"):
        try:
            value = int(text) if kind == "int" else float(text)
        except ValueError:
            raise UsageProblem(f"{where} must be {'an integer' if kind == 'int' else 'a number'}, got {text!r}") from None
        if value != value or value in (float("inf"), float("-inf")):
            raise UsageProblem(f"{where} must be finite, got {text!r}")
        if parameter.minimum is not None and value < parameter.minimum:
            raise UsageProblem(f"{where} must be at least {parameter.minimum:g}, got {text}")
        if parameter.maximum is not None and value > parameter.maximum:
            raise UsageProblem(f"{where} must be at most {parameter.maximum:g}, got {text}")
        return value
    if kind == "bool":
        lowered = text.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        raise UsageProblem(f"{where} must be true or false, got {text!r}")
    if kind == "choice":
        choices = list(parameter.choices or [])
        if text not in choices:
            raise UsageProblem(f"{where} must be one of {', '.join(choices)}, got {text!r}")
        return text
    return text


def _parameters(definition, assignments: list[str]) -> dict[str, Any]:
    """The full parameter dict a run is handed: declared defaults, then `--param`.

    The application sends every declared parameter with its default, so this does too
    -- and an undeclared name is **refused**, because the registry passes keys no
    parameter declares straight through ("callers may hand a calculator internal
    settings"), which would make a misspelt name a silently different calculation.
    """
    declared = {p.name: p for p in definition.parameters}
    values: dict[str, Any] = {p.name: p.default for p in definition.parameters}
    for item in assignments:
        name, separator, text = item.partition("=")
        if not separator:
            raise UsageProblem(f"--param needs name=value, got {item!r}")
        parameter = declared.get(name)
        if parameter is None:
            takes = ", ".join(declared) or "no parameters"
            raise UsageProblem(f"{definition.calculator_id} does not take {name!r}; it takes {takes}")
        values[name] = _coerce(definition.calculator_id, parameter, text)
    return values


# -- commands ----------------------------------------------------------------


def _definition_row(definition) -> dict:
    from openchem.domain.calculator_support import support_of

    from openchem.cli.calculation import runnable_reason

    support = support_of(definition)
    reason = runnable_reason(definition)
    notes: list[str] = []
    return {
        "id": definition.calculator_id,
        "display_name": definition.display_name,
        "category": definition.category,
        "description": definition.description,
        "calculation_input": definition.calculation_input,
        "applies_to": sorted(definition.applies_to),
        "prediction_basis": definition.prediction_basis,
        "tags": list(definition.tags),
        "scope": to_plain(definition.scope, notes),
        "support": {
            "stage": support.stage.value,
            "default_visibility": support.default_visibility.value,
            "support_reason": support.support_reason,
            "scope_note": support.scope_note,
        },
        "parameters": [
            {
                "name": p.name, "label": p.label, "kind": p.kind, "default": p.default,
                "minimum": p.minimum, "maximum": p.maximum,
                "choices": list(p.choices) if p.choices else None,
                "enabled_by": p.enabled_by, "required": p.required,
            }
            for p in definition.parameters
        ],
        "has_preflight": definition.preflight is not None,
        "cli_runnable": not reason,
        "cli_reason": reason or None,
    }


def _configure_calculators(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", default="", help="describe only this calculator")
    parser.add_argument("--category", default="", help="only calculators in this category")


def _cmd_calculators(args: argparse.Namespace) -> Result:
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    rows = [_definition_row(d) for d in CALCULATOR_DEFINITIONS
            if (not args.id or d.calculator_id == args.id)
            and (not args.category or d.category == args.category)]
    if args.id and not rows:
        raise UsageProblem(f"no calculator {args.id!r}; run `calculators` for the list")
    return Result(EXIT_OK, {"calculators": rows}, human=f"{len(rows)} calculator(s)")


def _configure_calculate(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--smiles", required=True, help="the structure, as SMILES")
    parser.add_argument("--calculator", required=True, help="a calculator id; see `calculators`")
    parser.add_argument("--param", action="append", default=[], metavar="NAME=VALUE",
                        help="a declared parameter; repeat for several. Undeclared names are refused")
    parser.add_argument("--conformer", action="store_true",
                        help="generate one seeded, unoptimised 3D conformer first, for the "
                             "calculators that need real coordinates")
    from openchem.cli.calculation import DEFAULT_CONFORMER_SEED

    parser.add_argument("--conformer-seed", type=int, default=DEFAULT_CONFORMER_SEED,
                        help="seed for --conformer, so the geometry repeats")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS,
                        help="end the process if the calculation takes longer than this (seconds)")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES,
                        help="withhold a result larger than this, saying so; raise it to receive it")


def _cmd_calculate(args: argparse.Namespace) -> Result:
    from openchem.chem.engine import ChemistryEngine

    from openchem.cli.calculation import (
        StructureError, build_model, build_registry, run_calculator, runnable_reason,
    )

    if args.timeout <= 0 or args.max_bytes <= 0:
        raise UsageProblem("--timeout and --max-bytes must be positive")
    registry = build_registry()
    definition = registry.get(args.calculator)
    if definition is None:
        raise UsageProblem(f"no calculator {args.calculator!r}; run `calculators` for the list")
    blocked = runnable_reason(definition)
    if blocked:
        raise UsageProblem(f"{args.calculator} is not available here: {blocked}")
    parameters = _parameters(definition, args.param)

    engine = ChemistryEngine()
    try:
        model, conformer = build_model(
            engine, args.smiles, conformer=args.conformer, seed=args.conformer_seed)
    except StructureError as error:
        raise UsageProblem(str(error)) from None

    outcome = run_calculator(registry, engine, model, args.calculator, parameters)

    notes: list[str] = []
    data: dict[str, Any] = {
        "calculator": {
            "id": definition.calculator_id,
            "display_name": definition.display_name,
            "category": definition.category,
            "support": _definition_row(definition)["support"],
            "parameters": to_plain(parameters, notes),
        },
        "input": {
            "smiles": args.smiles,
            "canonical_smiles": model.canonical_smiles,
            "calculation_input": definition.calculation_input,
            "input_fingerprint": outcome.input_fingerprint,
            "conformer": conformer,
        },
        "status": outcome.status,
        "result": result_payload(outcome.result, args.max_bytes) if outcome.result is not None else None,
        "refusal": to_plain(outcome.refusal, notes) if outcome.refusal is not None else None,
        "error": outcome.error or None,
    }
    warnings = list(dict.fromkeys(notes))
    if conformer["requested"] and not conformer["generated"]:
        warnings.append(f"no conformer was generated: {conformer['error']}")
    if conformer["generated"] and definition.calculation_input == GEOMETRY:
        # `ready` says the calculator ran, not that its input was a good geometry.
        warnings.append(
            "this value describes a seeded, unoptimised embedding (a starting geometry), "
            "not a minimised structure")
    if outcome.result is not None:
        warnings.extend(data["result"]["notes"])
    code = STATUS_EXIT.get(outcome.status, EXIT_FAILED)
    message = ""
    if code != EXIT_OK:
        refusal = outcome.refusal or {}
        message = (refusal.get("summary") or outcome.error
                   or str(getattr(outcome.result, "error", "") or "") or outcome.status)
    return Result(code, data, warnings=warnings, error=message,
                  human=f"{args.calculator}: {outcome.status}")


def _cmd_commands(args: argparse.Namespace) -> Result:
    return Result(EXIT_OK, _manifest(), human=f"{len(COMMANDS)} command(s)")


def _no_arguments(parser: argparse.ArgumentParser) -> None:
    """A command that takes nothing beyond the shared flags."""


#: Every command, named once for the parser, the dispatch and the manifest.
COMMANDS: tuple[Command, ...] = (
    Command("commands", "emit the tool's command vocabulary", PURE_READ,
            _cmd_commands, _no_arguments),
    Command("calculators", "list the calculators, their parameters and whether this "
                           "command line can run them", PURE_READ,
            _cmd_calculators, _configure_calculators),
    Command("calculate", "run one calculator on one structure and report its status "
                         "and result", PURE_READ, _cmd_calculate, _configure_calculate),
)
#: `COMMANDS` by name, for the dispatch.
BY_NAME = {c.name: c for c in COMMANDS}


# -- the manifest ------------------------------------------------------------


def _describe_arg(action: argparse.Action) -> dict:
    """One flag as a row, read from the parser rather than restated."""
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        kind = "flag"
    elif action.type is float:
        kind = "number"
    elif action.type is int:
        kind = "integer"
    else:
        kind = "string"
    default = action.default
    if not isinstance(default, (str, int, float, bool, list, type(None))):
        default = None
    positional = not action.option_strings
    return {
        "flag": action.dest if positional else max(action.option_strings, key=len),
        "positional": positional,
        "kind": kind,
        "required": bool(action.required),
        "multiple": action.nargs in ("*", "+") or isinstance(action, argparse._AppendAction),
        "default": default,
        "choices": list(action.choices) if action.choices else None,
        "help": action.help or "",
    }


def _version() -> str:
    from openchem.services.result_identity import application_version

    return application_version()


def _manifest() -> dict:
    """`commands --json`: the keys the TokenSave Manager's manifest carries (`tool`,
    `side_effect_classes`, `commands`, `invocation`), so one adapter can read any of
    these tools."""
    parser = _build_parser()
    subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    invocation = {
        name: {
            "unattended_safe": BY_NAME[name].side_effect == PURE_READ,
            "args": [_describe_arg(a) for a in sp._actions
                     if not isinstance(a, argparse._HelpAction)],
        }
        for name, sp in subs.choices.items()
    }
    return {
        "tool": {"name": parser.prog, "cli_version": _version(),
                 "schema_version": SCHEMA_VERSION, "scope": "self"},
        "side_effect_classes": dict(SIDE_EFFECT_MEANING),
        "commands": [
            {"action": c.name, "cli": c.name, "detail": c.summary,
             "side_effect": c.side_effect, "requires_project": False}
            for c in COMMANDS
        ],
        "invocation": invocation,
    }


# -- parser and entry --------------------------------------------------------


class _Parser(argparse.ArgumentParser):
    """Argument errors become an envelope, not usage text on stderr alone."""

    def error(self, message: str):  # noqa: D401 - argparse's own hook
        raise UsageProblem(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="openchem-cli",
        description="OpenChem Studio's calculators, headless. stdout is always one "
                    "JSON envelope; stderr is for humans.")
    parser.add_argument("--version", action="version", version=f"openchem-cli {_version()} "
                                                              f"(schema {SCHEMA_VERSION})")
    subs = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        sub = subs.add_parser(command.name, help=command.summary)
        sub.add_argument("--json", action="store_true",
                         help="suppress the human summary on stderr "
                              "(stdout is JSON either way)")
        command.configure(sub)
    return parser


def _envelope(command: str, result: Result) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "cli_version": _version(),
        "command": command,
        "ok": result.code == EXIT_OK,
        "data": result.data,
        "findings": [],
        "warnings": result.warnings,
        "error": result.error or None,
    }


class _Output:
    """Exactly one envelope on the real stdout, from whichever of the run or its
    deadline gets there first."""

    def __init__(self, stream) -> None:
        self._stream = stream
        self._lock = threading.Lock()
        self._done = False

    def emit(self, envelope: dict) -> bool:
        """Write the envelope unless one has already been written. Strict JSON: a
        stray NaN becomes an error, not a document no parser accepts."""
        with self._lock:
            if self._done:
                return False
            self._done = True
            try:
                text = json.dumps(envelope, allow_nan=False)
            except ValueError as error:
                envelope = {**envelope, "ok": False, "data": {},
                            "error": f"the result is not valid JSON: {error}"}
                text = json.dumps(envelope)
            self._stream.write(text + "\n")
            self._stream.flush()
            return True


def _human(result: Result) -> None:
    if result.human:
        sys.stderr.write(result.human.encode("ascii", "replace").decode("ascii") + "\n")
    for warning in result.warnings:
        sys.stderr.write(f"warning: {warning.encode('ascii', 'replace').decode('ascii')}\n")


def main(argv: list[str] | None = None, *, _exit: Callable[[int], Any] = os._exit) -> int:
    """Run one command. Returns the process exit code; never raises.

    `_exit` is what ends the process when a calculation passes its deadline. It is a
    parameter so a test can observe it instead of dying.
    """
    arguments = sys.argv[1:] if argv is None else list(argv)
    output = _Output(sys.stdout)
    command = ""
    quiet = False
    timer: threading.Timer | None = None
    try:
        args = _build_parser().parse_args(arguments)
        command, quiet = args.command, args.json
        timeout = getattr(args, "timeout", None)
        if timeout:
            def _deadline() -> None:
                late = Result(EXIT_FAILED, error=f"timed out after {timeout:g} s",
                              human=f"{command} timed out after {timeout:g} s")
                if output.emit(_envelope(command, late)):
                    _exit(EXIT_FAILED)

            timer = threading.Timer(timeout, _deadline)
            timer.daemon = True
            timer.start()
        with contextlib.redirect_stdout(sys.stderr):
            result = BY_NAME[command].handler(args)
    except UsageProblem as error:
        command = command or (arguments[0] if arguments and not arguments[0].startswith("-") else "")
        result = Result(EXIT_USAGE, error=str(error), human=str(error))
    except KeyboardInterrupt:
        result = Result(EXIT_FAILED, error="interrupted", human="interrupted")
    except Exception as error:  # noqa: BLE001 - a crash must still be an envelope
        result = Result(EXIT_FAILED, error=f"{type(error).__name__}: {error}",
                        human=f"unexpected failure: {error}")
    finally:
        if timer is not None:
            timer.cancel()

    if not output.emit(_envelope(command, result)):
        return EXIT_FAILED  # the deadline spoke first
    if not quiet:
        _human(result)
    return result.code


__all__ = ["COMMANDS", "main"]
