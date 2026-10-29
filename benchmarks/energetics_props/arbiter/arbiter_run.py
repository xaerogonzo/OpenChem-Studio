"""Drive the computed gas-phase enthalpy arbiter (PLAN.md): conformers, ORCA, ensemble, reaction enthalpies.

    python arbiter_run.py conformers NAME [NAME ...] [--keep 30]
    python arbiter_run.py opt        NAME [NAME ...] [--jobs 4] [--procs 4]     r2SCAN-3c geometry scan of every conformer
    python arbiter_run.py freq       NAME [NAME ...]                           tight optimisation + frequencies, low-energy ones
    python arbiter_run.py select     NAME [NAME ...]                           free energies, duplicates, imaginary modes
    python arbiter_run.py sp         NAME [NAME ...] [--basis TZ|QZ]           DLPNO-CCSD(T) single points
    python arbiter_run.py report     [--basis TZ|QZ] [--targets]

Raw ORCA files live outside the repository (SCRATCH); only the summaries written by `report` are committed. Every stage is
re-runnable: a finished job is detected from its output and skipped, an unfinished or failed one is run again and a failure is
reported by name rather than dropped. ORCA is called with a backslash path (a forward-slash path kills it at startup).
`report` withholds every scheme whose target is one of the plan's two questions unless --targets is given: the validation set is
read first (PLAN.md).
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRATCH = Path(r"D:\OpenChemStudio-scratch\arbiter")
ORCA = Path(r"D:\ORCA\orca.exe")
RESULTS = HERE / "results"
SEED = 20261029


def _core():
    spec = importlib.util.spec_from_file_location("epb_arbiter_core_run", HERE / "arbiter_core.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["epb_arbiter_core_run"] = module
    spec.loader.exec_module(module)
    return module


core = _core()


def _embeddings(n_heavy: int) -> int:
    """More embeddings for the molecules with several hydroxyl or nitrate rotors: the minima of a hydrogen-bonded polyol are
    numerous, and random embedding finds each with small probability."""
    return 50 if n_heavy <= 3 else 300 if n_heavy <= 6 else 1500


def conformers(name: str, keep: int = 30, window_kj: float = 40.0, rmsd: float = 0.05) -> list[Path]:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.Chem import rdMolAlign

    smiles = core.REFERENCES[name][0]
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    params = AllChem.ETKDGv3()
    params.randomSeed = SEED
    params.onlyHeavyAtomsForRMS = False          # a hydroxyl or nitrate rotamer differs by a hydrogen or an oxygen only
    params.pruneRmsThresh = rmsd
    cids = list(AllChem.EmbedMultipleConfs(mol, _embeddings(mol.GetNumHeavyAtoms()), params))
    if not cids:
        raise RuntimeError(f"{name}: no embedding")
    props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94s")
    if props is None:
        raise RuntimeError(f"{name}: no MMFF parameters")
    energies = []
    for cid in cids:
        ff = AllChem.MMFFGetMoleculeForceField(mol, props, confId=cid)
        ff.Minimize(maxIts=5000)
        energies.append(ff.CalcEnergy())
    order = sorted(range(len(cids)), key=lambda i: energies[i])
    low = energies[order[0]]
    allatoms = [(a.GetIdx(), a.GetIdx()) for a in mol.GetAtoms()]
    kept: list[int] = []
    for i in order:
        if energies[i] - low > window_kj:
            break
        # symmetry-blind all-atom RMSD: keeps symmetry-related rotamers apart (a few extra optimisations, nothing lost);
        # `select` collapses identical energies afterwards. AlignMol moves conformer i rigidly, changing no internal coordinate.
        if any(rdMolAlign.AlignMol(mol, mol, prbCid=cids[i], refCid=cids[j], atomMap=allatoms) < rmsd for j in kept):
            continue
        kept.append(i)
        if len(kept) >= keep:
            break
    out_dir = SCRATCH / name / "conf"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("c[0-9][0-9].xyz"):
        old.unlink()
    paths = []
    for rank, i in enumerate(kept):
        conf = mol.GetConformer(cids[i])
        lines = [str(mol.GetNumAtoms()), f"{name} conformer {rank} mmff {energies[i] - low:.2f}"]
        for a in mol.GetAtoms():
            p = conf.GetAtomPosition(a.GetIdx())
            lines.append(f"{a.GetSymbol():2s} {p.x:12.6f} {p.y:12.6f} {p.z:12.6f}")
        path = out_dir / f"c{rank:02d}.xyz"
        path.write_text("\n".join(lines) + "\n", encoding="ascii")
        paths.append(path)
    print(f"{name}: {len(cids)} embedded, {len(kept)} kept")
    return paths


def _run_orca(inp: Path) -> tuple[bool, str]:
    out = inp.with_suffix(".out")
    if out.exists() and "ORCA TERMINATED NORMALLY" in out.read_text(errors="replace")[-3000:]:
        return True, "cached"
    with out.open("w") as fh:
        subprocess.run([str(ORCA), inp.name], cwd=inp.parent, stdout=fh, stderr=subprocess.STDOUT, check=False)
    return ("ORCA TERMINATED NORMALLY" in out.read_text(errors="replace")[-3000:]), "ran"


def _write(inp: Path, text: str) -> Path:
    inp.write_text(text, encoding="ascii")
    return inp


def _run_all(inputs: list[Path], jobs: int, label: str) -> list[Path]:
    print(f"{len(inputs)} {label}, {jobs} at a time", flush=True)
    failed = []
    with cf.ThreadPoolExecutor(max_workers=jobs) as pool:
        for inp, (ok, how) in zip(inputs, pool.map(_run_orca, inputs)):
            print(("ok  " if ok else "FAIL"), how, inp.parent.parent.name, inp.stem, flush=True)
            if not ok:
                failed.append(inp)
    if failed:
        print("FAILED:", ", ".join(f"{p.parent.parent.name}/{p.stem}" for p in failed), flush=True)
    return failed


def opt(names: list[str], jobs: int, procs: int) -> None:
    inputs = []
    for name in names:
        for xyz in sorted((SCRATCH / name / "conf").glob("c[0-9][0-9].xyz")):
            inputs.append(_write(xyz.with_name(xyz.stem + "_opt.inp"),
                f"! r2SCAN-3c Opt TightSCF\n%pal nprocs {procs} end\n%maxcore 1000\n* xyzfile 0 1 {xyz.name}\n"))
    _run_all(inputs, jobs, "geometry optimisations")


_NUM = r"(-?\d+\.\d+)"


def _last(t: str, pattern: str) -> float | None:
    m = re.findall(pattern, t)
    return float(m[-1]) if m else None


def parse_opt_energy(out: Path) -> float | None:
    if not out.exists():
        return None
    t = out.read_text(errors="replace")
    if "ORCA TERMINATED NORMALLY" not in t or "THE OPTIMIZATION HAS CONVERGED" not in t:
        return None
    return _last(t, r"FINAL SINGLE POINT ENERGY\s+" + _NUM)


def freq(names: list[str], jobs: int, procs: int, window_kj: float = 12.0, dedupe_kj: float = 0.05) -> None:
    inputs = []
    for name in names:
        rows = []
        for out in sorted((SCRATCH / name / "conf").glob("c[0-9][0-9]_opt.out")):
            e = parse_opt_energy(out)
            if e is None:
                print(f"{name}/{out.stem}: optimisation not converged, dropped", flush=True)
                continue
            rows.append((e * core.HARTREE_KJ, out.stem.removesuffix("_opt")))
        rows.sort()
        uniq: list[tuple[float, str]] = []
        for e, stem in rows:
            if not any(abs(e - u) < dedupe_kj for u, _ in uniq):
                uniq.append((e, stem))
        low = uniq[0][0]
        for e, stem in uniq:
            if e - low <= window_kj:
                inputs.append(_write(SCRATCH / name / "conf" / f"{stem}_freq.inp",
                    f"! r2SCAN-3c TightOpt Freq TightSCF\n%pal nprocs {procs} end\n%maxcore 1000\n* xyzfile 0 1 {stem}_opt.xyz\n"))
        print(f"{name}: {len(rows)} converged, {len(uniq)} distinct, "
              f"{sum(1 for e, _ in uniq if e - low <= window_kj)} within {window_kj} kJ/mol for frequencies", flush=True)
    _run_all(inputs, jobs, "tight optimisations with frequencies")


def parse_freq(out: Path) -> dict | None:
    t = out.read_text(errors="replace")
    if "ORCA TERMINATED NORMALLY" not in t:
        return None
    e_scf = _last(t, r"FINAL SINGLE POINT ENERGY\s+" + _NUM)
    e_el = _last(t, r"Electronic energy\s+\.\.\.\s+" + _NUM + r"\s+Eh")
    h_tot = _last(t, r"Total Enthalpy\s+\.\.\.\s+" + _NUM + r"\s+Eh")
    g_tot = _last(t, r"Final Gibbs free energy\s+\.\.\.\s+" + _NUM + r"\s+Eh")
    if None in (e_scf, e_el, h_tot, g_tot):
        return None
    return {"e_scf": e_scf, "h_corr": h_tot - e_el, "g_corr": g_tot - e_el,
            "imaginary": len(re.findall(r"\*\*\*imaginary mode\*\*\*", t)),
            "converged": "THE OPTIMIZATION HAS CONVERGED" in t}


def select(names: list[str], window_kj: float = 12.0, dedupe_kj: float = 0.05) -> None:
    for name in names:
        rows = []
        for out in sorted((SCRATCH / name / "conf").glob("c[0-9][0-9]_freq.out")):
            r = parse_freq(out)
            if r is None:
                print(f"{name}/{out.stem}: no result", flush=True)
                continue
            r["stem"] = out.stem.removesuffix("_freq")
            r["g"] = (r["e_scf"] + r["g_corr"]) * core.HARTREE_KJ
            rows.append(r)
        good = [r for r in rows if r["converged"] and r["imaginary"] == 0]
        bad = [r["stem"] for r in rows if r not in good]
        if bad:
            print(f"{name}: excluded (not converged or imaginary): {bad}", flush=True)
        good.sort(key=lambda r: r["g"])
        uniq: list[dict] = []
        for r in good:
            if not any(abs(r["g"] - u["g"]) < dedupe_kj for u in uniq):
                uniq.append(r)
        low = uniq[0]["g"]
        chosen = [r for r in uniq if r["g"] - low <= window_kj]
        for r in chosen:
            r["dg_kj"] = r["g"] - low
        (SCRATCH / name / "selected.json").write_text(json.dumps(chosen, indent=1))
        print(f"{name}: {len(rows)} with frequencies, {len(uniq)} distinct, {len(chosen)} within {window_kj} kJ/mol; "
              f"lowest {chosen[0]['stem']}", flush=True)


def sp(names: list[str], basis: str, jobs: int, procs: int, within_kj: float = 6.0, only_lowest: bool = False) -> None:
    b = "def2-TZVPP def2-TZVPP/C" if basis == "TZ" else "def2-QZVPP def2-QZVPP/C"
    inputs = []
    for name in names:
        sel = json.loads((SCRATCH / name / "selected.json").read_text())
        pick = sel[:1] if only_lowest else [r for r in sel if r["dg_kj"] <= within_kj]
        for r in pick:
            src = f"{r['stem']}_freq.xyz"
            inputs.append(_write(SCRATCH / name / "conf" / f"{r['stem']}_cc{basis.lower()}.inp",
                f"! DLPNO-CCSD(T) {b} def2/J TightPNO TightSCF\n%pal nprocs {procs} end\n%maxcore 2800\n* xyzfile 0 1 {src}\n"))
    _run_all(inputs, jobs, f"DLPNO-CCSD(T)/{basis} single points")


def parse_cc(out: Path) -> float | None:
    if not out.exists():
        return None
    t = out.read_text(errors="replace")
    if "ORCA TERMINATED NORMALLY" not in t:
        return None
    return _last(t, r"FINAL SINGLE POINT ENERGY\s+" + _NUM)


def species_enthalpy(name: str, basis: str = "TZ") -> dict:
    """Ensemble H(298.15 K) in kJ/mol: the coupled-cluster electronic energy where it was computed, the r2SCAN-3c difference to
    the lowest conformer elsewhere, thermal corrections from r2SCAN-3c, populations from the free energies."""
    sel = json.loads((SCRATCH / name / "selected.json").read_text())
    cc = {}
    for r in sel:
        e = parse_cc(SCRATCH / name / "conf" / f"{r['stem']}_cc{basis.lower()}.out")
        if e is not None:
            cc[r["stem"]] = e
    ref = sel[0]
    if ref["stem"] not in cc:
        raise RuntimeError(f"{name}: no coupled-cluster energy for the lowest conformer")
    hs, gs = [], []
    for r in sel:
        e_cc = cc.get(r["stem"], cc[ref["stem"]] + (r["e_scf"] - ref["e_scf"]))
        hs.append((e_cc + r["h_corr"]) * core.HARTREE_KJ)
        gs.append((e_cc + r["g_corr"]) * core.HARTREE_KJ)
    return {"h": core.ensemble_enthalpy(hs, gs), "n_conformers": len(sel), "n_cc": len(cc),
            "lowest": ref["stem"], "weights": core.boltzmann_weights(gs)}


def report(basis: str, targets: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    species = {}
    for name in core.REFERENCES:
        if (SCRATCH / name / "selected.json").exists():
            try:
                species[name] = species_enthalpy(name, basis)
            except RuntimeError as exc:
                print("skip:", exc)
    out = {"basis": basis, "species": {n: {k: v for k, v in s.items() if k != "weights"} for n, s in species.items()},
           "schemes": {}}
    for sname, spec in core.SCHEMES.items():
        reactants, products = core._sides(spec)
        if not (set(reactants) | set(products)) <= set(species):
            continue
        # PLAN.md: no target is read until the validation set is done.
        if core.REFERENCES[spec["target"]][1] is None and not targets:
            continue
        dh = sum(k * species[n]["h"] for n, k in products.items()) - sum(k * species[n]["h"] for n, k in reactants.items())
        value, u_ref = core.reaction_to_formation(sname, dh)
        out["schemes"][sname] = {"reaction_enthalpy": dh, "dfH": value, "u_ref": u_ref}
    path = RESULTS / f"schemes_{basis.lower()}{'_targets' if targets else ''}.json"
    path.write_text(json.dumps(out, indent=1))
    for sname, r in out["schemes"].items():
        exp = core.REFERENCES[core.SCHEMES[sname]["target"]][1]
        cmp = f"  exp {exp:.2f}  err {r['dfH'] - exp:+.2f}" if exp is not None else ""
        print(f"{sname:22s} dfH {r['dfH']:9.2f}  (u_ref {r['u_ref']:.2f}){cmp}")
    print("wrote", path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["conformers", "opt", "freq", "select", "sp", "report"])
    ap.add_argument("names", nargs="*")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--keep", type=int, default=30)
    ap.add_argument("--basis", default="TZ", choices=["TZ", "QZ"])
    ap.add_argument("--lowest-only", action="store_true")
    ap.add_argument("--targets", action="store_true", help="also print schemes whose target is a question (after validation)")
    a = ap.parse_args()
    if a.stage == "conformers":
        for n in a.names:
            conformers(n, keep=a.keep)
    elif a.stage == "opt":
        opt(a.names, a.jobs, a.procs)
    elif a.stage == "freq":
        freq(a.names, a.jobs, a.procs)
    elif a.stage == "select":
        select(a.names)
    elif a.stage == "sp":
        sp(a.names, a.basis, a.jobs, a.procs, only_lowest=a.lowest_only)
    else:
        report(a.basis, a.targets)


if __name__ == "__main__":
    main()
