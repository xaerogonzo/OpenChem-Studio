"""Nitrate esters (and four-arm quaternary carbons) in the COD that the Phase B census did not look at.

`cod_structure_pass.candidates` keeps only entries with a diffraction density, a temperature in 273-303 K and no stated
pressure. That window is the preregistration's primary cohort for crystal density, but it is NOT the question the PETN
evidence hunt asks: a low-temperature structure of a nitrate ester is evidence that the structure exists, and a pressure
study of PETN is evidence about the polymorph. This pass takes every organic entry the census skipped that could hold a
nitrate ester (carbon, nitrogen, at least three oxygens, elements within the preregistration's organic set) plus every
C5 entry that could hold a pentaerythrityl core, streams the archive once (never unpacked), and records for each hit:

* `nitrate_ester`: the section 5 family-1 group (bond-order-free pattern of `cod_structure_pass`);
* `four_arm`: a carbon whose four heavy-atom neighbours are all carbons, each bonded to exactly one further heavy atom, the
  four being the same element (the PETN topology of ROADMAP.md / PREREGISTRATION.md 12.1), with the arm element.

    uv run --no-sync python benchmarks/energetics_props/inventory_scripts/cod_nitrate_ester_pass.py \
        --archive ".../cod-cifs-mysql.txz" --index ".../index/cod_index.sqlite" \
        --done ".../index/cod_structure.sqlite" --out ".../index/cod_nitrate_extra.sqlite"
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sqlite3
import sys
import tarfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("cod_structure_pass", _HERE / "cod_structure_pass.py")
sp = importlib.util.module_from_spec(_spec)
sys.modules["cod_structure_pass"] = sp
_spec.loader.exec_module(sp)

ALLOWED = {"H", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Br", "I"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS hit (
  code TEXT PRIMARY KEY, nitrate_ester INTEGER, four_arm TEXT, groups TEXT, components TEXT, moiety TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS cif (code TEXT PRIMARY KEY, text TEXT);
"""


def _counts(formula: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for el, n in re.findall(r"([A-Z][a-z]?)([0-9.]*)", formula or ""):
        try:
            out[el] = out.get(el, 0.0) + (float(n) if n else 1.0)
        except ValueError:
            return {}
    return out


def wanted(index: Path, done: Path) -> dict[str, str]:
    """code -> reason ('ester' or 'core') for entries the census skipped."""
    skip = {r[0] for r in sqlite3.connect(done).execute("select code from structure")}
    out: dict[str, str] = {}
    for code, formula in sqlite3.connect(index).execute("select code, formula from cod"):
        if code in skip:
            continue
        c = _counts(formula)
        if not c or "C" not in c or not set(c) <= ALLOWED:
            continue
        if "N" in c and c.get("O", 0) >= 3:
            out[code] = "ester"
        elif c.get("C") == 5 and 8 <= c.get("H", 0) <= 12:
            out[code] = "core"
    return out


def four_arm_element(frag) -> str | None:
    """Arm element if the fragment holds a carbon with four identical one-atom-deep arms off four CH2-like carbons."""
    from rdkit import Chem

    pt = Chem.GetPeriodicTable()

    def heavy(atom):
        return [n for n in atom.GetNeighbors() if n.GetAtomicNum() > 1]

    for atom in frag.GetAtoms():
        if atom.GetAtomicNum() != 6:
            continue
        nb = heavy(atom)
        if len(nb) != 4 or any(n.GetAtomicNum() != 6 for n in nb):
            continue
        arms = []
        for n in nb:
            rest = [m for m in heavy(n) if m.GetIdx() != atom.GetIdx()]
            if len(rest) != 1:
                break
            arms.append(pt.GetElementSymbol(rest[0].GetAtomicNum()))
        else:
            if len(set(arms)) == 1 and arms[0] != "C":
                return arms[0]
    return None


def classify(text: str) -> dict:
    from openbabel import openbabel as ob
    from openbabel import pybel

    ob.obErrorLog.SetOutputLevel(0)
    m = sp._MOIETY.search(text)
    kind, _ = sp.components(m.group(1) if m else None)
    out = {"moiety": m.group(1)[:200] if m else None, "components": kind}
    try:
        mol = pybel.readstring("cif", text)
    except Exception as exc:  # noqa: BLE001
        return {**out, "error": f"read: {str(exc)[:80]}"}
    groups: set[str] = set()
    four = None
    for frag in sp.graph_from_obmol(mol.OBMol):
        groups.update(sp.families_from_graph(frag)["groups"])
        four = four or four_arm_element(frag)
    return {**out, "groups": sorted(groups), "four_arm": four}


def run(archive: Path, index: Path, done: Path, out: Path, limit: int | None) -> dict:
    want = wanted(index, done)
    if out.exists():
        out.unlink()
    db = sqlite3.connect(out)
    db.executescript(SCHEMA)
    t0 = time.time()
    n = errors = 0
    batch = []
    with tarfile.open(archive, mode="r|xz") as tar:
        for member in tar:
            if not (member.isfile() and member.name.endswith(".cif")):
                continue
            code = Path(member.name).stem
            if code not in want:
                continue
            text = tar.extractfile(member).read().decode("utf-8", errors="replace")
            r = classify(text)
            if "nitrate_ester" in r.get("groups", []) or r.get("four_arm"):
                # the hits are few; keeping their CIFs means the cell, the density and the temperature can be read
                # without streaming 18 GB a second time
                db.execute("INSERT OR REPLACE INTO cif VALUES (?,?)", (code, text))
            if "error" in r:
                errors += 1
            batch.append((code, int("nitrate_ester" in r.get("groups", [])), r.get("four_arm"),
                          ",".join(r.get("groups", [])), r["components"], r["moiety"], r.get("error")))
            n += 1
            if len(batch) >= 2000:
                db.executemany("INSERT OR REPLACE INTO hit VALUES (?,?,?,?,?,?,?)", batch)
                db.commit()
                batch.clear()
                print(f"{n} of {len(want)}, {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
            if limit and n >= limit:
                break
    db.executemany("INSERT OR REPLACE INTO hit VALUES (?,?,?,?,?,?,?)", batch)
    db.commit()
    db.close()
    return {"wanted": len(want), "classified": n, "errors": errors, "seconds": round(time.time() - t0, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--done", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)
    print(run(a.archive, a.index, a.done, a.out, a.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
