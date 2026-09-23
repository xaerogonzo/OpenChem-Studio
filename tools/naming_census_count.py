"""Counts every `census_queries.toml` shape against `benchmarks/naming/census_sample.json`.

    python tools/naming_census_count.py

Each query's hit count is `hits / sample_size`, compared against `admissions_r9.toml`'s
`natural_frequency_min` (committed in R0, before this file or the census existed, so no count seen here
can move it). Prints wrong-molecule-independent NATURAL_FREQUENCY only -- REGRESSION_COVERAGE (from the
tuning populations) is a separate, never-combined measurement the admissions ledger reads elsewhere.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

from rdkit import Chem

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BENCH = ROOT / "benchmarks" / "naming"

CENSUS = BENCH / "census_sample.json"
QUERIES = BENCH / "census_queries.toml"
ADMISSIONS = BENCH / "admissions_r9.toml"


def large_fused_polycyclic_aromatic(mol: Chem.Mol) -> bool:
    """True if any set of FUSED (edge-sharing) SSSR rings, all-aromatic, spans 5 or more rings.

    Not expressible as a fixed-size SMARTS -- see census_queries.toml's own definition for this query.
    Fusion is edge-sharing (two rings sharing a bond, i.e. 2+ atoms), the same notion
    `ring_naming/vb_decompose.py` uses; a spiro junction (one shared atom) does not count as fusion here.
    """
    ring_info = mol.GetRingInfo()
    rings = [set(r) for r in ring_info.AtomRings()]
    aromatic_rings = [
        r for r in rings if all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in r)
    ]
    if len(aromatic_rings) < 5:
        return False
    # Union-find over ring indices, joined when two rings share 2+ atoms (an edge).
    parent = list(range(len(aromatic_rings)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(aromatic_rings)):
        for j in range(i + 1, len(aromatic_rings)):
            if len(aromatic_rings[i] & aromatic_rings[j]) >= 2:
                union(i, j)

    groups: dict[int, int] = {}
    for i in range(len(aromatic_rings)):
        root = find(i)
        groups[root] = groups.get(root, 0) + 1
    return max(groups.values(), default=0) >= 5


def multiparent_fusion_hub(mol: Chem.Mol) -> bool:
    """True if any ring is edge-fused to 3 or more OTHER rings.

    A proxy for the "multiparent fusion" shape (round 5's open list, e.g.
    "benzo[1,2-b:4,5-c']difuran", p. 234) -- naming a fused system with no
    single dominant component requires MULTIPARENT nomenclature. The true
    condition is about nomenclature seniority (no base component senior
    enough to be THE parent), which this predicate does not decide; a
    ring fused to 3+ others (a "hub", not a simple ortho-fused chain where
    every ring has fusion-graph degree <= 2) is a structural precondition
    for that ambiguity to arise, and a cheap, well-defined upper bound on
    it -- not an exact count, same convention as this file's other
    prevalence-only predicates and this project's other census SMARTS.
    Not expressible as a fixed-size SMARTS for the same reason as
    ``large_fused_polycyclic_aromatic``: the ring count is the variable.
    """
    ring_info = mol.GetRingInfo()
    rings = [set(r) for r in ring_info.AtomRings()]
    if len(rings) < 3:
        return False
    for i, ri in enumerate(rings):
        fused_partners = sum(
            1 for j, rj in enumerate(rings)
            if j != i and len(ri & rj) >= 2
        )
        if fused_partners >= 3:
            return True
    return False


PYTHON_PREDICATES = {
    "large_fused_polycyclic_aromatic": large_fused_polycyclic_aromatic,
    "multiparent_fusion_hub": multiparent_fusion_hub,
}


def load_census() -> list[dict]:
    return json.loads(CENSUS.read_text(encoding="utf-8"))


def load_queries() -> dict:
    return tomllib.loads(QUERIES.read_text(encoding="utf-8"))["query"]


def count(rows: list[dict], queries: dict) -> dict[str, dict]:
    mols = [(row, Chem.MolFromSmiles(row["smiles"])) for row in rows]
    mols = [(row, mol) for row, mol in mols if mol is not None]

    compiled: dict[str, list] = {}
    for qid, q in queries.items():
        if "smarts" in q:
            patterns = q["smarts"] if isinstance(q["smarts"], list) else [q["smarts"]]
            compiled[qid] = [Chem.MolFromSmarts(s) for s in patterns]

    results: dict[str, dict] = {}
    for qid, q in queries.items():
        hits = []
        if qid in compiled:
            patterns = compiled[qid]
            for row, mol in mols:
                if any(mol.HasSubstructMatch(p) for p in patterns):
                    hits.append(row["label"])
        else:
            predicate = PYTHON_PREDICATES[q["python_predicate"]]
            for row, mol in mols:
                if predicate(mol):
                    hits.append(row["label"])
        results[qid] = {
            "hits": len(hits),
            "sample_size": len(mols),
            "frequency": len(hits) / len(mols) if mols else 0.0,
            "hit_labels": hits,
        }
    return results


def main() -> None:
    if not CENSUS.exists():
        raise SystemExit(f"{CENSUS} does not exist yet -- run tools/naming_census_build.py first")

    rows = load_census()
    queries = load_queries()
    admissions = tomllib.loads(ADMISSIONS.read_text(encoding="utf-8"))
    threshold = admissions["cap"]["natural_frequency_min"]

    results = count(rows, queries)

    print(f"{len(rows)} census structures, threshold {threshold} ({int(threshold * len(rows))} hits)\n")
    for qid, r in sorted(results.items(), key=lambda kv: -kv[1]["frequency"]):
        clears = "CLEARS" if r["frequency"] >= threshold else "below "
        print(f"  {clears}  {qid:42s} {r['hits']:4d}/{r['sample_size']} = {r['frequency']:.4f}")

    out = BENCH / "census_counts.json"
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
