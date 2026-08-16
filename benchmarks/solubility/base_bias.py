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
AMENDMENT -> acceptance_criteria_version = 3   (MORE CORPORA)
--------------------------------------------------------------------

**WRITTEN BEFORE THE NEW CORPORA WERE RUN THROUGH IT.** v2's verdict was
SURFACE_ONLY on a CI that missed by 0.0009, which is a POWER question, so
two further corpora were extracted (`extract_avdeef_sets.py`). v3 changes
only how extra corpora enter; every v2 criterion survives verbatim.

ELIGIBILITY IS DECLARED, NEVER "WHATEVER HAS THE LARGEST n":

    ELIGIBLE     endpoint-compatible; may be fitted, held out and pooled
    TEST_ONLY    reported as a sensitivity arm; never enters a fit
    INELIGIBLE   excluded, with the failing field named

The endpoint must be `target_type == "intrinsic"`. The correction is a
claim about the intrinsic solubility of the NEUTRAL SPECIES, so fitting it
across a corpus of aqueous solubility of whatever solid form would measure
a different quantity under the same name -- which is why AqSolDB, the
largest set available, is TEST_ONLY and not merely unused.

`solid_form == "unknown"` is ACCEPTED and recorded. Every corpus this
project has declares it, so requiring a known solid form leaves zero
eligible corpora and no experiment; it is a stated limitation instead of a
criterion nobody can meet.

LEAVE-ONE-CORPUS-OUT, not merely "cross-corpus": each eligible corpus is
held out in turn while the others are pooled to fit, with the fit
composition printed per arm because each arm's offset depends on who was
on the other side. A corpus with fewer than MIN_HELDOUT_BASES eligible
bases after every filter cannot be a TEST side, and says so.

THE POOLED ARM IS SENSITIVITY ONLY and can never turn UNDECIDED or
SURFACE_ONLY into SHIP -- otherwise a larger pooled n eventually gets used
to rescue the experiment.

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
from enum import Enum
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

ACCEPTANCE_CRITERIA_VERSION = 3
OFFSET_AGREEMENT_MAX = 0.25
MIN_HELDOUT_BASES = 10
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20260816
#: Two measurements of one compound differing by more than this are a
#: conflict rather than rounding, and stop the experiment.
DUPLICATE_CONFLICT_LOG = 0.05


#: Every corpus this experiment knows about. `manifest` supplies the
#: declared endpoint; eligibility is read from it rather than assumed.
CORPORA = {
    "SC-1": ("evaluation.csv", "manifest.json", False),
    "SC-2": ("sc2_tight.csv", "sc2_manifest.json", True),
    "A1": ("avdeef_a1.csv", "avdeef_a1_manifest.json", True),
    "A2": ("avdeef_a2.csv", "avdeef_a2_manifest.json", True),
}


class Eligibility(Enum):
    ELIGIBLE = "eligible"
    TEST_ONLY = "test_only"
    INELIGIBLE = "ineligible"


def corpus_eligibility(manifest: dict) -> tuple[Eligibility, str]:
    """Declared, printed, and never inferred from size.

    The endpoint is the whole check: this fits a correction to the
    INTRINSIC solubility of the neutral species, so a corpus measuring
    something else is measuring a different quantity under the same name.
    `solid_form == "unknown"` is accepted because every corpus here
    declares it -- requiring otherwise leaves no experiment at all -- and
    is carried as a limitation instead.
    """
    endpoint = manifest.get("target_type")
    if endpoint != "intrinsic":
        return Eligibility.TEST_ONLY, f"endpoint_mismatch: target_type={endpoint!r}"
    return Eligibility.ELIGIBLE, f"target_type={endpoint!r}, solid_form={manifest.get('solid_form')!r}"


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
    base_bias_before: float
    base_bias_after: float
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
            "base_bias_before": round(self.base_bias_before, 4),
            "base_bias_after": round(self.base_bias_after, 4),
            "overall_mae_before": round(self.overall_mae_before, 4),
            "overall_mae_after": round(self.overall_mae_after, 4),
            "improvement_ci95": None if self.ci is None else [round(self.ci[0], 4), round(self.ci[1], 4)],
            "base_rmse_improves": self.base_rmse_improves,
            "overall_mae_not_worse": self.overall_mae_not_worse,
            "ci_excludes_zero": self.ci_excludes_zero,
        }


def _fit_offset(compounds: list[Compound]) -> float:
    """The pre-registered statistic: mean(measured - raw ESOL), unweighted."""
    return -statistics.fmean(_errors(compounds))


def _arm(name: str, fit_names: list[str], fit: list[Compound], test: list[Compound],
         test_all: list[Compound], removed: int) -> Arm:
    """One leave-one-corpus-out arm, with disjointness asserted.

    The fit composition travels with the arm because each arm's offset
    depends on which corpora were pooled on the other side -- reporting an
    offset without it invites reading the arms as independent estimates of
    one number.
    """
    fit_ids = {c.key for c in fit}
    test_ids = {c.key for c in test}
    if fit_ids & test_ids:
        raise ExperimentError(
            f"{name}: held-out arm is not held out -- {len(fit_ids & test_ids)} shared identifiers"
        )

    offset = _fit_offset(fit)
    before = _errors(test)
    after = _errors(test, offset)
    improvements = [abs(b) - abs(a) for b, a in zip(before, after)]

    overall_before = _errors(test_all)
    overall_after = [
        e + (offset if c.ionization is IonizationClass.BASE else 0.0)
        for c, e in zip(test_all, overall_before)
    ]
    return Arm(
        fit_on="+".join(fit_names), test_on=name, offset=offset,
        fit_n=len(fit), test_n=len(test), overlap_removed=removed,
        base_rmse_before=_rmse(before), base_rmse_after=_rmse(after),
        base_mae_before=_mae(before), base_mae_after=_mae(after),
        base_bias_before=statistics.fmean(before), base_bias_after=statistics.fmean(after),
        overall_mae_before=_mae(overall_before), overall_mae_after=_mae(overall_after),
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
    print(f"acceptance_criteria_version = {ACCEPTANCE_CRITERIA_VERSION}  "
          "(pre-registered; see the module docstring)")
    print()

    drop = _delaney_keys()
    loaded: dict[str, Corpus] = {}
    states: dict[str, tuple[str, str]] = {}
    try:
        for name, (corpus_file, manifest_file, deleak) in CORPORA.items():
            manifest_path = DATA / manifest_file
            if not manifest_path.is_file() or not (DATA / corpus_file).is_file():
                states[name] = ("MISSING", f"{corpus_file} or {manifest_file} absent")
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            state, why = corpus_eligibility(manifest)
            states[name] = (state.name, why)
            if state is not Eligibility.ELIGIBLE:
                continue
            loaded[name] = _load(DATA / corpus_file, name, drop_keys=drop if deleak else set())
    except ExperimentError as exc:
        print(f"EXPERIMENT_ERROR  {exc}")
        RESULT.write_text(
            json.dumps({"outcome": "EXPERIMENT_ERROR", "reason": str(exc)}, indent=1),
            encoding="utf-8",
        )
        return 1

    print("CORPUS ELIGIBILITY (declared, not inferred from size)")
    for name, (state, why) in states.items():
        n = len(loaded[name].compounds) if name in loaded else 0
        bases = len(loaded[name].bases) if name in loaded else 0
        print(f"  {name:<6} {state:<11} n={n:<4} bases={bases:<4} {why}")
    print("  AqSolDB TEST_ONLY   endpoint_mismatch: aqueous solubility of whatever solid")
    print("                      form, not intrinsic. Never fitted, never pooled.")
    print()

    print("PAIRWISE OVERLAP (InChIKey)")
    names = list(loaded)
    overlaps: dict[str, int] = {}
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            shared = {c.key for c in loaded[first].compounds} & {
                c.key for c in loaded[second].compounds
            }
            overlaps[f"{first}|{second}"] = len(shared)
            if shared:
                print(f"  {first} n {second}: {len(shared)}")
    print()

    participating = [n for n in names if len(loaded[n].bases) >= MIN_HELDOUT_BASES]
    for name in names:
        if name not in participating:
            print(f"  {name} cannot be a held-out side: {len(loaded[name].bases)} bases "
                  f"< MIN_HELDOUT_BASES={MIN_HELDOUT_BASES}")

    arms: list[Arm] = []
    try:
        for test_name in participating:
            fit_names = [n for n in names if n != test_name]
            fit_pool: dict[str, Compound] = {}
            for other in fit_names:
                for compound in loaded[other].bases:
                    fit_pool.setdefault(compound.key, compound)
            fit_keys = set(fit_pool)
            test_bases = [c for c in loaded[test_name].bases if c.key not in fit_keys]
            test_all = [c for c in loaded[test_name].compounds if c.key not in fit_keys]
            removed = len(loaded[test_name].bases) - len(test_bases)
            if len(test_bases) < MIN_HELDOUT_BASES or len(fit_pool) < MIN_HELDOUT_BASES:
                print(f"  test on {test_name}: UNDECIDED, fit n={len(fit_pool)} "
                      f"test n={len(test_bases)} after removing {removed} shared")
                continue
            arms.append(
                _arm(test_name, fit_names, list(fit_pool.values()), test_bases, test_all, removed)
            )
    except ExperimentError as exc:
        print(f"EXPERIMENT_ERROR  {exc}")
        return 1

    print()
    for arm in arms:
        print(f"--- fit on {arm.fit_on} (n={arm.fit_n}) -> test on {arm.test_on} "
              f"(n={arm.test_n}, {arm.overlap_removed} removed as shared)")
        print(f"    offset fitted        {arm.offset:+.4f}")
        print(f"    base RMSE   {arm.base_rmse_before:.4f} -> {arm.base_rmse_after:.4f}"
              f"   {'improves' if arm.base_rmse_improves else 'WORSE'}")
        print(f"    base MAE    {arm.base_mae_before:.4f} -> {arm.base_mae_after:.4f}")
        print(f"    base bias   {arm.base_bias_before:+.4f} -> {arm.base_bias_after:+.4f}")
        print(f"    overall MAE {arm.overall_mae_before:.4f} -> {arm.overall_mae_after:.4f}"
              f"   {'ok' if arm.overall_mae_not_worse else 'WORSE'}")
        ci = arm.ci
        rendered = "not estimable" if ci is None else f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"
        print(f"    improvement 95% CI   {rendered}"
              f"   {'excludes zero' if arm.ci_excludes_zero else 'INCLUDES ZERO'}")
        print()

    checks: dict[str, bool] = {}
    offsets = [a.offset for a in arms]
    agreement = None
    if len(arms) < 2:
        outcome = "UNDECIDED"
        reason = (f"only {len(arms)} arm(s) had enough eligible held-out bases; the "
                  "criteria could not be evaluated to specification")
    else:
        agreement = max(offsets) - min(offsets)
        checks = {
            "same_sign": all(o > 0 for o in offsets) or all(o < 0 for o in offsets),
            f"offset_agreement <= {OFFSET_AGREEMENT_MAX}": agreement <= OFFSET_AGREEMENT_MAX,
            "base_rmse_improves_all": all(a.base_rmse_improves for a in arms),
            "overall_mae_not_worse_all": all(a.overall_mae_not_worse for a in arms),
            "ci_excludes_zero_all": all(a.ci_excludes_zero for a in arms),
        }
        print(f"offset agreement (max - min) = {agreement:.4f} over {len(arms)} arms")
        for label, value in checks.items():
            print(f"  {label:<34} {'PASS' if value else 'FAIL'}")
        outcome = "SHIP" if all(checks.values()) else "SURFACE_ONLY"
        reason = "" if outcome == "SHIP" else (
            "; ".join(k for k, v in checks.items() if not v) + " failed"
        )

    # Insufficient evidence and contrary evidence must never read alike.
    evidence = None
    if outcome == "SURFACE_ONLY":
        evidence = (
            "contrary_evidence"
            if any(a.base_rmse_after > a.base_rmse_before for a in arms)
            else "insufficient_evidence"
        )

    union: dict[str, Compound] = {}
    for name in names:
        for compound in loaded[name].bases:
            union.setdefault(compound.key, compound)
    combined = _fit_offset(list(union.values())) if union else 0.0

    print()
    print(f"OUTCOME  {outcome}" + (f"  ({reason})" if reason else ""))
    if evidence == "insufficient_evidence":
        print("  reading: insufficient evidence for the pre-registered claim -- the CI")
        print("           spans zero, which is NOT the same as showing there is no bias.")
    elif evidence == "contrary_evidence":
        print("  reading: contrary evidence -- an arm got WORSE, not merely unproven.")
    print(f"  combined in-sample offset {combined:+.4f} over {len(union)} unique bases")
    print("  That figure is IN-SAMPLE and is not evidence of generalisation.")
    print(f"  production_change_permitted = {str(outcome == 'SHIP').lower()}")

    RESULT.write_text(json.dumps({
        "outcome": outcome,
        "reason": reason,
        "evidence_reading": evidence,
        "production_change_permitted": outcome == "SHIP",
        "acceptance_criteria_version": ACCEPTANCE_CRITERIA_VERSION,
        "model": "esol",
        "fitting_method": "mean(measured_logS - raw_ESOL_logS), unweighted, one row per compound",
        "sd_and_n_are": "metadata, never weights",
        "shipped_constant_logs": round(combined, 4) if outcome == "SHIP" else None,
        "combined_in_sample_offset": round(combined, 4),
        "offset_agreement": None if agreement is None else round(agreement, 4),
        "checks": checks,
        "arms": [a.as_dict() for a in arms],
        "corpus_states": {k: {"state": v[0], "why": v[1]} for k, v in states.items()},
        "corpora": {
            name: {
                "n": len(corpus.compounds),
                "bases": len(corpus.bases),
                "excluded": corpus.excluded,
                "sha256_16": _fingerprint(DATA / CORPORA[name][0]),
            }
            for name, corpus in loaded.items()
        },
        "pairwise_overlap": overlaps,
        "union_bases": len(union),
        "min_heldout_bases": MIN_HELDOUT_BASES,
        "bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES, "seed": BOOTSTRAP_SEED,
            "resample_unit": "compound", "method": "percentile 95%",
            "statistic": "mean(|error_before| - |error_after|)",
        },
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
