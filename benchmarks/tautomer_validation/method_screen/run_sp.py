"""Step 2: single points of candidate functionals on the PBE0/def2-TZVP optimized development geometries.
Rule: SELECTION_RULE.md (written before any number here existed). Development systems only."""
import json, pathlib, re, subprocess, concurrent.futures as cf

ROOT = pathlib.Path(r"D:\_scratch\screen")
FUNCS = {
    "M062X": "! M062X def2-TZVP",
    "wB97M-V": "! wB97M-V def2-TZVP",
    "revDSD": "! revDSD-PBEP86-D4/2021 def2-TZVP def2-TZVP/C",
}


def geometries():
    out = []
    for r in sorted((ROOT / "jobs").glob("*/result.json")):
        j = json.loads(r.read_text())
        if j["converged"] and j["xyz_file"]:
            out.append({"system": j["system"], "tautomer": j["tautomer"], "name": j["name"],
                        "xyz_file": j["xyz_file"], "pbe0": j["energy_hartree"]})
    acac = pathlib.Path(r"D:\_scratch\acac")
    for tag, tautomer, path in [("diketo_c0", "diketo", acac / "pool3" / "diketo_c0"), ("diketo_c1", "diketo", acac / "pool3" / "diketo_c1"),
                                ("diketo_c2", "diketo", acac / "pool3" / "diketo_c2"), ("enol_c0", "enol", acac / "pool3" / "enol_c0"),
                                ("enol_c1", "enol", acac / "pool3" / "enol_c1"), ("diketo_seed0", "diketo", acac / "diketo_seed0")]:
        if (path / "in.xyz").exists():
            out.append({"system": "acetylacetone", "tautomer": tautomer, "name": f"acetylacetone__{tag}",
                        "xyz_file": str(path / "in.xyz"), "pbe0": None})
    return out


def run(item):
    g, fname = item
    d = ROOT / "sp" / fname / g["name"]; d.mkdir(parents=True, exist_ok=True)
    done = d / "result.json"
    if done.exists():
        return json.loads(done.read_text())
    lines = pathlib.Path(g["xyz_file"]).read_text().splitlines()[2:]
    body = "\n".join(l for l in lines if l.strip())
    (d / "in.inp").write_text(f"{FUNCS[fname]}\n%pal nprocs 4 end\n* xyz 0 1\n{body}\n*\n")
    out = subprocess.run([r"D:\ORCA\orca.exe", "in.inp"], cwd=d, capture_output=True, text=True).stdout
    en = re.findall(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", out)
    res = {"functional": fname, **{k: g[k] for k in ("system", "tautomer", "name", "pbe0")},
           "energy_hartree": float(en[-1]) if en and "ORCA TERMINATED NORMALLY" in out else None}
    done.write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    gs = geometries()
    items = [(g, f) for f in FUNCS for g in gs]
    print("geometries:", len(gs), "single points:", len(items), flush=True)
    with cf.ThreadPoolExecutor(6) as ex:
        for r in ex.map(run, items):
            print(r["functional"], r["name"], r["energy_hartree"], flush=True)
    print("ALL DONE", flush=True)
