"""Stage 2: fetch each entry's mmCIF and measure every carbon-bound fluorine against the metals (and the nearest N/O).

A ligand fluorine is "organic" here when a carbon of the same residue is within 1.65 A. mmCIF carries no bonds, so that is the
bond test; B-F fluorines (a boron within 1.65 A) are counted apart. Only model 1, alternate location blank or A.
"""
import gzip
import json
import os
import re
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

BASE = sys.argv[1]  # the folder every stage reads and writes (outside the repository)
CACHE = os.path.join(BASE, "cif")
os.makedirs(CACHE, exist_ok=True)
stage1 = json.load(open(os.path.join(BASE, "stage1.json")))
FCOMPS = set(stage1["fcomps"])
ENTRIES = sorted({e for m in stage1["metals"].values() for e in m["sampled"]})
METALS = {"ZN", "MG", "CA", "NA", "K", "FE", "MN", "CU", "CO", "NI"}
TOKEN = re.compile(r"\"[^\"]*\"|'[^']*'|\S+")
HEADERS = {"User-Agent": "OpenChemStudio/1.0 (mailto:death1rock1334@gmail.com)"}


def fetch(entry):
    path = os.path.join(CACHE, entry + ".cif.gz")
    if not os.path.exists(path):
        req = urllib.request.Request(f"https://files.rcsb.org/download/{entry}.cif.gz", headers=HEADERS)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = r.read()
                open(path, "wb").write(data)
                break
            except Exception:
                if attempt == 2:
                    return None
    return path


def atoms_of(path):
    columns, rows, in_loop = [], [], False
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("_atom_site."):
                columns.append(line.strip().split(".", 1)[1])
                in_loop = True
                continue
            if in_loop and columns and not line.startswith("_"):
                if line.startswith(("#", "loop_")):
                    break
                rows.append(TOKEN.findall(line))
    index = {name: i for i, name in enumerate(columns)}
    need = ["group_PDB", "type_symbol", "label_atom_id", "label_comp_id", "label_asym_id", "label_seq_id", "Cartn_x", "Cartn_y", "Cartn_z", "label_alt_id", "pdbx_PDB_model_num"]
    out = []
    for r in rows:
        if len(r) < len(columns):
            continue
        if r[index["pdbx_PDB_model_num"]] != "1" or r[index["label_alt_id"]] not in (".", "A"):
            continue
        out.append((
            r[index["type_symbol"]].upper(), r[index["label_atom_id"]].strip('"'), r[index["label_comp_id"]],
            (r[index["label_asym_id"]], r[index["label_seq_id"]], r[index["label_comp_id"]]),
            r[index["group_PDB"]],
            float(r[index["Cartn_x"]]), float(r[index["Cartn_y"]]), float(r[index["Cartn_z"]]),
        ))
    return out


def analyse(entry):
    path = fetch(entry)
    if path is None:
        return {"entry": entry, "error": "download"}
    atoms = atoms_of(path)
    if not atoms:
        return {"entry": entry, "error": "no atoms"}
    xyz = np.array([[a[5], a[6], a[7]] for a in atoms])
    symbols = np.array([a[0] for a in atoms])
    residues = [a[3] for a in atoms]
    res_ids = {}
    for i, key in enumerate(residues):
        res_ids.setdefault(key, []).append(i)
    pairs, contacts = [], []
    metal_idx = [i for i, s in enumerate(symbols) if s in METALS]
    for i, atom in enumerate(atoms):
        if atom[0] != "F" or atom[2] not in FCOMPS or atom[4] != "HETATM":
            continue
        own = res_ids[atom[3]]
        own_sym = symbols[own]
        d_own = np.linalg.norm(xyz[own] - xyz[i], axis=1)
        carbon = any(s == "C" and d < 1.65 for s, d in zip(own_sym, d_own))
        boron = any(s == "B" and d < 1.65 for s, d in zip(own_sym, d_own))
        if not (carbon or boron):
            continue
        kind = "C-F" if carbon else "B-F"
        dist = np.linalg.norm(xyz - xyz[i], axis=1)
        for j in metal_idx:
            if residues[j] == atom[3] or dist[j] > 4.0:
                continue
            around = np.linalg.norm(xyz - xyz[j], axis=1)
            sphere = [symbols[k] for k in range(len(atoms)) if k != j and around[k] <= 3.0 and symbols[k] in ("N", "O", "S") and residues[k] != atom[3]]
            pairs.append({"entry": entry, "metal": symbols[j], "metal_res": list(residues[j]), "F_comp": atom[2], "F_name": atom[1], "kind": kind,
                          "distance": round(float(dist[j]), 3), "metal_sphere_NOS": len(sphere), "sphere": sorted(sphere)})
        if kind == "C-F":
            for k in range(len(atoms)):
                if residues[k] == atom[3] or symbols[k] not in ("N", "O") or dist[k] > 3.8:
                    continue
                contacts.append({"entry": entry, "F_comp": atom[2], "partner": symbols[k], "partner_comp": atoms[k][2], "partner_name": atoms[k][1], "distance": round(float(dist[k]), 2),
                                 "ligand_partner": atoms[k][4] == "HETATM" and atoms[k][2] not in ("HOH", "DOD")})
    nF = sum(1 for a in atoms if a[0] == "F" and a[2] in FCOMPS and a[4] == "HETATM")
    return {"entry": entry, "organic_F": nF, "pairs": pairs, "contacts": contacts}


results = []
lock = threading.Lock()


def work(entry):
    try:
        res = analyse(entry)
    except Exception as exc:  # noqa: BLE001 - record and carry on, a survey must not die on one file
        res = {"entry": entry, "error": repr(exc)}
    with lock:
        results.append(res)
        if len(results) % 100 == 0:
            print(len(results), "of", len(ENTRIES), flush=True)


with ThreadPoolExecutor(max_workers=6) as pool:
    list(pool.map(work, ENTRIES))
json.dump(results, open(os.path.join(BASE, "stage2.json"), "w"))
print("done", len(results), "errors", sum(1 for r in results if "error" in r))
