"""Stage 2 of the Within-Assay Docking Ranking Benchmark: the statistics.

    uv run --no-sync python benchmarks/docking/rank_report.py
    uv run --no-sync python benchmarks/docking/rank_report.py --json out.json

No network and no Vina, so it costs seconds and can be re-run against a
finished Stage 1 as often as anybody wants.

## The sign convention, stated once and never negotiated per column

Vina is more-negative-is-better; pChEMBL is higher-is-better. A GOOD scoring
function therefore produces a NEGATIVE raw correlation, which is true,
useless, and read backwards by everyone. So the score is negated **before**
the statistic and every column is labelled `rho(-score, pChEMBL)`: higher is
better agreement, everywhere, with no per-column exceptions.

## What is being compared, and what is not

**Vinardo rescores the IDENTICAL Vina-generated poses.** The comparison is
"Vina's score against Vinardo's rescoring of the same poses" -- NOT "Vina
docking against Vinardo docking", which is a different experiment that would
need Vinardo to run the search. That distinction matters more the moment a
second engine (smina) arrives, being both an engine and a rescorer.

**The representative replicate is the SHIPPED one.**
`domain.affinity_range.AffinityRange.median` is imported rather than
reimplemented: it is `sorted(values)[n // 2]`, which for even n takes the LESS
negative of the two middle values on purpose. A local median averaging them
gives -8.5 where the application gives -8.0 on the same four runs, and the
benchmark would be reporting a representative the panel never shows.

**A representative is a DOCKING-SCORE STATISTIC, never a measured-affinity
estimate.** It sits in a column beside pChEMBL and must not acquire the word
"affinity" on the way.

## Search repeatability is NOT a noise ceiling

`rho(half A, half B)` measures how consistently the stochastic search orders
the same ligands under this protocol. It does **not** bound the attainable
correlation with experiment, which is also limited by assay noise, chemical
space and model misspecification -- and the oracle's own reproducibility is
unmeasurable here, because ChEMBL carries no per-row uncertainty. So the
docking's repeatability is measurable and the oracle's is not, and only the
first is reported.

The halves are `_stats.REPLICATE_HALVES`, fixed before any run. Reported
beside it: the number of ligand PAIRS that actually swapped, because a
repeatability of +1.0 over well-separated ligands means "noise did not
reorder ligands that were far apart", not "the search is noiseless".

## Not comparable to any published table

A per-assay congeneric rho is not [source:su2019]'s pooled ~0.6 across 57
targets, nor [source:nguyen2020]'s 0.498 +/- 0.026 over 800 complexes. It is
a different quantity on a harder question, and `docs/ROADMAP.md` already
says this route's numbers "would not be comparable to any published table".
This script prints that rather than trusting a reader to remember it.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _stats import REPLICATE_HALVES, distinct, pairs_reordered, random_floor_sd, spearman  # noqa: E402
from openchem.domain.affinity_range import AffinityRange  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
RESULTS = HERE / "results"

BASELINES = ("heavy_atoms", "mol_weight", "clogp", "tpsa")

#: Resamples for the series-level interval on the Vinardo-minus-Vina effect.
#: A DESCRIPTIVE interval, not a hypothesis test: with of order 16 series
#: there is little power for a subtle difference, and inventing a test to look
#: rigorous is worse than reporting an effect with its spread.
BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20260905


def load_runs(series_id: str) -> list[dict]:
    path = RESULTS / f"{series_id}.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def representative(values: list[float]) -> float:
    """The shipped median. See the module docstring for why not a local one."""
    return AffinityRange(tuple(values)).median


def series_row(series: dict, runs: list[dict], presence: dict) -> dict | None:
    """Every number for one series, or None if it is not complete.

    **INCOMPLETE SERIES ARE NOT REPORTED**, and that is not fastidiousness: a
    series with 11 of 14 ligands docked has its rho over a different ligand set
    than its baselines, and comparing the two is the membership-mismatch defect
    in another costume. They are NAMED instead, so a partial run is visible
    rather than silently smaller.
    """
    wanted = {ligand["molecule_chembl_id"] for ligand in series["ligands"]}
    by_molecule: dict[str, list[dict]] = {}
    for run in runs:
        if run["vina_best"] is not None:
            by_molecule.setdefault(run["molecule_chembl_id"], []).append(run)
    if set(by_molecule) != wanted:
        return None
    replicate_counts = {len(v) for v in by_molecule.values()}
    if len(replicate_counts) != 1:
        return None

    order = sorted(wanted)
    potency = [
        next(l["pchembl_value"] for l in series["ligands"] if l["molecule_chembl_id"] == m)
        for m in order
    ]
    # NEGATED BEFORE THE STATISTIC. See the module docstring.
    vina = [-representative([r["vina_best"] for r in by_molecule[m]]) for m in order]
    rescored = [
        -representative([r["rescore_best"] for r in by_molecule[m]])
        if all(r["rescore_best"] is not None for r in by_molecule[m])
        else None
        for m in order
    ]

    halves = []
    replicates = replicate_counts.pop()
    for group in REPLICATE_HALVES:
        usable = [index for index in group if index < replicates]
        if not usable:
            halves.append(None)
            continue
        halves.append([
            -representative([
                r["vina_best"] for r in by_molecule[m] if r["replicate"] in usable
            ])
            for m in order
        ])

    by_id = {l["molecule_chembl_id"]: l for l in series["ligands"]}
    row = {
        "series_id": series["series_id"],
        "pdb_id": series["pdb_id"],
        "endpoint": series["endpoint"],
        "organism_match": series["organism_match"],
        "n": len(order),
        "effective_n_potency": distinct(potency),
        "effective_n_vina": distinct(vina),
        "span": series["span_pchembl"],
        "replicates": replicates,
        "rho_vina": spearman(vina, potency),
        "rho_rescore": (
            spearman([v for v in rescored if v is not None], potency)
            if all(v is not None for v in rescored)
            else None
        ),
        "rho_repeatability": (
            spearman(halves[0], halves[1]) if halves[0] and halves[1] else None
        ),
        "pairs_reordered": (
            pairs_reordered(halves[0], halves[1]) if halves[0] and halves[1] else None
        ),
        "pairs_total": len(order) * (len(order) - 1) // 2,
        "random_floor_sd": random_floor_sd(len(order)),
        "rho_vina_vs_size": spearman(vina, [by_id[m]["heavy_atoms"] for m in order]),
        "ligands_over_box": sum(
            1 for m in order if any(r["ligand_exceeds_box"] for r in by_molecule[m])
        ),
    }
    for name in BASELINES:
        row[f"rho_{name}"] = spearman([by_id[m][name] for m in order], potency)
    if presence:
        # **NOT_LOOKED_UP IS ITS OWN VERDICT**, and folding it into the others
        # was this function's bug. A compound with no cache entry has not been
        # checked; reporting that as "no exact match" is the absence-versus-
        # inability confusion `pdb_presence.py` refuses one layer down, arriving
        # in the layer that summarises it. It bit immediately: the presence
        # cache was resolved for the v1 selection, v2 selects different
        # compounds, and 125 of 194 had no entry -- so the report announced
        # that nothing in the corpus was in the PDB, on evidence it did not
        # have.
        verdicts = [
            presence.get(by_id[m]["inchikey"], {}).get("verdict") or "NOT_LOOKED_UP"
            for m in order
        ]
        row["presence"] = {v: verdicts.count(v) for v in set(verdicts)}
        clean = [i for i, v in enumerate(verdicts) if v == "ABSENT"]
        row["rho_vina_absent_only"] = (
            spearman([vina[i] for i in clean], [potency[i] for i in clean])
            if len(clean) >= 2
            else None
        )
        row["n_absent"] = len(clean)
    return row


def bootstrap_interval(values: list[float]) -> tuple[float, float] | None:
    """A percentile interval on the MEDIAN across series.

    Resampling SERIES, not ligands: a series is the independent unit here --
    ligands within one assay share a laboratory, a protocol and often a
    scaffold, so resampling them would report an interval far narrower than
    the evidence supports.
    """
    if len(values) < 3:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    medians = []
    for _ in range(BOOTSTRAP):
        sample = [rng.choice(values) for _ in values]
        medians.append(sorted(sample)[len(sample) // 2])
    medians.sort()
    return medians[int(0.025 * BOOTSTRAP)], medians[int(0.975 * BOOTSTRAP)]


def _report_first_selection(rows: list[dict], manifest: dict) -> None:
    """The original fifteen, beside the widened set.

    **THE PRE-COMMITMENT MADE GOOD.** `SERIES_PER_TARGET` was raised from 2 to
    8 after the first result's interval spanned zero, which is legitimate only
    as ADDING SAMPLES -- and the way a reader checks that it was not a re-roll
    is to see both numbers. If the widened median sits far from the original,
    that is worth knowing and possibly worth distrusting; if it sits near it,
    the widening did what widening is supposed to do.

    Prints nothing when the manifest records no earlier selection, so a corpus
    built fresh does not grow a section about a history it does not have.
    """
    first = set(manifest.get("first_frozen_selection") or [])
    if not first:
        return
    subset = [r for r in rows if r["series_id"] in first]
    added = [r for r in rows if r["series_id"] not in first]
    if not subset or not added:
        return

    print(f"\n  THE FIRST FIFTEEN, AND WHAT WIDENING ADDED")
    print("  The selection was widened AFTER the first result, whose interval")
    print("  spanned zero. Both are shown because that is the only way to see")
    print("  whether adding data changed the answer or merely sharpened it.")
    for label, group in (("first selection", subset), ("added by widening", added)):
        values = [r["rho_vina"] for r in group if r["rho_vina"] is not None]
        if not values:
            continue
        interval = bootstrap_interval(values)
        span = f"  95% [{interval[0]:+.3f}, {interval[1]:+.3f}]" if interval else ""
        print(f"    {label:20s} median rho {sorted(values)[len(values) // 2]:+.3f}  "
              f"(n = {len(values)}){span}")


def _sign_test(positive: int, total: int) -> float:
    """Two-sided exact binomial p for `positive` of `total` at p = 0.5.

    A DISTRIBUTION-FREE COMPANION to the median, because the median of fifteen
    noisy per-series correlations is exactly the statistic that looks
    convincing without being: it says nothing about how many series carry the
    sign, and a handful of large positives can hold it up while most series
    sit at zero.

    Exact rather than normal-approximated, at these counts.
    """
    from math import comb

    if total == 0:
        return 1.0
    tail = sum(comb(total, k) for k in range(positive, total + 1)) / 2**total
    return min(1.0, 2 * tail)


def _fmt(value: float | None, width: int = 6) -> str:
    return " " * (width - 3) + "n/a" if value is None else f"{value:+{width}.2f}"


def _swap(row: dict) -> str:
    """The reordered-pairs cell.

    `n/a` when repeatability could not be computed -- a single replicate has
    no halves to compare. Printing `None/91` there reads as a measurement of
    zero swaps out of 91, which is the opposite of what happened.
    """
    if row["pairs_reordered"] is None:
        return "n/a"
    return f"{row['pairs_reordered']}/{row['pairs_total']}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    manifest_path = DATA / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("No corpus. Run chembl_corpus.py first.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    presence_path = DATA / "pdb_presence.json"
    presence = json.loads(presence_path.read_text(encoding="utf-8")) if presence_path.is_file() else {}

    print("WITHIN-ASSAY DOCKING RANKING BENCHMARK")
    print(f"corpus {manifest['chembl_release']}, schema {manifest['schema_version']}, "
          f"endpoint {manifest['endpoint']} ({manifest['relation']}, {manifest['units']})")
    print("\nNOT COMPARABLE TO CASF. This ranks compounds measured in ONE assay")
    print("against poses this application generated; su2019's ~0.6 and")
    print("nguyen2020's 0.498 are pooled cross-target quantities on a different")
    print("question. The numbers below do not belong in the same table.")
    print("\nrho is rho(-score, pChEMBL): HIGHER means better agreement.")
    print("Vinardo rescores the IDENTICAL Vina poses; this is not Vinardo docking.")

    rows: list[dict] = []
    incomplete: list[str] = []
    for series_id in manifest.get("docking_selection", []):
        path = DATA / "series" / f"{series_id}.json"
        if not path.is_file():
            incomplete.append(f"{series_id} (no corpus file)")
            continue
        series = json.loads(path.read_text(encoding="utf-8"))
        if series["schema_version"] != manifest["schema_version"]:
            raise SystemExit(
                f"{series_id} was built under schema {series['schema_version']} and the "
                f"manifest says {manifest['schema_version']}. Rebuild the corpus, or the "
                "numbers describe two different curations."
            )
        row = series_row(series, load_runs(series_id), presence)
        if row is None:
            incomplete.append(series_id)
        else:
            rows.append(row)

    if incomplete:
        print(f"\nINCOMPLETE, and therefore not reported ({len(incomplete)}):")
        for series_id in incomplete:
            print(f"  {series_id}")
    if not rows:
        print("\nNothing complete yet. Run rank_power.py --all.")
        return 0

    print(f"\n{'series':30s} {'n':>3s} {'eff':>4s} {'span':>5s} {'VINA':>6s} {'VNRD':>6s} "
          f"{'repeat':>6s} {'swap':>5s} {'floor':>6s} {'heavy':>6s} {'MW':>6s} {'cLogP':>6s}")
    for row in sorted(rows, key=lambda r: r["series_id"]):
        print(
            f"{row['series_id']:30s} {row['n']:>3d} {row['effective_n_potency']:>4d} "
            f"{row['span']:>5.2f} {_fmt(row['rho_vina'])} {_fmt(row['rho_rescore'])} "
            f"{_fmt(row['rho_repeatability'])} "
            f"{_swap(row):>7s} "
            f"{_fmt(row['random_floor_sd'])} {_fmt(row['rho_heavy_atoms'])} "
            f"{_fmt(row['rho_mol_weight'])} {_fmt(row['rho_clogp'])}"
        )

    vina = [r["rho_vina"] for r in rows if r["rho_vina"] is not None]
    deltas = [
        r["rho_rescore"] - r["rho_vina"]
        for r in rows
        if r["rho_rescore"] is not None and r["rho_vina"] is not None
    ]
    beat_baseline = [
        r for r in rows
        if r["rho_vina"] is not None
        and r["rho_vina"] > max(
            (abs(r[f"rho_{n}"]) for n in BASELINES if r[f"rho_{n}"] is not None), default=-2
        )
    ]

    print(f"\nAGGREGATE over {len(rows)} complete series")
    if vina:
        # THE HEADLINE GETS AN INTERVAL TOO. The first version gave one to the
        # Vinardo delta and not to the number a reader looks at first, which
        # invites the median being read as a point estimate of a real effect.
        # Same series-level bootstrap, and a sign test beside it because the
        # median of 15 noisy series is exactly the statistic that looks
        # convincing without being.
        interval = bootstrap_interval(vina)
        span = f"  95% series bootstrap [{interval[0]:+.3f}, {interval[1]:+.3f}]" if interval else ""
        print(f"  median rho(-vina, pChEMBL)          {sorted(vina)[len(vina) // 2]:+.3f}{span}")
        positive = sum(1 for v in vina if v > 0)
        negative = sum(1 for v in vina if v < 0)
        print(f"  series with rho > 0                 {positive}/{positive + negative}"
              f"  (sign test p = {_sign_test(positive, positive + negative):.3f}, two-sided)")
    if deltas:
        median_delta = sorted(deltas)[len(deltas) // 2]
        interval = bootstrap_interval(deltas)
        span = f"  95% series bootstrap [{interval[0]:+.3f}, {interval[1]:+.3f}]" if interval else ""
        print(f"  median rho(Vinardo) - rho(Vina)     {median_delta:+.3f}{span}")
        print(f"  series where Vinardo ranks higher   {sum(1 for d in deltas if d > 0)}/{len(deltas)}")
    print(f"  series beating every trivial baseline {len(beat_baseline)}/{len(rows)}")

    _report_first_selection(rows, manifest)
    if not beat_baseline:
        print("    NONE. On this corpus the docking score does not order these")
        print("    compounds better than a physicochemical descriptor does, which")
        print("    is the result -- not a reason to look for a better statistic.")

    print("\n  'repeat' is SEARCH REPEATABILITY, not a noise ceiling: how")
    print("  consistently the search orders the same ligands under this")
    print("  protocol. The oracle's own reproducibility is unmeasurable here,")
    print("  because ChEMBL carries no per-row uncertainty.")
    print("  'floor' is the SD of rho under a random ranking, 1/sqrt(n-1).")
    print("  'eff' is the DISTINCT potency count: a rho over 14 ligands tied at")
    print("  four values is driven by four points.")

    if presence:
        absent = [r for r in rows if r.get("rho_vina_absent_only") is not None]
        buckets: dict[str, int] = {}
        for row in rows:
            for verdict, count in (row.get("presence") or {}).items():
                buckets[verdict] = buckets.get(verdict, 0) + count
        print("\nLEAKAGE BOUND")
        for verdict in sorted(buckets):
            print(f"  {verdict:11s} {buckets[verdict]}")
        if absent:
            values = [r["rho_vina_absent_only"] for r in absent]
            print(f"  median rho over ABSENT-only subsets {sorted(values)[len(values) // 2]:+.3f} "
                  f"({len(absent)} series)")
        unchecked = buckets.get("NOT_LOOKED_UP", 0)
        if unchecked:
            print(f"  {unchecked} compound(s) were never looked up, so the arms below")
            print("  are NOT a leakage split -- run chembl_corpus.py --presence-only.")
            print("  'Not checked' is not 'not in the PDB', and reporting the")
            print("  second on evidence for the first is what this line prevents.")
        elif not buckets.get("PRESENT"):
            print("  The split could not discriminate: every compound was checked")
            print("  and NONE has an exact PDB chemical-component match, so the two")
            print("  arms are the same numbers. That is a statement about leakage")
            print("  being minimal, not about the split being informative.")
        print("  ABSENT is a SUFFICIENT exclusion from PDBbind under exact-InChIKey")
        print("  identity -- a MINIMAL bound, not a leakage-free claim. PRESENT")
        print("  implies nothing: a compound can be in the PDB bound to a protein")
        print("  PDBbind never included.")
    else:
        print("\nLEAKAGE BOUND not resolved. Run chembl_corpus.py --presence.")

    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
