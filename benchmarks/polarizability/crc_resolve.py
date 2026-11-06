import json, re, sys
S = r"C:/Users/pmpd/AppData/Local/Temp/claude/4cd43690c7cd3765/576dc894-3071-410c-bc47-8ed7c7d32f84/scratchpad/"
from openchem.chem.naming_providers import opsin_structures_for_names
from rdkit import Chem
from rdkit.Chem.rdMolDescriptors import CalcMolFormula

rows = [r for r in json.load(open(S + "crc_mol.json", encoding="utf-8")) if not r["calculated"] and "D" not in r["composition"]]
rows = [r for r in rows if sum(r["composition"].values()) <= 40]
names = [re.sub(r"\(\d\)$", "", r["name"]).replace("\u2019", "'").encode("ascii", "ignore").decode() for r in rows]
res = opsin_structures_for_names(names)
print(type(res), len(res))
out = []
ok = bad = 0
for r, n, s in zip(rows, names, res):
    smi = s if isinstance(s, str) else getattr(s, "smiles", None)
    r2 = dict(r, name_used=n, smiles=None, match=False)
    if smi:
        m = Chem.MolFromSmiles(smi)
        if m is not None:
            f = CalcMolFormula(m)
            comp = {}
            for el, k in re.findall(r"([A-Z][a-z]?)(\d*)", f):
                comp[el] = comp.get(el, 0) + (int(k) if k else 1)
            r2["smiles"] = smi
            r2["match"] = comp == r["composition"]
    ok += r2["match"]; bad += not r2["match"]
    out.append(r2)
json.dump(out, open(S + "crc_resolved.json", "w", encoding="utf-8"), indent=1)
print("formula-matched", ok, "not", bad)
