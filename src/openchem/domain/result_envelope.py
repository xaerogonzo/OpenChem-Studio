"""A stored result, as the assistant is told about it: every number with the facts that give it meaning.

The one serialiser behind `read_results` and the outcome of a run (`docs/AI_CALCULATION_BRIDGE.md`,
section 9). A number detached from its method, units, structure and freshness is the plausible-
looking wrong answer this project refuses to ship, and a model that is handed `[[0, -0.31], ...]` has
nothing to say but a guess about what it is. So an envelope is a **header that is always present** and
a **`data` block that is present only for a result that computed something**:

* `result_id`, `name`, `calculator`, `kind`: which result this is;
* `freshness` and `freshness_note`: whether it still describes the structure (`current`, `historical`,
  `unverifiable`), and why not when it does not;
* `outcome` and `status`: what it says (`computed`, `refused`, `failed`), in the application's own words;
* `input`: which structure it was computed on (drawing or a stored conformer, the input fingerprint,
  which conformer and its energy), so a number is never read as belonging to the untouched drawing;
* `method` and `parameters`: how, and with which settings (the dialog's dict, as recorded; each setting
  is named as the calculator names it, and `describe_calculator` says what it means). A result a SERVICE
  ran, such as an ORCA job, has no registry dialog dict: its `parameters` are the run's calculation type,
  method and basis, charge and multiplicity (`domain.common.RUN_SETTINGS`), stamped from the job's
  submission snapshot. Without them B3LYP/def2-SVP and HF/STO-3G read the same;
* `refusal`: for a result that declined, its code, kind, both sentences and the inputs it wants;
* `caveats`: the report's own assumptions and limitations, never paraphrased away.

**NOTHING NUMERIC LEAVES WITHOUT ITS UNITS.** A per-atom dataset, a spectrum and a curve each put
`units` beside their numbers; a report's facts carry `units` per fact; a number whose unit is in its
key (`energy_kcal_mol`) says so there. `tests/test_result_envelope.py` walks every supported kind and
fails if a numeric value has no unit statement or the header is incomplete.

**BOUNDED, AND SAYING SO.** A result can hold thousands of values; the model is told the count, a
sample of at most `Caps.atoms`, and the minimum, maximum and mean over ALL of them, with `truncated`
stating how many were left out. Identity, units and caveats are never the thing dropped to make room.

**A KIND WITH NO SAFE SERIALISER IS `unsupported`, NOT FORCED THROUGH A GENERIC DICT.** Its header still
says what it is and where it came from; its numbers are not offered. Eight kinds are stored today and all
eight are handled; the fallback is for the ninth nobody has taught this yet.

Pure: no Qt, no RDKit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

#: What the reachability guard accepts for a module nothing in the application imports. Its only
#: importer is the AI Assistant plugin (`plugins/ai_assistant/bridge.py`), which the plugin manager
#: loads from source at run time, so the static walk from `openchem.main` cannot see that edge.
#: `tests/test_calculator_reachability.py` checks the claim is true.
REACHED_BY = (
    "plugin_source: imported only by plugins/ai_assistant/bridge.py, which the plugin manager "
    "loads from source at run time rather than by an import from openchem.main"
)

from openchem.domain.common import ATOM_BASIS, CATEGORICAL_SCALE, RUN_PREFIX, RUN_SETTINGS, TOTAL
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.refusal_kinds import REFUSAL_KEY, missing_inputs_of, refusal_kind_of_result
from openchem.domain.report import Fact, ReportResult, StructureReport
from openchem.domain.run_lifecycle import RunOutcome
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureSetResult,
    TrajectoryResult,
)
from openchem.domain.turn_snapshot import Freshness, Outcome, ResultEntry, ResultsView

#: The shape of what a model is sent, bumped when a reader of an old transcript would misread a new one.
#: NOT `result_store.ENVELOPE_VERSION`, which is the version of the saved-project format: a different
#: thing that happens to share the word.
MODEL_ENVELOPE_VERSION = 1

#: The keys `provenance.parameters` uses for the structure a result was computed on. They are
#: written by `chem.calculation_input` (`INPUT_PREFIX`), which `domain/` may not import; a test pins
#: that these are the same strings.
_INPUT = "input_"
#: Where the input came from: the drawing, or an automatically chosen lowest-energy conformer.
INPUT_SOURCE_KEY = _INPUT + "source"
#: The settings the structure was chosen with, when the producer recorded any.
INPUT_PARAMETERS_KEY = _INPUT + "parameters"
#: Which of the molecule's stored conformers was used.
INPUT_CONFORMER_INDEX_KEY = _INPUT + "conformer_index"
#: That conformer's energy as recorded, in the units of its own record.
INPUT_CONFORMER_ENERGY_KEY = _INPUT + "conformer_energy"
#: The force field that conformer was optimised with.
INPUT_FORCE_FIELD_KEY = _INPUT + "force_field"
#: `provenance.parameters["scale"]`, by which a producer says its per-atom values are category ids.
SCALE_KEY = "scale"

#: The kinds this module can read, in `kind_of`'s order. The test walks this tuple.
SUPPORTED_KINDS = (
    "descriptor", "report", "alert", "per_atom", "spectrum", "structure_set", "ph_curve", "trajectory",
)


@dataclass(frozen=True)
class Caps:
    """How much of a result an envelope carries. Halved, in steps, until a reply fits its budget."""

    atoms: int = 60
    facts: int = 40
    items: int = 40
    evidence: int = 3
    points: int = 25
    text: int = 400

    def scaled(self, factor: float) -> Caps:
        def cut(n: int) -> int:
            return max(1, int(n * factor))

        return Caps(cut(self.atoms), cut(self.facts), cut(self.items), cut(self.evidence), cut(self.points), max(60, cut(self.text)))


#: The full-size caps: what a reply is built with first, before `CAP_STEPS` shrinks it.
FULL = Caps()
#: What is tried, in order, when a reply is over budget. The last still carries every header.
CAP_STEPS = (FULL, FULL.scaled(0.5), FULL.scaled(0.25), FULL.scaled(0.1))


def _n(value: Any) -> Any:
    """A number to six significant figures; a non-finite one as its name. Everything else untouched."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return float(f"{value:.6g}")
    return value


def _t(text: Any, limit: int) -> str:
    """Text cut at `limit` characters, saying so."""
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "…"


def kind_of(result: object) -> str:
    """Which of `SUPPORTED_KINDS` this is, or "unsupported"."""
    if isinstance(result, DescriptorValue):
        return "descriptor"
    if isinstance(result, StructureReport):
        return "report"
    if isinstance(result, AlertResult):
        return "alert"
    if isinstance(result, PerAtomDataset):
        return "per_atom"
    if isinstance(result, SpectrumResult):
        return "spectrum"
    if isinstance(result, StructureSetResult):
        return "structure_set"
    if isinstance(result, PhCurveResult):
        return "ph_curve"
    if isinstance(result, TrajectoryResult):
        return "trajectory"
    return "unsupported"


def _provenance_parameters(result: object) -> dict[str, Any]:
    parameters = getattr(getattr(result, "provenance", None), "parameters", None)
    return parameters if isinstance(parameters, dict) else {}


#: Most settings one envelope names. Settings are part of what a number MEANS, so unlike rows they are
#: not halved with the caps; this only stops a pathological record (a project saved by something else)
#: from flooding a reply. A real calculator has a handful.
MAX_SETTINGS = 32


def _setting_value(value: Any, caps: Caps, nested: bool = False) -> Any:
    """One recorded setting, bounded. A number stays exact (it is a setting, not a measurement), except a
    non-finite one, which JSON cannot carry and is named instead."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _n(value)
    if isinstance(value, (list, tuple)) and not nested:
        return [_setting_value(item, caps, nested=True) for item in value[: caps.items]]
    return _t(value, caps.text)


def _settings_of(parameters: dict[str, Any], caps: Caps) -> tuple[dict[str, Any], int]:
    """What the result was run with, and how many settings were left out for length.

    Two recorded forms, one block: the routing layer's `input_parameters` (the dict a registry calculator
    was handed) and a service run's `run_*` keys (`RUN_SETTINGS`), shown WITHOUT the prefix, as the
    panel names them. A result has one or the other, so they do not meet; if one ever did, the dialog's
    own dict wins rather than being overwritten. Never `provenance.parameters` as a whole: that holds the
    producer's working (`orca_version`, a caveat, a refusal code) and the structure keys, which have
    blocks of their own.
    """
    recorded = parameters.get(INPUT_PARAMETERS_KEY)
    settings: dict[str, Any] = dict(recorded) if isinstance(recorded, dict) else {}
    for key in RUN_SETTINGS:
        if key in parameters:
            settings.setdefault(key[len(RUN_PREFIX):], parameters[key])
    shown = {
        _t(name, 80): _setting_value(value, caps) for name, value in list(settings.items())[:MAX_SETTINGS]
    }
    return shown, max(0, len(settings) - MAX_SETTINGS)


def _name_of(result: object, fallback: str) -> str:
    return str(getattr(result, "name", "") or fallback)


def _method_of(result: object) -> str:
    return str(getattr(result, "method", "") or getattr(getattr(result, "provenance", None), "method", "") or "")


def _input_block(entry: ResultEntry, parameters: dict[str, Any]) -> dict[str, Any]:
    """Which structure the numbers belong to. Never left to be assumed to be the drawing."""
    identity = entry.stored.identity
    block: dict[str, Any] = {
        "kind": identity.calculation_input,
        "fingerprint": identity.input_fingerprint[:16],
        "source": parameters.get(INPUT_SOURCE_KEY, "drawing" if identity.calculation_input != "geometry" else ""),
    }
    if INPUT_CONFORMER_INDEX_KEY in parameters:
        block["conformer_index"] = parameters[INPUT_CONFORMER_INDEX_KEY]
    energy = parameters.get(INPUT_CONFORMER_ENERGY_KEY)
    if isinstance(energy, (int, float)) and not isinstance(energy, bool):
        block["conformer_energy_kcal_mol"] = _n(energy)
    if parameters.get(INPUT_FORCE_FIELD_KEY):
        block["force_field"] = parameters[INPUT_FORCE_FIELD_KEY]
    return block


def _refusal_block(result: object, caps: Caps) -> dict[str, Any]:
    kind = refusal_kind_of_result(result)
    parameters = _provenance_parameters(result)
    return {
        "code": str(parameters.get(REFUSAL_KEY, "") or ""),
        "kind": kind.value if kind is not None else "",
        "summary": _t(getattr(result, "error_summary", None), caps.text),
        "detail": _t(getattr(result, "error", None), caps.text * 2),
        "missing_inputs": [item.to_dict() for item in missing_inputs_of(result)],
    }


def _fact(fact: Fact, caps: Caps) -> dict[str, Any]:
    data: dict[str, Any] = {
        "label": _t(fact.label, caps.text),
        "value": _t(fact.display_value, caps.text),
        "units": fact.units,
        "basis": getattr(fact.basis, "value", str(fact.basis)),
        "source": fact.source,
    }
    if fact.evidence:
        data["evidence"] = [_t(item, caps.text) for item in fact.evidence[: caps.evidence]]
    if fact.limitations:
        data["limitations"] = [_t(item, caps.text) for item in fact.limitations]
    return data


def _facts_block(facts: tuple[Fact, ...], caps: Caps) -> dict[str, Any]:
    shown = facts[: caps.facts]
    block: dict[str, Any] = {"facts": [_fact(f, caps) for f in shown], "count": len(facts)}
    if len(facts) > len(shown):
        block["truncated"] = len(facts) - len(shown)
    return block


def _stats(values: list[float]) -> dict[str, Any]:
    return {"min": _n(min(values)), "max": _n(max(values)), "mean": _n(sum(values) / len(values))}


def _per_atom_data(result: PerAtomDataset, parameters: dict[str, Any], caps: Caps) -> dict[str, Any]:
    items = sorted(result.values.items())
    categorical = parameters.get(SCALE_KEY) == CATEGORICAL_SCALE
    data: dict[str, Any] = {
        "units": result.units,
        "count": len(items),
        "values": [[atom, _n(value)] for atom, value in items[: caps.atoms]],
        "atom_basis": str(parameters.get(ATOM_BASIS, "") or ""),
        "atom_index_space": (
            "atom indices of the structure carried with this result (not the drawing)"
            if result.structure_molblock
            else "atom indices of the structure named in `input`"
        ),
        "categorical": categorical,
    }
    if len(items) > caps.atoms:
        data["truncated"] = len(items) - caps.atoms
    if items and not categorical:
        data["statistics_over_all_values"] = _stats([value for _atom, value in items])
    total = parameters.get(TOTAL)
    if isinstance(total, dict):
        if total.get("declared"):
            data["declared_total"] = {
                "label": str(total.get("label", "")), "value": _n(total.get("value")),
                "units": str(total.get("units", "")), "basis": str(total.get("basis", "")),
            }
        else:
            data["no_total"] = _t(total.get("reason", ""), caps.text)
    else:
        data["no_total"] = "the producer declared no molecular total; none is implied by summing these"
    return data


def _descriptor_data(result: DescriptorValue, caps: Caps) -> dict[str, Any]:
    value = result.value
    if isinstance(value, (list, tuple)):
        shown = [_n(v) if isinstance(v, (int, float)) else _t(v, caps.text) for v in value[: caps.items]]
        value_block: Any = shown
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        value_block = _n(value)
    elif isinstance(value, (bool, type(None))):
        value_block = value
    else:
        value_block = _t(value, caps.text)
    return {
        "descriptor_id": result.descriptor_id, "provider": result.provider, "category": result.category,
        "value": value_block, "units": result.units,
    }


def _report_data(result: StructureReport, caps: Caps) -> dict[str, Any]:
    data = _facts_block(result.facts, caps)
    severity = getattr(getattr(result, "severity", None), "value", "")
    if severity:
        data["severity"] = severity
    return data


def _alert_data(result: AlertResult, caps: Caps) -> dict[str, Any]:
    return {
        "alert_id": result.alert_id, "severity": getattr(result.severity, "value", str(result.severity)),
        "count": len(result.matched), "matched": [_t(m, caps.text) for m in result.matched[: caps.items]],
        "truncated": max(0, len(result.matched) - caps.items) or None,
    }


def _spectrum_data(result: SpectrumResult, caps: Caps) -> dict[str, Any]:
    items = sorted(result.values.items())
    data: dict[str, Any] = {
        "spectrum_type": result.spectrum_type, "units": result.units, "count": len(items),
        "peaks": [[atom, result.elements.get(atom, ""), _n(value)] for atom, value in items[: caps.atoms]],
        "peak_columns": ["atom_index", "element", "value"],
    }
    if len(items) > caps.atoms:
        data["truncated"] = len(items) - caps.atoms
    if items:
        data["statistics_over_all_values"] = _stats([v for _a, v in items])
    return data


def _structure_set_data(result: StructureSetResult, caps: Caps) -> dict[str, Any]:
    shown = result.entries[: caps.items]
    data: dict[str, Any] = {
        "count": len(result.entries),
        "total_available": result.total_available,
        "generation_truncated": result.truncated,
        "labels": [_t(e.label, caps.text) for e in shown],
        "note": "scores and energies are not included in this summary; the structures are in the application",
    }
    if len(result.entries) > len(shown):
        data["truncated"] = len(result.entries) - len(shown)
    return data


def _ph_curve_data(result: PhCurveResult, caps: Caps) -> dict[str, Any]:
    xs = result.ph_values
    step = max(1, len(xs) // max(1, caps.points)) if xs else 1
    series: dict[str, Any] = {}
    for name, ys in list(result.series.items())[: caps.items]:
        if ys:
            series[name] = {
                **_stats(list(ys)),
                "sampled_points": [[_n(x), _n(y)] for x, y in list(zip(xs, ys))[::step]],
            }
    data: dict[str, Any] = {
        "x_label": result.x_label, "units": result.y_label, "points": len(xs),
        "x_range": [_n(min(xs)), _n(max(xs))] if xs else [], "series": series,
    }
    if result.facts:
        data.update(_facts_block(result.facts, caps))
    return data


def _trajectory_data(result: TrajectoryResult, caps: Caps) -> dict[str, Any]:
    data: dict[str, Any] = {"frames": len(result.frames), "units": "kcal/mol for energies, fs for times, K for temperature"}
    if result.times:
        data["time_range_fs"] = [_n(min(result.times)), _n(max(result.times))]
    if result.energies:
        data["energy_kcal_mol"] = _stats(list(result.energies))
    if isinstance(result.temperature, (int, float)) and not isinstance(result.temperature, bool):
        data["initial_temperature_k"] = _n(result.temperature)
    return data


def _caveats(result: object, entry: ResultEntry, caps: Caps) -> list[str]:
    caveats: list[str] = []
    if entry.note:
        caveats.append(entry.note)
    for attribute in ("assumptions", "limitations"):
        caveats.extend(_t(item, caps.text) for item in (getattr(result, attribute, ()) or ()))
    return caveats


def envelope_of(entry: ResultEntry, caps: Caps = FULL) -> dict[str, Any]:
    """One stored result as a plain, JSON-safe dict. See the module docstring."""
    stored = entry.stored
    result = stored.result
    identity = stored.identity
    kind = kind_of(result)
    parameters = _provenance_parameters(result)
    settings, settings_left_out = _settings_of(parameters, caps)
    envelope: dict[str, Any] = {
        "result_id": identity.result_id,
        "name": _t(_name_of(result, identity.result_id), caps.text),
        "calculator": identity.producer,
        "kind": kind,
        "freshness": entry.freshness.value,
        "freshness_note": entry.note,
        "outcome": entry.outcome.value,
        "status": entry.status,
        "input": _input_block(entry, parameters),
        "method": {
            "name": _method_of(result),
            "version": identity.method_version,
            "created_by": str(getattr(getattr(result, "provenance", None), "created_by", "") or ""),
            "application_version": stored.application_version,
            "from_saved_project": bool(stored.restored),
        },
        "parameters": settings,
        "caveats": _caveats(result, entry, caps),
    }
    if settings_left_out:
        envelope["caveats"].append(f"{settings_left_out} further recorded settings were left out for length")
    if entry.outcome is not Outcome.COMPUTED:
        envelope["refusal"] = _refusal_block(result, caps)
        return envelope
    if kind == "descriptor":
        envelope["data"] = _descriptor_data(result, caps)
    elif kind == "report":
        envelope["data"] = _report_data(result, caps)
    elif kind == "alert":
        envelope["data"] = {k: v for k, v in _alert_data(result, caps).items() if v is not None}
    elif kind == "per_atom":
        envelope["data"] = _per_atom_data(result, parameters, caps)
    elif kind == "spectrum":
        envelope["data"] = _spectrum_data(result, caps)
    elif kind == "structure_set":
        envelope["data"] = _structure_set_data(result, caps)
    elif kind == "ph_curve":
        envelope["data"] = _ph_curve_data(result, caps)
    elif kind == "trajectory":
        envelope["data"] = _trajectory_data(result, caps)
    else:
        envelope["unsupported"] = (
            f"{type(result).__name__} has no serialiser here, so its values are not offered; "
            "its identity above says what it is and where it came from"
        )
    return envelope


def results_view_envelope(view: ResultsView, caps: Caps = FULL) -> dict[str, Any]:
    """A `ResultsView` as the dict `read_results` returns."""
    return {
        "envelope_version": MODEL_ENVELOPE_VERSION,
        "molecule_uuid": view.molecule_uuid,
        "results": [envelope_of(entry, caps) for entry in view.entries],
        "not_run": list(view.not_run),
        "only_not_current": list(view.only_not_current),
        "left_out_for_length": view.truncated,
        "note": (
            "A result is current only if its freshness says so. Anything not run is absent, never zero. "
            "Do not state a value that is not in a result here."
        ),
    }


def outcome_envelope(outcome: RunOutcome, caps: Caps = FULL) -> dict[str, Any]:
    """What a run came to, with the result's envelope when it produced one."""
    data: dict[str, Any] = {
        "envelope_version": MODEL_ENVELOPE_VERSION,
        "run_id": outcome.run_id,
        "calculator": outcome.calculator_id,
        "state": outcome.state.value,
        "message": _t(outcome.message, caps.text * 2),
        "has_number": outcome.has_number,
        "problems": [p.to_dict() for p in outcome.problems],
    }
    if outcome.stored is not None:
        entry = ResultEntry(
            stored=outcome.stored, freshness=Freshness.CURRENT, status=outcome.status,
            outcome=Outcome.COMPUTED if outcome.has_number else (
                Outcome.FAILED if outcome.state.value == "failed" else Outcome.REFUSED
            ),
        )
        data["result"] = envelope_of(entry, caps)
    return data
