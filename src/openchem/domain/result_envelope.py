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

**A USER-DEFINED SCORE IS ANSWERED THE SAME WAY, THOUGH IT IS NOT A STORED RESULT** (`scores_view_envelope`, behind `read_scores`): a header that is always present (its label with the
suffix `(user-defined, unvalidated)`, its formula, its declared unit, the definition's digest, every input with the state it was read in) and a `data` block only for a score that has a
number. It says it is a formula a person wrote and is not a prediction; owner and note, which are a person's free text, are never sent.

**A KIND WITH NO SAFE SERIALISER IS `unsupported`, NOT FORCED THROUGH A GENERIC DICT.** Its header still
says what it is and where it came from; its numbers are not offered. Eight kinds are stored today and all
eight are handled; the fallback is for the ninth nobody has taught this yet.

Pure: no Qt, no RDKit.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
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
from openchem.domain.score_answer import DEFAULTED as SCORE_DEFAULTED
from openchem.domain.score_answer import LIMITATION as SCORE_LIMITATION
from openchem.domain.score_definition import VALIDATION as SCORE_VALIDATION
from openchem.domain.score_outputs import ENDPOINTS, READ_FROM, ApprovedOutput, output_title
from openchem.domain.score_proposal import ASSISTANT_OWNER, ProposalRefusal, Registered
from openchem.domain.score_reading import ScoresView
from openchem.domain.score_value import InputEvidence, InputState, ScoreStatus, ScoreValue
from openchem.domain.quantum_chemistry_run import OutputStatus
from openchem.domain.quantum_run_snapshot import RunEntry, RunsView
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureSetResult,
    TrajectoryResult,
    VibrationalSpectrumResult,
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

#: Longest a caveat a PRODUCER recorded in its provenance is sent whole. It is not halved with the caps: what a number
#: is not, or that its method did not pass its own check, is part of what it MEANS, and the Fukui caveat is five sentences
#: (1320 characters measured with every warning on) whose last, the standing of the calculation, was cut away by the 400 a
#: header caveat gets. Producers write fixed sentences, so this only stops a runaway string from a project saved by something else.
RECORDED_CAVEAT_LIMIT = 2000


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


def _vibrational_data(result: VibrationalSpectrumResult, caps: Caps) -> dict[str, Any]:
    """The modes of a harmonic analysis. NOT `_spectrum_data`: a vibrational spectrum keeps its numbers in `modes` and leaves `values` empty on purpose, so reading it as per-atom peaks would tell a model it has none."""
    modes = sorted(result.modes, key=lambda mode: mode.wavenumber_cm1)
    shown = modes[: caps.atoms]
    data: dict[str, Any] = {
        "spectrum_type": result.spectrum_type, "units": "wavenumber in cm^-1, IR intensity in km/mol", "count": len(modes),
        "modes": [[_n(m.wavenumber_cm1), _n(m.ir_intensity_km_mol), m.character or ""] for m in shown],
        "mode_columns": ["wavenumber_cm1", "ir_intensity_km_mol", "character"],
        "imaginary_modes": len(result.imaginary_modes),
        "scaling_factor_applied_here": _n(result.scaling_factor),
    }
    if len(modes) > len(shown):
        data["truncated"] = len(modes) - len(shown)
    if result.imaginary_warning:
        data["imaginary_warning"] = _t(result.imaginary_warning, caps.text)
    return data


def _spectrum_data(result: SpectrumResult, caps: Caps) -> dict[str, Any]:
    if isinstance(result, VibrationalSpectrumResult):
        return _vibrational_data(result, caps)
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
    caveats.extend(_result_caveats(result, caps))
    return caveats


def _result_caveats(result: object, caps: Caps) -> list[str]:
    """What the result itself says about its limits (assumptions, limitations, a producer's recorded caveat), without the freshness note."""
    caveats: list[str] = []
    for attribute in ("assumptions", "limitations"):
        caveats.extend(_t(item, caps.text) for item in (getattr(result, attribute, ()) or ()))
    # A caveat a PRODUCER recorded in its provenance (`caveat`): the Koopmans hardness that inverts ammonia and
    # phosphine, a Fukui f+ taken on an unbound anion. It travels with the number in the Atom Inspector, and was
    # not sent to a model at all, because a descriptor and a per-atom dataset have no `assumptions` field to
    # carry it. It is not a setting (`_settings_of` leaves it out on purpose), so it belongs here.
    recorded = _provenance_parameters(result).get("caveat")
    if isinstance(recorded, str) and recorded.strip():
        caveats.append(_t(recorded, max(caps.text, RECORDED_CAVEAT_LIMIT)))
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
    data = data_of(result, caps)
    if data is not None:
        envelope["data"] = data
    else:
        envelope["unsupported"] = _unsupported(result)
    return envelope


def _unsupported(result: object) -> str:
    return (
        f"{type(result).__name__} has no serialiser here, so its values are not offered; "
        "its identity above says what it is and where it came from"
    )


def data_of(result: object, caps: Caps = FULL) -> dict[str, Any] | None:
    """The numbers of one result as a plain dict, by its kind, or None for a kind with no safe serialiser. The one dispatch behind a stored result and an output of an ORCA run."""
    kind = kind_of(result)
    parameters = _provenance_parameters(result)
    if kind == "descriptor":
        return _descriptor_data(result, caps)
    if kind == "report":
        return _report_data(result, caps)
    if kind == "alert":
        return {k: v for k, v in _alert_data(result, caps).items() if v is not None}
    if kind == "per_atom":
        return _per_atom_data(result, parameters, caps)
    if kind == "spectrum":
        return _spectrum_data(result, caps)
    if kind == "structure_set":
        return _structure_set_data(result, caps)
    if kind == "ph_curve":
        return _ph_curve_data(result, caps)
    if kind == "trajectory":
        return _trajectory_data(result, caps)
    return None


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


# --- the ORCA runs a person ran (`read_quantum_runs`) -----------------------------------------------------------------------------------------------------------------

#: What a model is told with every read of the ORCA runs: what a run is, what freshness means, that a failed or cancelled job has no numbers, and that no value may be stated that is not in a run read here.
READ_RUNS_NOTE = (
    "A run is one ORCA job a person ran for this molecule. Its freshness says whether it was run on the structure now drawn; a run that is not current is listed only when asked for and must never be reported as the "
    "answer for this structure. 'failed' and 'cancelled' runs have no numbers: say how they ended and quote the warnings. A listed output with status 'available' holds numbers, which are returned only when you "
    "ask for that run by run_id. Never state a value that is not in a run read here, and never treat an output that was not produced as zero."
)


def _iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(timespec="seconds")


def _output_summary(key: str, status: OutputStatus | None, results: tuple[Any, ...], caps: Caps) -> dict[str, Any]:
    """One output of a run, named and counted, with no numbers: the header a list carries."""
    item: dict[str, Any] = {"status": status.value if status is not None else ("available" if results else "not_recorded")}
    if not results:
        return item
    kinds = {"number" if isinstance(r, (int, float)) and not isinstance(r, bool) else kind_of(r) for r in results}
    item["kind"] = kinds.pop() if len(kinds) == 1 else "mixed"
    item["count"] = len(results)
    names = [_t(_name_of(r, ""), caps.text) for r in results[: caps.items]]
    if any(names):
        item["names"] = names
    return item


def _output_detail(key: str, status: OutputStatus | None, results: tuple[Any, ...], caps: Caps) -> dict[str, Any]:
    """One output of a run with its numbers, each result through the serialiser a stored result of that kind uses."""
    item = _output_summary(key, status, results, caps)
    if not results:
        return item
    shown: list[dict[str, Any]] = []
    for result in results[: caps.items]:
        if isinstance(result, (int, float)) and not isinstance(result, bool):
            shown.append({"name": key, "value": _n(result)})
            continue
        entry: dict[str, Any] = {"name": _t(_name_of(result, key), caps.text), "kind": kind_of(result)}
        data = data_of(result, caps)
        if data is not None:
            entry["data"] = data
        else:
            entry["unsupported"] = _unsupported(result)
        caveats = _result_caveats(result, caps)
        if caveats:
            entry["caveats"] = caveats
        shown.append(entry)
    item["results"] = shown
    if len(results) > len(shown):
        item["truncated"] = len(results) - len(shown)
    return item


def run_envelope(entry: RunEntry, caps: Caps = FULL, *, detailed: bool = False) -> dict[str, Any]:
    """One stored ORCA run as a plain dict. A header always; numbers only when `detailed` and only for a run that computed something."""
    keys = list(dict.fromkeys([*entry.output_status, *entry.outputs]))
    outputs: dict[str, Any] = {}
    for key in keys:
        status = entry.output_status.get(key)
        results = entry.outputs.get(key, ())
        outputs[key] = (
            _output_detail(key, status, results, caps) if detailed and entry.usable else _output_summary(key, status, results, caps)
        )
    duration = None if entry.completed_at is None else round(max(0.0, entry.completed_at - entry.started_at), 1)
    return {
        "run_id": entry.run_id,
        "calculation": {
            "calc_type": entry.calc_type, "method_basis": entry.method_basis, "charge": entry.charge,
            "multiplicity": entry.multiplicity, "solvent": entry.solvent, "provider": entry.provider,
        },
        "input": {"kind": entry.calculation_input, "fingerprint": entry.input_fingerprint},
        "freshness": entry.freshness.value,
        "freshness_note": entry.note,
        "outcome": entry.outcome.value,
        "status": entry.status.value,
        "started_at": _iso(entry.started_at),
        "finished_at": _iso(entry.completed_at),
        "duration_seconds": duration,
        "warnings": [_t(w, caps.text) for w in entry.warnings],
        "produced_geometry": entry.produced_geometry,
        "outputs": outputs,
    }


def runs_view_envelope(view: RunsView, caps: Caps = FULL) -> dict[str, Any]:
    """A `RunsView` as the dict `read_quantum_runs` returns."""
    return {
        "envelope_version": MODEL_ENVELOPE_VERSION,
        "molecule_uuid": view.molecule_uuid,
        "runs": [run_envelope(entry, caps, detailed=view.detailed) for entry in view.entries],
        "not_found": list(view.not_found),
        "not_current_left_out": view.not_current_left_out,
        "left_out_for_length": view.truncated,
        "note": READ_RUNS_NOTE,
    }


#: Said with every score, because it is what a model reporting one most needs to be told.
SCORE_NOT_A_PREDICTION = (
    "A score is a formula a person wrote over numbers this application computes. It is not a prediction of anything and nothing has validated it: report it with its label and unit, "
    "and never as an experimental or predicted property."
)

#: What a model is told about reading and changing scores, sent with every read.
SCORES_NOTE = (
    "Each score is worked out from this molecule's CURRENT results as of this turn, so its value is current or it has none. An input is read from the drawing, except the geometry outputs "
    "(the shape descriptors, eight of Geometry Analysis's sizes, HOMA's two extremes, the dipole's magnitude and five surface numbers; their input has `calculation_input` set to `geometry`; every other input has none), which are read from the conformer every calculation uses and named in the input's `conformer`: "
    "a score over one has no value for a molecule with no conformer, or one measured on an earlier conformer than the one used now, and you must say so rather than substitute another. "
    "An input in the state `not_applicable` is a geometry output the application declines to read for this molecule (it is several fragments, such as a salt, whose 3D shape is not a property of the compound, "
    "or Geometry Analysis measured another geometry than the conformer or scaled its radii, or, for the highest and lowest HOMA of any ring, the conformer was not one ORCA optimised, or the dipole was not Gasteiger's or is of a charged species, "
    "or an accessible area was made with another probe than 1.4 Å or on the major microspecies): its `note` says which, and you must pass that on and never suggest a number for it. "
    "The two HOMA outputs read bond lengths, so they are read only from a conformer a quantum calculation optimised, and the input's `conformer` then names its level of theory; a force-field conformer's bond lengths are the force field's own. "
    "The dipole is read only as the magnitude from Gasteiger charges of a species with no net charge (the three charge models differ by a factor of up to five on one molecule, and a charged species has no dipole of its own), "
    "and the accessible areas only at the 1.4 Å probe on the structure as it is; a dipole is of one conformer, and a flexible molecule's differs between its conformers. "
    "A score whose outcome is 'refused' has no value: say which input could not be read and why, and never state a value or treat it as zero. A unit of 1 means a plain number. "
    "A score whose outcome is 'computed_with_defaults' used a default its definition declares for an input nobody calculated (`defaults_used`): say so, name those inputs, "
    "and never present the number as the result of calculating them. "
    "You cannot create, change or delete a score; you may suggest formula text for the person to enter in Tools > Derived Scores."
)


def _input_envelope(item: InputEvidence, caps: Caps) -> dict[str, Any]:
    data: dict[str, Any] = {"name": item.name, "reads": output_title(item.output_id) or item.output_id, "output_id": item.output_id, "state": item.state.value}
    if item.state in (InputState.READ, InputState.DEFAULT):
        data["value"] = _n(item.value)
        data["units"] = item.carried_as
    if item.state is InputState.READ and item.calculation_input != READ_FROM:
        # Said only for an input that is NOT the drawing's: the absence of the key is the drawing, which is what nearly every output is.
        data["calculation_input"] = item.calculation_input
        if item.geometry:
            data["conformer"] = _t(item.geometry, 120)
    if item.state is not InputState.READ:
        data["note"] = _t(item.note, caps.text)
    return data


def score_envelope_of(value: ScoreValue, caps: Caps = FULL) -> dict[str, Any]:
    """One score as the model is told it: the header always, the number only when there is one."""
    definition = value.definition
    computed = value.status is ScoreStatus.VALUE
    defaulted = [item.name for item in value.defaulted]
    outcome = ("computed_with_defaults" if defaulted else "computed") if computed else "refused"
    data: dict[str, Any] = {
        "score_id": definition.score_id,
        "name": definition.display_label,
        "kind": "user_defined_score",
        "validation": SCORE_VALIDATION,
        "freshness": "current",
        "freshness_note": "worked out from the molecule's current results as of this turn; a score is never stored",
        "outcome": outcome,
        "formula": _t(value.formula or definition.formula, caps.text),
        "declared_units": definition.result_unit,
        "definition": definition.digest,
        "inputs": [_input_envelope(item, caps) for item in value.inputs[: caps.items]],
        "constants": [{"name": c.name, "value": _n(c.value), "units": c.unit} for c in definition.constants[: caps.items]],
        "caveats": [SCORE_LIMITATION, SCORE_NOT_A_PREDICTION],
    }
    if definition.defaults:
        data["declared_defaults"] = [{"input": name, "value": _n(number)} for name, number in definition.defaults[: caps.items]]
    if computed:
        data["data"] = {"value": _n(value.value), "units": definition.result_unit}
        if defaulted:
            data["defaults_used"] = defaulted
            data["caveats"] = [*data["caveats"], SCORE_DEFAULTED.format(names=", ".join(defaulted))]
    else:
        data["refusal"] = {
            "reason": _t(value.reason, caps.text * 2),
            "inputs_not_read": [i.name for i in value.inputs if i.state not in (InputState.READ, InputState.DEFAULT)],
        }
        if value.defaulted:
            data["refusal"]["inputs_defaulted"] = [i.name for i in value.defaulted]
    return data


def scores_view_envelope(view: ScoresView, caps: Caps = FULL) -> dict[str, Any]:
    """A `ScoresView` as the dict `read_scores` returns."""
    shown = view.values[: caps.items]
    return {
        "envelope_version": MODEL_ENVELOPE_VERSION,
        "molecule_uuid": view.molecule_uuid,
        "scores": [score_envelope_of(value, caps) for value in shown],
        "not_found": list(view.not_found),
        "defined_in_this_project": view.defined,
        "left_out_for_length": view.truncated + (len(view.values) - len(shown)),
        "note": SCORES_NOTE,
    }


#: What a model is told with the list of outputs a score may read.
SCORE_OUTPUTS_NOTE = (
    "Name an output in propose_score by its output_id. `unit` is how to write that output's unit for a constant or the result_unit (for example 'Å^2'); `1` is a plain number. "
    "Two outputs with the same endpoint estimate one quantity and cannot be in one score. Units are never converted: a formula that adds two different units is refused, and a bare number "
    "in a formula takes the unit of what it is added to or compared with. An output whose `input` is `geometry` is measured on a conformer: it has no value for a molecule that has none, or whose structure is several fragments (a salt)."
)

#: What a model is told when a proposal is waiting, which is what it most needs to say correctly to the person.
SCORE_PROPOSAL_NOTE = (
    "A card showing this score is on the user's screen. NOTHING IS SAVED until they press Approve, and you cannot approve it: say that it is waiting for them, never that it is saved or "
    "that you created it. Do not propose it again; you will be told what they decided with their next message. If it is approved the owner is recorded as the AI assistant."
)


#: How many outputs `list_score_outputs` lists at full size, scaled with the caps like every other list. Its own limit and not `Caps.items` (40, for facts and structures): the approved table passed 40 outputs
#: and the 41st, the last by id, fell off the model's list with only `left_out_for_length` to say so. A row is about 215 bytes, and with the ten shape outputs (2026-10-17) the table passed what `REPLY_BUDGET` (12000) holds, so the stepped caps
#: began dropping the last rows. `list_score_outputs` therefore has a budget of its own (`plugins/ai_assistant/bridge.SCORE_OUTPUTS_BUDGET`); `tests/test_ai_assistant_score_proposals.py` turns red before it is crossed. With Geometry Analysis's
#: eight sizes (59 outputs, rows of about 350 bytes for the long ids) the list took 14,249 of 16,000, so the budget is 20,000.
SCORE_OUTPUT_ROWS = 120


def score_outputs_envelope(entries: Sequence[ApprovedOutput], caps: Caps = FULL) -> dict[str, Any]:
    """The outputs a score may read (`entries`, from the plugin handle), as `list_score_outputs` returns them."""
    shown = entries[: max(1, SCORE_OUTPUT_ROWS * caps.items // FULL.items)]
    return {
        "envelope_version": MODEL_ENVELOPE_VERSION,
        "outputs": [
            {
                "output_id": entry.output_id, "reads": output_title(entry.output_id) or entry.output_id, "unit": entry.unit,
                "endpoint": entry.endpoint, "measures": ENDPOINTS.get(entry.endpoint, ""),
                # Only a geometry row says its input: a row with none is the drawing's, and 41 rows saying so would cost a fifth of a reply that has a budget.
                **({} if entry.input == READ_FROM else {"input": entry.input}),
            }
            for entry in shown
        ],
        "left_out_for_length": len(entries) - len(shown),
        "note": SCORE_OUTPUTS_NOTE,
    }


def score_proposal_envelope(registered: Registered, caps: Caps = FULL) -> dict[str, Any]:
    """A proposal that is waiting for a person, as the model is told: what it would be and give, and that nothing is saved."""
    proposal = registered.proposal
    score = score_envelope_of(proposal.preview, caps)
    score.pop("score_id", None)  # the draft's id is not the id it will have, and a model must not refer to it
    return {
        "ok": True,
        "state": "awaiting_approval",
        "proposal_id": proposal.proposal_id,
        "already_waiting": registered.already_waiting,
        "molecule_uuid": proposal.molecule_uuid,
        "score": score,
        "owner_if_approved": ASSISTANT_OWNER,
        "message": SCORE_PROPOSAL_NOTE,
    }


def score_refusal_envelope(refusal: ProposalRefusal, caps: Caps = FULL) -> dict[str, Any]:
    """A request that was not made a proposal, said in the request's own terms so the model can fix it. Nothing is on the user's screen."""
    data: dict[str, Any] = {"ok": False, "problem": refusal.problem.value, "message": _t(refusal.message, caps.text * 2), "nothing_saved": True}
    if refusal.where:
        data["where"] = refusal.where
    if refusal.rule:
        data["rule"] = refusal.rule
    if refusal.position is not None:
        data["position_in_formula"] = refusal.position
    data["next"] = "nothing is on the user's screen; correct the request and call propose_score again, or tell the user what cannot be done"
    return data


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
