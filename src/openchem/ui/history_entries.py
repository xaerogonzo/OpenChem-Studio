"""Results-reader projections of property executions and Quantum runs.

**NOT THE CACHE.** `SessionResultStore` still answers "fresh for this
structure". These entries are history: they keep `parameters_key` and
`run_id`, they survive a drawing change, and they are deletable without
touching bundle manifests.
"""

from __future__ import annotations

from typing import Iterable

from openchem.domain.property_execution import PropertyExecution
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun
from openchem.domain.report import Fact, FactCategory
from openchem.domain.structure_issue import Basis
from openchem.ui.result_adapters import summarise
from openchem.ui.result_summary import ResultSummaryView

EXEC_PREFIX = "exec:"
QC_PREFIX = "qc:"


def skip_current_duplicate_ids(
    executions: Iterable[PropertyExecution],
    fingerprints: dict[str, str],
    live_result_ids: set[str],
) -> set[str]:
    """Newest current execution per method that the live reader already shows."""
    skip: set[str] = set()
    seen_outputs: set[tuple[str, ...]] = set()
    for execution in executions:
        if not execution.matches_current(fingerprints):
            continue
        outputs = tuple(item.identity.result_id for item in execution.outputs)
        if outputs in seen_outputs:
            continue
        seen_outputs.add(outputs)
        if any(result_id in live_result_ids for result_id in outputs):
            skip.add(execution.execution_id)
    return skip


def history_reader_entries(
    executions: Iterable[PropertyExecution],
    qc_runs: Iterable[QuantumChemistryRun],
    *,
    fingerprints: dict[str, str],
    structure_version: int,
    live_result_ids: set[str] | None = None,
) -> list:
    live = set(live_result_ids or ())
    listed = list(executions)
    skip = skip_current_duplicate_ids(listed, fingerprints, live)
    entries: list = []
    for execution in listed:
        if execution.execution_id in skip:
            continue
        entry = entry_from_execution(execution, fingerprints, structure_version)
        if entry is not None:
            entries.append(entry)
    for run in qc_runs:
        entry = entry_from_quantum_run(run, fingerprints, structure_version)
        if entry is not None:
            entries.append(entry)
    return entries


def entry_from_execution(
    execution: PropertyExecution,
    fingerprints: dict[str, str],
    structure_version: int,
) -> ResultSummaryView | None:
    historical = not execution.matches_current(fingerprints)
    stamp = 0 if historical else structure_version
    order_id = ""
    name = execution.producer
    category = "other"
    facts: list[Fact] = []
    charts = ()
    rich_view = ""
    rich_view_label = ""
    molecule_uuid = execution.molecule_uuid
    for stored in execution.outputs:
        order_id = order_id or stored.identity.result_id
        projected = _project_stored(stored, stamp)
        if projected is None:
            continue
        name = projected.name or name
        category = projected.category or category
        facts.extend(projected.facts)
        if not charts:
            charts = projected.charts
        rich_view = rich_view or projected.rich_view
        rich_view_label = rich_view_label or projected.rich_view_label
        molecule_uuid = projected.molecule_uuid or molecule_uuid
    method = execution.method_model or execution.parameters_key or "default"
    label = name
    if method and method not in label:
        label = f"{name} · {method}"
    if historical:
        label += " · historical"
    if execution.status.value != "completed":
        label += f" · {execution.status.value}"
    facts = [
        Fact(
            category=FactCategory.IDENTITY,
            label="Execution",
            value=execution.execution_id,
            display_value=execution.execution_id[:8],
            source=execution.producer,
            basis=Basis.DETERMINISTIC,
        ),
        Fact(
            category=FactCategory.IDENTITY,
            label="Method / model",
            value=method,
            display_value=method,
            source=execution.producer,
            basis=Basis.DETERMINISTIC,
        ),
        *facts,
    ]
    return ResultSummaryView(
        report_id=f"{EXEC_PREFIX}{execution.execution_id}",
        name=label,
        category=category,
        facts=tuple(facts),
        charts=charts,
        rich_view=rich_view,
        rich_view_label=rich_view_label,
        molecule_uuid=molecule_uuid,
        structure_version=stamp,
        order_id=order_id,
        method_model=method,
        history_kind="execution",
        history_id=execution.execution_id,
        historical=historical,
    )


def entry_from_quantum_run(
    run: QuantumChemistryRun,
    fingerprints: dict[str, str],
    structure_version: int,
) -> ResultSummaryView:
    historical = fingerprints.get(run.calculation_input) != run.input_fingerprint
    stamp = 0 if historical else structure_version
    facts: list[Fact] = [
        Fact(
            category=FactCategory.QUANTUM,
            label="Run id",
            value=run.run_id,
            display_value=run.run_id[:8],
            source=run.provider,
            basis=Basis.DETERMINISTIC,
        ),
        Fact(
            category=FactCategory.QUANTUM,
            label="Engine",
            value=run.provider,
            display_value=run.provider,
            source=run.provider,
            basis=Basis.DETERMINISTIC,
        ),
        Fact(
            category=FactCategory.QUANTUM,
            label="Method / basis",
            value=run.method_basis,
            display_value=run.method_basis,
            source=run.provider,
            basis=Basis.DETERMINISTIC,
        ),
        Fact(
            category=FactCategory.QUANTUM,
            label="Charge / multiplicity",
            value=(run.charge, run.multiplicity),
            display_value=f"{run.charge} / {run.multiplicity}",
            source=run.provider,
            basis=Basis.DETERMINISTIC,
        ),
        Fact(
            category=FactCategory.QUANTUM,
            label="Status",
            value=run.status.value,
            display_value=run.status.value,
            source=run.provider,
            basis=Basis.DETERMINISTIC,
        ),
    ]
    charts = ()
    rich_view = ""
    rich_view_label = ""
    spectrum = run.results.get("spectrum")
    if spectrum is not None:
        projected = _project_result(
            spectrum,
            result_id=f"{QC_PREFIX}{run.run_id}:spectrum",
            name=getattr(spectrum, "name", run.calc_type),
            category="quantum_chemistry",
            structure_version=stamp,
        )
        if projected is not None:
            facts.extend(projected.facts)
            charts = projected.charts or charts
            rich_view = projected.rich_view
            rich_view_label = projected.rich_view_label
    label = f"{run.calc_type} · {run.provider} · {run.method_basis} · {run.run_id[:8]}"
    if historical:
        label += " · historical"
    return ResultSummaryView(
        report_id=f"{QC_PREFIX}{run.run_id}",
        name=label,
        category="quantum_chemistry",
        facts=tuple(facts),
        charts=charts,
        rich_view=rich_view,
        rich_view_label=rich_view_label,
        molecule_uuid=run.molecule_uuid,
        structure_version=stamp,
        order_id="",
        method_model=f"{run.provider} {run.method_basis}".strip(),
        history_kind="quantum",
        history_id=run.run_id,
        historical=historical,
    )


def _project_stored(stored, structure_version: int) -> ResultSummaryView | None:
    identity = stored.identity
    return _project_result(
        stored.result,
        result_id=identity.result_id,
        name=getattr(stored.result, "name", identity.result_id),
        category=getattr(stored.result, "category", "") or "other",
        structure_version=structure_version,
    )


def _project_result(result, *, result_id: str, name: str, category: str, structure_version: int):
    try:
        projected = summarise(
            result,
            result_id=result_id,
            name=name,
            category=category,
            structure_version=structure_version,
        )
    except Exception:
        return None
    if isinstance(projected, ResultSummaryView):
        return projected
    return ResultSummaryView(
        report_id=str(getattr(projected, "report_id", result_id) or result_id),
        name=str(getattr(projected, "name", name) or name),
        category=str(getattr(projected, "category", category) or category),
        facts=tuple(getattr(projected, "facts", ()) or ()),
        charts=tuple(getattr(projected, "charts", ()) or ()),
        molecule_uuid=str(getattr(projected, "molecule_uuid", "") or ""),
        structure_version=structure_version,
    )
