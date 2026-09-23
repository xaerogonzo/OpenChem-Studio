"""Attach an acetamido group at every legal position of every curated ring and check that each name reads back.

    python tools/naming_ring_locant_sweep.py --write-population      # (re)write the hashed ring population
    python tools/naming_ring_locant_sweep.py                          # the sweep; refuses a stale population
    python tools/naming_ring_locant_sweep.py --out sweep.json         # also one record per case
    python tools/naming_ring_locant_sweep.py --rings thiadiazole      # only rings whose name contains this (development)

**WHY IT EXISTS.** The census scan (round 13's prelude) found a wrong `-3-yl` on 1,3,4-oxa/thiadiazoles and a wrong `-2-yl`
on benzodioxin-6-yl. Both rings are curated in `_RING_CURATED_SMILES` with no `atom_locants`, so their substituent locant
comes from a fallback, not from a table. A census can only find the rings that happen to occur in its 2000 structures. This
sweep asks the same question of ALL 371 curated rings at once, and separates the rings whose table is complete, partial or
absent, so "69 rings have no table" is never mistaken for "69 rings are wrong".

**THE DENOMINATOR IS FROZEN BEFORE THE FIRST RESULT.** `benchmarks/naming/ring_sweep_population.json` lists every ring
with its id, canonical SMILES, atom count, attachable sites and whether it has `atom_locants`, and carries a hash over that
content. The sweep refuses to run if the live table no longer hashes to it, so a data change cannot silently move the
number of rings or sites; regenerating it (`--write-population`) is a deliberate act that shows in a diff.

**WHAT IS ATTACHABLE.** Only a CARBON ring atom that has a free hydrogen and is not a fusion atom. A heteroatom attachment
(`[nH]`, N-, O-, S-substitution) follows different numbering rules and a fusion atom carries no substituent locant, so both
are recorded as SKIPPED with the reason, never silently dropped and never counted as "every position".

**THE CASES** (each carries what it tests, so a future contributor does not read it as "two-substituent molecules"):

    single             acetamido alone: the plain attachment locant
    pair_equivalent    acetamido at i and a methyl at a SYMMETRY-EQUIVALENT atom j: the ring's own symmetry is kept and an
                       internal substituent breaks the tie between the two orientations -- the shape 1,3,4-thiadiazole failed
    pair_inequivalent  acetamido at i and a methyl at an inequivalent atom j: numbering with the symmetry already broken

For a ring with many positions the second substituent is capped at three per site (one symmetry-equivalent if any, the
nearest, the farthest) so the population stays measurable; the cap is a constant and is printed.

**WHAT THE ORACLE SAYS AND DOES NOT.** The read-back is a STRUCTURAL oracle: it says the name denotes the molecule it came
from. It cannot say the locant is the lowest, or the preferred one, because two symmetry-equivalent locants parse to the same
structure. So every result is `wrong_structure`, `structurally_correct`, `engine_error` or `opsin_unsupported`, and the report
states that numbering preference is NOT independently adjudicated for any ring without a source-backed table.

This tool must not name the census file (the census lock forbids it); it reuses the census scan's naming, read-back and
classification by import.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import shutil
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmarks" / "naming"
POPULATION = BENCH / "ring_sweep_population.json"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import naming_census_scan as census_scan  # noqa: E402

#: The second substituent is placed at no more than this many positions per acetamido site.
SECOND_SUBSTITUENT_CAP = 3

#: What each census-scan class means for THIS sweep. The oracle is structural only.
OUTCOME_OF = {
    "exact": "structurally_correct",
    "same_connectivity": "structurally_correct",
    "mismatch_formula": "wrong_structure",
    "mismatch_same_formula": "wrong_structure",
    "unparsable": "opsin_unsupported",
    "naming_error": "engine_error",
    "refused": "engine_error",
}


def curated_rings() -> dict[str, dict]:
    """`{canonical ring SMILES: curated entry}` as the engine holds it."""
    from openchem.vendor.iupac_namer.data_loader import _RING_CURATED_SMILES

    return _RING_CURATED_SMILES


def _skip_reason(atom) -> str | None:
    """Why this atom is not a legal attachment site, or None when it is one."""
    if not atom.IsInRing():
        return "exocyclic"
    if atom.GetAtomicNum() != 6:
        return "heteroatom"
    # Fusion first: a ring-fusion carbon has no hydrogen either, and "fusion atom" is the informative reason.
    if atom.GetOwningMol().GetRingInfo().NumAtomRings(atom.GetIdx()) > 1:
        return "fusion_atom"
    if atom.GetTotalNumHs() == 0:
        return "no_free_hydrogen"
    return None


def describe_ring(smiles: str, entry: dict) -> dict:
    """One ring's row in the population: identity, size, attachable sites, skipped sites, table state."""
    from rdkit import Chem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"smiles": smiles, "name": entry.get("name"), "atoms": 0, "unreadable": True}
    sites: list[int] = []
    skipped: dict[str, list[int]] = collections.defaultdict(list)
    for atom in mol.GetAtoms():
        reason = _skip_reason(atom)
        if reason is None:
            sites.append(atom.GetIdx())
        else:
            skipped[reason].append(atom.GetIdx())
    table = entry.get("atom_locants")
    return {
        "smiles": smiles,
        "name": entry.get("name"),
        "atoms": mol.GetNumAtoms(),
        "has_atom_locants": bool(table),
        "locant_atoms": sorted(int(k) for k in table) if table else [],
        "sites": sites,
        "skipped": {k: v for k, v in sorted(skipped.items())},
    }


def build_population() -> dict:
    """The whole population and its hash. Deterministic: rings in sorted SMILES order."""
    rings = [describe_ring(smi, e) for smi, e in sorted(curated_rings().items())]
    body = json.dumps(rings, sort_keys=True)
    return {
        "purpose": "the frozen ring denominator for tools/naming_ring_locant_sweep.py (naming round 13)",
        "second_substituent_cap": SECOND_SUBSTITUENT_CAP,
        "n_rings": len(rings),
        "population_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "rings": rings,
    }


def load_population() -> dict:
    """The committed population, refused if the live curated table no longer matches it."""
    stored = json.loads(POPULATION.read_text(encoding="utf-8"))
    live = build_population()
    if stored["population_sha256"] != live["population_sha256"]:
        raise SystemExit(
            "ring_sweep_population.json is stale: the curated ring table changed since it was written. "
            "Review the change, then run --write-population and commit the diff."
        )
    return stored


def _second_sites(mol, site: int, sites: list[int]) -> list[int]:
    """Up to SECOND_SUBSTITUENT_CAP positions for the methyl: a symmetry-equivalent one if any, the nearest, the farthest."""
    from rdkit import Chem

    others = [j for j in sites if j != site]
    if not others:
        return []
    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
    dist = Chem.GetDistanceMatrix(mol)
    chosen: list[int] = []
    equivalent = [j for j in others if ranks[j] == ranks[site]]
    for j in (equivalent[:1] + [min(others, key=lambda x: (dist[site][x], x))] + [max(others, key=lambda x: (dist[site][x], -x))]):
        if j not in chosen:
            chosen.append(j)
    return chosen[:SECOND_SUBSTITUENT_CAP]


def _attach(mol, site: int, other: int | None) -> str | None:
    """SMILES with an acetamido group at `site` and, if given, a methyl at `other`; None if it cannot be built."""
    from rdkit import Chem

    rw = Chem.RWMol(mol)
    n, c, o, m = (rw.AddAtom(Chem.Atom(z)) for z in (7, 6, 8, 6))
    rw.AddBond(site, n, Chem.BondType.SINGLE)
    rw.AddBond(n, c, Chem.BondType.SINGLE)
    rw.AddBond(c, o, Chem.BondType.DOUBLE)
    rw.AddBond(c, m, Chem.BondType.SINGLE)
    if other is not None:
        k = rw.AddAtom(Chem.Atom(6))
        rw.AddBond(other, k, Chem.BondType.SINGLE)
    try:
        Chem.SanitizeMol(rw)
    except Exception:  # noqa: BLE001 - an unbuildable case is recorded as skipped, not a naming result
        return None
    return Chem.MolToSmiles(rw)


def build_cases(ring_index: int, ring: dict) -> tuple[list[dict], list[dict]]:
    """`(cases, unbuildable)` for one ring: every eligible site alone, then with a second substituent."""
    from rdkit import Chem

    mol = Chem.MolFromSmiles(ring["smiles"])
    if mol is None or not ring.get("sites"):
        return [], []
    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
    cases: list[dict] = []
    bad: list[dict] = []
    for site in ring["sites"]:
        wanted = [(None, "single")] + [
            (j, "pair_equivalent" if ranks[j] == ranks[site] else "pair_inequivalent")
            for j in _second_sites(mol, site, ring["sites"])
        ]
        for other, variant in wanted:
            smiles = _attach(mol, site, other)
            record = {"ring": ring_index, "site": site, "other": other, "variant": variant}
            if smiles is None:
                bad.append(record)
            else:
                cases.append({**record, "label": f"{ring_index}:{site}:{other}", "smiles": smiles})
    return cases, bad


def run(population: dict, *, rings_filter: str | None = None, names_only: bool = False) -> dict:
    """Build every case, name them all, then read them all back. Returns cases, unbuildable and timings."""
    t0 = time.time()
    cases: list[dict] = []
    unbuildable: list[dict] = []
    for index, ring in enumerate(population["rings"]):
        if rings_filter and rings_filter.lower() not in str(ring.get("name") or "").lower():
            continue
        c, b = build_cases(index, ring)
        cases += c
        unbuildable += b
    t_build = time.time() - t0

    t1 = time.time()
    named = census_scan.name_rows([{"label": c["label"], "smiles": c["smiles"]} for c in cases])
    t_name = time.time() - t1

    t2 = time.time()
    readable = [c["label"] for c in cases
                if "NAMING ERROR" not in named[c["label"]]["name"] and not named[c["label"]]["name"].startswith("RAISED")]
    back: dict[str, str] = {}
    if not names_only:
        back = dict(zip(readable, census_scan.read_back([named[k]["name"] for k in readable])))
    t_back = time.time() - t2

    for case in cases:
        rec = named[case["label"]]
        case["name"] = rec["name"]
        case["cls"] = census_scan.classify(rec["smiles"], rec["name"], None if names_only else back.get(case["label"]))
        case["outcome"] = OUTCOME_OF[case["cls"]]
    return {
        "cases": cases,
        "unbuildable": unbuildable,
        "timing_seconds": {"build": round(t_build, 1), "naming": round(t_name, 1), "read_back": round(t_back, 1),
                           "total": round(time.time() - t0, 1)},
    }


def table_state(ring: dict) -> str:
    """`full` if every attachable site has a locant in the ring's table, `partial` if only some do, `table_less` if it has none."""
    if not ring.get("has_atom_locants"):
        return "table_less"
    return "full" if set(ring.get("sites", [])) <= set(ring["locant_atoms"]) else "partial"


def summarise(population: dict, result: dict) -> list[str]:
    """The report: per table state, how many rings, how many failed, and the failing rings by name."""
    rings = population["rings"]
    per_ring: dict[int, list[dict]] = collections.defaultdict(list)
    for case in result["cases"]:
        per_ring[case["ring"]].append(case)
    lines = [f"{len(rings)} curated rings, {len(result['cases'])} cases (second substituent capped at "
             f"{population['second_substituent_cap']} per site); {len(result['unbuildable'])} could not be built"]
    groups: dict[str, dict] = {}
    for index, ring in enumerate(rings):
        state = table_state(ring)
        g = groups.setdefault(state, {"rings": 0, "tested": 0, "no_sites": 0, "wrong": 0, "engine_error": 0, "cases": 0,
                                      "rings_wrong": 0, "rings_only_correct": 0})
        g["rings"] += 1
        cases = per_ring.get(index, [])
        if not ring.get("sites"):
            g["no_sites"] += 1
            continue
        if not cases:
            continue
        g["tested"] += 1
        g["cases"] += len(cases)
        wrong = sum(c["outcome"] == "wrong_structure" for c in cases)
        g["wrong"] += wrong
        g["engine_error"] += sum(c["outcome"] == "engine_error" for c in cases)
        g["rings_wrong"] += bool(wrong)
        g["rings_only_correct"] += all(c["outcome"] == "structurally_correct" for c in cases)
    lines.append("  table state    rings tested  no-site  rings w/ wrong  only-correct   cases  wrong  engine-err")
    for state in ("table_less", "partial", "full"):
        if state in groups:
            g = groups[state]
            lines.append(f"  {state:12s} {g['rings']:6d} {g['tested']:6d} {g['no_sites']:8d} {g['rings_wrong']:12d} "
                         f"{g['rings_only_correct']:13d} {g['cases']:7d} {g['wrong']:6d} {g['engine_error']:10d}")
    skipped = collections.Counter()
    for ring in rings:
        for reason, atoms in ring.get("skipped", {}).items():
            skipped[reason] += len(atoms)
    lines.append("  skipped sites (never swept): " + ", ".join(f"{k} {v}" for k, v in skipped.most_common()))
    failing = sorted(((sum(c["outcome"] == "wrong_structure" for c in cs), i) for i, cs in per_ring.items()), reverse=True)
    lines.append("  rings with wrong-structure cases (wrong/cases, table state, variants that failed):")
    for wrong, index in [f for f in failing if f[0]][:30]:
        cs = per_ring[index]
        variants = sorted({c["variant"] for c in cs if c["outcome"] == "wrong_structure"})
        lines.append(f"    {wrong:3d}/{len(cs):3d}  {table_state(rings[index]):10s} {str(rings[index].get('name'))[:58]:58s} {','.join(variants)}")
    t = result["timing_seconds"]
    lines.append(f"  time: build {t['build']}s, naming {t['naming']}s, read-back {t['read_back']}s, total {t['total']}s")
    lines.append("  the oracle is STRUCTURAL: numbering preference is NOT independently adjudicated for any table-less ring")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write-population", action="store_true", help="(re)write the hashed ring population and exit")
    parser.add_argument("--out", type=Path, help="write every case as JSON")
    parser.add_argument("--rings", help="only rings whose curated name contains this (development)")
    parser.add_argument("--names-only", action="store_true", help="skip the OPSIN read-back")
    args = parser.parse_args(argv)

    if args.write_population:
        population = build_population()
        POPULATION.write_text(json.dumps(population, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{population['n_rings']} rings, sha256 {population['population_sha256'][:16]} -> {POPULATION}")
        return 0
    if not args.names_only and shutil.which("java") is None:
        print("No bare `java` on PATH (use the /c/... form in bash) or pass --names-only.", file=sys.stderr)
        return 2
    warnings.filterwarnings("ignore")
    population = load_population()
    result = run(population, rings_filter=args.rings, names_only=args.names_only)
    for line in summarise(population, result):
        print(line)
    if args.out:
        args.out.write_text(json.dumps(result), encoding="utf-8")
        print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
