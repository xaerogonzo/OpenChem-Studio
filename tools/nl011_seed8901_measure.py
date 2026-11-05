"""NL-011: twenty three-component spiro chains, seed 8901 (matrix oracle).

Run from repo root with JAVA_HOME set:
  uv run --no-sync python tools/nl011_seed8901_measure.py
  uv run --no-sync python tools/nl011_seed8901_measure.py --json benchmarks/naming/artifacts_nl011_seed8901.json
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import sys
import tempfile
import time
import warnings
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

RDLogger.DisableLog("rdApp.*")

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.data_loader import _RING_CURATED_SMILES
from openchem.vendor.iupac_namer.perception.atoms import AtomAnalysis
from openchem.vendor.iupac_namer.perception.rings import RingAnalysis
from openchem.vendor.iupac_namer.ring_naming.spiro import _try_multicomponent_spiro

BRIDGED = {
    "adamantane": "C1C2CC3CC1CC(C2)C3",
    "norbornane": "C1CC2CCC1C2",
    "bicyclo222": "C1CC2CCC1CC2",
    "tropane": "CN1C2CCC1CCC2",
    "quinuclidine": "C1CN2CCC1CC2",
    "bicyclo331": "C1CC2CCCC(C1)C2",
    "oxaadamantane": "C1C2CC3CC1COC(C2)C3",
    "azaadamantane": "C1C2CC3CC1CNC(C2)C3",
    "bicyclo321_O": "C1CC2CCC(C1)O2",
    "bicyclo211": "C1CC2CC1C2",
    "bicyclo111pent": "C1C2CC1C2",
    "noradamantane": "C1C2CC3CC1CC23",
    "bicyclo410": "C1CCC2CC2C1",
    "decalin": "C1CCC2CCCCC2C1",
}
SKIP = (33, 34, 52, 51, 5, 14, 15)
N = 20
SEED = 8901

# Pre-bucket-A (fa3a0115): flat names OPSIN would not parse.
BUCKET_B_INDICES = [2, 3, 4, 5, 6, 7, 9, 12, 13, 14, 15, 18, 19, 20]


def ring_count(m):
    return len(Chem.GetSymmSSSR(m))


def polycyclic(m):
    return m is not None and ring_count(m) >= 2


def ch2(m):
    return [
        a.GetIdx()
        for a in m.GetAtoms()
        if a.IsInRing()
        and a.GetTotalNumHs() >= 2
        and not a.GetIsAromatic()
        and a.GetAtomicNum() == 6
    ]


def join(m1, m2, i, j):
    rw = Chem.RWMol(m1)
    off = rw.GetNumAtoms()
    for a in m2.GetAtoms():
        na = Chem.Atom(a.GetAtomicNum())
        na.SetFormalCharge(a.GetFormalCharge())
        rw.AddAtom(na)
    for b in m2.GetBonds():
        rw.AddBond(b.GetBeginAtomIdx() + off, b.GetEndAtomIdx() + off, b.GetBondType())
    for idx, a in enumerate(m2.GetAtoms()):
        if a.GetIsAromatic():
            rw.GetAtomWithIdx(idx + off).SetIsAromatic(True)
    for idx, a in enumerate(m1.GetAtoms()):
        if a.GetIsAromatic():
            rw.GetAtomWithIdx(idx).SetIsAromatic(True)
    j += off
    for nb in list(rw.GetAtomWithIdx(j).GetNeighbors()):
        rw.AddBond(i, nb.GetIdx(), rw.GetBondBetweenAtoms(j, nb.GetIdx()).GetBondType())
    rw.RemoveAtom(j)
    return rw


def spiro_carbons(m):
    return [
        a.GetIdx()
        for a in m.GetAtoms()
        if a.GetAtomicNum() == 6
        and a.IsInRing()
        and a.GetDegree() == 4
        and a.GetTotalNumHs() == 0
    ]


def build_pools():
    rings = []
    for smi, entry in _RING_CURATED_SMILES.items():
        m = Chem.MolFromSmiles(smi)
        if m is None or m.GetNumAtoms() > 16:
            continue
        if any(a.GetFormalCharge() for a in m.GetAtoms()):
            continue
        if any(a.GetAtomicNum() in SKIP for a in m.GetAtoms()):
            continue
        if len(Chem.GetMolFrags(m)) != 1:
            continue
        if not polycyclic(m):
            continue
        rings.append((entry["name"], m))
    bridged = []
    for key, smi in BRIDGED.items():
        m = Chem.MolFromSmiles(smi)
        if polycyclic(m):
            bridged.append((key, m))
    return rings, bridged


def opsin(name: str) -> tuple[str | None, str | None]:
    from py2opsin import py2opsin

    handle, scratch = tempfile.mkstemp(prefix="opsin-", suffix=".txt")
    os.close(handle)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = py2opsin(name, tmp_fpath=scratch)
    except Exception as ex:
        return None, str(ex)[:160]
    finally:
        try:
            os.unlink(scratch)
        except OSError:
            pass
    if not result:
        return None, "empty"
    if isinstance(result, (list, tuple)):
        result = result[0] if result else None
    return result, None


def conn(m) -> str:
    return inchi.MolToInchiKey(m)[:14]


def generate_cases():
    rings, bridged = build_pools()
    random.seed(SEED)
    cases = []
    seen = set()
    rejected = 0
    tries = 0
    while len(cases) < N and tries < N * 80:
        tries += 1
        mode = random.choice(["curated_bridged", "curated_bridged", "bridged_bridged"])
        n1, m1 = random.choice(rings) if mode == "curated_bridged" and rings else random.choice(bridged)
        n2, m2 = random.choice(bridged)
        n3, m3 = random.choice(bridged)
        c1, c2 = ch2(m1), ch2(m2)
        if not c1 or not c2:
            rejected += 1
            continue
        rw = join(m1, m2, random.choice(c1), random.choice(c2))
        try:
            mid = rw.GetMol()
            Chem.SanitizeMol(mid)
        except Exception:
            rejected += 1
            continue
        c_mid, c3 = ch2(mid), ch2(m3)
        if not c_mid or not c3:
            rejected += 1
            continue
        rw = join(mid, m3, random.choice(c_mid), random.choice(c3))
        try:
            m = rw.GetMol()
            Chem.SanitizeMol(m)
        except Exception:
            rejected += 1
            continue
        if len(Chem.GetMolFrags(m)) != 1:
            rejected += 1
            continue
        if len(spiro_carbons(m)) != 2:
            rejected += 1
            continue
        s = Chem.MolToSmiles(m)
        if s in seen or "." in s:
            continue
        seen.add(s)
        cases.append((f"{n1} + {n2} + {n3}", s, conn(m), ring_count(m)))
    return cases, len(rings), len(bridged), tries, rejected


def flat_name(mol) -> str | None:
    rs = RingAnalysis(mol, AtomAnalysis(mol)).ring_systems[0]
    got = _try_multicomponent_spiro(rs, None, mol)
    if not got:
        return None
    return got[0].name


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    cases, n_rings, n_br, tries, rejected = generate_cases()
    print(f"polycyclic curated {n_rings} bridged {n_br}", flush=True)
    print(f"kept {len(cases)} tries {tries} rejected {rejected}", flush=True)

    rows = []
    for idx, (label, smiles, key, rings_n) in enumerate(cases, start=1):
        m = Chem.MolFromSmiles(smiles)
        Chem.SanitizeMol(m)
        flat = flat_name(m)
        t0 = time.perf_counter()
        try:
            emitted = name_smiles(smiles)
            err = None
        except Exception as ex:
            emitted = None
            err = str(ex).splitlines()[0][:180]
        dt = time.perf_counter() - t0
        back = None
        back_key = None
        opsin_err = None
        if emitted and "NAMING ERROR" not in emitted:
            back, opsin_err = opsin(emitted)
            if back:
                bm = Chem.MolFromSmiles(back)
                if bm is not None:
                    try:
                        Chem.SanitizeMol(bm)
                        back_key = conn(bm)
                    except Exception as ex:
                        opsin_err = str(ex)[:120]
        if emitted is None:
            verdict = "refused"
        elif "NAMING ERROR" in emitted:
            verdict = "naming_error"
        elif not back:
            verdict = "unparsable"
        elif back_key == key:
            verdict = "ok"
        else:
            verdict = "wrong"
        flat_back = None
        flat_verdict = "no_flat"
        if flat:
            flat_back, _ = opsin(flat)
            if flat_back:
                bm = Chem.MolFromSmiles(flat_back)
                if bm is not None:
                    try:
                        Chem.SanitizeMol(bm)
                        flat_verdict = "ok" if conn(bm) == key else "wrong"
                    except Exception:
                        flat_verdict = "unparsable"
                else:
                    flat_verdict = "unparsable"
            else:
                flat_verdict = "unparsable"
        row = {
            "index": idx,
            "label": label,
            "smiles": smiles,
            "key": key,
            "rings": rings_n,
            "emitted": emitted,
            "flat": flat,
            "emitted_eq_flat": emitted == flat if (emitted and flat) else None,
            "back": back,
            "back_key": back_key,
            "flat_back": flat_back,
            "verdict": verdict,
            "flat_verdict": flat_verdict,
            "t": round(dt, 3),
            "err": err or opsin_err,
        }
        rows.append(row)
        print(f"{idx:2d} {verdict:12} flat={flat_verdict:12} {dt:5.2f}s {label}", flush=True)

    counts = collections.Counter(r["verdict"] for r in rows)
    flat_counts = collections.Counter(r["flat_verdict"] for r in rows)
    print("emitted", dict(counts), flush=True)
    print("flat_only", dict(flat_counts), flush=True)
    print("slow max", max(r["t"] for r in rows), flush=True)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "seed": SEED,
            "n": N,
            "tries": tries,
            "rejected": rejected,
            "counts": dict(counts),
            "flat_counts": dict(flat_counts),
            "rows": rows,
        }
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("wrote", args.json, flush=True)

    unparsable = [r for r in rows if r["verdict"] != "ok"]
    print("\n=== TRIAGE (not ok on emitted name) ===", flush=True)
    for r in unparsable:
        print(f"\n#{r['index']} {r['verdict']} emitted_flat_same={r['emitted_eq_flat']}", flush=True)
        print(r["smiles"], flush=True)
        print("EMITTED:", r["emitted"], flush=True)
        print("FLAT:   ", r["flat"], flush=True)
        print("flat_verdict:", r["flat_verdict"], "err:", r["err"], flush=True)

    return 0 if counts.get("ok", 0) == N else 1


if __name__ == "__main__":
    sys.exit(main())
