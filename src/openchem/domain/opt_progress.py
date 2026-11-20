"""What an optimization has reported so far, as plain immutable data.

Lives in `domain/` so an event can carry it; the reader that fills it from ORCA's stdout is
`chem/orca_progress.py`. A field not yet reported is None or empty, never 0.
"""

from __future__ import annotations

from dataclasses import dataclass

#: ORCA's names for the criteria, in the order its table prints them.
CRITERIA_NAMES = ("Energy change", "RMS gradient", "MAX gradient", "RMS step", "MAX step")


@dataclass(frozen=True)
class ConvergenceItem:
    """One row of ORCA's "Geometry convergence" table."""

    name: str
    value: float
    tolerance: float
    converged: bool


@dataclass(frozen=True)
class OptProgress:
    """What the optimization has said so far. Every field may be missing, and a missing one is None or empty."""

    cycle: int | None = None
    #: ORCA's own MaxIter for this job (printed in its settings block), so "cycle 106 of 123" can be shown.
    max_cycles: int | None = None
    #: The energy of the last finished cycle, in Eh.
    energy: float | None = None
    #: Last cycle's energy minus the one before it, from this parser's own history (None before the second cycle).
    energy_change: float | None = None
    #: The most recent convergence table; empty until the first one is printed.
    criteria: tuple[ConvergenceItem, ...] = ()
    #: Every cycle's energy in order, for a trace. Capped by the parser.
    energy_history: tuple[float, ...] = ()
    scf_iteration: int | None = None
    #: Times ORCA rebuilt its optimizer state ("Reseting .opt file"): nearly one per cycle means it is not learning curvature.
    resets: int = 0
    #: "RMS(Cart) too big" / "RMS(Cart) increases" messages: failed internal-to-Cartesian steps.
    back_transform_failures: int = 0
    converged: bool = False
    reached_max_cycles: bool = False

    @property
    def criteria_met(self) -> tuple[int, int] | None:
        """(met, total) of the latest convergence table, or None when none has been printed."""
        if not self.criteria:
            return None
        return sum(item.converged for item in self.criteria), len(self.criteria)

    def unmet(self) -> tuple[ConvergenceItem, ...]:
        """The criteria of the latest table that are not yet met, so a reader can see WHICH one is holding the job up."""
        return tuple(item for item in self.criteria if not item.converged)


def _short(value: float) -> str:
    return f"{value:.1e}"


def summary_line(progress: OptProgress) -> str:
    """One line a person can read at a glance, built only from what has been reported: "cycle 106 of 123 · E -810.24190 Eh ·
    ΔE -2.0e-06 Eh · 3/5 criteria met". A missing part is left out, never filled in."""
    parts: list[str] = []
    if progress.cycle is not None:
        parts.append(f"cycle {progress.cycle}" + (f" of {progress.max_cycles}" if progress.max_cycles else ""))
    if progress.energy is not None:
        parts.append(f"E {progress.energy:.5f} Eh")
    if progress.energy_change is not None:
        parts.append(f"ΔE {progress.energy_change:+.1e} Eh")
    met = progress.criteria_met
    if met is not None:
        parts.append(f"{met[0]}/{met[1]} criteria met")
    return " · ".join(parts)


#: Cycles looked back over, and the energy change (Eh, 0.1 kcal/mol) under which an optimization is calling itself slow.
SLOW_WINDOW = 10
#: The energy change (Eh) under which the last `SLOW_WINDOW` cycles count as barely moving: 0.1 kcal/mol.
SLOW_ENERGY_EH = 1.6e-4


def slow_progress_note(progress: OptProgress) -> str:
    """A sentence when the optimization looks slow, else "". An observation, never a cause: it needs ALL of a tiny energy
    change over the last `SLOW_WINDOW` cycles, a criterion still unmet, and ORCA having rebuilt its optimizer in at least
    half the cycles. A small energy change alone is what a finished optimization looks like, so it never triggers this alone."""
    history = progress.energy_history
    if len(history) <= SLOW_WINDOW or not progress.unmet() or not progress.cycle or progress.resets * 2 < progress.cycle:
        return ""
    if abs(history[-1] - history[-1 - SLOW_WINDOW]) >= SLOW_ENERGY_EH:
        return ""
    return (
        f"Progress is slow: the energy changed by less than 0.1 kcal/mol over the last {SLOW_WINDOW} cycles, "
        "a criterion is still unmet, and ORCA has rebuilt its optimizer in at least half the cycles. "
        "Stop and keep geometry keeps what it has reached."
    )


def detail_text(progress: OptProgress) -> str:
    """The criteria still unmet (value against threshold), so the one holding the job up is visible, and how often ORCA
    rebuilt its optimizer. Observations only: no cause is named."""
    lines: list[str] = []
    for item in progress.unmet():
        lines.append(f"{item.name}: {_short(item.value)} (needs {_short(item.tolerance)})")
    if progress.resets:
        lines.append(f"ORCA rebuilt its optimizer {progress.resets} times"
                     + (f" in {progress.cycle} cycles" if progress.cycle else ""))
    note = slow_progress_note(progress)
    if note:
        lines.append(note)
    return "\n".join(lines)
