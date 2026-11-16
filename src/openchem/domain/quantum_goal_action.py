"""Quantum service actions offered beside a goal -- never as `GoalRun.calculator_ids`.

A goal's registry rows stay in `calculator_goals`. Ab initio NMR, IR, and xtb
frequencies are jobs the Quantum Chemistry panel runs: they have an engine, a
calculation type, and settings `RunChoice` already carries. Putting those ids on
`GoalRun` would either fail `validate_goals` (panel-only calculators) or sneak a
job onto the project table. This module is the separate, validated table.

**Staging is not starting.** `decide_stage` returns a `StageDecision` (calc type,
engine, method, limitation) for the panel to select, or a refusal sentence. The
person presses Run on that panel. `prepare_run` still does not start; `start` is
not called from a goal, Batch, or Fill table.

**Chemistry, not labels.** Database 1H (`nmr_database`) is a lookup. Ab initio
NMR is one `nmr` job (`NMRSpectrumResult`) without a nucleus field; 1H and 13C
are views of that job, not two actions. IR is ORCA `opt_freq`. Psi4 runs `sp`
and `opt` only. xtb can compute frequencies but does not parse IR intensities
from `vibspectrum`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from openchem.domain.calculator_goals import SCOPE_THIS, SCOPES

#: Engines a Quantum goal action may name. Closed so a typo is a table error.
KNOWN_ENGINES = frozenset({"orca", "psi4", "xtb"})

#: Calculation types a Quantum goal action may name. Closed; a nucleus-specific
#: NMR type is deliberately absent.
KNOWN_CALC_TYPES = frozenset({"nmr", "opt_freq", "sp", "opt"})

#: What each engine actually runs. `None` means the engine's full panel set (ORCA).
ENGINE_CALC_TYPES: Mapping[str, frozenset[str] | None] = {
    "orca": None,
    "psi4": frozenset({"sp", "opt"}),
    "xtb": frozenset({"sp", "opt", "opt_freq"}),
}

#: xtb can emit frequencies; it must not be offered as ORCA-style IR.
XTB_FREQ_LIMITATION = (
    "Frequencies only: xtb IR intensities are not parsed from the vibspectrum file, "
    "so this is not an IR spectrum in the ORCA sense."
)

#: One NMR job; 1H vs 13C are views, and this is not the database lookup.
NMR_LIMITATION = (
    "One NMR calculation. 1H and 13C are views of the same job, not two jobs. "
    "This is not the database 1H lookup (nmr_database)."
)

#: IR is ORCA opt_freq, not a generic engine capability.
IR_LIMITATION = "Infrared frequencies and intensities from an ORCA opt_freq job, not a generic engine capability."

#: All/chosen scope is refused rather than silently running the selected molecule.
SCOPE_REFUSAL = (
    "Quantum calculations run on one selected molecule. Properties is set to "
    "several molecules; choose This molecule, then stage again. Nothing started."
)

#: Staging needs the selected molecule; an empty selection starts nothing.
NO_MOLECULE_REFUSAL = "Select a molecule first. Nothing started."


@dataclass(frozen=True)
class QuantumGoalAction:
    """One Quantum job a goal may stage on the Quantum Chemistry panel."""

    action_id: str
    goal_id: str
    calc_type: str
    provider_id: str
    #: Empty means the panel's current / type-default method.
    method_basis: str = ""
    #: Shown on the panel. Required for xtb frequencies.
    limitation: str = ""
    #: One line in the wizard. Not a calculator reason.
    reason: str = ""
    label: str = ""


@dataclass(frozen=True)
class StageDecision:
    """Outcome of asking whether an action may be staged. Never starts a job."""

    ok: bool
    message: str
    calc_type: str = ""
    provider_id: str = ""
    method_basis: str = ""
    limitation: str = ""


def _r(
    action_id: str,
    *,
    goal_id: str,
    calc_type: str,
    provider_id: str,
    reason: str,
    label: str,
    method_basis: str = "",
    limitation: str = "",
) -> QuantumGoalAction:
    return QuantumGoalAction(
        action_id=action_id,
        goal_id=goal_id,
        calc_type=calc_type,
        provider_id=provider_id,
        method_basis=method_basis,
        limitation=limitation,
        reason=reason,
        label=label,
    )


#: Optional Quantum actions the wizard may offer, keyed by goal. Not ticks.
QUANTUM_ACTIONS: tuple[QuantumGoalAction, ...] = (
    _r(
        "orca.nmr",
        goal_id="spectra",
        calc_type="nmr",
        provider_id="orca",
        method_basis="B3LYP pcSseg-1",
        limitation=NMR_LIMITATION,
        label="Ab initio NMR (ORCA)",
        reason="Shieldings from one NMR job. Not the experimental-database lookup.",
    ),
    _r(
        "orca.opt_freq",
        goal_id="spectra",
        calc_type="opt_freq",
        provider_id="orca",
        method_basis="B3LYP def2-SVP",
        limitation=IR_LIMITATION,
        label="Infrared (ORCA)",
        reason="opt_freq: frequencies and IR intensities on ORCA.",
    ),
    _r(
        "xtb.opt_freq",
        goal_id="spectra",
        calc_type="opt_freq",
        provider_id="xtb",
        method_basis="GFN2-xTB",
        limitation=XTB_FREQ_LIMITATION,
        label="Frequencies (xtb)",
        reason=XTB_FREQ_LIMITATION,
    ),
)


def action_of(action_id: str) -> QuantumGoalAction | None:
    return next((a for a in QUANTUM_ACTIONS if a.action_id == action_id), None)


def actions_for_goal(goal_id: str) -> tuple[QuantumGoalAction, ...]:
    return tuple(a for a in QUANTUM_ACTIONS if a.goal_id == goal_id)


def engine_supports(provider_id: str, calc_type: str) -> bool:
    if provider_id not in ENGINE_CALC_TYPES:
        return False
    allowed = ENGINE_CALC_TYPES[provider_id]
    return True if allowed is None else calc_type in allowed


def validate_action(action: QuantumGoalAction) -> list[str]:
    """Every way an action is unsound. Empty means it may be offered (not started)."""
    problems: list[str] = []
    where = action.action_id
    if action.provider_id not in KNOWN_ENGINES:
        problems.append(f"{where}: unknown engine {action.provider_id!r}")
    if action.calc_type not in KNOWN_CALC_TYPES:
        problems.append(f"{where}: unknown calculation type {action.calc_type!r}")
    if action.provider_id in ENGINE_CALC_TYPES and not engine_supports(action.provider_id, action.calc_type):
        problems.append(
            f"{where}: {action.provider_id} does not run {action.calc_type}"
        )
    if action.calc_type in {"nmr", "nmr_1h", "nmr_13c"} and "1H" in action.action_id:
        problems.append(f"{where}: nucleus-specific NMR actions are not offered")
    if action.provider_id == "xtb" and action.calc_type == "opt_freq":
        text = f"{action.limitation} {action.reason}".lower()
        if "intensit" not in text and "vibspectrum" not in text:
            problems.append(f"{where}: xtb frequencies must disclose missing IR intensities")
    if action.calc_type == "nmr" and "one nmr" not in action.limitation.lower():
        problems.append(f"{where}: NMR must say it is one job, not 1H and 13C jobs")
    if not action.reason.strip() or not action.label.strip():
        problems.append(f"{where}: missing label or reason")
    return problems


def validate_quantum_actions(actions: tuple[QuantumGoalAction, ...] = QUANTUM_ACTIONS) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    nmr_ids = [a.action_id for a in actions if a.calc_type == "nmr"]
    if len(nmr_ids) > 1:
        problems.append(f"more than one NMR action would double the job: {nmr_ids}")
    for action in actions:
        if action.action_id in seen:
            problems.append(f"{action.action_id}: listed twice")
        seen.add(action.action_id)
        problems.extend(validate_action(action))
    return problems


def decide_stage(
    action: QuantumGoalAction,
    *,
    available_engines: set[str],
    scope_mode: str,
    molecule_count: int,
    selected: bool,
) -> StageDecision:
    """Whether this action may be staged. Never starts a calculation."""
    problems = validate_action(action)
    if problems:
        return StageDecision(False, problems[0])
    if scope_mode not in SCOPES:
        return StageDecision(False, f"unknown scope {scope_mode!r}")
    if scope_mode != SCOPE_THIS:
        return StageDecision(False, SCOPE_REFUSAL)
    if not selected or molecule_count != 1:
        return StageDecision(False, NO_MOLECULE_REFUSAL)
    if action.provider_id != "orca" and action.provider_id not in available_engines:
        return StageDecision(
            False,
            f"{action.provider_id} is not set up. Open Settings > External tools. Nothing started.",
        )
    if not engine_supports(action.provider_id, action.calc_type):
        return StageDecision(
            False,
            f"{action.provider_id} does not run {action.calc_type}. Nothing started.",
        )
    return StageDecision(
        True,
        action.limitation,
        calc_type=action.calc_type,
        provider_id=action.provider_id,
        method_basis=action.method_basis,
        limitation=action.limitation,
    )
