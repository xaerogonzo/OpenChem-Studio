"""The low-temperature density correction study of Phase B (`PREREGISTRATION.md` 15.8, 15.9 item c). Nothing here has been run on real pairs.

    python benchmarks/energetics_props/epb_density_correction.py counts  [--pairs cod_correction_pairs.json]
    python benchmarks/energetics_props/epb_density_correction.py freeze  --out results_correction/freeze.json
    python benchmarks/energetics_props/epb_density_correction.py holdout --freeze results_correction/freeze.json --out results_correction/holdout.json --confirm-holdout-once

The question: given a crystal density measured at 80-160 K, how well does a one-parameter thermal-expansion model predict the density of the same
form at 273-303 K? A *pair* is two determinations of one entity key, one space group and one Z, one at each temperature, with a cell-volume ratio
V(RT)/V(low) in [1.00, 1.08] (`cod_correction_pairs.json`, built by `epb_cod_corpus.py`). The population is every organic, nitrogen-containing
crystal (owner, 2026-10-27: the four explosophore groups alone hold too few held-out entities); the pairs whose two determinations carry one of the four
groups are flagged and reported beside the whole as a descriptive subset, never as the gate. Because the formula is the same, the density ratio is the
volume ratio, so both forms are fitted to it by ordinary least squares, in closed form, with nothing to tune:

    constant:  rho_low / rho_rt - 1 = alpha * (T_rt - T_low)
    linear:    rho_low / rho_rt - 1 = (a + b * (T_low - 120 K)) * (T_rt - T_low)       (120 K is the middle of 80-160 K; any other centre is the same model)

and the prediction is rho_rt = rho_low / (1 + that). Fitted on **development pairs only**, the form chosen on **selection pairs** (lower MAE; a tie, within
`TIE_TOLERANCE`, goes to the constant form, which has one parameter), scored **once** on held-out pairs. Pairs are split by entity key with the same 60/20/20 hash as
every other Phase B row, with the previously examined compounds forced into development (15.6). The uncorrected error, which is the low-temperature
density used as the prediction, is reported beside every number.

**The bar** (15.8): held-out MAE <= 0.015 g/cm3 and the upper end of the 95% bootstrap interval <= 0.02. The interval resamples *entity keys* (a key
with several forms moves as one), not pairs, 10,000 times with a fixed seed, and the bar is applied to the interval's upper end (the 97.5th percentile),
the stricter of the two readings of "upper 95% bound". **The minimum held-out entities, `MIN_HELD_OUT_ENTITIES`, is NOT in the preregistration.** It is
set here, and the owner confirmed 35 on 2026-10-27: the derivation of section 13 (an interval half-width of P/3 at P = 0.015 and a standard deviation as large as the
mean) gives n >= (3 x 1.96)^2 = 34.6, so 35, with no allowance added. Fewer held-out entities is `NOT_EVALUABLE`, never a relaxed bar.

Outcomes, machine-readable: `NOT_RUN` (this file's default state without a freeze), `NOT_EVALUABLE`, `FAIL`, `PASS`.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
JUDGE_VERSION = "epb-density-correction-1"

MAE_CEILING = 0.015  # g/cm3, the owner's bar (15.8)
UPPER_CEILING = 0.02  # g/cm3, 4/3 of the bar, as in 11.2
MIN_HELD_OUT_ENTITIES = 35  # ceil((3 * 1.96) ** 2), see the module docstring; the owner confirmed it 2026-10-27, the preregistration text does not say it yet
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261027
T_CENTRE_K = 120.0
TIE_TOLERANCE = 1e-9  # g/cm3: the linear form must beat the constant one by more than rounding to be chosen
FORMS = ("constant", "linear")
PAIRS_PATH = HERE / "cod_correction_pairs.json"
FROZEN_FILES = (
    "benchmarks/energetics_props/epb_density_correction.py",
    "benchmarks/energetics_props/epb_cod_corpus.py",
    "benchmarks/energetics_props/cod_correction_pairs.json",
    "benchmarks/energetics_props/cod_split_manifest.json",
    "tools/validation_rows.py",
)


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _corpus():
    return _load("epb_cod_corpus", HERE / "epb_cod_corpus.py")


@dataclass(frozen=True)
class Pair:
    key: str
    space_group: str
    z: float
    low_code: str
    rt_code: str
    t_low: float
    t_rt: float
    rho_low: float
    rho_rt: float
    volume_ratio: float
    explosophore: bool = False  # both determinations carry one of the four groups: reported beside the whole, never the gate

    @property
    def dt(self) -> float:
        return self.t_rt - self.t_low

    @property
    def expansion(self) -> float:
        """The observed V(RT)/V(low) - 1, from the densities (one formula, one Z, so the same as the volume ratio)."""
        return self.rho_low / self.rho_rt - 1.0


@dataclass(frozen=True)
class Fit:
    form: str
    params: tuple[float, ...]
    n: int


# ------------------------------------------------------------------------------------------------------- pairs
def pair_problem(row: dict) -> str | None:
    """Why a row is not a pair under 15.8, or None. A file that holds such a row is refused, never silently filtered."""
    c = _corpus()
    try:
        t_low, t_rt = float(row["t_low"]), float(row["t_rt"])
        rho_low, rho_rt, ratio = float(row["rho_low"]), float(row["rho_rt"]), float(row["volume_ratio"])
    except (KeyError, TypeError, ValueError):
        return "a field is missing or not a number"
    if not all(math.isfinite(v) for v in (t_low, t_rt, rho_low, rho_rt, ratio)) or rho_low <= 0 or rho_rt <= 0:
        return "a density, temperature or ratio is not a finite positive number"
    if not c.LOW_T_K[0] <= t_low <= c.LOW_T_K[1]:
        return f"the low temperature {t_low} K is outside {c.LOW_T_K}"
    if not c.WINDOW_K[0] <= t_rt <= c.WINDOW_K[1]:
        return f"the room temperature {t_rt} K is outside {c.WINDOW_K}"
    if not c.PAIR_VOLUME_RATIO[0] <= ratio <= c.PAIR_VOLUME_RATIO[1]:
        return f"the volume ratio {ratio:.4f} is outside {c.PAIR_VOLUME_RATIO}"
    if not row.get("key") or row.get("space_group") is None or row.get("z") is None:
        return "no entity key, space group or Z"
    if not isinstance(row.get("explosophore"), bool):
        return "no explosophore flag"
    return None


def read_pairs(path: Path = PAIRS_PATH) -> list[Pair]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for row in rows:
        why = pair_problem(row)
        if why:
            raise ValueError(f"{row.get('low_code')}/{row.get('rt_code')}: {why}")
        out.append(Pair(row["key"], row["space_group"], float(row["z"]), str(row["low_code"]), str(row["rt_code"]), float(row["t_low"]),
                        float(row["t_rt"]), float(row["rho_low"]), float(row["rho_rt"]), float(row["volume_ratio"]), row["explosophore"]))
    if len({(p.key, p.space_group, p.z) for p in out}) != len(out):
        raise ValueError("two pairs share one entity key, space group and Z: one form is one pair")
    return out


def split_pairs(pairs: list[Pair], forced: dict[str, str]) -> dict[str, list[Pair]]:
    c = _corpus()
    parts: dict[str, list[Pair]] = {"development": [], "selection": [], "holdout": []}
    for p in pairs:
        parts[c.assign_partition(p.key, forced)[0]].append(p)
    return parts


def counts(parts: dict[str, list[Pair]]) -> dict:
    """Pairs and entities per partition: a count, never a score."""
    out = {name: {"pairs": len(ps), "entities": len({p.key for p in ps}),
                  "explosophore_entities": len({p.key for p in ps if p.explosophore})} for name, ps in parts.items()}
    held = out["holdout"]["entities"]
    out["min_held_out_entities"] = MIN_HELD_OUT_ENTITIES
    out["evaluable"] = held >= MIN_HELD_OUT_ENTITIES
    out["entities_in_all_partitions_needed_at_20_percent"] = math.ceil(MIN_HELD_OUT_ENTITIES / 0.20)
    return out


# ------------------------------------------------------------------------------------------------------- fits
def fit_constant(pairs: list[Pair]) -> Fit:
    """alpha = sum(dt * e) / sum(dt^2), the least-squares line through the origin of expansion against temperature difference."""
    if not pairs:
        raise ValueError("no pairs to fit")
    den = sum(p.dt**2 for p in pairs)
    return Fit("constant", (sum(p.dt * p.expansion for p in pairs) / den,), len(pairs))


def fit_linear(pairs: list[Pair]) -> Fit | None:
    """(a, b) of alpha = a + b (T_low - 120 K), by the 2x2 normal equations; None when the low temperatures do not vary enough to separate them."""
    if len(pairs) < 3:
        return None
    x1 = [p.dt for p in pairs]
    x2 = [p.dt * (p.t_low - T_CENTRE_K) for p in pairs]
    y = [p.expansion for p in pairs]
    s11, s12, s22 = sum(a * a for a in x1), sum(a * b for a, b in zip(x1, x2)), sum(b * b for b in x2)
    det = s11 * s22 - s12 * s12
    if det <= 1e-9 * s11 * s22:
        return None
    s1y, s2y = sum(a * v for a, v in zip(x1, y)), sum(b * v for b, v in zip(x2, y))
    return Fit("linear", ((s22 * s1y - s12 * s2y) / det, (s11 * s2y - s12 * s1y) / det), len(pairs))


def _alpha(fit: Fit, t_low: float) -> float:
    if fit.form == "constant":
        return fit.params[0]
    return fit.params[0] + fit.params[1] * (t_low - T_CENTRE_K)


def correct_density(fit: Fit, rho_low: float, t_low: float, t_rt: float) -> float:
    """The density predicted at `t_rt` from one measured at `t_low` (used by the secondary analysis, 15.8, and by the scoring below)."""
    factor = 1.0 + _alpha(fit, t_low) * (t_rt - t_low)
    if not factor > 0:
        raise ValueError(f"the fitted expansion gives a non-positive volume factor {factor}")
    return rho_low / factor


def combined_error(method_error: float, correction_mae: float) -> float:
    """A corrected result's error: the method's and the correction's, added in quadrature (15.8)."""
    return math.hypot(method_error, correction_mae)


def errors(pairs: list[Pair], fit: Fit | None) -> list[float]:
    """Absolute density errors in g/cm3; with no fit, the uncorrected one (the low-temperature density as the prediction)."""
    if fit is None:
        return [abs(p.rho_low - p.rho_rt) for p in pairs]
    return [abs(correct_density(fit, p.rho_low, p.t_low, p.t_rt) - p.rho_rt) for p in pairs]


def mae(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def entity_bootstrap(pairs: list[Pair], errs: list[float], *, resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    """The 95% percentile interval of the MAE, resampling entity keys with replacement (a key's pairs move together)."""
    import numpy as np

    by_key: dict[str, list[float]] = {}
    for p, e in zip(pairs, errs):
        by_key.setdefault(p.key, []).append(e)
    sums = np.array([sum(v) for v in by_key.values()])
    sizes = np.array([len(v) for v in by_key.values()])
    rng = np.random.default_rng(seed)
    draw = rng.integers(0, len(sums), size=(resamples, len(sums)))
    boot = sums[draw].sum(axis=1) / sizes[draw].sum(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return float(lo), float(hi)


# ------------------------------------------------------------------------------------------------------- the two stages
def develop(development: list[Pair], selection: list[Pair]) -> dict:
    """Fit both forms on development pairs and pick one on selection pairs. No held-out pair is read."""
    fits = {"constant": fit_constant(development), "linear": fit_linear(development)}
    sel = {name: (mae(errors(selection, f)) if f is not None else None) for name, f in fits.items()}
    if sel["constant"] is None:
        raise ValueError("no pairs to score the constant form on")
    linear = sel["linear"]
    chosen = "linear" if linear is not None and linear < sel["constant"] - TIE_TOLERANCE else "constant"
    return {
        "fits": {n: ({"params": list(f.params), "n": f.n} if f else None) for n, f in fits.items()},
        "selection_mae": sel,
        "selection_uncorrected_mae": mae(errors(selection, None)),
        "chosen": chosen,
    }


def _explosophore_subset(holdout: list[Pair], fit: Fit) -> dict:
    """The held-out pairs whose two determinations both carry one of the four groups: descriptive, with no bar and no verdict."""
    sub = [p for p in holdout if p.explosophore]
    if not sub:
        return {"pairs": 0, "entities": 0, "mae": None, "uncorrected_mae": None}
    return {"pairs": len(sub), "entities": len({p.key for p in sub}), "mae": mae(errors(sub, fit)), "uncorrected_mae": mae(errors(sub, None))}


def judge(fit: Fit, holdout: list[Pair]) -> dict:
    """The one held-out evaluation of the chosen fit: numbers, the bar, and the outcome."""
    entities = len({p.key for p in holdout})
    errs, raw = errors(holdout, fit), errors(holdout, None)
    out = {"judge_version": JUDGE_VERSION, "form": fit.form, "params": list(fit.params), "held_out_pairs": len(holdout),
           "held_out_entities": entities, "min_held_out_entities": MIN_HELD_OUT_ENTITIES,
           "mae_ceiling": MAE_CEILING, "upper_ceiling": UPPER_CEILING, "bootstrap_resamples": BOOTSTRAP_RESAMPLES, "bootstrap_seed": BOOTSTRAP_SEED}
    if not holdout:
        return {**out, "status": "NOT_EVALUABLE", "reason": "no held-out pair", "mae": None, "interval": None, "uncorrected_mae": None}
    lo, hi = entity_bootstrap(holdout, errs)
    point = mae(errs)
    out.update(mae=point, interval=[lo, hi], uncorrected_mae=mae(raw), uncorrected_interval=list(entity_bootstrap(holdout, raw)),
               signed_bias=sum(correct_density(fit, p.rho_low, p.t_low, p.t_rt) - p.rho_rt for p in holdout) / len(holdout))
    out["explosophore_subset"] = _explosophore_subset(holdout, fit)
    if entities < MIN_HELD_OUT_ENTITIES:
        out.update(status="NOT_EVALUABLE", reason=f"{entities} held-out entities, {MIN_HELD_OUT_ENTITIES} needed; the bar is not relaxed")
    elif point <= MAE_CEILING and hi <= UPPER_CEILING:
        out.update(status="PASS", reason="MAE and the interval's upper end are within the bar")
    else:
        out.update(status="FAIL", reason="the MAE or the interval's upper end exceeds the bar")
    return out


# ------------------------------------------------------------------------------------------------------- freeze, lock, holdout
def file_hashes() -> dict[str, str]:
    return {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in FROZEN_FILES}


def git_commit() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def git_dirty() -> bool:
    return bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip())


def stage_freeze(pairs_path: Path, out_path: Path) -> dict:
    """Fit on development, choose on selection, write the frozen choice with the hashes of every file that produced it."""
    parts = split_pairs(read_pairs(pairs_path), _corpus().previously_examined_keys())
    frozen = {"judge_version": JUDGE_VERSION, "counts": counts(parts), "file_hashes": file_hashes(), "commit": git_commit(),
              **develop(parts["development"], parts["selection"])}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(frozen, indent=1, sort_keys=True), encoding="utf-8")
    return frozen


def stage_holdout(freeze_path: Path, pairs_path: Path, out_path: Path, *, confirmed: bool, lock: Path | None = None) -> dict:
    """The one holdout evaluation. Refuses unless confirmed, unless every frozen file is byte-identical, and a second time."""
    lock = lock or freeze_path.with_name("holdout_scored.lock")
    if not confirmed:
        raise SystemExit("refused: the holdout is scored once; pass --confirm-holdout-once")
    if lock.exists():
        raise SystemExit(f"refused: the holdout was already scored ({lock.read_text(encoding='utf-8').strip()})")
    frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
    changed = [k for k, v in file_hashes().items() if frozen["file_hashes"].get(k) != v]
    if changed:
        raise SystemExit(f"refused: files changed since the freeze: {changed}")
    if git_dirty():
        raise SystemExit("refused: the working tree has uncommitted changes to tracked files")
    lock.write_text(f"started {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} at {git_commit()}\n", encoding="utf-8")
    parts = split_pairs(read_pairs(pairs_path), _corpus().previously_examined_keys())
    chosen = frozen["chosen"]
    fit = Fit(chosen, tuple(frozen["fits"][chosen]["params"]), frozen["fits"][chosen]["n"])
    verdict = judge(fit, parts["holdout"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(verdict, indent=1, sort_keys=True), encoding="utf-8")
    return verdict


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("counts", "freeze", "holdout"):
        p = sub.add_parser(name)
        p.add_argument("--pairs", type=Path, default=PAIRS_PATH)
        if name != "counts":
            p.add_argument("--out", type=Path, required=True)
        if name == "holdout":
            p.add_argument("--freeze", type=Path, required=True)
            p.add_argument("--confirm-holdout-once", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "counts":
        print(json.dumps(counts(split_pairs(read_pairs(args.pairs), _corpus().previously_examined_keys())), indent=1))
    elif args.cmd == "freeze":
        stage_freeze(args.pairs, args.out)
    else:
        print(json.dumps(stage_holdout(args.freeze, args.pairs, args.out, confirmed=args.confirm_holdout_once), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
