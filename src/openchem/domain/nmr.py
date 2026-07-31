"""Value objects for NMR calibration.

Lives in `domain/` rather than beside the fitting code in
`chem/nmr_scaling.py` because `events/events.py` carries these across the
bus and must not import a chemistry module. Same split
`domain/alignment.py` makes for `EnsembleEntry`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScalingFactors:
    """`delta = slope * sigma + intercept`, plus the evidence for it.

    `r_squared` and `sample_count` travel WITH the factors rather than
    being logged and dropped, so the UI can show what a calibration was
    actually based on -- a slope fitted to four points and one fitted to
    eleven are not equally trustworthy and should not look identical.
    """

    slope: float
    intercept: float
    r_squared: float
    sample_count: int

    def apply(self, shielding: float) -> float:
        return self.slope * shielding + self.intercept
