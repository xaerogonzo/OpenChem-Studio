import gzip
import json
import os
import re
import sys
import urllib.request
from collections import Counter

import numpy as np

BASE = sys.argv[1]  # the folder every stage reads and writes (outside the repository)
TOKEN = re.compile(r"\"[^\"]*\"|'[^']*'|\S+")
stage1 = json.load(open(os.path.join(BASE, "stage1.json")))
FCOMPS = set(stage1["fcomps"])
ENTRIES = sorted({e for m in stage1["metals"].values() for e in m["sampled"]})


def atoms_of(entry):
    columns, rows, in_loop = [], [], False
    with gzip.open(os.path.join(BASE, "cif", entry + ".cif.gz"), "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("_atom_site."):
                columns.append(line.strip().split(".", 1)[1])
                in_loop = True
                continue
            if in_loop and columns and not line.startswith("_"):
                if line.startswith(("#", "loop_")):
                    break
                rows.append(TOKEN.findall(line))
    idx = {n: i for i, n in enumerate(columns)}
    out = []
    for r in rows:
        if len(r) < len(columns) or r[idx["pdbx_PDB_model_num"]] != "1" or r[idx["label_alt_id"]] not in (".", "A"):
            continue
        out.append((r[idx["type_symbol"]].upper(), r[idx["label_atom_id"]].strip('"'), r[idx["label_comp_id"]],
                    (r[idx["label_asym_id"]], r[idx["label_seq_id"]], r[idx["label_comp_id"]]), r[idx["group_PDB"]],
                    float(r[idx["Cartn_x"]]), float(r[idx["Cartn_y"]]), float(r[idx["Cartn_z"]])))
    return out


# 1. look at the close metal contacts
for entry, ligand, metal in [("6QXD", "JKB", "CU"), ("6EI4", "B5N", "CU"), ("7ZLU", "U2F", "CA"), ("1GZG", "LAF", "NA")]:
    atoms = atoms_of(entry)
    xyz = np.array([[a[5], a[6], a[7]] for a in atoms])
    fs = [i for i, a in enumerate(atoms) if a[2] == ligand and a[0] == "F"]
    ms = [i for i, a in enumerate(atoms) if a[0] == metal]
    print("\n==", entry, ligand, metal, "F atoms", len(fs), "metals", len(ms))
    for m in ms:
        for f in fs:
            d = np.linalg.norm(xyz[m] - xyz[f])
            if d < 3.2:
                near = sorted(((float(np.linalg.norm(xyz[m] - xyz[k])), atoms[k][2] + ":" + atoms[k][1]) for k in range(len(atoms)) if k != m and np.linalg.norm(xyz[m] - xyz[k]) < 3.0))
                print(f"  {metal} {atoms[m][3]} -- F {atoms[f][1]} {d:.2f} ; metal sphere:", [(round(x, 2), n) for x, n in near][:9])

# 2. hydrogen-bond control: protein N (ATOM) against a ligand C-F fluorine and against a ligand terminal oxygen
fN, oN = Counter(), Counter()
nF = nO = 0
for entry in ENTRIES:
    atoms = atoms_of(entry)
    xyz = np.array([[a[5], a[6], a[7]] for a in atoms])
    sym = np.array([a[0] for a in atoms])
    prot_n = np.array([i for i, a in enumerate(atoms) if a[4] == "ATOM" and a[0] == "N"])
    if len(prot_n) == 0:
        continue
    by_res = {}
    for i, a in enumerate(atoms):
        if a[4] == "HETATM" and a[2] not in ("HOH", "DOD"):
            by_res.setdefault(a[3], []).append(i)
    for key, members in by_res.items():
        if len(members) < 3:
            continue
        for i in members:
            if sym[i] not in ("F", "O"):
                continue
            neigh = [k for k in members if k != i and np.linalg.norm(xyz[k] - xyz[i]) < 1.65]
            if sym[i] == "F" and atoms[i][2] in FCOMPS and any(sym[k] == "C" for k in neigh):
                bucket, kind = fN, "F"
            elif sym[i] == "O" and len(neigh) == 1 and sym[neigh[0]] == "C":
                bucket, kind = oN, "O"
            else:
                continue
            d = np.linalg.norm(xyz[prot_n] - xyz[i], axis=1)
            for x in d[(d >= 2.4) & (d < 3.8)]:
                bucket[int((x - 2.4) / 0.1)] += 1
            if kind == "F":
                nF += 1
            else:
                nO += 1
print("\nprotein-N partners per 0.1 A bin, 2.4 to 3.7; ligand atoms:", "C-F", nF, " terminal C-O", nO)
for name, c, n in (("C-F", fN, nF), ("C-O", oN, nO)):
    print(f"{name}: " + " ".join(f"{2.4 + 0.1 * k:.1f}:{c.get(k, 0)}" for k in range(14)))
    near = sum(c.get(k, 0) for k in range(4, 8))   # 2.8 to 3.1
    far = sum(c.get(k, 0) for k in range(9, 13))   # 3.3 to 3.7
    print(f"   per ligand atom: 2.8-3.1 A {near / n:.3f}   3.3-3.7 A {far / n:.3f}   ratio near/far {near / far:.2f}")
