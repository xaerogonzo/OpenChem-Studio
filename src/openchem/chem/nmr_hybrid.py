"""Combining shift predictions from different methods, per atom.

WHY THIS EXISTS. The database lookup and the ab initio path fail in
opposite places. The lookup is excellent where the environment is
well-represented (held-out MAE 1.12 ppm on its `good` band) and poor
where it is not (10.0 ppm on `rough`, 7.5% of carbons even in ordinary
drug-like molecules). ORCA has no database at all, so its accuracy does
not care whether anyone has measured this environment before -- which is
exactly the case a lookup cannot help with, and exactly what someone
checking a novel compound is asking about.

Choosing one method for a whole spectrum wastes the other. Choosing per
atom does not.

SELECTION IS BY EXPECTED ERROR, NOT BY METHOD. Every candidate carries a
number in ppm saying how wrong it expects to be, and the lowest wins. A
hardcoded table ("good -> lookup") would bake today's benchmark into the
code and keep choosing wrong once the index grows or the calibration
improves. Both numbers here are MEASURED:

  * lookup -- `nmr_database.HELD_OUT_BAND_MAE`, imported rather than
    copied, from 24,280 carbons excluded from the index before predicting
    them.
  * ORCA -- the residual RMS of the user's own calibration fit
    (`nmr_scaling.ScalingFactors.residual_rms`), which is specific to
    their install, functional and basis.

A candidate with no expected error never wins. "Unknown" losing to
"measured" is the whole point; a method that cannot say how wrong it
might be has not earned the atom.

THE SCALED PATH ONLY. A computed shielding must go through
`nmr_scaling.scale_spectrum`, never `nmr_reference` alone. TMS
referencing removes a constant offset; computed shieldings are also
systematically stretched, by an amount depending on functional, basis and
geometry. Splicing TMS-referenced values into measured ones puts part of
one spectrum on a different scale, and the step that produces looks like
chemistry.

MEASURED, on a real ORCA 6.1.1 install at B3LYP/def2-SVP, against
literature 13C shifts. The calibration this selects on came out at a
residual RMS of 2.339 ppm for carbon (R^2 0.9978, 7 points) -- NOT the
"~1.5" that was remembered when this was planned, which is why the
number is fitted rather than written down.

CAFFEINE, the case the phase exists for. One of its eight carbons is
`rough`: the N7-methyl, which the lookup puts at 62.58 ppm against a real
33.6 -- a 29 ppm miss, on an atom whose environment the index barely
covers. Every other carbon is `good`.

    atom   lit    lookup    ORCA   hybrid   source
       0   33.6    62.58   36.11    36.11   ORCA (scaled)
       2  141.5   144.15  139.16   144.15   trusted lookup
       4  148.7   148.97  147.71   148.97   trusted lookup
       5  107.6   107.73  108.28   107.73   trusted lookup
       6  155.4   155.11  154.84   155.11   trusted lookup
       9   27.9    28.58   29.95    28.58   trusted lookup
      10  151.7   150.24  152.77   150.24   trusted lookup
      13   29.7    29.50   31.28    29.50   trusted lookup

    MAE   lookup 4.33     ORCA 1.47     hybrid 1.02 ppm
    vs lookup alone: 1 improved, 7 unchanged, 0 worsened

The hybrid beats BOTH methods it is built from, which is the whole claim:
it keeps the lookup's 0.1-0.7 ppm accuracy on covered atoms and replaces
its one 29 ppm blunder with a 2.5 ppm answer. The calibration check
passed here at an offset of -0.05 ppm over the 7 trusted atoms.

THERE IS NO GATE ANY MORE, and removing it is the measured result of
this work rather than a simplification. An earlier version refused the
whole merge when the calculation sat too far from trusted database
values. Scored on DELTA50 -- 131 assigned 13C shifts in CDCl3 over 46
compounds (Molecules 2023, 28, 2449), independent of nmrshiftdb2, which
IS this lookup's index -- that refusal was worse than doing nothing:

    vs refusing (paired over molecules)   delta MAE   95% CI
    report but merge anyway                  -0.131   [-0.308, -0.017]

It refused 13 of 46 molecules to achieve that. The reason is structural,
not a threshold that wanted loosening: selection already declines a bad
calculation atom by atom, so a second, spectrum-wide veto can only remove
atoms the selection would have got right. The check still runs and its
numbers are still reported -- how far a calculation sits from trusted
values is real information about the run -- it simply no longer decides
anything.

QUININE is the case that exposed it, and is kept as a fixture in
`tests/test_nmr_hybrid.py`. Scored against Moreland/Philip/Carroll's
assigned CDCl3 table (J. Org. Chem. 1974, 39, 2413,
doi:10.1021/jo00930a020), 12 of its 20 carbons are `rough` and the lookup
is 12.50 ppm MAE on them. The old gate refused at +3.00 ppm against a
2.62 limit, and merging anyway takes the spectrum from 7.96 to 3.44 ppm
and those twelve carbons from 12.50 to 4.09.

WHAT WAS TRIED AND REJECTED, recorded so it is not re-invented. All are
in `benchmarks/nmr/hybrid_strategies.py` and can be re-scored without
ORCA from the committed shieldings:

  * estimating the calculation's accuracy PER MOLECULE from the atoms the
    lookup rates `good`, instead of trusting the install-wide calibration
    residual. Not distinguishable from the simple rule (+0.017 ppm, CI
    spanning zero) and notably worse at choosing (74.9% vs 80.2%): seven
    atoms is too small a sample to pay for itself.
  * the same, shrunk toward the install-wide figure. Identical.
  * deferring to the lookup when the two methods disagree beyond what
    their errors explain. This one was written after looking at a single
    atom it fixed, in a 28-atom sample, and DELTA50 shows what that is
    worth: the WORST hybrid at both levels of theory (1.65 ppm MAE
    against 1.33, worst regret 14.21 against 6.39), and significantly
    worse than refusing at wB97X-D3. Overfitting, caught by a held-out
    split.

A NOTE ON THE BAND CONSTANTS. `LOOKUP_EXPECTED_ERROR` was measured on
held-out nmrshiftdb2, and it does not transfer exactly: on DELTA50 the
observed errors are good 0.67, medium 4.06, rough 13.51 against the
assumed 1.12/3.36/10.00. The ordering survives, and at the accuracy a
real calculation achieves every selection still lands the same way -- but
these are corpus-specific numbers, not constants of nature.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from statistics import fmean

from openchem.chem.nmr_database import HELD_OUT_BAND_MAE

logger = logging.getLogger("openchem.chemistry")

#: Per-band held-out MAE, in ppm, keyed by the rating
#: `ShiftPrediction.quality` assigns itself. Measured, not estimated.
#:
#: IMPORTED rather than copied. These decide which method wins an atom, so
#: a second copy is a way for predictions to change silently -- which had
#: already happened: this file shipped 1.17/3.38/9.93 from an early run
#: while `nmr_database` had since remeasured them at 1.12/3.36/10.00 on
#: the format-2 index. One owner, no drift.
#:
#: CARBON ONLY, for the reason given at `MERGEABLE_ELEMENTS` below.
LOOKUP_EXPECTED_ERROR = HELD_OUT_BAND_MAE

#: Elements the merge will run on at all. Selection needs a measured
#: expected error from BOTH methods, and only carbon has one on the
#: lookup side. A proton merge would be selecting on a number nobody
#: measured, which is the failure this module exists to avoid.
MERGEABLE_ELEMENTS = ("C",)

#: Floor on the scale-agreement tolerance, per element, in ppm. The real
#: limit is derived per call (see `check_calibration`); this only stops
#: an unrealistically tight one from being computed.
MIN_CALIBRATION_OFFSET: dict[str, float] = {"C": 1.5, "H": 0.15}


@dataclass(frozen=True)
class Candidate:
    """One method's answer for one atom, with how wrong it expects to be.

    `expected_error` is None when the method cannot say. Such a candidate
    is still reported -- it may be the only one -- but never beats one
    that can.
    """

    value: float
    method: str
    expected_error: float | None = None
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CalibrationCheck:
    """How well a computed spectrum agrees with trusted lookup values.

    A free calibration check: atoms the lookup rates `good` are its most
    reliable, so comparing the calculation against those on the same
    molecule measures the calculation without needing any external data.

    `max_deviation` is reported alongside the RMS deliberately. One badly
    placed atom disappears inside a respectable RMS, and that atom is
    precisely the one someone would act on.
    """

    element: str
    compared: int
    mean_offset: float
    rms: float
    max_deviation: float
    passed: bool
    reason: str = ""


def check_calibration(
    trusted: dict[int, float],
    computed: dict[int, float],
    element: str,
    expected_error: float | None = None,
) -> CalibrationCheck | None:
    """Compare a computed spectrum against trusted values on shared atoms.

    Returns None when there is nothing to compare -- which is not a
    failure, but does mean the merge cannot verify itself and should say
    so rather than proceeding silently.

    THE TOLERANCE IS DERIVED, NOT PICKED. Two imperfect methods disagree
    even when both are working, by about as much as their errors combine.
    So the limit is those errors added in quadrature -- the lookup's own
    `good`-band MAE and the calculation's `expected_error` (its
    calibration residual RMS) -- floored so it can never come out
    unrealistically tight.

    That means the gate scales with how accurate the calculation claims
    to be, which a fixed constant cannot: a crude level of theory admits
    a wider disagreement before it counts as evidence of a scale problem,
    and it is also losing every atom on expected error anyway. Measured
    on a real B3LYP/def2-SVP run (residual RMS 2.34 ppm), this gives
    2.62 ppm for carbon, and aspirin's observed +4.10 ppm offset is
    correctly refused -- scaled ORCA was 3.75 ppm MAE against literature
    there where the lookup was 1.58, so merging would have made the
    spectrum worse.
    """
    shared = sorted(set(trusted) & set(computed))
    if not shared:
        return None
    deltas = [computed[index] - trusted[index] for index in shared]
    mean_offset = fmean(deltas)
    rms = (sum(d * d for d in deltas) / len(deltas)) ** 0.5
    max_deviation = max(abs(d) for d in deltas)
    trusted_error = LOOKUP_EXPECTED_ERROR["good"]
    combined = (trusted_error**2 + (expected_error or 0.0) ** 2) ** 0.5
    limit = max(MIN_CALIBRATION_OFFSET.get(element, 1.5), combined)
    passed = abs(mean_offset) <= limit
    return CalibrationCheck(
        element=element,
        compared=len(shared),
        mean_offset=mean_offset,
        rms=rms,
        max_deviation=max_deviation,
        passed=passed,
        reason=(
            ""
            if passed
            else (
                f"The calculation sits {mean_offset:+.2f} ppm from trusted database "
                f"values over {len(shared)} atoms — more than the {limit:.2f} ppm the "
                f"two methods' own errors can account for. Merging them would put part "
                f"of this spectrum on a different scale. Re-run the scaling calibration "
                f"for this method and basis, or use a larger basis set."
            )
        ),
    )


def lookup_candidates(result) -> dict[int, Candidate]:
    """Candidates from a database lookup, one per atom it answered for.

    The per-atom `quality` the lookup already records in
    `Provenance.parameters` selects the expected error. An unrecognised
    rating yields no expected error rather than a guessed one -- if a
    future band appears without a measured MAE, it should lose to a
    method that has one, not silently inherit `rough`'s.
    """
    details = (result.provenance.parameters if result.provenance else {}) or {}
    atoms = details.get("per_atom") or {}
    out: dict[int, Candidate] = {}
    for index, value in result.values.items():
        detail = dict(atoms.get(str(index)) or {})
        quality = str(detail.get("quality", ""))
        out[index] = Candidate(
            value=value,
            method="trusted lookup",
            expected_error=LOOKUP_EXPECTED_ERROR.get(quality),
            detail={
                "quality": quality,
                "matches": detail.get("matches"),
                "spread_ppm": detail.get("spread_ppm"),
                "spheres": detail.get("spheres"),
            },
        )
    return out


def computed_candidates(scaled: dict[int, float], factors) -> dict[int, Candidate]:
    """Candidates from a SCALED ORCA spectrum.

    `factors` is the `ScalingFactors` the values were scaled by; its
    `residual_rms` is this method's expected error, measured on the
    user's own install. Pass None (or a calibration predating that
    field) and the candidates carry no expected error, so the lookup
    wins wherever it has one.

    Takes already-scaled values rather than a raw result, so there is no
    way to reach this with TMS-referenced shieldings by accident -- the
    scale mismatch that would cause is the single worst failure mode
    here, and it looks like chemistry rather than like a bug.
    """
    expected = getattr(factors, "residual_rms", None)
    detail = (
        {
            "slope": round(factors.slope, 4),
            "r_squared": round(factors.r_squared, 4),
            "calibration_points": factors.sample_count,
        }
        if factors is not None
        else {}
    )
    return {
        index: Candidate(
            value=value, method="ORCA (scaled)", expected_error=expected, detail=dict(detail)
        )
        for index, value in scaled.items()
    }


def trusted_values(result) -> dict[int, float]:
    """Only the lookup values good enough to calibrate against.

    `good` atoms carry a held-out MAE of 1.17 ppm and a median of 0.55 --
    close enough to experiment to measure a calculation against. Using
    every atom instead would compare the calculation against the
    lookup's own 9.93 ppm band and call the disagreement the
    calculation's fault.
    """
    details = (result.provenance.parameters if result.provenance else {}) or {}
    atoms = details.get("per_atom") or {}
    return {
        index: value
        for index, value in result.values.items()
        if str((atoms.get(str(index)) or {}).get("quality", "")) == "good"
    }


def _best(candidates: list[Candidate]) -> tuple[Candidate, str]:
    """The candidate expected to be least wrong, and why it won."""
    known = [c for c in candidates if c.expected_error is not None]
    if not known:
        only = candidates[0]
        return only, f"only {only.method} had a value; no expected error to compare"
    best = min(known, key=lambda c: c.expected_error)
    others = [c for c in known if c is not best]
    if not others:
        return best, (
            f"{best.method} was the only method able to state an expected error "
            f"({best.expected_error:.2f} ppm)"
        )
    runner_up = min(others, key=lambda c: c.expected_error)
    return best, (
        f"{best.method} expects {best.expected_error:.2f} ppm against "
        f"{runner_up.method}'s {runner_up.expected_error:.2f}"
    )


def fuse(
    candidates: dict[int, list[Candidate]],
    elements: dict[int, str],
    molecule_uuid: str,
    element: str = "C",
    calibration: CalibrationCheck | None = None,
):
    """Merge per-atom candidates into one spectrum, choosing by expected
    error and recording why for every atom.

    Takes a LIST per atom rather than two named arguments so that a third
    predictor needs no change to this logic. There is deliberately no
    class hierarchy behind it: two producers do not justify one, and this
    project has declined that abstraction three times already.
    """
    from openchem.domain.common import CacheState, Provenance
    from openchem.domain.scientific_result import NMRSpectrumResult

    # A failing calibration check is REPORTED, not obeyed. It used to
    # refuse the whole merge; DELTA50 says that costs accuracy and buys
    # nothing (see the module docstring). Selection already declines a bad
    # calculation atom by atom, so a second spectrum-wide veto can only
    # remove atoms the selection would have got right.
    warning = "" if calibration is None or calibration.passed else calibration.reason

    values: dict[int, float] = {}
    kept: dict[int, str] = {}
    details: dict[str, dict] = {}
    for index, options in candidates.items():
        if not options:
            continue
        chosen, reason = _best(options)
        values[index] = chosen.value
        kept[index] = elements.get(index, element)
        spread = (
            round(max(o.value for o in options) - min(o.value for o in options), 3)
            if len(options) > 1
            else 0.0
        )
        details[str(index)] = {
            "source": chosen.method,
            "expected_error": chosen.expected_error,
            "selection_reason": reason,
            # Named for what it is. This module will also carry deltas from
            # experiment and from calibration, and a bare `delta` would not
            # survive that.
            "disagreement_ppm": spread,
            **chosen.detail,
        }

    counts: dict[str, int] = {}
    for detail in details.values():
        counts[detail["source"]] = counts.get(detail["source"], 0) + 1
    errors = [d["expected_error"] for d in details.values() if d["expected_error"] is not None]

    return NMRSpectrumResult(
        spectrum_type="nmr_13c" if element == "C" else "nmr_1h",
        name=f"{element} NMR (hybrid)",
        units="ppm",
        method="hybrid",
        molecule_uuid=molecule_uuid,
        values=values,
        elements=kept,
        cache_state=CacheState.COMPLETED if values else CacheState.FAILED,
        error="" if values else "No method produced a value for any atom.",
        provenance=Provenance(
            created_by="core",
            method="hybrid (expected-error selection)",
            parameters={
                "per_atom": details,
                "sources": counts,
                "expected_average_error": round(fmean(errors), 3) if errors else None,
                "calibration": (
                    {
                        "compared": calibration.compared,
                        "mean_offset": round(calibration.mean_offset, 3),
                        "rms": round(calibration.rms, 3),
                        "max_deviation": round(calibration.max_deviation, 3),
                        "passed": calibration.passed,
                        # Carried so a caller can surface the disagreement
                        # without re-deriving it. Advisory: the merge went
                        # ahead regardless.
                        "warning": warning,
                    }
                    if calibration
                    else None
                ),
            },
        ),
    )
