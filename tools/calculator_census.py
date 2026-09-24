"""The calculator census: every calculator over a fixed panel, through the app's own path.

**WHY IT EXISTS.** A live session on one nitramine found, in an afternoon, a
crash nothing had caught (a feature pattern raising per edit), a calculator
reading "Failed" for a molecule with nothing to ionise, one reading "Not
applicable" for a method that merely needed two numbers, and one that refuses
most of what people draw. Each was invisible until somebody drew the right
molecule. This draws them all, on purpose, and says what every calculator did
with each -- so the next such finding is a row in a table on the day the
calculator is added, not a screenshot in a live session.

**THROUGH THE SERVICE, NOT BY IMPORT.** Each result is whatever
`DescriptorService` records (`ResultRecorded`) for a real `MoleculeModel`, built
by the real `build_service_container`, so the registry binding, the
calculation-input resolution and the refusal paths under test are the
application's own. A direct call to a compute function once passed while its
registration was broken (`tests/multicomponent_sweep.py`, which this generalises
and leaves in place: its S1 matrix and guards are their own evidence).

**TWO THINGS ARE RECORDED THAT NO SCREENSHOT CAN SHOW.**

    result       READY / LIMIT / NEEDS_INPUT / NEEDS_SETUP / FAULT / PENDING,
                 from `domain.result_status.status_of` and nothing else --
                 the census is not a second opinion about what a status is.
    observation  clean / warning / error_logged: what the APPLICATION LOGGED
                 while that calculator ran. This is never a chemistry status.
                 A calculator can return a perfectly good number while logging a
                 traceback, and only this column sees it.

**A REFUSAL CODE NOBODY CLASSIFIED IS REPORTED, NOT SWALLOWED.** A refusal whose
code is in no kind table and declared no kind reads as a limit only because a
producer set the legacy flag. The census lists every such code, so the
classification work has a to-do list instead of a guess; a guard lets that list
only shrink.

Run it directly (isolated settings, no sidecars, no experimental database):

    python tools/calculator_census.py --report            # the matrix and its findings
    python tools/calculator_census.py --record            # rewrite the baseline
    python tools/calculator_census.py --check             # compare with the baseline

The pytest guard is `tests/test_calculator_census.py`.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

CORPUS = ROOT / "tests" / "fixtures" / "census_panel.toml"
BASELINE = ROOT / "tests" / "fixtures" / "calculator_census_baseline.json"

#: One letter per outcome, so a whole calculator's row across the panel is one
#: short string in the baseline -- diffable by eye and small enough to commit.
READY, LIMIT, NEEDS_INPUT, NEEDS_SETUP, FAULT, PENDING = "R", "L", "I", "S", "F", "P"
#: Worst first: a calculator is only READY if every result it recorded is.
_SEVERITY = (FAULT, PENDING, NEEDS_SETUP, NEEDS_INPUT, LIMIT, READY)

CLEAN, WARNING, ERROR_LOGGED = "c", "w", "e"

#: The always-on descriptor and alert set is not a registered calculator, but it
#: is where the live crash was. It is a column of its own so what it logs is seen.
ALWAYS_ON = "always_on"


@dataclass(frozen=True)
class CensusRow:
    id: str
    smiles: str
    stratum: str
    why: str


def load_corpus(path: Path = CORPUS) -> list[CensusRow]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return [CensusRow(**row) for row in data["row"]]


class _LogCollector(logging.Handler):
    """The WARNING-and-above records of one calculator's run."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def observation(self) -> str:
        if any(r.levelno >= logging.ERROR for r in self.records):
            return ERROR_LOGGED
        return WARNING if self.records else CLEAN

    def samples(self, limit: int = 3) -> list[str]:
        out = []
        for record in self.records[:limit]:
            try:
                text = record.getMessage()
            except Exception:  # noqa: BLE001 - a malformed record is still evidence
                text = str(record.msg)
            out.append(f"{record.levelname} {record.name}: {text.splitlines()[0][:160] if text else ''}")
        return out


def _drain(qapp, timeout_ms: int) -> bool:
    from PySide6.QtCore import QThreadPool

    done = QThreadPool.globalInstance().waitForDone(timeout_ms)
    for _ in range(50):
        qapp.processEvents()
    return done


def _with_conformer(engine, model) -> str:
    """Attach one conformer as the Conformers panel would; '' or why not."""
    from openchem.chem.conformer_providers import RDKitConformerProvider
    from openchem.domain.conformer import ConformerModel

    try:
        results = RDKitConformerProvider().generate_conformers(
            engine.mol_from_model(model), num_conformers=1, optimize=False
        )
        if not results:
            return "the embedder returned no conformer"
        conformer_mol, _energy = results[0]
        model.conformers.append(
            ConformerModel(molblock=engine.mol_to_molblock(conformer_mol), energy=-1.0)
        )
    except Exception as exc:  # noqa: BLE001 - recorded, it is a finding
        return f"{type(exc).__name__}: {exc}"[:240]
    return ""


def classify_result(result) -> str:
    """One recorded result as R/L/I/S/F, by the launcher's own status word."""
    from openchem.domain import result_status as rs

    status = rs.status_of(result, structure_version=getattr(result, "structure_version", 0))
    return {
        rs.READY: READY,
        rs.STALE: READY,
        rs.INAPPLICABLE: LIMIT,
        rs.NEEDS_INPUT: NEEDS_INPUT,
        rs.NEEDS_SETUP: NEEDS_SETUP,
        rs.FAILED: FAULT,
    }.get(status, PENDING)


def _worst(classes: list[str]) -> str:
    for candidate in _SEVERITY:
        if candidate in classes:
            return candidate
    return PENDING


def _unclassified_code(result) -> str:
    """The refusal code of a FAILED result that has no kind, or ''."""
    from openchem.domain.common import CacheState
    from openchem.domain.refusal_kinds import (
        REFUSAL_CLASSIFIED_KEY,
        REFUSAL_KEY,
        refusal_kind_of_result,
    )

    if getattr(result, "cache_state", None) is not CacheState.FAILED:
        return ""
    provenance = getattr(result, "provenance", None)
    parameters = getattr(provenance, "parameters", None) or {}
    code = parameters.get(REFUSAL_KEY, "")
    # No kind at all, OR a kind that was only DERIVED from the legacy flag.
    if code and (
        refusal_kind_of_result(result) is None or parameters.get(REFUSAL_CLASSIFIED_KEY) is False
    ):
        return str(code)
    return ""


def run_census(
    qapp,
    rows: list[CensusRow],
    *,
    calculator_ids: list[str] | None = None,
    timeout_ms: int = 180_000,
) -> dict[str, Any]:
    """Every row through the always-on set and every registry calculator.

    Returns `rows`, `calculators`, and `cells` keyed "<calculator>|<row>" -- each
    with its class, observation, the sampled log lines, and any unclassified code.
    """
    from openchem.bootstrap import build_service_container
    from openchem.domain.calculator import DRAWING, GEOMETRY, CalculationRequest, RegistryExecution
    from openchem.domain.calculator_support import support_of
    from openchem.domain.molecule import MoleculeModel
    from openchem.events.events import ResultRecorded

    container = build_service_container()
    engine = container.chemistry_engine
    service = container.descriptor_service
    registry = service._calculator_registry  # the SAME instance the app dispatches through
    definitions = [
        d for category in registry.categories() for d in registry.by_category(category)
        if isinstance(d.execution, RegistryExecution)
        and (calculator_ids is None or d.calculator_id in calculator_ids)
    ]
    recorded: list = []
    container.event_bus.subscribe(ResultRecorded, lambda e: recorded.append(e.stored))

    cells: dict[str, dict[str, Any]] = {}
    rows_out: dict[str, Any] = {}
    root = logging.getLogger()

    def run_one(column: str, row: CensusRow, model, start) -> None:
        collector = _LogCollector()
        root.addHandler(collector)
        recorded.clear()
        try:
            timed_out = not start()
        finally:
            root.removeHandler(collector)
        mine = [s for s in recorded if s.identity.molecule_uuid == model.uuid]
        results = [s.result for s in mine]
        if column == ALWAYS_ON:
            # Its descriptors legitimately fail on a drawing (a 3D one asked of
            # a flat structure): the result column would be noise, and what
            # matters here is what it LOGGED.
            outcome = READY if results else PENDING
        else:
            outcome = _worst([classify_result(r) for r in results]) if results else PENDING
        if timed_out:
            outcome = PENDING
        key = f"{column}|{row.id}"
        previous = cells.get(key)
        if previous is not None:
            # A second run of the same column (always-on on the geometry) merges: worst wins.
            outcome = _worst([previous["result"], outcome])
            collector.records[:0] = previous.pop("_records")
        cells[key] = {
            "column": column, "row": row.id, "result": outcome, "observation": collector.observation(),
            "log": collector.samples(),
            "unclassified": sorted({c for c in (_unclassified_code(r) for r in results) if c}),
            "_records": collector.records,
        }

    for row in rows:
        model = MoleculeModel()
        engine.set_structure_from_smiles(model, row.smiles)
        conformer_error = _with_conformer(engine, model)
        started = time.perf_counter()
        rows_out[row.id] = {"stratum": row.stratum, "conformer_error": conformer_error}
        for calculation_input in (DRAWING, GEOMETRY):
            if calculation_input == GEOMETRY and not model.conformers:
                continue

            def start_always_on(calculation_input=calculation_input) -> bool:
                service.request_descriptors(model, calculation_input)
                return _drain(qapp, timeout_ms)

            run_one(ALWAYS_ON, row, model, start_always_on)
        for definition in definitions:

            def start(definition=definition) -> bool:
                service.run_calculator(model, CalculationRequest(
                    calculator_id=definition.calculator_id, molecule_uuid=model.uuid,
                    parameters={p.name: p.default for p in definition.parameters},
                ))
                return _drain(qapp, timeout_ms)

            run_one(definition.calculator_id, row, model, start)
        rows_out[row.id]["seconds"] = round(time.perf_counter() - started, 1)
    for cell in cells.values():
        cell.pop("_records", None)
    return {
        "rows": rows_out,
        "columns": [ALWAYS_ON] + sorted(d.calculator_id for d in definitions),
        "support": {
            d.calculator_id: {
                "stage": support_of(d).stage.value, "visibility": support_of(d).default_visibility.value,
            } for d in definitions
        },
        "cells": cells,
    }


# --- what the census says -----------------------------------------------------


def findings(census: dict[str, Any]) -> dict[str, Any]:
    """The things a person should look at, by category."""
    cells = census["cells"].values()
    return {
        "faults": sorted(f"{c['column']}|{c['row']}" for c in cells if c["result"] == FAULT),
        "error_logged": sorted(f"{c['column']}|{c['row']}" for c in cells if c["observation"] == ERROR_LOGGED),
        "pending": sorted(f"{c['column']}|{c['row']}" for c in cells if c["result"] == PENDING),
        "unclassified_codes": sorted({
            f"{c['column']}:{code}" for c in cells for code in c["unclassified"]
        }),
    }


def proposal(census: dict[str, Any]) -> list[dict[str, Any]]:
    """Calculators whose non-READY outcomes are LIMITS, for a person to sign off.

    **A PROPOSAL, NEVER AN ASSIGNMENT.** A stage is earned (`docs/CALCULATOR_MATURITY.md`);
    this only says which calculators the panel found refusing a large share of it as a
    limit of the method, because that is the evidence a LIMITED classification starts from.
    """
    out = []
    for column in census["columns"]:
        if column == ALWAYS_ON:
            continue
        classes = [c["result"] for c in census["cells"].values() if c["column"] == column]
        if not classes:
            continue
        limited = classes.count(LIMIT)
        if limited and limited / len(classes) >= 0.25 and FAULT not in classes:
            out.append({
                "calculator": column, "limit_share": round(limited / len(classes), 2),
                "declared": census["support"][column],
            })
    return sorted(out, key=lambda item: -item["limit_share"])


def baseline_form(census: dict[str, Any]) -> dict[str, Any]:
    """A compact, deterministic form: one string of letters per column, in row order."""
    row_ids = list(census["rows"])
    matrix, observation = {}, {}
    for column in census["columns"]:
        matrix[column] = "".join(census["cells"][f"{column}|{r}"]["result"] for r in row_ids)
        observation[column] = "".join(census["cells"][f"{column}|{r}"]["observation"] for r in row_ids)
    found = findings(census)
    return {
        "version": 1,
        "rows": row_ids,
        "legend": {
            "result": "R ready, L limit, I needs input, S needs setup, F fault, P pending",
            "observation": "c clean, w warning logged, e error logged",
        },
        "matrix": matrix,
        "observation": observation,
        "unclassified_codes": found["unclassified_codes"],
    }


def diff_against(census: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    """Every cell whose result or observation moved, as a sentence."""
    now = baseline_form(census)
    lines: list[str] = []
    if now["rows"] != baseline["rows"]:
        lines.append(f"the panel changed: {baseline['rows']} -> {now['rows']}")
        return lines
    for kind in ("matrix", "observation"):
        for column in sorted(set(now[kind]) | set(baseline[kind])):
            was, is_ = baseline[kind].get(column), now[kind].get(column)
            if was is None:
                lines.append(f"{kind}: a new column {column}")
            elif is_ is None:
                lines.append(f"{kind}: {column} is gone")
            elif was != is_:
                moved = [
                    f"{now['rows'][i]} {was[i]}->{is_[i]}" for i in range(len(was)) if was[i] != is_[i]
                ]
                lines.append(f"{kind}: {column}: " + ", ".join(moved))
    return lines


# --- the command line ---------------------------------------------------------


def _isolated_environment():
    """Settings in a throwaway INI file and no experimental NMR database.

    The census must not read or write the person's registry, and a developer who
    had built the NMR database would otherwise see a different panel from CI
    (this went green locally and red on CI once: PR #133).
    """
    import tempfile

    from PySide6.QtCore import QSettings

    import openchem.app.settings as settings_module
    from openchem.chem import nmr_database

    scratch = Path(tempfile.mkdtemp(prefix="openchem-census-"))
    ini = scratch / "qsettings.ini"
    settings_module.QSettings = lambda *_a, **_k: QSettings(str(ini), QSettings.Format.IniFormat)
    nmr_database.default_database_path = lambda: scratch / "absent.sqlite"
    return scratch


def _report(census: dict[str, Any]) -> None:
    rows = list(census["rows"])
    width = max(len(c) for c in census["columns"])
    print("rows: " + ", ".join(f"{i}={r}" for i, r in enumerate(rows)))
    print("seconds per row: " + ", ".join(f"{r}={census['rows'][r]['seconds']}" for r in rows))
    print(f"{'calculator'.ljust(width)}  result{' ' * max(0, len(rows) - 6)}  observation")
    form = baseline_form(census)
    for column in census["columns"]:
        print(f"{column.ljust(width)}  {form['matrix'][column]}  {form['observation'][column]}")
    found = findings(census)
    warned = sorted(k for k, c in census["cells"].items() if c["observation"] == WARNING)
    print(f"\nwarnings logged ({len(warned)}):")
    for key in warned:
        print(f"  {key}")
        for line in census["cells"][key]["log"]:
            print(f"      {line}")
    for name in ("faults", "error_logged", "pending", "unclassified_codes"):
        print(f"\n{name} ({len(found[name])}):")
        for item in found[name]:
            print(f"  {item}")
            if name in ("faults", "error_logged"):
                for line in census["cells"][item]["log"]:
                    print(f"      {line}")
    print("\nproposed for a LIMITED classification (a proposal, not an assignment):")
    for item in proposal(census):
        print(f"  {item['calculator']}: {item['limit_share']:.0%} of the panel refused as a limit; declared {item['declared']}")


def main(argv: list[str] | None = None) -> int:
    import json

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--report", action="store_true", help="print the matrix and what it found")
    mode.add_argument("--record", action="store_true", help="rewrite the committed baseline")
    mode.add_argument("--check", action="store_true", help="compare with the baseline; exit 1 on a change")
    parser.add_argument("--rows", nargs="*", help="only these row ids")
    args = parser.parse_args(argv)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _isolated_environment()
    from PySide6.QtWidgets import QApplication

    qapp = QApplication.instance() or QApplication([])
    rows = load_corpus()
    if args.rows:
        rows = [r for r in rows if r.id in set(args.rows)]
    census = run_census(qapp, rows)
    if args.report:
        _report(census)
        return 0
    if args.record:
        BASELINE.write_text(json.dumps(baseline_form(census), indent=1) + "\n", encoding="utf-8")
        print(f"wrote {BASELINE.relative_to(ROOT)}")
        return 0
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    changes = diff_against(census, baseline)
    for line in changes:
        print(line)
    return 1 if changes else 0


if __name__ == "__main__":
    raise SystemExit(main())
