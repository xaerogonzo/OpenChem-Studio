"""One machine-readable record per naming stage: what every row was named,
and enough provenance that a later difference can be attributed.

**WHY A COUNT IS NOT ENOUGH.** `benchmarks/naming` reports 187/187 correct,
and that total can hold while one molecule quietly swaps to a different
equivalent naming path -- a different parent, a different suffix, a different
numbering -- because "equivalent" is a success class. Naming round 3 changes
parent selection, PCG assignment, numbering and the retained-name policy, so
the question after every stage is not "is the total still 187" but **"which
names moved, and why"**. That needs a per-row record taken before the stage
and compared after it.

**WHY THE TOOLCHAIN IS IN HERE.** Round 2 spent real time on a Windows shard
crash that turned out not to be attributable, and the standing lesson is that
a difference blamed on "the code" is sometimes a library. So an artifact
carries the git SHA, the branch, and the versions of Python, RDKit, OPSIN and
Java. Without the OPSIN version in particular, a change in the *oracle* would
read as a change in the engine.

**WHY THE TRACE SAYS WHERE A CANDIDATE CAME FROM.** The central finding of
this round is that four defects which all looked like "the comparator picked
wrong" were in four different layers, and three of them were candidates that
**never existed** rather than candidates that lost. So the winner trace
records the parent hypothesis and the plan count alongside the winner: "the
candidate lost" and "the candidate was never proposed" must be
distinguishable from the artifact alone.

## Use

    python tools/naming_stage_artifact.py --stage baseline
    python tools/naming_stage_artifact.py --stage 2-budget \
        --compare benchmarks/naming/stages/baseline.json

Written to `benchmarks/naming/stages/<stage>.json`. `--compare` prints
every row whose name changed, which is the review a stage's commit message
quotes.

## Populations, and the one that is locked

    regression    corpus.json     187  tuning, adjudication, per-stage invariant
    heldout       heldout.json     40  USED for tuning since naming round 4
    heldout_v2    heldout2.json    40  USED for tuning since naming round 5
    heldout_v3    heldout3.json    40  USED for tuning since naming round 7
    heldout_v4                     40  evaluation only -- `--final-evaluation`

Which is which lives in `benchmarks/naming/populations.toml`, read through
`tools/naming_populations.py`; this tool no longer carries its own list.
`heldout_v4` was drawn and frozen before any round-7 diagnosis, taking the
place `heldout_v3` held in round 5; v3 was scored once, at round 5's final
evaluation, and is a tuning population from round 7 on. A per-stage run cannot
load the frozen one: `load_population` raises before the file is opened, and
`tests/test_naming_heldout_lock.py` fails if any other tracked script so much
as names the file. The final evaluation reports it as AGGREGATES only -- no
per-row diff is printed for it even then, because a row read during the round
becomes a row fixed during the round.

Every count is printed with its denominator, so three populations can never
collapse into one percentage.

**Needs a bare `java` on PATH** for the round-trip classification; without it
py2opsin fails and every row would classify as unparsable. The tool refuses
to write an artifact in that state rather than recording a corpus-wide
regression that is really a missing JRE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmarks" / "naming"
STAGES = BENCH / "stages"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(BENCH))

SCHEMA_VERSION = 2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naming_populations as registry  # noqa: E402

#: (key, file, final_evaluation_only), from benchmarks/naming/populations.toml,
#: which is the ONLY place that says which populations exist and which are
#: frozen. Order is report order.
POPULATIONS: tuple[tuple[str, str, bool], ...] = tuple(
    (p.key, p.file, p.frozen) for p in registry.registry()
)

#: Re-exported: the lock test and callers catch it by this name.
FrozenPopulation = registry.FrozenPopulation


def load_population(key: str, *, final_evaluation: bool = False) -> tuple[str, list[dict]]:
    """The rows of one population, refusing a frozen one unless this is the final run.

    The refusal happens BEFORE the file is opened, so a mistaken call cannot
    even put the rows in memory.
    """
    rows = registry.load(key, final_evaluation=final_evaluation)
    return registry.get(key).file, rows


def active_populations(*, final_evaluation: bool = False) -> list[str]:
    return registry.keys(final_evaluation=final_evaluation)


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _opsin_version() -> str:
    """Read it off the bundled jar's filename, which is where it lives."""
    try:
        import py2opsin

        jars = list(Path(py2opsin.__file__).parent.rglob("*.jar"))
        if jars:
            return jars[0].name
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def _java_version() -> str:
    if shutil.which("java") is None:
        return "ABSENT"
    try:
        done = subprocess.run(
            ["java", "-version"], capture_output=True, text=True, timeout=30
        )
        return (done.stderr or done.stdout).splitlines()[0].strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _provenance(stage: str) -> dict:
    import rdkit

    return {
        "artifact_schema_version": SCHEMA_VERSION,
        "stage": stage,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "git_sha": _git("rev-parse", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "rdkit": rdkit.__version__,
        "opsin_jar": _opsin_version(),
        "java": _java_version(),
        # Filled in by the stages that introduce them; declared here from the
        # start so an early artifact and a late one have the same field
        # semantics rather than differing by absence.
        "comparator_spec_id": _comparator_spec_id(),
        "strategy_id": "IUPACCanonical(default)",
        "linter_spec_id": None,
    }


def _comparator_spec_id() -> str:
    from openchem.vendor.iupac_namer.strategy import IUPACCanonical

    return IUPACCanonical().comparator_spec_id()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _name_rows(rows: list[dict]) -> list[dict]:
    """Name every row, and record the search shape alongside the name.

    `_search_plans` is instrumented rather than `score_plan`: it carries
    `output_form`, so a top-level parent hypothesis can be told apart from
    the naming of a substituent. Instrumenting the score function instead
    conflates them, which is how the silicon defect was first misdiagnosed
    as a ranking problem when it is a budget one.
    """
    from openchem.vendor.iupac_namer import engine as eng
    from openchem.vendor.iupac_namer import name_smiles
    from openchem.vendor.iupac_namer.types import (
        OutputForm,
        RetainedPlan,
        SubstitutivePlan,
    )

    original = eng._search_plans
    captured: list[dict] = []

    def hypothesis(plan) -> str:
        if isinstance(plan, RetainedPlan):
            return f"retained:{plan.match.name}"
        if not isinstance(plan, SubstitutivePlan):
            return type(plan).__name__
        candidate = plan.named_parent.candidate
        element = getattr(candidate, "element", None) or "-"
        return (
            f"{candidate.type}/len={candidate.length}/elem={element}"
            f"/pcg={plan.pcg_type or '-'}/n_pcg={len(plan.pcg_instances or ())}"
        )

    def spy(perception, mol, output_form, free_valence, query, strategy, session):
        ranked = original(
            perception, mol, output_form, free_valence, query, strategy, session
        )
        if output_form == OutputForm.STANDALONE and not captured:
            captured.append(
                {
                    "plans": len(ranked),
                    # Distinct parent hypotheses, which is the number that
                    # matters: 20 plans over 2 hypotheses is a starved search
                    # even though the cap was reached.
                    "hypotheses": sorted({hypothesis(p) for _s, _q, p in ranked}),
                    "winner": hypothesis(ranked[-1][2]) if ranked else None,
                }
            )
        return ranked

    out: list[dict] = []
    eng._search_plans = spy
    try:
        for row in rows:
            captured.clear()
            started = time.perf_counter()
            error = None
            try:
                name = name_smiles(row["smiles"])
            except Exception as exc:  # noqa: BLE001
                name, error = None, f"{type(exc).__name__}: {exc}"
            trace = captured[0] if captured else {}
            out.append(
                {
                    "label": row["label"],
                    "category": row.get("category"),
                    "smiles": row["smiles"],
                    "pubchem_name": row.get("pubchem_name"),
                    "name": name,
                    "error": error,
                    "seconds": round(time.perf_counter() - started, 3),
                    "top_level_plans": trace.get("plans"),
                    "top_level_hypotheses": trace.get("hypotheses"),
                    "winning_hypothesis": trace.get("winner"),
                }
            )
    finally:
        eng._search_plans = original
    return out


def _classify(rows: list[dict], named: list[dict]) -> None:
    """Attach the round-trip class, using the benchmark's own classifier.

    Reusing `score.classify` rather than reimplementing it is the point: two
    definitions of "correct" would drift, and the one that matters is the one
    the benchmark gates on.
    """
    import score

    for row, record in zip(rows, named, strict=True):
        record["outcome"] = score.classify(row, record["name"])


def _adjudicated_targets() -> dict[str, str]:
    """{canonical SMILES: adjudicated preferred name} for every row of
    `adjudication.toml` whose preferred name is settled. Keyed by canonical
    SMILES so a row matches however either file happens to write it."""
    import tomllib

    from rdkit import Chem

    path = BENCH / "adjudication.toml"
    if not path.exists():
        return {}
    targets: dict[str, str] = {}
    for row in tomllib.loads(path.read_text(encoding="utf-8")).get("row", []):
        preferred = row.get("preferred_name")
        mol = Chem.MolFromSmiles(row.get("smiles", "")) if preferred else None
        if mol is not None:
            targets[Chem.MolToSmiles(mol)] = preferred
    return targets


def _preferred_scores(named: list[dict], targets: dict[str, str]) -> dict:
    """The two agreements a PubChem-verbatim count cannot show: the engine
    against the adjudicated preferred name, and PubChem against it (round 4,
    A13). Counted over the rows that HAVE a settled target, which is the
    denominator; an evaluation-only population has none by construction."""
    from rdkit import Chem

    rows = engine = pubchem = 0
    for record in named:
        mol = Chem.MolFromSmiles(record["smiles"])
        target = targets.get(Chem.MolToSmiles(mol)) if mol is not None else None
        if target is None:
            continue
        rows += 1
        engine += record["name"] == target
        pubchem += record["pubchem_name"] == target
    return {"adjudicated_rows": rows, "engine": engine, "pubchem": pubchem}


def build(stage: str, *, allow_no_java: bool, final_evaluation: bool = False) -> dict:
    provenance = _provenance(stage)
    if provenance["java"] == "ABSENT" and not allow_no_java:
        raise SystemExit(
            "No bare `java` on PATH, so every row would classify as unparsable "
            "and this artifact would record a corpus-wide regression that is "
            "really a missing JRE. Put the JRE on PATH, or pass "
            "--allow-no-java to record names WITHOUT round-trip classes."
        )

    provenance["final_evaluation"] = final_evaluation
    targets = _adjudicated_targets()
    populations = {}
    for key in active_populations(final_evaluation=final_evaluation):
        filename, rows = load_population(key, final_evaluation=final_evaluation)
        path = BENCH / filename
        named = _name_rows(rows)
        if provenance["java"] != "ABSENT":
            _classify(rows, named)
        counts: dict[str, int] = {}
        for record in named:
            outcome = record.get("outcome", "unclassified")
            counts[outcome] = counts.get(outcome, 0) + 1
        verbatim = sum(
            1
            for record in named
            if record["pubchem_name"] and record["name"] == record["pubchem_name"]
        )
        populations[key] = {
            "source_file": filename,
            "source_sha256": _digest(path),
            "rows": len(rows),
            "outcomes": counts,
            # NAMED FOR WHAT IT MEASURES. This is agreement with a second
            # engine's string, not a preferred-name score: PubChem's displayed
            # IUPAC Name is generated, not curated. The adjudicated count is a
            # separate field, added once adjudication exists.
            "pubchem_verbatim_exact": verbatim,
            "adjudicated_preferred_exact": _preferred_scores(named, targets),
            "records": named,
        }
    return {**provenance, "populations": populations}


def compare(previous: dict, current: dict) -> list[str]:
    lines: list[str] = []
    for key, now in current["populations"].items():
        before = previous.get("populations", {}).get(key)
        if before is None:
            lines.append(f"[{key}] not present in the previous artifact")
            continue
        was = {r["label"]: r for r in before["records"]}
        moved = 0
        winners_moved = 0
        # A frozen population is compared in AGGREGATE only; see the module
        # docstring. Its per-row lines are never printed.
        quiet = any(k == key and final for k, _f, final in POPULATIONS)
        for record in now["records"]:
            old = was.get(record["label"])
            if old is None:
                lines.append(f"[{key}] NEW ROW {record['label']}: {record['name']}")
                continue
            if old.get("winning_hypothesis") != record.get("winning_hypothesis"):
                winners_moved += 1
            if old["name"] != record["name"]:
                moved += 1
                if quiet:
                    continue
                lines.append(f"[{key}] {record['label']}")
                lines.append(f"    was: {old['name']}")
                lines.append(f"    now: {record['name']}")
                if old.get("outcome") != record.get("outcome"):
                    lines.append(
                        f"    outcome: {old.get('outcome')} -> {record.get('outcome')}"
                    )
                if old.get("winning_hypothesis") != record.get("winning_hypothesis"):
                    lines.append(
                        f"    winner: {old.get('winning_hypothesis')} "
                        f"-> {record.get('winning_hypothesis')}"
                    )
        # A row losing structural correctness is the invariant this round
        # holds, so it is reported separately from a name merely moving.
        regressed = [
            r["label"]
            for r in now["records"]
            if was.get(r["label"], {}).get("outcome") in score_success()
            and r.get("outcome") not in score_success()
        ]
        n = now["rows"]
        lines.append(
            f"[{key}] {moved}/{n} names changed; {winners_moved}/{n} winning "
            f"hypotheses changed; verbatim {before['pubchem_verbatim_exact']}/{n} -> "
            f"{now['pubchem_verbatim_exact']}/{n}; "
            f"STRUCTURALLY REGRESSED: "
            f"{(len(regressed) if quiet else regressed) or 'none'}"
        )
    return lines


def score_success() -> set[str]:
    import score

    return set(score.SUCCESS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a naming stage artifact.")
    parser.add_argument("--stage", required=True, help="stage name, e.g. baseline")
    parser.add_argument("--compare", help="a previous artifact to diff against")
    parser.add_argument(
        "--final-evaluation",
        action="store_true",
        help="also score the frozen evaluation-only population (end of round only)",
    )
    parser.add_argument(
        "--allow-no-java",
        action="store_true",
        help="record names without round-trip classes (diagnostics only)",
    )
    args = parser.parse_args()

    artifact = build(
        args.stage,
        allow_no_java=args.allow_no_java,
        final_evaluation=args.final_evaluation,
    )
    STAGES.mkdir(parents=True, exist_ok=True)
    out = STAGES / f"{args.stage}.json"
    out.write_text(json.dumps(artifact, indent=1), encoding="utf-8")

    print(f"stage {args.stage}  sha {artifact['git_sha'][:7]}"
          f"{' DIRTY' if artifact['git_dirty'] else ''}"
          f"  rdkit {artifact['rdkit']}  opsin {artifact['opsin_jar']}")
    for key, population in artifact["populations"].items():
        n = population["rows"]
        print(
            f"  {key:11s} verbatim={population['pubchem_verbatim_exact']:3d}/{n}  "
            + "  ".join(f"{k}={v}/{n}" for k, v in sorted(population["outcomes"].items()))
        )
        preferred = population["adjudicated_preferred_exact"]
        if preferred and preferred["adjudicated_rows"]:
            m = preferred["adjudicated_rows"]
            print(
                f"  {'':11s} preferred: engine={preferred['engine']}/{m}  "
                f"pubchem={preferred['pubchem']}/{m}  (rows with a settled target)"
            )
    print(f"-> {out}")

    if args.compare:
        previous = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        print()
        for line in compare(previous, artifact):
            print(line)


if __name__ == "__main__":
    main()
