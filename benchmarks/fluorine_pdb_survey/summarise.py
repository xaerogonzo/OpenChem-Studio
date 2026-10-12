import sys
import os
import json
from collections import Counter, defaultdict

BASE = sys.argv[1]  # the folder every stage reads and writes (outside the repository)
res = json.load(open(os.path.join(BASE, "stage2.json")))
ok = [r for r in res if "error" not in r]
print("entries", len(res), "ok", len(ok), "with ligand F atoms", sum(1 for r in ok if r["organic_F"]))
pairs = [p for r in ok for p in r["pairs"]]
cf = [p for p in pairs if p["kind"] == "C-F"]
bf = [p for p in pairs if p["kind"] == "B-F"]
print("C-F...metal pairs within 4.0 A:", len(cf), " B-F:", len(bf))
by = defaultdict(list)
for p in cf:
    by[p["metal"]].append(p)
print("\nmetal: pairs<=4.0 | <=3.5 | <=3.0 | <=2.8 | closest; entries")
for m in ["ZN", "MG", "CA", "NA", "K", "FE", "MN", "CU", "CO", "NI"]:
    ds = sorted(p["distance"] for p in by[m])
    ent = len({p["entry"] for p in by[m]})
    print(f"{m:3s} {len(ds):4d} | {sum(d<=3.5 for d in ds):4d} | {sum(d<=3.0 for d in ds):3d} | {sum(d<=2.8 for d in ds):3d} | closest {ds[:6]}; {ent} entries")
print("\nthe closest C-F...M pairs overall:")
for p in sorted(cf, key=lambda p: p["distance"])[:25]:
    print(p["entry"], p["metal"], p["F_comp"], p["F_name"], p["distance"], "metal's N/O/S within 3.0:", p["metal_sphere_NOS"])
print("\nB-F pairs closest:")
for p in sorted(bf, key=lambda p: p["distance"])[:6]:
    print(p["entry"], p["metal"], p["F_comp"], p["distance"])

# H-bond partners
contacts = [c for r in ok for c in r["contacts"]]
print("\nC-F...N/O contacts<=3.8:", len(contacts))
def hist(sel, name):
    c = Counter(int((x["distance"] - 2.4) / 0.1) for x in sel if 2.4 <= x["distance"] < 3.8)
    print(name, " ".join(f"{2.4 + 0.1*k:.1f}:{c.get(k,0)}" for k in range(14)))
hist([c for c in contacts if c["partner"] == "N"], "N all   ")
hist([c for c in contacts if c["partner"] == "O" and c["partner_comp"] in ("HOH", "DOD")], "O water ")
hist([c for c in contacts if c["partner"] == "O" and c["partner_comp"] not in ("HOH", "DOD")], "O other ")
