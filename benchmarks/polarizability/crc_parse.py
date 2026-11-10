import re, json, collections
S = r"C:/Users/pmpd/AppData/Local/Temp/claude/4cd43690c7cd3765/576dc894-3071-410c-bc47-8ed7c7d32f84/scratchpad/"
lines = [l.strip() for l in open(S + "crc_pol2.txt", encoding="utf-8") if l.strip()]
lines = [l for l in lines if not l.startswith("=== PAGE") and l not in ("Atomic and Molecular Polarizabilities", "Name", "Mol. Form.", "Ref.", "Note", "Atomic") and not re.match(r"^10-\d+$", l) and "α/10" not in l]
FORM = re.compile(r"^(?:[A-Z][a-z]?\d*)+$")
VAL = re.compile(r"^\d+\.\s?\d+$")
idx = [i for i in range(1, len(lines) - 1) if FORM.match(lines[i]) and VAL.match(lines[i + 1]) and not FORM.match(lines[i - 1]) ]
rows = []
for k, i in enumerate(idx):
    j = idx[k + 1] - 1 if k + 1 < len(idx) else len(lines)
    rec = lines[i + 2: j]
    rows.append({"name": lines[i - 1], "formula": lines[i], "value": float(lines[i + 1].replace(" ", "")), "tail": rec})


def comp(f):
    c = {}
    for el, n in re.findall(r"([A-Z][a-z]?)(\d*)", f):
        c[el] = c.get(el, 0) + (int(n) if n else 1)
    return c


out = []
for r in rows:
    tail = " ".join(r["tail"]).lower()
    r["composition"] = comp(r["formula"])
    r["calculated"] = any(w in tail for w in ("calculated", "theor", "ab initio", "semi"))
    out.append(r)
json.dump(out, open(S + "crc_mol.json", "w", encoding="utf-8"), indent=1)
exp = [r for r in out if not r["calculated"]]
print(len(out), "records;", len(exp), "not marked calculated")
by = collections.Counter()
for r in exp:
    for e in r["composition"]:
        by[e] += 1
print(dict(by))
for e in ("B", "Si", "P", "Se", "Na", "Fe", "Pt"):
    print(e, [(r["formula"], r["value"]) for r in exp if e in r["composition"]][:20])
print([ (r["formula"], r["value"], r["tail"]) for r in out if r["formula"] in ("H2O", "NH3", "CH4")])
