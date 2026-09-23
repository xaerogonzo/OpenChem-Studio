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
    heldout_v4    heldout4.json    40  USED for tuning since naming round 8
    heldout_v5    heldout5.json    40  USED for tuning since naming round 9
    heldout_v6                     40  evaluation only -- `--final-evaluation`

Which is which lives in `benchmarks/naming/populations.toml`, read through
`tools/naming_populations.py`; this tool no longer carries its own list.
`heldout_v6` was drawn and frozen before any round-9 diagnosis, taking the
place `heldout_v5` held in round 8; v5 was scored once, at round 8's final
evaluation, and is a tuning population from round 9 on. (More than one
population may be frozen at once from round 9: the Blue Book's held-out half
joins `heldout_v6`, and every guard below is per frozen population.) A per-stage run cannot
load the frozen one: `load_population` raises before the file is opened, and
`tests/test_naming_heldout_lock.py` fails if any other tracked script so much
as names the file. The final evaluation reports it as AGGREGATES only -- no
per-row diff is printed for it even then, because a row read during the round
becomes a row fixed during the round.

**AGGREGATES ONLY MUST HOLD FOR WHAT IS COMMITTED, NOT JUST WHAT IS PRINTED.**
Through round 7 the final artifact carried a `records` list for the frozen
population, so `stages/r7-final.json` held every row's name and outcome while
the console showed counts. From round 8 the committed artifact stores a frozen
population's counts, its source hash and a reference to a SEALED sidecar
(`stages/sealed/<stage>.<key>.records.json`, hash-referenced); `seal_frozen_records`
does the split. The seal is a convention with a guard, not a lock: a file in a
repository can always be opened. What the guard does is make opening it a
deliberate act -- no tracked script may name the sealed directory but this one.
Every artifact also records the registry state (each population's status, and
for a frozen one its hash and row count as its META file states them, so the
frozen file itself is never touched).

Every count is printed with its denominator, so three populations can never
collapse into one percentage.

**Needs a bare `java` on PATH** for the round-trip classification; without it
py2opsin fails and every row would classify as unparsable. The tool refuses
to write an artifact in that state rather than recording a corpus-wide
regression that is really a missing JRE.

**EVERY ROW IS NAMED IN A WORKER PROCESS, NOT IN-PROCESS.** A coronene-class
fused ring system in the Blue Book harvest ran `decompose_ring_system` for
over 2.5 hours with no output before it was found stuck there by a `py-spy`
dump (round 9, `bb-ad1954622ac3`, measured 2026-09-21). Fusion is out of
scope for round 9's fixes, but the tool that MEASURES has to survive a row
like it regardless, because every later stage and the RC checkpoint's frozen
scoring would hang the same silent way. `ROW_TIMEOUT_SECONDS` bounds it.
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


SEALED = STAGES / "sealed"


def registry_state() -> dict[str, dict]:
    """Each population's status, and for a frozen one only what its META file says.

    Never opens the frozen file: the hash and the row count come from the freeze
    record, which is exactly the "locked hash/metadata object" the round-8 plan
    allows an artifact to carry.
    """
    state: dict[str, dict] = {}
    for population in registry.registry():
        entry: dict = {"status": population.status, "file": population.file}
        if population.frozen:
            meta_path = BENCH / population.file.replace(".json", ".meta.json")
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            entry["sha256"] = meta["heldout_sha256"]
            entry["rows"] = meta["rows"]
        state[population.key] = entry
    return state


def seal_frozen_records(artifact: dict, frozen_keys: set[str]) -> tuple[dict, dict[str, list]]:
    """Split an artifact into what may be committed and what is sealed.

    Returns `(public, sealed)`: `public` is a copy in which every population in
    `frozen_keys` has NO `records` -- only a `records_sealed` reference carrying
    the sidecar's relative path and the sha256 of its bytes -- and `sealed` maps
    each such population key to its records. The input is not modified, because
    the in-memory artifact is still what `--compare` reads.
    """
    import copy

    public = copy.deepcopy(artifact)
    sealed: dict[str, list] = {}
    for key in frozen_keys & set(public["populations"]):
        records = public["populations"][key].pop("records")
        sealed[key] = records
        body = json.dumps(records, indent=1).encode("utf-8")
        public["populations"][key]["records_sealed"] = {
            "file": f"sealed/{public['stage']}.{key}.records.json",
            "sha256": hashlib.sha256(body).hexdigest(),
        }
    return public, sealed


def _provenance(stage: str) -> dict:
    import rdkit

    return {
        "artifact_schema_version": SCHEMA_VERSION,
        "stage": stage,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "git_sha": _git("rev-parse", "HEAD"),
        # The engine's identity, independent of the commit: two artifacts with the same `src_tree` were
        # produced by byte-identical source, whatever else (benchmarks, tools, docs) differs between the
        # commits. It is what makes "R0 changed no src file, so the baseline is master" a checkable claim.
        "src_tree": _git("rev-parse", "HEAD:src"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "rdkit": rdkit.__version__,
        "opsin_jar": _opsin_version(),
        "java": _java_version(),
        "registry": registry_state(),
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


#: `bb-ad1954622ac3` (SMILES `c1cc2ccc3cc4ccc5ccc6ccc7cc8ccc1c1c2c3c2c4c5c6c7c2c81`, a
#: coronene-class fused ring system, 32 ring atoms) sent `decompose_ring_system`
#: into a combinatorial search that ran over 2.5 hours with zero output before
#: it was found stuck there by `py-spy dump` (measured 2026-09-21). Fusion is
#: already out of scope for round 9's fixes, but the MEASUREMENT tool still has
#: to survive a row like this one: every later stage, B2, B3 and the RC
#: checkpoint's frozen scoring would otherwise silently hang the same way, and
#: nothing about a hang looks different from "still working" from outside.
#: 120s is generous against every population that has ever run through this
#: tool in seconds; it exists to bound the rare pathological row, not to
#: pressure a legitimately slow one.
ROW_TIMEOUT_SECONDS = 120

#: A fresh worker pays for importing RDKit and the vendored engine before it
#: can pull its first row off the queue. That cost belongs to STARTUP, never
#: to a row's own budget -- charging it to the first row (or the row right
#: after a restart) would make a perfectly ordinary structure look like a
#: timeout. `ready` (below) is what keeps the two separate.
WORKER_STARTUP_TIMEOUT_SECONDS = 60


def _row_worker(in_queue, out_queue, ready) -> None:
    """Name one SMILES at a time, in a process of its own.

    A process boundary -- not a thread -- is what makes `ROW_TIMEOUT_SECONDS`
    enforceable: CPython cannot forcibly stop a runaway thread, but the
    parent CAN terminate this process outright and start a fresh one. The
    monkeypatch below installs once per worker lifetime, not once per row, so
    a restart costs one process spawn, not a per-row tax.

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

    eng._search_plans = spy
    ready.set()  # imports are done; the parent's per-row clock may start now
    try:
        while True:
            smiles = in_queue.get()
            if smiles is None:
                return
            captured.clear()
            try:
                name = name_smiles(smiles)
                out_queue.put((name, None, dict(captured[0]) if captured else {}))
            except Exception as exc:  # noqa: BLE001
                out_queue.put((None, f"{type(exc).__name__}: {exc}", {}))
    finally:
        eng._search_plans = original


def _name_rows(rows: list[dict]) -> list[dict]:
    """Name every row, and record the search shape alongside the name.

    Each row is named in a persistent worker process (`_row_worker`) rather
    than in-process, so a row that runs past `ROW_TIMEOUT_SECONDS` can be
    killed outright and the rest of the population still completes. The
    worker is reused across rows -- restarted only after a timeout or a
    crash -- so the per-row cost of the process boundary is one queue round
    trip, not one process spawn.
    """
    import multiprocessing as mp
    import queue as queue_mod

    ctx = mp.get_context("spawn")

    def spawn_worker():
        in_q, out_q = ctx.Queue(), ctx.Queue()
        ready = ctx.Event()
        proc = ctx.Process(target=_row_worker, args=(in_q, out_q, ready), daemon=True)
        proc.start()
        if not ready.wait(timeout=WORKER_STARTUP_TIMEOUT_SECONDS):
            kill(proc)
            raise RuntimeError(
                f"naming worker did not finish starting within "
                f"{WORKER_STARTUP_TIMEOUT_SECONDS}s (import failure?)"
            )
        return proc, in_q, out_q

    def kill(proc) -> None:
        proc.terminate()
        proc.join(timeout=10)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=10)

    proc, in_q, out_q = spawn_worker()
    out: list[dict] = []
    try:
        for index, row in enumerate(rows, start=1):
            started = time.perf_counter()
            in_q.put(row["smiles"])
            result = None
            while result is None and time.perf_counter() - started < ROW_TIMEOUT_SECONDS:
                remaining = ROW_TIMEOUT_SECONDS - (time.perf_counter() - started)
                try:
                    result = out_q.get(timeout=min(1.0, max(0.05, remaining)))
                except queue_mod.Empty:
                    if not proc.is_alive():
                        break  # crashed rather than hung -- don't wait out the rest of the budget
            if result is not None:
                name, error, trace = result
            else:
                elapsed = time.perf_counter() - started
                still_alive = proc.is_alive()
                error = (
                    f"TIMEOUT after {elapsed:.0f}s (row killed)"
                    if still_alive
                    else f"worker process died after {elapsed:.0f}s"
                )
                name, trace = None, {}
                if still_alive:
                    kill(proc)
                proc, in_q, out_q = spawn_worker()
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
            if index % 100 == 0 or index == len(rows):
                print(f"    ...{index}/{len(rows)} named", file=sys.stderr, flush=True)
    finally:
        try:
            in_q.put(None)
        except Exception:  # noqa: BLE001
            pass
        if proc.is_alive():
            proc.join(timeout=5)
            if proc.is_alive():
                kill(proc)
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

    import known_deviations

    rows = engine = pubchem = deviating = 0
    for record in named:
        mol = Chem.MolFromSmiles(record["smiles"])
        target = targets.get(Chem.MolToSmiles(mol)) if mol is not None else None
        if target is None:
            continue
        rows += 1
        # A name that carries a DECLARED legacy locant (known_deviations.toml) is reported as a known deviation and is NEVER an exact preferred match, however
        # it round-trips: OPSIN accepting a name does not make it preferred (naming round 8).
        if known_deviations.deviation_in(record["name"]):
            deviating += 1
        else:
            engine += record["name"] == target
        pubchem += record["pubchem_name"] == target
    return {"adjudicated_rows": rows, "engine": engine, "pubchem": pubchem, "known_deviation": deviating}


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
        if "records" not in before:
            lines.append(f"[{key}] the previous artifact sealed its records; not compared row by row")
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


def frozen_impact(against_stage: str) -> dict[str, tuple[int, int]]:
    """How many FROZEN rows the working tree names differently from a sealed final evaluation.

    Returns `{population key: (rows, changed)}` and nothing else -- no label, no name, no outcome
    leaves this function, so asking the question does not un-blind the set. It exists because
    `naming_ref_compare.py` reaches the TUNING populations only: a change to a shared path can move a
    frozen row that no tuning row exposes, and "the fix is narrow" is not a measurement. If every count
    is 0 the previous evaluation's score stands and the frozen set is NOT re-scored (the rule is
    scored ONCE per round only when something moved); if any count is above 0, the round scores it
    once, at the end, the ordinary way.

    Names only -- no OPSIN, so no JRE is needed. A row absent from the sidecar counts as changed.
    """
    frozen = {key for key, _f, is_frozen in POPULATIONS if is_frozen}
    impact: dict[str, tuple[int, int]] = {}
    for key in active_populations(final_evaluation=True):
        if key not in frozen:
            continue
        sidecar = SEALED / f"{against_stage}.{key}.records.json"
        if not sidecar.exists():
            raise SystemExit(f"no sealed final evaluation of {key} at stage {against_stage!r}")
        was = {r["label"]: r["name"] for r in json.loads(sidecar.read_text(encoding="utf-8"))}
        _filename, rows = load_population(key, final_evaluation=True)
        changed = sum(1 for r in _name_rows(rows) if was.get(r["label"]) != r["name"])
        impact[key] = (len(rows), changed)
    return impact


def score_success() -> set[str]:
    import score

    return set(score.SUCCESS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a naming stage artifact.")
    parser.add_argument("--stage", help="stage name, e.g. baseline (required unless --frozen-impact)")
    parser.add_argument(
        "--frozen-impact",
        metavar="SEALED_STAGE",
        help="BLIND check: compare the working tree's names for the frozen populations against this "
             "sealed final-evaluation stage and print only unchanged / changed_count per population. "
             "Writes nothing. Exit status 3 if anything moved.",
    )
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

    if args.frozen_impact:
        impact = frozen_impact(args.frozen_impact)
        for key, (n, changed) in impact.items():
            print(f"[{key}] " + (f"unchanged ({n} rows)" if not changed else f"changed_count={changed} of {n}"))
        moved = any(changed for _n, changed in impact.values())
        print("FROZEN IMPACT: " + ("changed -- score the frozen set once at the end of the round" if moved
                                   else "unchanged -- the previous evaluation's score stands"))
        raise SystemExit(3 if moved else 0)
    if not args.stage:
        parser.error("--stage is required unless --frozen-impact is given")

    artifact = build(
        args.stage,
        allow_no_java=args.allow_no_java,
        final_evaluation=args.final_evaluation,
    )
    STAGES.mkdir(parents=True, exist_ok=True)
    out = STAGES / f"{args.stage}.json"
    frozen = {key for key, _f, is_frozen in POPULATIONS if is_frozen}
    public, sealed = seal_frozen_records(artifact, frozen)
    out.write_text(json.dumps(public, indent=1), encoding="utf-8")
    for key, records in sealed.items():
        SEALED.mkdir(parents=True, exist_ok=True)
        (SEALED / f"{args.stage}.{key}.records.json").write_text(
            json.dumps(records, indent=1), encoding="utf-8"
        )

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
