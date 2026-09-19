"""Run every calculator over the multicomponent panel, through the app's path.

Round 5, branch S1. **THROUGH THE SERVICE, NOT BY IMPORT**: each result is
whatever `DescriptorService` records (`ResultRecorded`) for a real
`MoleculeModel`, built by the real `build_service_container`, so the
registry binding, the calculation-input resolution and the failure paths
under test are the application's own. A direct call to a compute function
once passed while its registration was broken.

Needs pytest: the container builds `Settings`, and only the suite's
autouse fixture keeps that off the real registry.

A cell is (panel row, producer, result id). Three things are recorded that
a screenshot cannot show:

- **MISSING**: the eager provider LOGS an alert or per-atom failure and
  records nothing, so a result that silently never arrived is found by
  comparing against the results the same producer made for other rows.
- **the refusal code**, from `provenance.parameters["refusal"]`, the
  convention `debug_drive.result_report` already reads.
- **whether the same producer also fails on a single-component control**,
  which separates "this calculator cannot handle a salt" from "this
  calculator needs something the harness did not give it".
"""

from __future__ import annotations

import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThreadPool
from rdkit import Chem

from openchem.domain.calculator import DRAWING, GEOMETRY, CalculationRequest, RegistryExecution
from openchem.domain.common import CacheState
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.events import ResultRecorded

PANEL = Path(__file__).parent / "fixtures" / "multicomponent_panel.toml"

#: Metals and metalloid cations the panel carries; a row containing one is
#: "metal-containing" for the matrix's summary columns.
_METALS = {3, 11, 12, 19, 20, 26}


@dataclass(frozen=True)
class PanelRow:
    id: str
    smiles: str
    shape: str
    why: str
    control: str | None = None

    @property
    def is_control(self) -> bool:
        return self.shape == "control"


def load_panel() -> list[PanelRow]:
    data = tomllib.loads(PANEL.read_text(encoding="utf-8"))
    return [PanelRow(**row) for row in data["row"]]


def shape_facts(smiles: str) -> dict[str, Any]:
    mol = Chem.MolFromSmiles(smiles)
    frags = Chem.GetMolFrags(mol)
    return {
        "components": len(frags),
        "metal": any(a.GetAtomicNum() in _METALS for a in mol.GetAtoms()),
        "formal_charges": sum(1 for a in mol.GetAtoms() if a.GetFormalCharge()),
    }


def _drain(qapp, timeout_ms: int) -> bool:
    done = QThreadPool.globalInstance().waitForDone(timeout_ms)
    for _ in range(50):
        qapp.processEvents()
    return done


def _gist(result) -> str:
    """A short, stable rendering of WHAT came back, for reading the matrix."""
    for attr in ("value", "values", "facts", "items", "matched"):
        if hasattr(result, attr):
            value = getattr(result, attr)
            text = repr(value)
            return f"{attr}={text[:80]}"
    return type(result).__name__


def _cell(row: PanelRow, stored) -> dict[str, Any]:
    result = stored.result
    provenance = getattr(result, "provenance", None)
    parameters = dict(getattr(provenance, "parameters", {}) or {})
    failed = getattr(result, "cache_state", None) is CacheState.FAILED
    return {
        "row": row.id,
        "producer": stored.identity.producer,
        "result_id": stored.identity.result_id,
        "input": stored.identity.calculation_input,
        "type": type(result).__name__,
        "state": "failed" if failed else "completed",
        "inapplicable": bool(getattr(result, "inapplicable", False)),
        "refusal": parameters.get("refusal", ""),
        "method": getattr(result, "method", "") or getattr(provenance, "method", ""),
        "summary": (getattr(result, "error_summary", "") or "")[:120],
        "error": (getattr(result, "error", "") or "")[:240],
        "gist": "" if failed else _gist(result),
    }


def _with_conformer(engine, model) -> str:
    """Attach one conformer as the Conformers panel would; '' or why not."""
    from openchem.chem.conformer_providers import RDKitConformerProvider

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


def run_sweep(qapp, rows: list[PanelRow], *, calculator_ids: list[str] | None = None,
              timeout_ms: int = 180_000) -> dict[str, Any]:
    """Every row through the always-on provider and every registry calculator."""
    from openchem.bootstrap import build_service_container

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

    cells: list[dict[str, Any]] = []
    rows_out: dict[str, Any] = {}
    timeouts: list[dict[str, str]] = []
    for row in rows:
        model = MoleculeModel()
        engine.set_structure_from_smiles(model, row.smiles)
        conformer_error = _with_conformer(engine, model)
        rows_out[row.id] = {**shape_facts(row.smiles), "conformer_error": conformer_error}

        def collect(producer_hint: str) -> None:
            for stored in recorded:
                if stored.identity.molecule_uuid == model.uuid:
                    cells.append(_cell(row, stored))
            recorded.clear()

        started = time.perf_counter()
        # The always-on set runs on the drawing, and AGAIN on a conformer when
        # one exists -- the app's shape descriptors only ever answer on the
        # second run, so a drawing-only sweep reads them all as failures.
        for calculation_input in (DRAWING, GEOMETRY):
            if calculation_input == GEOMETRY and not model.conformers:
                continue
            service.request_descriptors(model, calculation_input)
            if not _drain(qapp, timeout_ms):
                timeouts.append({"row": row.id, "producer": f"always-on/{calculation_input}"})
            collect("always-on")
        for definition in definitions:
            request = CalculationRequest(
                calculator_id=definition.calculator_id,
                molecule_uuid=model.uuid,
                parameters={p.name: p.default for p in definition.parameters},
            )
            service.run_calculator(model, request)
            if not _drain(qapp, timeout_ms):
                timeouts.append({"row": row.id, "producer": definition.calculator_id})
            collect(definition.calculator_id)
        rows_out[row.id]["seconds"] = round(time.perf_counter() - started, 1)
    return {
        "rows": rows_out,
        "calculators": sorted(d.calculator_id for d in definitions),
        "cells": cells,
        "timeouts": timeouts,
    }


def classify(sweep: dict[str, Any], rows: list[PanelRow]) -> list[dict[str, Any]]:
    """Each cell's outcome class, plus the MISSING cells nothing recorded.

    Before any calculator declares a scope, a value on a multicomponent or
    charged non-control row is `suspect` BY DEFINITION: nothing yet says
    which components it was computed over or whether the method covers
    them. That is the plan's rule, not a judgement of the number.
    """
    by_row = {r.id: r for r in rows}
    facts = sweep["rows"]
    seen: dict[str, set[str]] = {}
    for cell in sweep["cells"]:
        seen.setdefault(cell["producer"], set()).add(cell["result_id"])
    present = {(c["row"], c["producer"], c["result_id"]) for c in sweep["cells"]}
    # A result that failed on the drawing and answered on the conformer is
    # the app's normal shape for a 3D descriptor: judge the BEST outcome.
    answered = {(c["row"], c["producer"], c["result_id"]) for c in sweep["cells"] if c["state"] != "failed"}
    out: list[dict[str, Any]] = []
    control_failures = {
        (c["producer"], c["result_id"])
        for c in sweep["cells"]
        if c["state"] == "failed" and by_row[c["row"]].is_control
        and (c["row"], c["producer"], c["result_id"]) not in answered
    }
    for cell in sweep["cells"]:
        if cell["state"] == "failed" and (cell["row"], cell["producer"], cell["result_id"]) in answered:
            continue
        row = by_row[cell["row"]]
        f = facts[row.id]
        multi = f["components"] > 1 or f["metal"] or f["formal_charges"] > 0
        if cell["state"] == "failed":
            outcome = "inapplicable" if cell["inapplicable"] else "failed"
        elif row.is_control or not multi:
            outcome = "value"
        else:
            outcome = "suspect"
        out.append({
            **cell,
            "outcome": outcome,
            "fails_on_a_control_too": (cell["producer"], cell["result_id"]) in control_failures,
        })
    for producer, result_ids in seen.items():
        producer_rows = {c["row"] for c in sweep["cells"] if c["producer"] == producer}
        for row in rows:
            if producer != "rdkit":
                # A registry calculator ALWAYS records something, even a
                # failure, so only a row with nothing at all is missing.
                if row.id not in producer_rows:
                    out.append({"row": row.id, "producer": producer, "result_id": "*",
                                "outcome": "missing", "fails_on_a_control_too": False})
                continue
            # The always-on provider LOGS alert and per-atom failures and
            # records nothing, so an id it made for another row is compared.
            for result_id in sorted(result_ids):
                if (row.id, producer, result_id) not in present:
                    out.append({"row": row.id, "producer": producer, "result_id": result_id,
                                "outcome": "missing", "fails_on_a_control_too": False})
    return out
