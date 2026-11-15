"""Which calculators a drive Inspector walk will open.

Census already runs every calculator for crash/fault. This walk opens the
Inspector on in-process per-atom results and records why the rest were
left out (sidecar, service/ORCA, not a per-atom dataset). Inspector
``compute`` still skips sidecars. Those calculators are started
asynchronously by ``calculator_walk``.
"""

from __future__ import annotations

import inspect
import typing
from typing import Any

from openchem.domain.calculator import RegistryExecution, ServiceExecution

#: Calculator ids bound to an external interpreter in ``bootstrap``.
#: Computing them on the drive thread can wait on a sidecar; skip instead.
SIDECAR_CALCULATOR_IDS = frozenset(
    {
        "pka",
        "ionisable_sites",
        "logd",
        "pka_microspecies",
        "isoelectric_point",
        "cns_mpo",
        "bbb_descriptors",
        "gasteiger_charge_at_ph",
        "admet_ml",
        "solubility",
    }
)

#: pkasolver-backed ids (ADMET is in ``SIDECAR_CALCULATOR_IDS`` only).
PKASOLVER_CALCULATOR_IDS = frozenset(
    {
        "pka",
        "ionisable_sites",
        "logd",
        "pka_microspecies",
        "isoelectric_point",
        "cns_mpo",
        "bbb_descriptors",
        "gasteiger_charge_at_ph",
    }
)


def _ids_in(definitions: list[Any], wanted: frozenset[str]) -> list[str]:
    return [
        str(getattr(definition, "calculator_id", "") or "")
        for definition in definitions
        if str(getattr(definition, "calculator_id", "") or "") in wanted
    ]


def pkasolver_run_ids(definitions: list[Any]) -> list[str]:
    """Registered pkasolver calculator ids, in registry order."""
    return _ids_in(definitions, PKASOLVER_CALCULATOR_IDS)


def sidecar_run_ids(definitions: list[Any]) -> list[str]:
    """Every interpreter-bound calculator, including ADMET and solubility."""
    return _ids_in(definitions, SIDECAR_CALCULATOR_IDS)


def result_type_name(compute) -> str:
    """The compute callable's declared return type, or ``""``."""
    if compute is None:
        return ""
    try:
        annotation = typing.get_type_hints(compute).get("return")
        if annotation is not None:
            return getattr(annotation, "__name__", "") or ""
    except Exception:  # noqa: BLE001 - a plugin annotation must not break the walk
        pass
    try:
        raw = inspect.signature(compute).return_annotation
    except (TypeError, ValueError):
        return ""
    if raw is inspect.Signature.empty:
        return ""
    return str(raw).strip("\"'").rsplit(".", 1)[-1]


def registry_inspect_plan(definitions: list[Any]) -> list[dict[str, str]]:
    """One row per definition: ``inspect`` or ``skip`` with a reason."""
    rows: list[dict[str, str]] = []
    for definition in definitions:
        calculator_id = str(getattr(definition, "calculator_id", "") or "")
        execution = getattr(definition, "execution", None)
        if isinstance(execution, ServiceExecution):
            rows.append({"id": calculator_id, "action": "skip", "reason": "service"})
            continue
        if calculator_id in SIDECAR_CALCULATOR_IDS:
            rows.append({"id": calculator_id, "action": "skip", "reason": "sidecar"})
            continue
        if not isinstance(execution, RegistryExecution):
            rows.append({"id": calculator_id, "action": "skip", "reason": "not_registry"})
            continue
        declared = result_type_name(execution.compute)
        if declared != "PerAtomDataset":
            rows.append(
                {
                    "id": calculator_id,
                    "action": "skip",
                    "reason": "not_per_atom" if declared else "unknown_result",
                }
            )
            continue
        rows.append({"id": calculator_id, "action": "inspect", "reason": "per_atom"})
    return rows


def plan_counts(plan: list[dict[str, str]]) -> dict[str, int]:
    """How many rows inspect, and how many skip for each reason."""
    counts = {"inspect": 0, "skip": 0}
    for row in plan:
        action = row.get("action") or ""
        counts[action] = counts.get(action, 0) + 1
        if action == "skip":
            reason = f"skip_{row.get('reason') or 'other'}"
            counts[reason] = counts.get(reason, 0) + 1
    return counts
