"""NL-011 bucket B: op.py-style OPSIN probes on the fourteen baseline flat names.

Seed 8901 chains that had ``flat_verdict == unparsable`` at pre-bucket-A measure
(``fa3a0115``). For each chain, tries the baseline flat string, today's flat
and emitted names, and systematic spelling/locant variants; classifies outcomes.

Run from repo root with JAVA_HOME set:
  uv run --no-sync python tools/nl011_bucket_b_opsin_probe.py
  uv run --no-sync python tools/nl011_bucket_b_opsin_probe.py --json benchmarks/naming/artifacts_nl011_bucket_b_probe.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

RDLogger.DisableLog("rdApp.*")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from openchem.vendor.iupac_namer import name_smiles  # noqa: E402

from nl011_seed8901_measure import (  # noqa: E402
    BUCKET_B_INDICES,
    generate_cases,
    opsin,
    flat_name,
)

BASELINE_COMMIT = "fa3a0115"

# Spiro citation locants: -2, 2', 2'', before comma or closing bracket.
SPIRO_LOCANT = re.compile(r"-(\d{1,2})(''|')?(?=[,\]]|$)")


def conn_key(smiles: str) -> str:
    m = Chem.MolFromSmiles(smiles)
    Chem.SanitizeMol(m)
    return inchi.MolToInchiKey(m)[:14]


def opsin_ok(name: str, target_key: str) -> tuple[bool, str | None, str | None]:
    """Return (matches target connectivity key, opsin smiles or None, note)."""
    back, err = opsin(name)
    if not back:
        return False, None, err or "empty"
    bm = Chem.MolFromSmiles(back)
    if bm is None:
        return False, back, "invalid_smiles"
    try:
        Chem.SanitizeMol(bm)
    except Exception as ex:
        return False, back, str(ex)[:80]
    k = inchi.MolToInchiKey(bm)[:14]
    return k == target_key, back, None if k == target_key else f"key={k}"


def load_baseline_flats() -> dict[int, str]:
    snap = ROOT / "benchmarks/naming/artifacts_nl011_bucket_b_baseline_flats.json"
    if snap.is_file():
        data = json.loads(snap.read_text(encoding="utf-8"))
        return {int(k): v for k, v in data.items()}
    raw = subprocess.check_output(
        [
            "git",
            "show",
            f"{BASELINE_COMMIT}:benchmarks/naming/artifacts_nl011_seed8901.json",
        ],
        cwd=ROOT,
        text=True,
    )
    rows = json.loads(raw)["rows"]
    return {
        r["index"]: r["flat"]
        for r in rows
        if r.get("flat_verdict") == "unparsable" and r.get("flat")
    }


def _replace_spiro_locant(name: str, start: int, end: int, new_digit: str) -> str:
    return name[:start] + new_digit + name[end:]


def locant_sweep_variants(name: str, lo: int = 1, hi: int = 9) -> set[str]:
    out: set[str] = {name}
    for m in SPIRO_LOCANT.finditer(name):
        old = m.group(1)
        suffix = m.group(2) or ""
        for n in range(lo, hi + 1):
            if str(n) == old:
                continue
            repl = _replace_spiro_locant(name, m.start(1), m.end(1), str(n))
            if suffix:
                # suffix is outside group 1 end — already preserved in slice
                pass
            out.add(repl)
    return out


def spelling_variants(name: str) -> set[str]:
    out = {name}
    rules: list[tuple[str, str]] = [
        ("0^{3,6}", "0^3^6"),
        ("0^{3,8}", "0^3^8"),
        ("0^{3,6}", "0(3,6)"),
        ("0^{3,8}", "0(3,8)"),
        ("decahydronaphthalene", "decalin"),
        ("decahydronaphthalene", "naphthalene"),
        ("5H-", "6H-"),
        ("5H-", "4H-"),
        ("5H-", "1H-"),
        ("[1]benzazepine", "benzazepine"),
        ("imidazo[4,5-d]", "imidazo[4,5-c]"),
        ("bicyclo[2.1.1]hexane", "bicyclo[2.1.1]heptane"),  # deliberate negative control
    ]
    for a, b in rules:
        if a in name:
            out.add(name.replace(a, b))
    # Without substituent prefix on whole dispiro (#13)
    if name.startswith("1-methyldispiro"):
        out.add(name.replace("1-methyldispiro", "dispiro", 1))
    if name.startswith("dispiro") and "methyl" not in name:
        out.add("1-methyl" + name)
        out.add("1-methyldispiro" + name[len("dispiro") :])
    return out


def prime_swap_variants(name: str) -> set[str]:
    """Swap first two spiro citation locants (digit+optional prime)."""
    m = re.search(r"dispiro\[([^\]]+)\]", name)
    if not m:
        return set()
    inner = m.group(1)
    parts = inner.split("-")
    if len(parts) < 2:
        return set()
    # First segment ends with locant before comma: ...nonane-1,4'-
    seg0 = parts[0]
    comma = seg0.rfind(",")
    if comma == -1:
        return set()
    loc_a = seg0[comma + 1 :]
    head = seg0[: comma + 1]
    seg1 = parts[1]
    comma2 = seg1.find(",")
    if comma2 == -1:
        return set()
    loc_b = seg1[:comma2]
    tail = seg1[comma2:]
    swapped_inner = "-".join([head + loc_b, loc_b + tail] + parts[2:])
    # Fix: rebuild properly
    new_inner = head + loc_b + "-" + loc_a + tail + ("-" + "-".join(parts[2:]) if len(parts) > 2 else "")
    return {name.replace(inner, new_inner, 1)}


def all_candidates(*names: str | None) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    bases = [n for n in names if n]
    for base in bases:
        if base not in seen:
            seen.add(base)
            ordered.append(base)
    for base in bases:
        pool: set[str] = set()
        pool |= locant_sweep_variants(base)
        pool |= spelling_variants(base)
        pool |= prime_swap_variants(base)
        for c in sorted(pool):
            if c not in seen:
                seen.add(c)
                ordered.append(c)
    return ordered


def classify_chain(
    index: int,
    smiles: str,
    key: str,
    baseline_flat: str,
    current_flat: str | None,
    emitted: str | None,
    max_probe: int,
) -> dict:
    seeds = all_candidates(baseline_flat, current_flat, emitted)
    if len(seeds) > max_probe:
        seeds = seeds[:max_probe]

    current_flat_ok = False
    emitted_ok = False
    baseline_ok = False
    hits: list[dict] = []
    parses_wrong: list[dict] = []
    unparsable = 0

    for cand in seeds:
        ok, back, note = opsin_ok(cand, key)
        if cand == baseline_flat and ok:
            baseline_ok = True
        if current_flat and cand == current_flat and ok:
            current_flat_ok = True
        if emitted and cand == emitted and ok:
            emitted_ok = True
        if ok:
            hits.append({"name": cand, "back": back})
        elif back:
            parses_wrong.append({"name": cand, "back": back, "note": note})
        else:
            unparsable += 1

    winning = [h["name"] for h in hits]
    emitted_set = {emitted} if emitted else set()
    flat_set = {current_flat} if current_flat else set()
    fixable = [n for n in winning if n not in emitted_set and n not in flat_set]

    if emitted_ok:
        bucket = "resolved_emitted"
    elif current_flat_ok:
        bucket = "resolved_current_flat"
    elif fixable:
        bucket = "fixable_spelling"
    elif hits:
        bucket = "variant_ok_not_emitted"
    elif parses_wrong and not baseline_ok:
        bucket = "parses_wrong_only"
    else:
        bucket = "opsin_gap"

    return {
        "index": index,
        "smiles": smiles,
        "key": key,
        "baseline_flat": baseline_flat,
        "current_flat": current_flat,
        "emitted": emitted,
        "baseline_ok": baseline_ok,
        "current_flat_ok": bool(current_flat_ok),
        "emitted_ok": bool(emitted_ok),
        "candidates_tried": len(seeds),
        "unparsable": unparsable,
        "parses_wrong": len(parses_wrong),
        "hits": hits[:12],
        "hit_count": len(hits),
        "fixable_hits": fixable[:8],
        "classification": bucket,
        "sample_wrong": parses_wrong[:3],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--max-candidates", type=int, default=120)
    args = parser.parse_args()

    baseline = load_baseline_flats()
    cases, *_ = generate_cases()
    by_idx = {i + 1: (label, smi, key) for i, (label, smi, key, _rings) in enumerate(cases)}

    rows: list[dict] = []
    for idx in BUCKET_B_INDICES:
        if idx not in baseline or idx not in by_idx:
            print(f"missing index {idx}", flush=True)
            continue
        label, smiles, key = by_idx[idx]
        m = Chem.MolFromSmiles(smiles)
        Chem.SanitizeMol(m)
        cur_flat = flat_name(m)
        try:
            emitted = name_smiles(smiles)
        except Exception as ex:
            emitted = f"NAMING ERROR: {ex}"[:120]
        row = classify_chain(
            idx,
            smiles,
            key,
            baseline[idx],
            cur_flat,
            emitted if not str(emitted).startswith("NAMING") else None,
            args.max_candidates,
        )
        row["label"] = label
        rows.append(row)
        print(
            f"#{idx:2d} {row['classification']:22} "
            f"hits={row['hit_count']:3d} tried={row['candidates_tried']:3d} {label}",
            flush=True,
        )
        if row["fixable_hits"]:
            print(f"     fixable: {row['fixable_hits'][0][:100]}", flush=True)

    summary = {}
    for r in rows:
        summary[r["classification"]] = summary.get(r["classification"], 0) + 1
    print("summary", summary, flush=True)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "baseline_commit": BASELINE_COMMIT,
            "indices": BUCKET_B_INDICES,
            "summary": summary,
            "rows": rows,
        }
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("wrote", args.json, flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
