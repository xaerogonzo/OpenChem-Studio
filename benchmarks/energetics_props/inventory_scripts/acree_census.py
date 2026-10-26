"""Census of Acree 2010 (phase-change enthalpy compendium): entries that look energetic, with a numeric fusion
temperature and/or a numeric sublimation enthalpy. Counts and page locators only."""
import re, sys, json, pymupdf
sys.stdout.reconfigure(encoding="utf-8")
PDF = "D:/Xaero Stuff/Documents/Sci Downloads/acree2010.pdf"
d = pymupdf.open(PDF)
CAS = re.compile(r"^\d{2,7}-\d{2}-\d$")
FORM = re.compile(r"^(?:[A-Z][a-z]?\d*)+$")
toks = []  # (token, pdf page)
first_table_page = None
for i, p in enumerate(d):
    t = re.sub(r"[\x00-\x08]", "", p.get_text())
    if first_table_page is None and "Molecular Formula CAS Reg No Compound" in " ".join(t.split()):
        first_table_page = i + 1
    if first_table_page is None:
        continue
    for w in t.split():
        toks.append((w, i + 1))
entries = []   # (formula, cas, text, page)
starts = [k for k in range(1, len(toks)) if CAS.match(toks[k][0]) and FORM.match(toks[k - 1][0]) and any(c.isdigit() for c in toks[k - 1][0])]
for j, k in enumerate(starts):
    end = starts[j + 1] - 1 if j + 1 < len(starts) else len(toks)
    text = " ".join(w for w, _ in toks[k + 1:end])
    entries.append((toks[k - 1][0], toks[k][0], text, toks[k][1]))
ENERGETIC = re.compile(r"nitro|nitrat|nitramin|azid|furazan|tetrazol|tetrazin|oxadiazol|peroxid|picr|fulminat", re.I)
NUM = r"\d+(?:\.\d+)?"
fus = re.compile(r"fusH\s+(" + NUM + r")\S*\s+(" + NUM + r")\b")
sub = re.compile(r"subH\s+(?:\d+[–-]\d+\s+)?(" + NUM + ")")
def has_NO(f):
    return re.search(r"N(?!a|b|i|e|d)", f) is not None and re.search(r"O(?!s)", f) is not None
cand = [e for e in entries if has_NO(e[0]) and ENERGETIC.search(e[2][:120])]
res = {
    "table_first_pdf_page": first_table_page,
    "entries_total": len(entries),
    "energetic_keyword_entries_with_N_and_O": len(cand),
    "with_fusH_and_Tfus": sum(1 for e in cand if fus.search(e[2])),
    "with_subH": sum(1 for e in cand if sub.search(e[2])),
    "with_both": sum(1 for e in cand if fus.search(e[2]) and sub.search(e[2])),
}
POLY = re.compile(r"\b(di|tri|tetra|penta|hexa|octa)nitro|nitramin|nitrat(e|o)\b|dinitrate|trinitrate|tetranitrate|azid|picr|furazan|tetrazol|tetrazin|peroxid|nitroguanid", re.I)
poly = [e for e in cand if POLY.search(e[2][:120])]
res["polynitro_nitrate_azide_azole_peroxide_entries"] = len(poly)
res["poly_with_fusH_and_Tfus"] = sum(1 for e in poly if fus.search(e[2]))
res["poly_with_subH"] = sum(1 for e in poly if sub.search(e[2]))
res["poly_with_both"] = sum(1 for e in poly if fus.search(e[2]) and sub.search(e[2]))
res["poly_pages"] = [min(e[3] for e in poly), max(e[3] for e in poly)]
print("POLY SAMPLE")
for e in poly[:: max(1, len(poly) // 10)][:10]:
    print(e[3], e[0], e[1], e[2][:110])
print(json.dumps(res, indent=1))
for e in cand[:: max(1, len(cand) // 14)][:14]:
    print(e[3], e[0], e[1], e[2][:130])
json.dump({"res": res, "cand": [(e[0], e[1], e[2][:60], e[3]) for e in cand]}, open(sys.argv[1], "w", encoding="utf-8"))
