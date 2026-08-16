"""Does ESOL's negative bias on bases generalise well enough to adjust for?

    uv run --no-sync python benchmarks/solubility/base_bias.py

**EVERYTHING BELOW WAS WRITTEN BEFORE THIS SCRIPT WAS FIRST RUN.** That is
the only property that makes the answer worth anything: a criterion chosen
after seeing the numbers is a description of the numbers, not a test of
them.

`score.py` measures ESOL under-predicting bases by -0.59 log on the
Solubility Challenge and -0.42 on SC-2. Two corpora agreeing is what
raises the question; it is not on its own permission to subtract half a
log unit from every basic drug in the application.

(-0.59 supersedes the -0.52 this docstring first carried. The difference
is not drift: THIS SCRIPT found three polymorph pairs that `score.py` had
been scoring twice, and refusing them moved the figure. See the AMENDMENT
below.)

--------------------------------------------------------------------
PRE-REGISTRATION  (acceptance_criteria_version = 1)
--------------------------------------------------------------------

FITTING STATISTIC, exactly:

    offset = mean(measured_logS - raw_ESOL_logS)

over the held-in base stratum. Unweighted, one row per compound, computed
from RAW ESOL before any other adjustment. Rows that do not parse or carry
no measured value are excluded and counted, never imputed.

HELD OUT MEANS HELD OUT. The two corpora share compounds -- measured while
planning, 20 InChIKeys, a quarter of SC-1, several of them bases. Those are
removed from whichever corpus is acting as the TEST side, and the script
asserts the fit and test identifier sets are then disjoint. Only with that
assertion passing is the result called cross-corpus HELD-OUT validation.

BOOTSTRAP, exactly:

    improvement_i = |error_before_i| - |error_after_i|   per held-out compound

resampling compounds with replacement, 10000 replicates, percentile 95%
CI. It is a one-sample CI on the paired improvement WITHIN each held-out
corpus, not a comparison between the two corpora.

ACCEPTANCE -- one Boolean, every component printed separately, so that
"most criteria passed" can never be read as passing:

    ship = (same_sign
            and offset_agreement <= 0.25
            and heldout_base_RMSE_improves_in_both_directions
            and heldout_overall_MAE_not_worse_in_either_direction
            and improvement_CI_excludes_zero_in_both_directions)

The metrics are named and may not be substituted for one another: RMSE for
the base arm, MAE for the overall arm. Both are reported before and after
either way, so an effect masked by a large neutral/acid population is
visible rather than hidden by the predicate.

`offset_agreement <= 0.25` is a PRE-REGISTERED PRACTICAL THRESHOLD, chosen
arbitrarily and admitted as such. Being fixed before the offsets are seen
is its only meaningful property.

NO EFFECT-SIZE FLOOR. An earlier draft required the improvement to exceed
the set's 0.17 log interlaboratory noise floor. That was WRONG and is not
replaced by another invented number: the interlab SD bounds how low RMSE
can GO, not how small a real improvement can be, so the two are unlike
quantities. A statistically positive result is therefore recorded as not
necessarily chemically important, and that stays a stated limitation
rather than being legislated away by a threshold nobody can justify.

FOUR OUTCOMES, and only SHIP may change production behaviour:

    SHIP              every criterion evaluated and passed
    SURFACE_ONLY      evaluated, at least one failed
    UNDECIDED         held-out base n < 10 either direction, or no CI
    EXPERIMENT_ERROR  malformed corpus, conflicting duplicate, bad input

There is no path that uses the mean anyway.

REFIT ON SHIP: the shipped constant is the unweighted mean residual over
the UNION of both base strata, deduplicated by InChIKey. A duplicated
compound whose two measured values CONFLICT is an EXPERIMENT_ERROR, never
silently averaged. The combined in-sample figure is reported and is
explicitly NOT evidence of generalisation.

--------------------------------------------------------------------
AMENDMENT -> acceptance_criteria_version = 2   (POLYMORPHS)
--------------------------------------------------------------------

**MADE BEFORE ANY OFFSET OR ACCEPTANCE NUMBER EXISTED.** Version 1 halted
on its first run with EXPERIMENT_ERROR, having computed nothing: SC-1
carries `chlorprothixene_form_I` and `chlorprothixene_form_II` under one
InChIKey with measured logS -6.75 and -5.87.

That is a DEFECT IN THE PRE-REGISTRATION, not in the data. v1 conflated
two different things -- a corpus contradicting itself, and one compound
measured as two genuine solid forms. Three pairs exist in SC-1 and none in
SC-2:

    chlorprothixene   -6.75 / -5.87    spread 0.88
    sulindac          -3.68 / -4.50    spread 0.82
    phthalic acid     -1.49 / -1.61    spread 0.12

v2 DROPS both members of a polymorph pair, and the reason is that ESOL
predicts one number per STRUCTURE: it has no representation in which the
two forms differ, so any score against either is arbitrary and a mean is a
solubility no solid actually has. Refusing what cannot be scored is the
posture this project already takes with ampholytes. It costs 3 of SC-1's
77 compounds.

The amendment is recorded rather than applied silently because a criterion
changed after seeing data is worth nothing -- what makes this one
admissible is that the run produced no offset, no arm and no verdict
before it halted.

**AND IT IMPLICATES THE PUBLISHED SC-1 FIGURES.** `score.py` scores all
rows, so those three compounds are counted TWICE and the polymorph gap --
up to 0.88 log, comparable to the base bias under investigation -- enters
the error budget as though it were model error. Reported by this script;
see `score.py` for what was done about it.

--------------------------------------------------------------------
WHAT THIS EXPERIMENT CANNOT SETTLE
--------------------------------------------------------------------

`score.py` classifies with a FORCED `PKaStatus.FOUND`, so its base stratum
is every STRUCTURAL base. Production additionally requires a real pKa, so
the adjustment would apply to a SUBSET of the population measured here.
That is conservative rather than wrong -- but whether the pKa-resolvable
subset carries the same bias is NOT established by this script, and is
recorded as a limitation rather than assumed away.
"""

from __future__ import annotations

import csv
import json
import math
import platform
import random
import statistics
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from openchem.chem.pka_providers import PKaResolution, PKaStatus  # noqa: E402
from openchem.chem.solubility import (  # noqa: E402
    IonizationClass,
    classify_ionization,
    esol_logs,
)

RDLogger.DisableLog("rdApp.*")

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
RESULT = HERE / "base_bias_result.json"

ACCEPTANCE_CRITERIA_VERSION = 2
OFFSET_AGREEMENT_MAX = 0.25
MIN_HELDOUT_BASES = 10
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20260816
#: Two measurements of one compound differing by more than this are a
#: conflict rather than rounding, and stop the experiment.
DUPLICATE_CONFLICT_LOG = 0.05


@dataclass
class Compound:
    key: str
    name: str
    smiles: str
    measured: float
    ionization: IonizationClass


@dataclass
class Corpus:
    name: str
    compounds: list[Compound] = field(default_factory=list)
    excluded: dict = field(default_factory=dict)

    @property
    def bases(self) -> list[Compound]:
        return [c for c in self.compounds if c.ionization is IonizationClass.BASE]


class ExperimentError(RuntimeError):
    """Malformed input. Never downgraded into a result."""


def _classify(mol: Chem.Mol) -> IonizationClass:
    """The SAME public helper production uses.

    `PKaStatus.FOUND` is forced because the class is a structural question
    and no sidecar is called here -- exactly as `score.py` does, so the
    strata this fits on are the strata that were reported.
    """
    return classify_ionization(mol, PKaResolution(status=PKaStatus.FOUND, values=(7.0,)))


def _load(path: Path, name: str, *, drop_keys: set[str]) -> Corpus:
    if not path.is_file():
        raise ExperimentError(f"No corpus at {path}. Run fetch.py / extract_sc2.py first.")
    corpus = Corpus(name=name)
    excluded = {"unparseable": 0, "no measured value": 0, "ampholyte": 0,
                "salt or mixture": 0, "esol training data": 0, "polymorph pair": 0}
    seen: dict[str, Compound] = {}
    polymorphs: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            mol = Chem.MolFromSmiles(record.get("smiles") or "")
            if mol is None:
                excluded["unparseable"] += 1
                continue
            try:
                measured = float(record["measured_logs"])
            except (TypeError, ValueError, KeyError):
                excluded["no measured value"] += 1
                continue
            key = inchi.MolToInchiKey(mol)
            if key in drop_keys:
                excluded["esol training data"] += 1
                continue
            verdict = _classify(mol)
            if verdict is IonizationClass.AMPHOLYTE:
                excluded["ampholyte"] += 1
                continue
            if verdict is IonizationClass.UNSUPPORTED:
                excluded["salt or mixture"] += 1
                continue
            compound = Compound(key=key, name=record.get("name", ""),
                                smiles=record["smiles"], measured=measured,
                                ionization=verdict)
            if key in seen and abs(seen[key].measured - measured) > DUPLICATE_CONFLICT_LOG:
                # criteria v2: one compound, two solid forms. ESOL predicts
                # one number per structure, so neither value can be scored
                # against it and their mean is a solubility no solid has.
                # Both members go; see the AMENDMENT in the module docstring.
                polymorphs.add(key)
                continue
            seen[key] = compound
    for key in polymorphs:
        seen.pop(key, None)
        excluded["polymorph pair"] += 2
    corpus.compounds = list(seen.values())
    corpus.excluded = excluded
    return corpus


def _delaney_keys() -> set[str]:
    path = DATA / "esol_training_inchikeys.json"
    if not path.is_file():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def _errors(compounds: list[Compound], offset: float = 0.0) -> list[float]:
    return [esol_logs(Chem.MolFromSmiles(c.smiles)) + offset - c.measured for c in compounds]


def _mae(values: list[float]) -> float:
    return statistics.fmean(abs(v) for v in values)


def _rmse(values: list[float]) -> float:
    return math.sqrt(statistics.fmean(v * v for v in values))


def _bootstrap_ci(improvements: list[float]) -> tuple[float, float] | None:
    """Percentile 95% CI on the mean paired improvement."""
    if len(improvements) < 2:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(improvements)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(statistics.fmean(improvements[rng.randrange(n)] for _ in range(n)))
    means.sort()
    return means[int(0.025 * BOOTSTRAP_REPLICATES)], means[int(0.975 * BOOTSTRAP_REPLICATES) - 1]


@dataclass
class Arm:
    fit_on: str
    test_on: str
    offset: float
    fit_n: int
    test_n: int
    overlap_removed: int
    base_rmse_before: float
    base_rmse_after: float
    base_mae_before: float
    base_mae_after: float
    overall_mae_before: float
    overall_mae_after: float
    ci: tuple[float, float] | None

    @property
    def base_rmse_improves(self) -> bool:
        return self.base_rmse_after < self.base_rmse_before

    @property
    def overall_mae_not_worse(self) -> bool:
        return self.overall_mae_after <= self.overall_mae_before + 1e-12

    @property
    def ci_excludes_zero(self) -> bool:
        return self.ci is not None and self.ci[0] > 0.0

    def as_dict(self) -> dict:
        return {
            "fit_on": self.fit_on, "test_on": self.test_on,
            "offset_fitted": round(self.offset, 4),
            "fit_n": self.fit_n, "test_n": self.test_n,
            "overlap_removed_from_test": self.overlap_removed,
            "base_rmse_before": round(self.base_rmse_before, 4),
            "base_rmse_after": round(self.base_rmse_after, 4),
            "base_mae_before": round(self.base_mae_before, 4),
            "base_mae_after": round(self.base_mae_after, 4),
            "overall_mae_before": round(self.overall_mae_before, 4),
            "overall_mae_after": round(self.overall_mae_after, 4),
            "improvement_ci95": None if self.ci is None else [round(self.ci[0], 4), round(self.ci[1], 4)],
            "base_rmse_improves": self.base_rmse_improves,
            "overall_mae_not_worse": self.overall_mae_not_worse,
            "ci_excludes_zero": self.ci_excludes_zero,
        }


def _arm(fit: Corpus, test: Corpus, overlap: set[str]) -> Arm:
    """Fit on one corpus's bases, test on the other's, overlap removed."""
    fit_bases = fit.bases
    test_bases = [c for c in test.bases if c.key not in overlap]
    test_all = [c for c in test.compounds if c.key not in overlap]

    fit_ids = {c.key for c in fit_bases}
    test_ids = {c.key for c in test_bases}
    if fit_ids & test_ids:
        raise ExperimentError(
            f"held-out arm is not held out: {len(fit_ids & test_ids)} shared identifiers"
        )

    offset = -statistics.fmean(_errors(fit_bases))

    before = _errors(test_bases)
    after = _errors(test_bases, offset)
    improvements = [abs(b) - abs(a) for b, a in zip(before, after)]

    return Arm(
        fit_on=fit.name, test_on=test.name, offset=offset,
        fit_n=len(fit_bases), test_n=len(test_bases),
        overlap_removed=len(test.bases) - len(test_bases),
        base_rmse_before=_rmse(before), base_rmse_after=_rmse(after),
        base_mae_before=_mae(before), base_mae_after=_mae(after),
        overall_mae_before=_mae(_errors(test_all)),
        overall_mae_after=_mae([
            e + (offset if c.ionization is IonizationClass.BASE else 0.0)
            for c, e in zip(test_all, _errors(test_all))
        ]),
        ci=_bootstrap_ci(improvements),
    )


def _fingerprint(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else ""


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True,
                              text=True, timeout=30).stdout.strip()[:12]
    except Exception:  # noqa: BLE001 - provenance is best-effort, never fatal
        return ""


def main() -> int:
    try:
        drop = _delaney_keys()
        sc1 = _load(DATA / "evaluation.csv", "SC-1", drop_keys=set())
        sc2 = _load(DATA / "sc2_tight.csv", "SC-2", drop_keys=drop)
    except ExperimentError as exc:
        print(f"EXPERIMENT_ERROR  {exc}")
        RESULT.write_text(json.dumps({"outcome": "EXPERIMENT_ERROR", "reason": str(exc)}, indent=1),
                          encoding="utf-8")
        return 1

    overlap = {c.key for c in sc1.compounds} & {c.key for c in sc2.compounds}
    overlap_bases = overlap & ({c.key for c in sc1.bases} | {c.key for c in sc2.bases})

    print(f"acceptance_criteria_version = {ACCEPTANCE_CRITERIA_VERSION}  "
          f"(pre-registered; see the module docstring)")
    print()
    for corpus in (sc1, sc2):
        print(f"{corpus.name}: {len(corpus.compounds)} compounds, {len(corpus.bases)} bases")
        print(f"        excluded {corpus.excluded}")
    print(f"overlap between corpora: {len(overlap)} compounds, {len(overlap_bases)} of them bases")
    print()

    try:
        arms = [_arm(sc1, sc2, overlap), _arm(sc2, sc1, overlap)]
    except ExperimentError as exc:
        print(f"EXPERIMENT_ERROR  {exc}")
        return 1

    for arm in arms:
        print(f"--- fit on {arm.fit_on} bases (n={arm.fit_n}) -> test on {arm.test_on} "
              f"bases (n={arm.test_n}, {arm.overlap_removed} removed as overlap)")
        print(f"    offset fitted        {arm.offset:+.4f}")
        print(f"    base RMSE   {arm.base_rmse_before:.4f} -> {arm.base_rmse_after:.4f}"
              f"   {'improves' if arm.base_rmse_improves else 'WORSE'}")
        print(f"    base MAE    {arm.base_mae_before:.4f} -> {arm.base_mae_after:.4f}")
        print(f"    overall MAE {arm.overall_mae_before:.4f} -> {arm.overall_mae_after:.4f}"
              f"   {'ok' if arm.overall_mae_not_worse else 'WORSE'}")
        ci = arm.ci
        print(f"    improvement 95% CI   "
              f"{'not estimable' if ci is None else f'[{ci[0]:+.4f}, {ci[1]:+.4f}]'}"
              f"   {'excludes zero' if arm.ci_excludes_zero else 'INCLUDES ZERO'}")
        print()

    offsets = [a.offset for a in arms]
    same_sign = offsets[0] * offsets[1] > 0
    agreement = abs(offsets[0] - offsets[1])
    enough = all(a.test_n >= MIN_HELDOUT_BASES for a in arms)
    estimable = all(a.ci is not None for a in arms)

    checks = {
        "same_sign": same_sign,
        f"offset_agreement <= {OFFSET_AGREEMENT_MAX}": agreement <= OFFSET_AGREEMENT_MAX,
        "base_rmse_improves_both": all(a.base_rmse_improves for a in arms),
        "overall_mae_not_worse_both": all(a.overall_mae_not_worse for a in arms),
        "ci_excludes_zero_both": all(a.ci_excludes_zero for a in arms),
    }
    print(f"offset agreement |{offsets[0]:+.4f} - {offsets[1]:+.4f}| = {agreement:.4f}")
    for name, value in checks.items():
        print(f"  {name:<34} {'PASS' if value else 'FAIL'}")

    if not (enough and estimable):
        outcome = "UNDECIDED"
        reason = ("held-out base count below the pre-registered minimum"
                  if not enough else "bootstrap CI not estimable")
    elif all(checks.values()):
        outcome = "SHIP"
        reason = ""
    else:
        outcome = "SURFACE_ONLY"
        reason = "; ".join(n for n, v in checks.items() if not v) + " failed"

    # Combined refit, reported whatever the outcome -- it is only USED on SHIP.
    # **A CROSS-CORPUS DUPLICATE IS NOT A POLYMORPH PAIR**, and treating it
    # as one was a bug: cimetidine sits in both corpora with slightly
    # different measured values, which is ordinary inter-source variation
    # rather than two solid forms. SC-2 wins, because it is the tight set --
    # interlaboratory means over many sources, with an SD per compound --
    # where SC-1 carries single values.
    #
    # This resolution CANNOT influence the verdict: the combined constant is
    # used only on SHIP, and it is reported here for completeness whatever
    # the outcome.
    union: dict[str, Compound] = {c.key: c for c in sc1.bases}
    union.update({c.key: c for c in sc2.bases})
    combined = -statistics.fmean(_errors(list(union.values())))
    duplicates_removed = len(sc1.bases) + len(sc2.bases) - len(union)

    print()
    print(f"OUTCOME  {outcome}" + (f"  ({reason})" if reason else ""))
    print(f"  SC-1 fitted {offsets[0]:+.4f}   SC-2 fitted {offsets[1]:+.4f}   "
          f"combined {combined:+.4f} over {len(union)} unique bases "
          f"({duplicates_removed} duplicate rows removed)")
    print("  The combined figure is IN-SAMPLE and is not evidence of generalisation;")
    print("  the two held-out arms above are.")

    RESULT.write_text(json.dumps({
        "outcome": outcome,
        "reason": reason,
        "acceptance_criteria_version": ACCEPTANCE_CRITERIA_VERSION,
        "model": "esol",
        "fitting_method": "mean(measured_logS - raw_ESOL_logS), unweighted, one row per compound",
        "shipped_constant_logs": round(combined, 4) if outcome == "SHIP" else None,
        "offsets": {"sc1": round(offsets[0], 4), "sc2": round(offsets[1], 4),
                    "combined_in_sample": round(combined, 4)},
        "checks": checks,
        "arms": [a.as_dict() for a in arms],
        "corpora": {
            "sc1": {"n": len(sc1.compounds), "bases": len(sc1.bases),
                    "excluded": sc1.excluded, "sha256_16": _fingerprint(DATA / "evaluation.csv")},
            "sc2": {"n": len(sc2.compounds), "bases": len(sc2.bases),
                    "excluded": sc2.excluded, "sha256_16": _fingerprint(DATA / "sc2_tight.csv")},
        },
        "overlap": {"compounds": len(overlap), "bases": len(overlap_bases)},
        "union_bases": len(union),
        "duplicate_rows_removed": duplicates_removed,
        "bootstrap": {"replicates": BOOTSTRAP_REPLICATES, "seed": BOOTSTRAP_SEED,
                      "statistic": "mean(|error_before| - |error_after|), percentile 95% CI"},
        "provenance": {
            "command": "uv run --no-sync python benchmarks/solubility/base_bias.py",
            "git_sha": _git_sha(),
            "python": platform.python_version(),
            "rdkit": __import__("rdkit").__version__,
            "date": date.today().isoformat(),
        },
    }, indent=1), encoding="utf-8")
    print(f"\nwrote {RESULT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
