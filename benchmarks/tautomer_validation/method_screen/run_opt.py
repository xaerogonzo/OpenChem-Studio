"""Step 1 of the Phase R method screen: PBE0/def2-TZVP optimizations of the DEVELOPMENT systems' conformer pools.

Pool recipe (the planned v4 recipe): per stereo class, 50 ETKDGv3 embeds (seed 11, never 0),
MMFF94 minimisation, energy-sorted greedy prune on heavy atoms + polar H with mirror alignment
(0.3 A), at most CAP lowest-MMFF survivors go to ORCA. Held-out systems are NOT in this script.
"""
import json, pathlib, re, subprocess, sys, shutil, concurrent.futures as cf
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign
from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers, StereoEnumerationOptions

ROOT = pathlib.Path(r"D:\_scratch\screen")
SEED, EMBEDS, THR, CAP = 11, 50, 0.3, 6
SYSTEMS = {
    "cytosine": {"enol_amino": "Nc1ccnc(O)n1", "keto_amino": "Nc1cc[nH]c(=O)n1", "imino_oxo": "N=C1C=CNC(=O)N1"},
    "acetaldimine_vinylamine": {"acetaldimine": "CC=N", "vinylamine": "C=CN"},
    "pyridone": {"hydroxypyridine": "Oc1ccccn1", "pyridone": "O=c1cccc[nH]1"},
}


def pool(mol_noH):
    m = Chem.AddHs(mol_noH)
    p = AllChem.ETKDGv3(); p.randomSeed = SEED
    ids = list(AllChem.EmbedMultipleConfs(m, EMBEDS, p))
    if not ids:
        return m, []
    res = AllChem.MMFFOptimizeMoleculeConfs(m, maxIters=2000)
    amap = [(a.GetIdx(), a.GetIdx()) for a in m.GetAtoms()
            if a.GetAtomicNum() > 1 or a.GetNeighbors()[0].GetAtomicNum() in (7, 8, 15, 16)]
    rows = sorted((r[1], c) for r, c in zip(res, ids) if r[0] == 0)
    kept = []
    for e, c in rows:
        same = False
        for _e2, c2 in kept:
            a = rdMolAlign.AlignMol(Chem.Mol(m), Chem.Mol(m), prbCid=c, refCid=c2, atomMap=amap)
            b = rdMolAlign.AlignMol(Chem.Mol(m), Chem.Mol(m), prbCid=c, refCid=c2, atomMap=amap, reflect=True)
            if min(a, b) < THR:
                same = True; break
        if not same:
            kept.append((e, c))
    return m, kept[:CAP]


def jobs():
    out = []
    for system, tautomers in SYSTEMS.items():
        for tname, smi in tautomers.items():
            base = Chem.MolFromSmiles(smi)
            opts = StereoEnumerationOptions(onlyUnassigned=True, unique=True, tryEmbedding=False, maxIsomers=0)
            classes = list(EnumerateStereoisomers(base, options=opts)) or [base]
            for si, iso in enumerate(classes):
                m, kept = pool(iso)
                for ci, (e, cid) in enumerate(kept):
                    conf = m.GetConformer(cid)
                    xyz = "\n".join(f"{a.GetSymbol()} {conf.GetAtomPosition(a.GetIdx()).x:.6f} "
                                    f"{conf.GetAtomPosition(a.GetIdx()).y:.6f} {conf.GetAtomPosition(a.GetIdx()).z:.6f}"
                                    for a in m.GetAtoms())
                    out.append({"system": system, "tautomer": tname, "stereo": si, "stereo_smiles": Chem.MolToSmiles(iso),
                                "conf": ci, "mmff": e, "xyz": xyz, "natoms": m.GetNumAtoms()})
    return out


def run(j):
    name = f"{j['system']}__{j['tautomer']}__s{j['stereo']}__c{j['conf']}"
    d = ROOT / "jobs" / name; d.mkdir(parents=True, exist_ok=True)
    done = d / "result.json"
    if done.exists():
        return json.loads(done.read_text())
    (d / "in.inp").write_text(f"! PBE0 def2-TZVP Opt\n%pal nprocs 4 end\n* xyz 0 1\n{j['xyz']}\n*\n")
    out = subprocess.run([r"D:\ORCA\orca.exe", "in.inp"], cwd=d, capture_output=True, text=True).stdout
    en = re.findall(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", out)
    ok = "OPTIMIZATION RUN DONE" in out and bool(en)
    res = {k: v for k, v in j.items() if k != "xyz"}
    res.update({"name": name, "converged": ok, "energy_hartree": float(en[-1]) if ok else None,
                "xyz_file": str(d / "in.xyz") if (d / "in.xyz").exists() else None})
    done.write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    ROOT.mkdir(exist_ok=True)
    js = jobs()
    print("jobs:", len(js), [(j["system"], j["tautomer"], j["stereo"], j["conf"], round(j["mmff"], 2)) for j in js], flush=True)
    with cf.ThreadPoolExecutor(6) as ex:
        for r in ex.map(run, js):
            print(r["name"], "mmff", round(r["mmff"], 2), "E", r["energy_hartree"], "conv", r["converged"], flush=True)
    print("ALL DONE", flush=True)
