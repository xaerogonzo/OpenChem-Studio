import sys
"""Stage 1: which PDB entries hold BOTH a fluorine-containing ligand and one of the ten metals, resolution 2.5 A or better."""
import json
import random
import urllib.error
import urllib.request

URL = "https://search.rcsb.org/rcsbsearch/v2/query"
HEADERS = {"Content-Type": "application/json", "User-Agent": "OpenChemStudio/1.0 (mailto:death1rock1334@gmail.com)"}
OUT = sys.argv[1]  # the folder every stage reads and writes (outside the repository)
CAP = 700
METALS = {"ZN": ["ZN"], "MG": ["MG"], "CA": ["CA"], "NA": ["NA"], "K": ["K"], "FE": ["FE", "FE2"], "MN": ["MN"], "CU": ["CU", "CU1"], "CO": ["CO"], "NI": ["NI"]}


def post(request):
    req = urllib.request.Request(URL, data=json.dumps(request).encode(), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


formula = {"type": "terminal", "service": "chemical", "parameters": {"value": "F", "type": "formula", "match_subset": True}}
fcomps = post({"query": formula, "return_type": "mol_definition", "request_options": {"return_all_hits": True}})["result_set"]
fcomps = [x["identifier"] if isinstance(x, dict) else x for x in fcomps]
fcomps = sorted(set(fcomps) -{"F", "BF4", "SF6", "PF6", "AF3", "ALF", "MGF", "BEF", "ALF", "TFA"})
print("fluorine components", len(fcomps))


def text(attribute, operator, value):
    return {"type": "terminal", "service": "text", "parameters": {"attribute": attribute, "operator": operator, "value": value}}


result = {}
rng = random.Random(7)
for metal, ids in METALS.items():
    query = {
        "type": "group",
        "logical_operator": "and",
        "nodes": [
            text("rcsb_nonpolymer_entity_container_identifiers.nonpolymer_comp_id", "in", fcomps),
            text("rcsb_nonpolymer_entity_container_identifiers.nonpolymer_comp_id", "in", ids),
            text("rcsb_entry_info.resolution_combined", "less_or_equal", 2.5),
        ],
    }
    try:
        hits = post({"query": query, "return_type": "entry", "request_options": {"return_all_hits": True}}).get("result_set", [])
    except urllib.error.HTTPError as exc:
        print(metal, "HTTP", exc.code, exc.read()[:300])
        hits = []
    hits = [x["identifier"] if isinstance(x, dict) else x for x in hits]
    total = len(hits)
    sample = sorted(rng.sample(hits, CAP)) if total > CAP else sorted(hits)
    result[metal] = {"total": total, "sampled": sample}
    print(metal, total, len(sample))

import os

os.makedirs(OUT, exist_ok=True)
json.dump({"fcomps": fcomps, "metals": result}, open(os.path.join(OUT, "stage1.json"), "w"))
print("unique entries to fetch", len({e for m in result.values() for e in m["sampled"]}))
