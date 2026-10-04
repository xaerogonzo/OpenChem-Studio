"""Apply SELECTION_RULE.md to the single-point results. Includes the PBE0 baseline (opt energies)."""
import json, pathlib, itertools
from openchem.chem.tautomer_validation import load_spec

ROOT = pathlib.Path(r"D:\_scratch\screen")
H = 627.5094740631
spec = load_spec()
TIE, MAE_TOL, MAX_TOL = 1.0, 1.0, 2.0
SYSTEMS = ["cytosine", "acetylacetone", "acetaldimine_vinylamine", "pyridone"]

# tautomer id used by the spec -> id used in the job names
ALIAS = {}

def energies(func):
    """{system: {tautomer: lowest hartree}} for one functional."""
    out = {}
    if func == "PBE0":
        for r in (ROOT / "jobs").glob("*/result.json"):
            j = json.loads(r.read_text())
            if j["converged"]:
                e = out.setdefault(j["system"], {}); e[j["tautomer"]] = min(e.get(j["tautomer"], 0.0), j["energy_hartree"])
        # acetylacetone from the earlier pool run (PBE0 energies)
        a = {"diketo": [-345.532857749307, -345.532857557030, -345.532855034378, -345.532866339451],
             "enol": [-345.543873983520, -345.520363094162, -345.520375460775]}
        out["acetylacetone"] = {k: min(v) for k, v in a.items()}
        return out
    for r in (ROOT / "sp" / func).glob("*/result.json"):
        j = json.loads(r.read_text())
        if j["energy_hartree"] is None:
            continue
        e = out.setdefault(j["system"], {})
        e[j["tautomer"]] = min(e.get(j["tautomer"], 0.0), j["energy_hartree"])
    return out


def evaluate(system_id, comp):
    s = spec.system(system_id)
    ref = {t.id: t.reference_kcal for t in s.tautomers}
    missing = [t for t in ref if t not in comp]
    if missing:
        return {"error": f"missing {missing}"}
    rz = min(ref.values()); cz = min(comp[t] for t in ref)
    dref = {t: ref[t] - rz for t in ref}
    dcomp = {t: (comp[t] - cz) * H for t in ref}
    err = {t: abs(dcomp[t] - dref[t]) for t in ref}
    rank_ok = True
    for a, b in itertools.combinations(ref, 2):
        if abs(dref[a] - dref[b]) >= TIE and (dref[a] - dref[b]) * (dcomp[a] - dcomp[b]) <= 0:
            rank_ok = False
    mae = sum(err.values()) / len(err)
    return {"ref": dref, "comp": {k: round(v, 2) for k, v in dcomp.items()}, "err": {k: round(v, 2) for k, v in err.items()},
            "mae": round(mae, 2), "max": round(max(err.values()), 2), "rank_ok": rank_ok,
            "gate": rank_ok and mae <= MAE_TOL and max(err.values()) <= MAX_TOL}


if __name__ == "__main__":
    summary = {}
    for func in ["PBE0", "M062X", "wB97M-V", "revDSD"]:
        en = energies(func)
        print(f"\n===== {func}")
        worst, eligible, gates = 0.0, True, True
        for sid in SYSTEMS:
            r = evaluate(sid, en.get(sid, {}))
            print(f"  {sid}: {r}")
            if "error" in r:
                eligible = False; continue
            eligible &= r["rank_ok"]; gates &= r["gate"]; worst = max(worst, r["max"])
        summary[func] = {"eligible": eligible, "worst_max_error": round(worst, 2), "passes_full_gate": gates}
        print("  ->", summary[func])
    print("\nSUMMARY", json.dumps(summary, indent=1))
