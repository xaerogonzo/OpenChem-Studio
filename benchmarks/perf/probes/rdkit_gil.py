import threading, time
import rdkit
from rdkit import Chem
from rdkit.Chem import AllChem
from benchmarks.perf.scenarios import HEAVY_SMILES
print("rdkit", rdkit.__version__)
base = Chem.AddHs(Chem.MolFromSmiles(HEAVY_SMILES))

def measure(fn, label):
    gaps = []
    t = threading.Thread(target=fn); t.start()
    last = time.perf_counter()
    while t.is_alive():
        time.sleep(0.005)
        now = time.perf_counter(); gaps.append((now - last) * 1000); last = now
    t.join(); gaps.sort()
    print(f"{label:46s} ticks={len(gaps):5d} p50={gaps[len(gaps)//2]:6.1f}ms max={gaps[-1]:6.0f}ms over100={sum(g>100 for g in gaps)}")

def embed():
    m = Chem.Mol(base); AllChem.EmbedMultipleConfs(m, 10, randomSeed=7); embed.mol = m
measure(embed, "EmbedMultipleConfs (1 thread) in a thread")

def per_conf():
    m = Chem.Mol(embed.mol)
    for cid in range(m.GetNumConformers()):
        ff = AllChem.MMFFGetMoleculeForceField(m, AllChem.MMFFGetMoleculeProperties(m), confId=cid)
        ff.Minimize(maxIts=2000, forceTol=1e-4)
measure(per_conf, "ForceField.Minimize per conformer")

def confs_api():
    m = Chem.Mol(embed.mol); AllChem.MMFFOptimizeMoleculeConfs(m, numThreads=1, maxIters=2000)
measure(confs_api, "MMFFOptimizeMoleculeConfs numThreads=1")

def confs_api_mt():
    m = Chem.Mol(embed.mol); AllChem.MMFFOptimizeMoleculeConfs(m, numThreads=4, maxIters=2000)
measure(confs_api_mt, "MMFFOptimizeMoleculeConfs numThreads=4")
