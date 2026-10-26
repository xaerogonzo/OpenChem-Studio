"""Stage 2 of the COD census for Phase B crystal density: which candidate entries carry an energetic-family group.

Reads the COD archive as a stream (as `cod_index.py` does) and, for each candidate entry, asks Open Babel for the
CONNECTIVITY of the cell, then matches the section 5 family groups of `PREREGISTRATION.md` against that connectivity with
patterns that ignore bond order.

**Why connectivity only.** A first probe on 40 nitrogen-rich entries showed Open Babel's bond ORDERS, perceived from
coordinates, are not usable: aromatic nitrogens came out as impossible four-valent atoms and only 6 of 40 entries could
be sanitised and classified. The connectivity is sound, and every family group the census needs (nitro, nitrate ester,
nitramine, azide, a ring with two or more nitrogens) is a statement about connectivity.

**What this pass does not do.**
* It does not separate nitroaromatic from nitroaliphatic (that needs bond orders or planarity); C-nitro is one count.
* It reads the number of components from the CIF's own `_chemical_formula_moiety`, not from the geometry, because Open
  Babel breaks molecules at the cell boundary; an entry with no moiety is `unknown`, never "single".
* It does not look for peroxides: the candidate set requires nitrogen, and organic peroxides are rare.
* An entry that carries a group is not thereby an energetic material; it is a compound with that group.

    python -I cod_structure_pass.py --archive ".../cod-cifs-mysql.txz" --index ".../index/cod_index.sqlite" --out ".../index/cod_structure.sqlite"
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import tarfile
import time
from pathlib import Path

#: The section 5 family order. C-nitro stands for the two rows (nitroaromatic, nitroaliphatic) that need bond orders.
FAMILY_ORDER = ("nitrate_ester", "nitramine", "c_nitro", "azide", "n_rich_heterocycle", "halogenated", "other_organic")

#: Bond-order-agnostic patterns (`~` is any bond). `X` counts every neighbour, hydrogens included when present.
PATTERNS = {
    "nitrate_ester": "[OX2]([#6])[NX3](~[OX1])~[OX1]",
    "nitramine": "[#7;!$([#7](~[OX1])~[OX1])][NX3](~[OX1])~[OX1]",
    "c_nitro": "[#6][NX3](~[OX1])~[OX1]",
    "azide": "[NX1]~[NX2]~[NX2]",
    "halogenated": "[F,Cl,Br,I]",
}

_FORMULA = re.compile(r"^_chemical_formula_sum\s+'?([^'\n]+?)'?\s*$", re.MULTILINE)
_MOIETY = re.compile(r"^_chemical_formula_moiety\s+(.*?)\s*$", re.MULTILINE)


def components(moiety: str | None) -> tuple[str, int | None]:
    """How many components the CIF's own moiety formula lists, and a verdict.

    `"single"` (one component, uncharged), `"multi"` (a comma-separated list: salt, solvate, co-crystal, hydrate) and
    `"ionic"` (a charge is written in the moiety) are read from the text; no moiety is `"unknown"`, which is never counted as
    single."""
    if not moiety:
        return "unknown", None
    text = moiety.strip().strip("'\"")
    if not text or text in ("?", "."):
        return "unknown", None
    parts = [p for p in re.split(r"\s*,\s*", text) if p]
    if re.search(r"[A-Za-z0-9\]\)][0-9]*[+-]\s*(?:,|$)", text) or re.search(r"\b[A-Z][a-z]?\d*[+-]\d*\b", text):
        return "ionic", len(parts)
    return ("single" if len(parts) == 1 else "multi"), len(parts)


def _compiled():
    from rdkit import Chem

    return {name: Chem.MolFromSmarts(smarts) for name, smarts in PATTERNS.items()}


_CACHE: dict = {}


def families_from_graph(mol) -> dict:
    """The groups present in a molecule graph (an RDKit mol, sanitised or not) and the first family by section 5's order.

    Returns `{"groups": [names present], "family": first by FAMILY_ORDER}`. `n_rich_heterocycle` is a ring holding two or
    more nitrogens, read from the ring perception of the graph, not from aromaticity."""
    from rdkit import Chem

    if not _CACHE:
        _CACHE.update(_compiled())
    # A graph built from connectivity has no hydrogens it was not given. Left alone, RDKit would FILL IN implicit ones (a
    # singly-bonded nitro oxygen would gain an H and stop being [OX1]): the first full pass found no nitro group at all.
    mol = Chem.Mol(mol)
    for atom in mol.GetAtoms():
        atom.SetNoImplicit(True)
    mol.UpdatePropertyCache(strict=False)
    Chem.FastFindRings(mol)
    present = [name for name, q in _CACHE.items() if mol.HasSubstructMatch(q)]
    ring_info = mol.GetRingInfo()
    if any(sum(1 for i in ring if mol.GetAtomWithIdx(i).GetAtomicNum() == 7) >= 2 for ring in ring_info.AtomRings()):
        present.append("n_rich_heterocycle")
    for name in FAMILY_ORDER[:-1]:
        if name in present:
            return {"groups": sorted(present), "family": name}
    return {"groups": sorted(present), "family": "other_organic"}


def graph_from_obmol(obmol):
    """An RDKit graph (atoms and single bonds, nothing sanitised) from an Open Babel molecule, one per fragment."""
    from openbabel import openbabel as ob
    from rdkit import Chem

    fragments = []
    for fr in obmol.Separate():
        rw = Chem.RWMol()
        index = {}
        for a in ob.OBMolAtomIter(fr):
            index[a.GetIdx()] = rw.AddAtom(Chem.Atom(a.GetAtomicNum()))
        for b in ob.OBMolBondIter(fr):
            rw.AddBond(index[b.GetBeginAtomIdx()], index[b.GetEndAtomIdx()], Chem.BondType.SINGLE)
        fragments.append(rw.GetMol())
    return fragments


def _formula_counts(formula: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for el, n in re.findall(r"([A-Z][a-z]?)([0-9.]*)", formula):
        try:
            out[el] = out.get(el, 0) + int(float(n)) if n else out.get(el, 0) + 1
        except ValueError:
            return {}
    return out


def _counts_of(frag) -> dict[str, int]:
    from rdkit import Chem

    out: dict[str, int] = {}
    for a in frag.GetAtoms():
        sym = Chem.GetPeriodicTable().GetElementSymbol(a.GetAtomicNum())
        out[sym] = out.get(sym, 0) + 1
    return out


def classify_cif(text: str) -> dict:
    """Header moiety and the families of the best fragment of one CIF's connectivity."""
    from openbabel import openbabel as ob
    from openbabel import pybel

    ob.obErrorLog.SetOutputLevel(0)
    moiety_match = _MOIETY.search(text)
    kind, n_components = components(moiety_match.group(1) if moiety_match else None)
    out = {"moiety": moiety_match.group(1)[:200] if moiety_match else None, "components": kind, "n_components": n_components}
    try:
        mol = pybel.readstring("cif", text)
    except Exception as exc:  # noqa: BLE001
        return {**out, "error": f"read: {str(exc)[:80]}"}
    groups: set[str] = set()
    header = _formula_counts(_FORMULA.search(text).group(1)) if _FORMULA.search(text) else None
    whole = False
    for frag in graph_from_obmol(mol.OBMol):
        groups.update(families_from_graph(frag)["groups"])
        if header and _counts_of(frag) == header:
            whole = True
    if kind == "unknown" and whole:
        # no moiety to read, but a whole molecule with exactly the header formula exists: single by GEOMETRY, labelled apart
        out["components"] = "single_by_geometry"
    family = next((n for n in FAMILY_ORDER[:-1] if n in groups), "other_organic")
    return {**out, "groups": sorted(groups), "family": family}


SCHEMA = """
CREATE TABLE IF NOT EXISTS structure (
  code TEXT PRIMARY KEY, components TEXT, n_components INTEGER, moiety TEXT, family TEXT, groups TEXT, error TEXT
);
"""


def candidates(index: Path) -> set[str]:
    """Organic entries with nitrogen, a diffraction density, a temperature in 273-303 K and no stated pressure."""
    allowed = {"H", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Br", "I"}
    db = sqlite3.connect(index)
    keep = set()
    for code, formula in db.execute(
        "select code, formula from cod where density_diffrn is not null and temperature_k between 273 and 303 and pressure_raw is null"
    ):
        counts = {}
        for el, n in re.findall(r"([A-Z][a-z]?)([0-9.]*)", formula or ""):
            counts[el] = counts.get(el, 0) + 1
        if "C" in counts and "N" in counts and set(counts) <= allowed:
            keep.add(code)
    return keep


def run(archive: Path, index: Path, out: Path, limit: int | None) -> dict:
    wanted = candidates(index)
    out.parent.mkdir(parents=True, exist_ok=True)
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
            if code not in wanted:
                continue
            text = tar.extractfile(member).read().decode("utf-8", errors="replace")
            r = classify_cif(text)
            if "error" in r:
                errors += 1
            batch.append((code, r["components"], r["n_components"], r["moiety"], r.get("family"),
                          ",".join(r.get("groups", [])), r.get("error")))
            n += 1
            if len(batch) >= 2000:
                db.executemany("INSERT OR REPLACE INTO structure VALUES (?,?,?,?,?,?,?)", batch)
                db.commit()
                batch.clear()
                print(f"{n} of {len(wanted)}, {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
            if limit and n >= limit:
                break
    if batch:
        db.executemany("INSERT OR REPLACE INTO structure VALUES (?,?,?,?,?,?,?)", batch)
    db.commit()
    db.close()
    return {"candidates": len(wanted), "classified": n, "errors": errors, "seconds": round(time.time() - t0, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    print(run(args.archive, args.index, args.out, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
