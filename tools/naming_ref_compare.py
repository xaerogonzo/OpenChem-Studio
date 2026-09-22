"""Name the same structures with two versions of the engine and check the difference against a manifest.

    python tools/naming_ref_compare.py --base fbebdb3                       # working tree vs a ref
    python tools/naming_ref_compare.py --base fbebdb3 --manifest benchmarks/naming/stages/manifests/W1.toml
    python tools/naming_ref_compare.py --base fbebdb3 --sets r8,mc --out compare.json

**WHY IT EXISTS.** Naming round 7 found its two late defects only because a check of a DIFFERENT SHAPE than its
corpora finally ran, and it ran after the fresh set was scored. This is that check made routine: every stage ends by
naming the panels and the salt panel with the base engine and the working tree and comparing them, BEFORE the suites are
read, because a green 3,000-test suite says nothing about whether a name on a panel moved.

**THE FIREWALL IS THE MANIFEST.** A stage lists the rows it EXPECTS to change and why. Every other row must not move:

    MUST_CHANGE               the name changes, for a stated rule and layer, optionally to a stated name
    MUST_STAY                 the name does not change (listed only to say so out loud; UNLISTED is also MUST_STAY)
    STRUCTURALLY_EQUIVALENT   the name may change if it still round-trips to the same structure

A change that is not listed is a violation, a MUST_CHANGE that did not happen is a violation, and a row that round-tripped
before and does not now is a violation that no manifest entry can excuse. A row that changes for a DIFFERENT reason than
its entry states cannot satisfy it: the entry carries `reason_rule_id`, `expected_layer` and, where known, the name.

**WHAT IT NAMES.** The round-7 panel (`r7:`), the round-8 addendum panel (`r8:`), the multicomponent/salt panel (`mc:`)
and the TUNING populations (`pop:<key>:<label>`, through the registry, so a frozen population cannot be reached). The
structures come from the working tree for BOTH sides, so the row set is identical by construction.

**TOOLCHAIN CONTRACT.** The report records Python, RDKit, OPSIN and Java versions, both commit SHAs, both `src` tree
hashes and whether the working tree is dirty (with a hash of the uncommitted `src` diff), so a difference is never
attributed to source when it is the toolchain.

The base engine is `git archive <ref> src`, run in a subprocess with `PYTHONPATH` at the extracted tree, so no import
state leaks between the two sides.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmarks" / "naming"
SETS = ("r7", "r8", "mc", "pop")
MUST_CHANGE, MUST_STAY, EQUIVALENT = "MUST_CHANGE", "MUST_STAY", "STRUCTURALLY_EQUIVALENT"
EXPECTATIONS = {MUST_CHANGE, MUST_STAY, EQUIVALENT}


# ---------------------------------------------------------------- the pure comparison (unit-tested)
def load_manifest(path: Path | None) -> dict[str, dict]:
    """`{row id: entry}`. A MUST_CHANGE entry must say WHY and WHERE, or it cannot excuse a change."""
    if path is None:
        return {}
    entries = tomllib.loads(path.read_text(encoding="utf-8")).get("expect", [])
    manifest: dict[str, dict] = {}
    for entry in entries:
        if entry["id"] in manifest:
            raise ValueError(f"duplicate manifest entry for {entry['id']}")
        if entry["expect"] not in EXPECTATIONS:
            raise ValueError(f"{entry['id']}: unknown expectation {entry['expect']!r}")
        if entry["expect"] == MUST_CHANGE and not (
            entry.get("reason_rule_id", "").strip() and entry.get("expected_layer", "").strip()
        ):
            raise ValueError(f"{entry['id']}: a MUST_CHANGE entry names its reason_rule_id and expected_layer")
        manifest[entry["id"]] = entry
    return manifest


def evaluate(
    base: dict[str, str],
    head: dict[str, str],
    base_ok: dict[str, bool],
    head_ok: dict[str, bool],
    manifest: dict[str, dict],
) -> tuple[list[dict], list[str]]:
    """Classify every changed row and list the violations.

    `base_ok` / `head_ok` say whether a name round-trips to its structure; they are consulted ONLY for rows
    whose name changed (an unchanged name has an unchanged round-trip), so the caller need not compute the rest.
    """
    changed: list[dict] = []
    violations: list[str] = []
    for row_id in sorted(set(base) | set(head)):
        if row_id not in base or row_id not in head:
            violations.append(f"ROW_SET_DIFFERS {row_id}: named by only one side")
            continue
        entry = manifest.get(row_id)
        moved = base[row_id] != head[row_id]
        if not moved:
            if entry and entry["expect"] == MUST_CHANGE:
                violations.append(f"EXPECTED_CHANGE_MISSING {row_id}: still {head[row_id]!r} ({entry['reason_rule_id']})")
            continue
        record = {
            "id": row_id, "base": base[row_id], "head": head[row_id],
            "base_roundtrips": base_ok.get(row_id), "head_roundtrips": head_ok.get(row_id),
            "expectation": entry["expect"] if entry else "UNLISTED",
        }
        changed.append(record)
        if base_ok.get(row_id) and not head_ok.get(row_id):
            violations.append(f"STRUCTURAL_REGRESSION {row_id}: {base[row_id]!r} round-tripped, {head[row_id]!r} does not")
        if entry is None:
            violations.append(f"UNEXPECTED_CHANGE {row_id}: {base[row_id]!r} -> {head[row_id]!r}")
        elif entry["expect"] == MUST_STAY:
            violations.append(f"MUST_STAY_MOVED {row_id}: {base[row_id]!r} -> {head[row_id]!r}")
        elif entry["expect"] == MUST_CHANGE:
            want = entry.get("expected_name")
            if want and head[row_id] != want:
                violations.append(
                    f"WRONG_CHANGE_TARGET {row_id}: expected {want!r}, got {head[row_id]!r} ({entry['reason_rule_id']})"
                )
        elif entry["expect"] == EQUIVALENT and not head_ok.get(row_id):
            violations.append(f"EQUIVALENCE_LOST {row_id}: {head[row_id]!r} does not round-trip")
    return changed, violations


# ---------------------------------------------------------------- the two engines
def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _extract_src(ref: str, into: Path) -> Path:
    """`git archive <ref> src` into a temp dir; the tarball is read in memory, never written to the repo."""
    blob = subprocess.run(["git", "archive", ref, "src"], cwd=ROOT, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        tar.extractall(into, filter="data")
    return into / "src"


def _worker(src: Path, items: list[tuple[str, str]], out_file: Path) -> None:
    """Run the naming in a fresh interpreter whose import path starts at `src`, so no state leaks between sides."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    payload = json.dumps(items)
    done = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker", str(out_file)],
        input=payload, capture_output=True, text=True, encoding="utf-8", env=env, cwd=tempfile.gettempdir(),
    )
    if done.returncode != 0 or not out_file.exists():
        raise SystemExit(f"the worker for {src} failed ({done.returncode}):\n{done.stderr[-1500:]}")


# A row-timeout ceiling, mirroring naming_stage_artifact.py's ROW_TIMEOUT_SECONDS exactly (this tool had NO
# such protection until it hung on a large fused polycyclic aromatic during round 9's RC checkpoint -- the
# same coronene-shaped decompose_ring_system hang naming_stage_artifact.py's own timeout was built for,
# measured via py-spy: stuck in vb_decompose.py's decompose_ring_system with no way out). A thread cannot be
# forcibly stopped in CPython, but a child PROCESS can be killed outright, so each row is named in a process
# of its own and the parent restarts a hung one rather than waiting on it.
ROW_TIMEOUT_SECONDS = 120
WORKER_STARTUP_TIMEOUT_SECONDS = 60


def _row_namer(in_queue, out_queue, ready) -> None:
    """Name one SMILES at a time, in a process of its own (see ROW_TIMEOUT_SECONDS above)."""
    from rdkit import RDLogger

    RDLogger.DisableLog("rdApp.*")
    from openchem.vendor.iupac_namer.engine import name_smiles

    ready.set()  # imports are done; the parent's per-row clock may start now
    while True:
        smiles = in_queue.get()
        if smiles is None:
            return
        try:
            out_queue.put((str(name_smiles(smiles)), None))
        except Exception as exc:  # noqa: BLE001
            out_queue.put((None, f"{type(exc).__name__}: {exc}"))


def _name_all_rows(items: list[tuple[str, str]]) -> dict[str, str]:
    """Name every (row_id, smiles) pair with a fresh worker process, restarting it on a per-row timeout or
    an unexpected exit -- the same persistent-worker-with-restart shape as naming_stage_artifact.py's
    _name_rows, kept separate here because this tool's own worker needs no hypothesis-tracking."""
    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    in_queue: mp.Queue = ctx.Queue()
    out_queue: mp.Queue = ctx.Queue()
    ready = ctx.Event()

    def spawn():
        ready.clear()
        proc = ctx.Process(target=_row_namer, args=(in_queue, out_queue, ready), daemon=True)
        proc.start()
        if not ready.wait(WORKER_STARTUP_TIMEOUT_SECONDS):
            proc.terminate()
            proc.join()
            raise SystemExit("a naming_ref_compare row-worker never finished importing within "
                              f"{WORKER_STARTUP_TIMEOUT_SECONDS}s")
        return proc

    names: dict[str, str] = {}
    proc = spawn()
    try:
        for row_id, smiles in items:
            in_queue.put(smiles)
            try:
                name, error = out_queue.get(timeout=ROW_TIMEOUT_SECONDS)
            except Exception:  # noqa: BLE001 - queue.Empty on timeout, or a broken pipe if the worker died
                proc.terminate()
                proc.join()
                names[row_id] = f"ERROR TimeoutError: exceeded {ROW_TIMEOUT_SECONDS}s"
                proc = spawn()
                continue
            names[row_id] = name if error is None else f"ERROR {error[:100]}"
    finally:
        in_queue.put(None)
        proc.join(timeout=5)
        if proc.is_alive():
            proc.terminate()
    return names


def _run_worker(out_file: str) -> None:
    import openchem  # noqa: F401  (which one is decided by PYTHONPATH; recorded below)

    items = json.loads(sys.stdin.read())
    names: dict[str, str] = {"__openchem__": str(Path(openchem.__file__).resolve())}
    names.update(_name_all_rows(items))
    Path(out_file).write_text(json.dumps(names), encoding="utf-8")


# ---------------------------------------------------------------- the structure sets
def collect(sets: set[str]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if "r7" in sets:
        for r in tomllib.loads((BENCH / "charged_panel.toml").read_text(encoding="utf-8"))["row"]:
            items.append((f"r7:{r['id']}", r["smiles"]))
    if "r8" in sets:
        for r in tomllib.loads((BENCH / "charged_panel_r8.toml").read_text(encoding="utf-8"))["row"]:
            items.append((f"r8:{r['id']}", r["smiles"]))
    if "mc" in sets:
        for r in tomllib.loads((ROOT / "tests/fixtures/multicomponent_panel.toml").read_text(encoding="utf-8"))["row"]:
            items.append((f"mc:{r['id']}", r["smiles"]))
    if "pop" in sets:
        sys.path.insert(0, str(ROOT / "tools"))
        import naming_populations as registry

        for population in registry.tuning():
            for row in registry.load(population.key):
                items.append((f"pop:{population.key}:{row['label']}", row["smiles"]))
    return items


def toolchain(base_ref: str) -> dict:
    import rdkit

    diff = subprocess.run(["git", "diff", "HEAD", "--", "src"], cwd=ROOT, capture_output=True).stdout
    java = "ABSENT"
    if shutil.which("java"):
        done = subprocess.run(["java", "-version"], capture_output=True, text=True)
        java = ((done.stderr or done.stdout).splitlines() or ["unknown"])[0].strip()
    opsin = "unknown"
    try:
        import py2opsin

        jars = list(Path(py2opsin.__file__).parent.rglob("*.jar"))
        opsin = jars[0].name if jars else "unknown"
    except Exception:  # noqa: BLE001
        pass
    return {
        "python": sys.version.split()[0], "rdkit": rdkit.__version__, "opsin": opsin, "java": java,
        "base_ref": base_ref, "base_sha": _git("rev-parse", base_ref), "base_src_tree": _git("rev-parse", f"{base_ref}:src"),
        "head_sha": _git("rev-parse", "HEAD"), "head_src_tree": _git("rev-parse", "HEAD:src"),
        "working_tree_dirty": bool(_git("status", "--porcelain", "--", "src")),
        "working_tree_src_diff_sha256": hashlib.sha256(diff).hexdigest(),
    }


def _roundtrips(names: dict[str, str], smiles: dict[str, str], ids: list[str]) -> dict[str, bool]:
    sys.path.insert(0, str(ROOT / "src"))
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    from openchem.chem import naming_providers as providers

    ok: dict[str, bool] = {}
    for row_id in ids:
        name = names[row_id]
        ok[row_id] = (not name.startswith("ERROR")) and (
            providers.verify_name_round_trip(name, Chem.MolFromSmiles(smiles[row_id])) is providers.RoundTrip.MATCH
        )
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--worker", metavar="OUT_FILE", help=argparse.SUPPRESS)
    parser.add_argument("--base", help="the git ref whose engine is the 'before'")
    parser.add_argument("--sets", default=",".join(SETS), help=f"comma-separated subset of {SETS}")
    parser.add_argument("--manifest", type=Path, help="the stage's expected-change manifest (TOML)")
    parser.add_argument("--out", type=Path, help="write the full JSON report here")
    args = parser.parse_args()
    if args.worker:
        _run_worker(args.worker)
        return 0
    if not args.base:
        parser.error("--base is required")

    sets = {s.strip() for s in args.sets.split(",") if s.strip()}
    unknown = sets - set(SETS)
    if unknown:
        parser.error(f"unknown set(s) {sorted(unknown)}")
    manifest = load_manifest(args.manifest)
    items = collect(sets)
    smiles = dict(items)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        base_src = _extract_src(args.base, tmpdir)
        base_file, head_file = tmpdir / "base.json", tmpdir / "head.json"
        _worker(base_src, items, base_file)
        _worker(ROOT / "src", items, head_file)
        base = json.loads(base_file.read_text(encoding="utf-8"))
        head = json.loads(head_file.read_text(encoding="utf-8"))
    engines = {"base": base.pop("__openchem__"), "head": head.pop("__openchem__")}
    if Path(engines["base"]).parents[1] == Path(engines["head"]).parents[1]:
        raise SystemExit(f"both sides imported the same engine ({engines['base']}); the comparison would be vacuous")

    moved = [i for i in base if base[i] != head.get(i)]
    if moved and shutil.which("java") is None:
        raise SystemExit("java is not on PATH: the round-trip check of the changed names needs it. Refusing.")
    base_ok = _roundtrips(base, smiles, moved) if moved else {}
    head_ok = _roundtrips(head, smiles, moved) if moved else {}
    changed, violations = evaluate(base, head, base_ok, head_ok, manifest)

    report = {"toolchain": toolchain(args.base), "engines": engines, "sets": sorted(sets), "rows": len(items),
              "changed": changed, "violations": violations}
    print(f"base {args.base} ({report['toolchain']['base_sha'][:7]}, src {report['toolchain']['base_src_tree'][:7]})  vs  "
          f"working tree ({report['toolchain']['head_sha'][:7]}{' DIRTY' if report['toolchain']['working_tree_dirty'] else ''})")
    print(f"{len(items)} structures over {sorted(sets)}: {len(changed)} names changed")
    for record in changed:
        print(f"  [{record['expectation']}] {record['id']}\n      was: {record['base']}\n      now: {record['head']}")
    print(f"violations: {len(violations)}")
    for line in violations:
        print(f"  {line}")
    if args.out:
        args.out.write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(f"-> {args.out}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
