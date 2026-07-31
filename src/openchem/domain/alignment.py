"""Result shapes for 3D structural alignment.

Lives in `domain/` rather than next to the RDKit code that produces it in
`chem/alignment.py`, because `events/events.py` carries these across the
bus and must not import a chemistry engine. Same split
`domain/docking.py` already makes for `DockingResultModel`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnsembleEntry:
    """One molecule's outcome in an ensemble alignment.

    `error` is populated INSTEAD of the numbers when that one molecule
    could not be aligned -- one unembeddable structure must not discard
    the other nine's results, so failures are carried per entry rather
    than raised out of the whole run.

    `score` is an O3A overlap quality where HIGHER is better, on a scale
    that depends on molecular size; `rmsd` is a distance in angstroms
    where LOWER is better. They are deliberately separate fields:
    conflating them would invert the meaning of a result.
    """

    label: str
    molblock: str
    score: float | None = None
    rmsd: float | None = None
    matched_atoms: int = 0
    typing: str = ""
    error: str | None = None

    @property
    def aligned(self) -> bool:
        return self.error is None
