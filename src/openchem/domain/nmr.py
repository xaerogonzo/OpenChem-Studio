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
    #: RMS of the fit's own residuals, in ppm -- how far the reference
    #: compounds actually sat from the fitted line.
    #:
    #: This is the honest answer to "how accurate is a scaled shielding
    #: from THIS install at THIS method/basis". R^2 says the line explains
    #: the variance; it says nothing about scale, and an R^2 of 0.999 over
    #: a 200 ppm range still leaves several ppm of error. Selecting between
    #: prediction methods needs a number in ppm, not a correlation, which
    #: is why this exists rather than a remembered "about 1.5".
    #:
    #: Optional because a stored calibration from before this field
    #: existed has no value for it, and "unknown" must stay distinguishable
    #: from "zero" -- see `nmr_hybrid`, where unknown loses to measured.
    residual_rms: float | None = None

    def apply(self, shielding: float) -> float:
        return self.slope * shielding + self.intercept
