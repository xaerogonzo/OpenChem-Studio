"""Check the transcribed reference routes (refs_out/*.json): schema, SMILES parse, route shape, atom balance, and OPSIN agreement between each printed name and the SMILES given.

    uv run --no-sync python validate_refs.py [stem ...]      (run from the worktree so openchem and py2opsin import)
Writes refs_checked.json (per paper: problems and warnings) and prints a summary. A route with a PROBLEM is not usable until fixed; a WARNING is for a human to look at.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

S = Path(__file__).resolve().parent  # the folder that holds references/ (refs_out in the working copy)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from rdkit import Chem, RDLogger  # noqa: E402

RDLogger.DisableLog("rdApp.*")
from openchem.services.java_setup import java_home  # noqa: E402

home = java_home()
if home:
    os.environ["PATH"] = str(home / "bin") + os.pathsep + os.environ["PATH"]
import warnings  # noqa: E402

warnings.simplefilter("ignore")
from py2opsin import py2opsin  # noqa: E402


def fold(name):
    """py2opsin writes names through the Windows code page; fold the typographic characters of a printed name to ASCII first."""
    import unicodedata

    table = {"′": "'", "″": "''", "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-", "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "±": "+-", "’": "'", " ": " "}
    for k, v in table.items():
        name = name.replace(k, v)
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()


def largest(mol):
    frags = Chem.GetMolFrags(mol, asMols=True)
    return max(frags, key=lambda m: m.GetNumHeavyAtoms()) if len(frags) > 1 else mol


def canon(smiles, keep_stereo=True):
    """Canonical SMILES of the largest fragment (a salt's counter-ion is not part of the structure compared)."""
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        return None
    mol = largest(mol)
    if not keep_stereo:
        Chem.RemoveStereochemistry(mol)
    return Chem.MolToSmiles(mol)


def heavy(smiles):
    from collections import Counter as C

    mol = largest(Chem.MolFromSmiles(smiles))
    return C(a.GetSymbol() for a in mol.GetAtoms())


def molecules(doc):
    out = []
    t = doc.get("target") or {}
    if t:
        out.append(("target", t))
    for r in doc.get("reactions") or []:
        out.append((f"step {r.get('step')} product", r.get("product") or {}))
        for x in r.get("reactants") or []:
            out.append((f"step {r.get('step')} reactant", x))
    return out


def check_doc(doc, names_cache):
    problems, warnings_ = [], []
    if doc.get("decision") not in ("route", "excluded"):
        return ["decision is neither route nor excluded"], []
    if doc["decision"] == "excluded":
        if not doc.get("exclusion_reason") or not doc.get("exclusion_detail"):
            problems.append("excluded but reason or detail missing")
        return problems, warnings_
    reactions = doc.get("reactions") or []
    if not reactions:
        return ["route with no reactions"], []
    if len(reactions) > 4:
        problems.append(f"{len(reactions)} reactions (the limit is 4)")
    target = (doc.get("target") or {}).get("smiles")
    ct = canon(target)
    if ct is None:
        problems.append(f"target SMILES does not parse: {target}")
        return problems, warnings_
    products = []
    for r in reactions:
        p = (r.get("product") or {}).get("smiles")
        cp = canon(p)
        if cp is None:
            problems.append(f"step {r.get('step')} product SMILES does not parse: {p}")
            continue
        products.append(cp)
        have = Counter()
        for x in r.get("reactants") or []:
            if canon(x.get("smiles")) is None:
                problems.append(f"step {r.get('step')} reactant SMILES does not parse: {x.get('smiles')}")
            else:
                have.update(heavy(x["smiles"]))
        if not r.get("reactants"):
            problems.append(f"step {r.get('step')} has no reactants")
        need = heavy(p)
        short = {el: need[el] - have[el] for el in need if need[el] > have[el]}
        if short.get("C"):
            problems.append(f"step {r.get('step')}: product has carbon its listed reactants lack: {short}")
        elif short:
            warnings_.append(f"step {r.get('step')}: hetero atoms not in the listed reactants (a reagent supplies them?): {short}")
        if cp in [canon(x.get("smiles")) for x in r.get("reactants") or []]:
            problems.append(f"step {r.get('step')}: the product is one of its own reactants")
    if ct not in products:
        problems.append("the target is not the product of any step")
    # every non-target product consumed exactly once as a made_here reactant elsewhere
    consumed = Counter()
    for r in reactions:
        for c in {canon(x.get("smiles")) for x in r.get("reactants") or []}:  # two equivalents in one reaction are one use
            if c in products:
                consumed[c] += 1
    for p in set(products):
        if p != ct and consumed[p] != 1:
            problems.append(f"intermediate {p} is consumed {consumed[p]} times (expected once)")
    for r in reactions:
        for x in r.get("reactants") or []:
            c = canon(x.get("smiles"))
            if x.get("origin") == "made_here" and c not in products:
                warnings_.append(f"step {r.get('step')}: {x.get('label')} is marked made_here but no step makes it")
    # OPSIN: a printed name against the SMILES
    for where, m in molecules(doc):
        name, smi = (m.get("name") or "").strip(), m.get("smiles")
        if not name or canon(smi) is None:
            continue
        got = names_cache.get(name)
        if got is None:
            warnings_.append(f"{where}: OPSIN cannot read the name '{name[:60]}'")
            continue
        a, b = canon(got, False), canon(smi, False)
        if a != b:
            ia, ib = Chem.MolToInchiKey(Chem.MolFromSmiles(got)), Chem.MolToInchiKey(Chem.MolFromSmiles(smi))
            if ia.split("-")[0] != ib.split("-")[0]:
                warnings_.append(f"{where}: name '{name[:60]}' reads (OPSIN) as {a} but the SMILES is {b}")
        elif canon(got, True) != canon(smi, True) and any(tag in name for tag in ("(R", "(S", "(E", "(Z", "(1R", "(1S", "(2R", "(2S", "(3R", "(3S", "(4R", "(4S", "(5R", "(5S")):
            warnings_.append(f"{where}: same connectivity but the stereochemistry of '{name[:60]}' differs from the SMILES")
    return problems, warnings_


def main():
    stems = sys.argv[1:]
    files = sorted(glob.glob(str(S / "references" / "*.json")))
    if stems:
        files = [f for f in files if Path(f).stem in stems]
    docs = {}
    for f in files:
        try:
            docs[Path(f).stem] = json.load(open(f, encoding="utf-8"))
        except Exception as error:  # noqa: BLE001
            docs[Path(f).stem] = {"_unreadable": str(error)}
    names = sorted({(m.get("name") or "").strip() for d in docs.values() if isinstance(d, dict) and d.get("decision") == "route" for _, m in molecules(d) if (m.get("name") or "").strip()})
    cache = {}
    if names:
        for i in range(0, len(names), 200):
            chunk = names[i : i + 200]
            res = py2opsin([fold(n) for n in chunk])
            for n, s in zip(chunk, res if isinstance(res, list) else [res]):
                cache[n] = s if s else None
    report, tally = {}, Counter()
    for stem, d in docs.items():
        if "_unreadable" in d:
            report[stem] = {"problems": ["JSON unreadable: " + d["_unreadable"]], "warnings": []}
            tally["unreadable"] += 1
            continue
        problems, warns = check_doc(d, cache)
        report[stem] = {"decision": d.get("decision"), "reason": d.get("exclusion_reason"), "steps": len(d.get("reactions") or []), "problems": problems, "warnings": warns}
        tally[d.get("decision") if not problems else "route-with-problems"] += 1
    (S / "refs_checked.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(dict(tally))
    for stem, r in report.items():
        if r["problems"] or r["warnings"]:
            print(f"--- {stem}: {r.get('decision')}")
            for p in r["problems"]:
                print("   PROBLEM:", p[:230])
            for w in r["warnings"]:
                print("   warn:", w[:230])


if __name__ == "__main__":
    main()
