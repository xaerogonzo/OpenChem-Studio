"""Is the stock protocol 2 searched with the stock protocol 1 searched with? A DIAGNOSTIC of saved records: it decides nothing and the verdicts of both protocols stand.

    python stock_identity.py [--planner-python PY --paroutes DIR]

Protocol 1 kept no copy of its InChI-key stock and recorded no checksum of it, so the two key files cannot be compared directly. This asks the question the other way round, from what each search RECORDED:

  * every leaf of every route the planner returned carries an `in_stock` flag, which is the stock's answer to a lookup. For each leaf SMILES recorded by BOTH protocols, the two flags are compared. No key is derived (an earlier attempt that derived InChI keys here disagreed with the planner's own flags on a few E-alkenes, against protocol 2's own stock too, so it measured the derivation and not the stock);
  * with `--planner-python` and `--paroutes`, `make_stock.py` is run again on the source stock and the result compared byte for byte with protocol 2's key file (the script has had one commit since it was written, and protocol 1's recorded `stock_n1.txt` checksum is the same as the source file's today).

What it can show: the two stocks gave the same answer for every molecule both searches looked up. What it cannot: that the two key files are byte-identical, or anything about the molecules only protocol 2 looked up (nobody can compare those).

Needs protocol 2's raw main-run records `artifacts_protocol2/results_r1.jsonl` (gunzip `results_r1.jsonl.gz` if only that is kept) and protocol 1's committed records.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def leaves(node: dict, out: list) -> None:
    """Every starting material of a route tree with the stock's flag for it."""
    reactions = [child for child in node.get("children") or [] if isinstance(child, dict) and child.get("type") == "reaction"]
    if not reactions:
        out.append((node["smiles"], node.get("in_stock")))
        return
    for child in reactions[0].get("children") or []:
        if isinstance(child, dict):
            leaves(child, out)


def flags(path: Path) -> tuple[dict[str, object], dict[str, tuple]]:
    """The flag recorded for each distinct leaf, and the leaves given two different flags in this one file."""
    opener = gzip.open if str(path).endswith(".gz") else open
    seen: dict[str, object] = {}
    inconsistent: dict[str, tuple] = {}
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            for tree in json.loads(line).get("routes", []):
                found: list = []
                leaves(tree, found)
                for smiles, flag in found:
                    if smiles in seen and seen[smiles] != flag:
                        inconsistent[smiles] = (seen[smiles], flag)
                    seen[smiles] = flag
    return seen, inconsistent


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--planner-python")
    parser.add_argument("--paroutes")
    args = parser.parse_args()

    protocol1: dict[str, object] = {}
    bad1: dict[str, tuple] = {}
    for name in ("results_r1.jsonl.gz", "results_r2.jsonl.gz", "results_r3.jsonl.gz"):
        seen, bad = flags(HERE / "artifacts" / name)
        protocol1.update(seen)
        bad1.update(bad)
    protocol2, bad2 = flags(HERE / "artifacts_protocol2" / "results_r1.jsonl")
    for name in ("results_r2.jsonl.gz", "results_r3.jsonl.gz"):
        seen, bad = flags(HERE / "artifacts_protocol2" / name)
        protocol2.update(seen)
        bad2.update(bad)

    common = sorted(set(protocol1) & set(protocol2))
    differ = [(s, protocol1[s], protocol2[s]) for s in common if protocol1[s] != protocol2[s]]
    only1 = set(protocol1) - set(protocol2)
    lines = [
        "STOCK IDENTITY, PROTOCOL 1 AGAINST PROTOCOL 2, FROM WHAT EACH SEARCH RECORDED (a diagnostic; decides nothing)",
        f"distinct leaves recorded: protocol 1 {len(protocol1)}, protocol 2 {len(protocol2)}, both {len(common)}",
        f"leaves recorded by both with the SAME in_stock flag: {len(common) - len(differ)} of {len(common)} "
        f"(in stock in both {sum(1 for s in common if protocol1[s] and protocol2[s])}, out of stock in both {sum(1 for s in common if not protocol1[s] and not protocol2[s])})",
        f"leaves recorded by both with a DIFFERENT flag: {len(differ)}",
        f"protocol 1 leaves protocol 2 never looked up: {len(only1)} ({sum(1 for s in only1 if protocol1[s])} in stock)",
        f"leaves given two different flags inside one protocol: protocol 1 {len(bad1)}, protocol 2 {len(bad2)}",
    ]
    lines += [f"   differs: {item}" for item in differ[:8]]

    if args.planner_python and args.paroutes:
        committed = HERE / "artifacts_protocol2" / "stock_n1_inchikeys.txt"
        with tempfile.TemporaryDirectory() as scratch:
            regenerated = Path(scratch) / "stock_regenerated.txt"
            done = subprocess.run([args.planner_python, str(HERE / "make_stock.py"), str(Path(args.paroutes) / "stock_n1.txt"), str(regenerated)], capture_output=True, text=True)
            if done.returncode != 0 or not regenerated.exists():
                lines.append(f"regeneration FAILED: {done.stderr.strip()[:200]}")
            else:
                same = md5(regenerated) == md5(committed)
                lines.append(f"make_stock.py run again on the source stock: MD5 {md5(regenerated)} against the committed key file's {md5(committed)}: {'IDENTICAL' if same else 'DIFFERENT'}")
    else:
        lines.append("regeneration not run (needs --planner-python and --paroutes)")

    text = "\n".join(lines)
    print(text)
    (HERE / "artifacts_protocol2" / "stock_identity.txt").write_text(text, encoding="utf-8")
    if differ or bad1 or bad2:
        sys.exit(1)


if __name__ == "__main__":
    main()
