"""Runs the PRIMARY arm of the proton-affinity benchmark of `PREREGISTRATION.md` (M062X/def2-TZVPD optimization and frequencies, thermochemistry from them) and writes its verdict.

    python run_pa.py structures                     build every starting structure (RDKit; no ORCA): artifacts/structures.json
    python run_pa.py run [--workers 3] [--cores 4]  the ORCA jobs (resumes; a completed job is never repeated)
    python run_pa.py report                         report.txt, verdict.json (the judge's verdict for PA and GB, primary arm)
    python run_pa.py status                         how many structures and jobs there are and how many are done

The secondary arm (DLPNO-CCSD(T) single points on these geometries) is a later stage and is not here. **Every rule is in `PREREGISTRATION.md`; the arithmetic is `pa_core.py` and the verdict `judge.py`.**
A report is refused (NOT EVALUABLE) for records from more than one commit or made with a dirty `src/`. ORCA is `D:\\ORCA\\orca.exe`.

How the structures are made (the preregistration's rules): each base is embedded with RDKit ETKDG (seed 7, 30 conformers), MMFF94-relaxed, deduplicated by all-atom RMSD 0.5 Angstrom, and the lowest three within 5 kcal/mol kept.
A conjugate acid's starting geometry is a kept base conformer with one proton placed on a candidate site (`add_proton`): along the lone-pair direction for a heteroatom, perpendicular to the plane for a pi carbon, away from the neighbour for carbon monoxide.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdDetermineBonds

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import judge  # noqa: E402
import pa_core  # noqa: E402

ORCA = r"D:\ORCA\orca.exe"
HEADER = "! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq"
SEED = 7
CONFORMERS = 30
DEDUPE_RMSD = 0.5
KEEP = 3
KEEP_WINDOW_KCAL = 5.0
#: A vibrational frequency below this (cm-1) makes a structure not accepted (PREREGISTRATION.md).
IMAGINARY_CM = -20.0
JOB_TIMEOUT_SECONDS = 4 * 3600
LOCK = threading.Lock()

#: The 28 bases: the name of `nist_values.json` -> SMILES.
BASES = {
    "ammonia": "N", "methylamine": "CN", "dimethylamine": "CNC", "trimethylamine": "CN(C)C", "pyridine": "c1ccncc1", "pyrrolidine": "C1CCNC1", "imidazole": "c1c[nH]cn1",
    "pyrimidine": "c1cncnc1", "aniline": "Nc1ccccc1", "acetonitrile": "CC#N", "hydrogen cyanide": "C#N", "water": "O", "methanol": "CO", "dimethyl ether": "COC",
    "tetrahydrofuran": "C1CCOC1", "formaldehyde": "C=O", "acetaldehyde": "CC=O", "acetone": "CC(C)=O", "formamide": "NC=O", "acetic acid": "CC(=O)O",
    "hydrogen sulfide": "S", "methanethiol": "CS", "dimethyl sulfide": "CSC", "phosphine": "P", "trimethylphosphine": "CP(C)C", "benzene": "c1ccccc1", "ethene": "C=C",
    "carbon monoxide": "[C-]#[O+]",
}
LONE_PAIR_ELEMENTS = {7, 8, 15, 16}  # N, O, P, S
XH_DISTANCE = {6: 1.09, 7: 1.02, 8: 0.97, 15: 1.42, 16: 1.34}


# --- structures -------------------------------------------------------------------------------------------------------------


def base_molecule(name: str) -> Chem.Mol:
    return Chem.AddHs(Chem.MolFromSmiles(BASES[name]))


def candidate_sites(mol: Chem.Mol) -> list[dict]:
    """The protonation sites of a base (explicit hydrogens), equivalent sites by graph symmetry merged into one.

    (a) every N, O, S or P without a positive charge ('lone_pair'); (b) every carbon of a C=C, C#C or aromatic bond ('pi_carbon'); plus the carbon of carbon monoxide ('lone_pair': it carries the negative charge). Returns `{"atom": index, "kind": ..., "class": rank}` with the lowest-index atom of each symmetry class.
    """
    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
    seen: set[tuple[str, int]] = set()
    sites = []
    for atom in mol.GetAtoms():
        kind = None
        if atom.GetAtomicNum() in LONE_PAIR_ELEMENTS and atom.GetFormalCharge() <= 0:
            kind = "lone_pair"
        elif atom.GetAtomicNum() == 6 and atom.GetFormalCharge() < 0:
            kind = "lone_pair"  # carbon monoxide's carbon
        elif atom.GetAtomicNum() == 6 and any(b.GetBondType() == Chem.BondType.AROMATIC for b in atom.GetBonds()):
            kind = "pi_carbon"  # every carbon of an aromatic ring, including one bonded only to heteroatoms (pyrimidine C2, imidazole C2)
        elif atom.GetAtomicNum() == 6 and any(b.GetBondType() == Chem.BondType.DOUBLE and b.GetOtherAtom(atom).GetAtomicNum() == 6 for b in atom.GetBonds()):
            kind = "pi_carbon"
        elif atom.GetAtomicNum() == 6 and any(b.GetBondType() == Chem.BondType.TRIPLE and b.GetOtherAtom(atom).GetAtomicNum() == 6 for b in atom.GetBonds()):
            kind = "pi_carbon"
        if kind is None or (kind, ranks[atom.GetIdx()]) in seen:
            continue
        seen.add((kind, ranks[atom.GetIdx()]))
        sites.append({"atom": atom.GetIdx(), "kind": kind, "class": int(ranks[atom.GetIdx()])})
    return sites


def _rmsd(mol: Chem.Mol, probe: int, reference: int) -> float:
    """All-atom (hydrogens included) symmetry-aware RMSD of two conformers of one molecule; works on copies because the call aligns the probe in place."""
    from rdkit.Chem import rdMolAlign

    return rdMolAlign.GetBestRMS(Chem.Mol(mol), Chem.Mol(mol), probe, reference)


def conformers_of(mol: Chem.Mol) -> list[np.ndarray]:
    """The kept conformers of a base: ETKDG (seed 7, 30), MMFF94, deduplicated by all-atom RMSD 0.5 Angstrom (symmetry-aware), the lowest three within 5 kcal/mol of the lowest."""
    work = Chem.Mol(mol)
    ids = list(AllChem.EmbedMultipleConfs(work, numConfs=CONFORMERS, randomSeed=SEED))
    if not ids:
        raise RuntimeError("no conformer could be embedded")
    if work.GetNumAtoms() < 3:
        results = [(0.0, cid) for cid in ids]
    else:
        energies = AllChem.MMFFOptimizeMoleculeConfs(work, maxIters=5000)
        results = sorted(((e, cid) for (_c, e), cid in zip(energies, ids)), key=lambda pair: pair[0])
    lowest = results[0][0]
    kept: list[int] = []
    for energy, cid in results:
        if energy - lowest > KEEP_WINDOW_KCAL or len(kept) >= KEEP:
            break
        if all(_rmsd(work, cid, k) > DEDUPE_RMSD for k in kept):
            kept.append(cid)
    return [np.array(work.GetConformer(cid).GetPositions()) for cid in kept]


def add_proton(mol: Chem.Mol, coordinates: np.ndarray, site: dict) -> tuple[list[str], np.ndarray]:
    """A conjugate acid's starting geometry: the base's atoms and one more hydrogen on the site.

    A heteroatom (or carbon monoxide's carbon) takes it along the lone-pair direction, the negative sum of the unit vectors to its neighbours (the plane's normal if that sum is nearly zero); a pi carbon takes it perpendicular to the plane of its neighbours.
    Returns (the element symbols, the coordinates) with the new hydrogen LAST, so the base's atom indices are unchanged."""
    atom = mol.GetAtomWithIdx(site["atom"])
    origin = coordinates[site["atom"]]
    vectors = []
    for neighbor in atom.GetNeighbors():
        v = coordinates[neighbor.GetIdx()] - origin
        vectors.append(v / np.linalg.norm(v))
    normal = None
    if len(vectors) >= 2:
        n = np.cross(vectors[0], vectors[1])
        if np.linalg.norm(n) > 1e-6:
            normal = n / np.linalg.norm(n)
    away = -np.sum(vectors, axis=0)
    if site["kind"] == "pi_carbon" and normal is not None:
        direction = normal
    elif np.linalg.norm(away) > 0.3:
        direction = away / np.linalg.norm(away)
    elif normal is not None:
        direction = normal
    else:
        raise ValueError(f"no direction for the proton on atom {site['atom']}")
    distance = XH_DISTANCE.get(atom.GetAtomicNum(), 1.1)
    symbols = [a.GetSymbol() for a in mol.GetAtoms()] + ["H"]
    return symbols, np.vstack([coordinates, origin + distance * direction])


def build_structures() -> list[dict]:
    structures = []
    for name in BASES:
        mol = base_molecule(name)
        sites = candidate_sites(mol)
        symbols = [a.GetSymbol() for a in mol.GetAtoms()]
        for index, coordinates in enumerate(conformers_of(mol)):
            structures.append({"id": f"{name}|base|{index}", "base": name, "role": "base", "charge": 0, "symbols": symbols, "coordinates": coordinates.tolist()})
            for site in sites:
                s, xyz = add_proton(mol, coordinates, site)
                structures.append({"id": f"{name}|ion|{site['kind']}{site['atom']}|{index}", "base": name, "role": "ion", "charge": 1, "site_atom": site["atom"], "site_class": site["class"],
                                   "site_kind": site["kind"], "symbols": s, "coordinates": xyz.tolist()})
    return structures


# --- the ORCA job and its output ---------------------------------------------------------------------------------------------


def orca_input(structure: dict, cores: int, retry: bool = False) -> str:
    lines = [HEADER, f"%pal nprocs {cores} end", "%maxcore 3000"]
    if retry:
        lines += ["%geom", "  Calc_Hess true", "end"]
    lines.append(f"* xyz {structure['charge']} 1")
    lines += [f"{s:<3}{x:>14.8f}{y:>14.8f}{z:>14.8f}" for s, (x, y, z) in zip(structure["symbols"], structure["coordinates"])]
    lines += ["*", ""]
    return "\n".join(lines)


def parse_output(text: str) -> dict:
    """What the benchmark needs from one Opt Freq output; raises ValueError naming the first thing missing."""

    def last(pattern: str, group: int = 1):
        found = re.findall(pattern, text)
        return found[-1] if found else None

    if "THE OPTIMIZATION HAS CONVERGED" not in text:
        raise ValueError("the geometry optimization did not converge")
    block_start = text.rfind("CARTESIAN COORDINATES (ANGSTROEM)")
    if block_start < 0:
        raise ValueError("no final geometry")
    symbols, coordinates = [], []
    for line in text[block_start:].splitlines()[2:]:
        m = re.match(r"^\s*([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$", line)
        if not m:
            break
        symbols.append(m.group(1))
        coordinates.append([float(m.group(2)), float(m.group(3)), float(m.group(4))])
    frequencies = []
    freq_start = text.rfind("VIBRATIONAL FREQUENCIES")
    if freq_start >= 0:
        for line in text[freq_start:].splitlines():
            m = re.match(r"^\s*\d+:\s+(-?\d+\.\d+) cm\*\*-1", line)
            if m:
                frequencies.append(float(m.group(1)))
            elif frequencies and not line.strip():
                break
    enthalpy, gibbs, energy = last(r"Total enthalpy\s+\.\.\.\s+(-?\d+\.\d+) Eh"), last(r"Final Gibbs free energy\s+\.\.\.\s+(-?\d+\.\d+) Eh"), last(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
    sigma, temperature, pressure = last(r"Symmetry Number:\s+(\d+)"), last(r"Temperature\s+\.\.\.\s+(\d+\.\d+) K"), last(r"Pressure\s+\.\.\.\s+(\d+\.\d+) atm")
    for label, value in (("enthalpy", enthalpy), ("Gibbs free energy", gibbs), ("electronic energy", energy), ("symmetry number", sigma), ("frequencies", frequencies or None)):
        if value is None:
            raise ValueError(f"no {label} in the output")
    if abs(float(temperature) - 298.15) > 1e-6 or abs(float(pressure) - 1.0) > 1e-6:
        raise ValueError(f"thermochemistry at {temperature} K and {pressure} atm, not 298.15 K and 1 atm")
    version = last(r"Program Version\s+(\S+)")
    return {"energy": float(energy), "enthalpy": float(enthalpy), "gibbs": float(gibbs), "sigma_orca": int(sigma), "frequencies": frequencies, "lowest_frequency": min(frequencies),
            "symbols": symbols, "coordinates": coordinates, "orca_version": version}


def connectivity(symbols: list[str], coordinates) -> Chem.Mol:
    """An RDKit molecule with bonds perceived from distances only (no bond orders, no charges): what the symmetry number and the site assignment need."""
    block = f"{len(symbols)}\n\n" + "\n".join(f"{s} {x:.6f} {y:.6f} {z:.6f}" for s, (x, y, z) in zip(symbols, coordinates)) + "\n"
    mol = Chem.MolFromXYZBlock(block)
    rdDetermineBonds.DetermineConnectivity(mol)
    mol.UpdatePropertyCache(strict=False)
    Chem.FastFindRings(mol)
    return mol


def hydrogen_counts(mol: Chem.Mol) -> dict[int, int]:
    return {a.GetIdx(): sum(1 for n in a.GetNeighbors() if n.GetAtomicNum() == 1) for a in mol.GetAtoms() if a.GetAtomicNum() != 1}


def assigned_site(structure: dict, result: dict) -> int | None:
    """The base atom that gained the proton in the optimized ion: the ONE heavy atom (of the base's atoms, which come first) whose hydrogen count rose, or None if it is not exactly one (the proton was lost or went somewhere a count cannot place)."""
    base = base_molecule(structure["base"])
    before = hydrogen_counts(base)
    after = hydrogen_counts(connectivity(result["symbols"], result["coordinates"]))
    gained = [i for i in before if after.get(i, 0) - before[i] == 1]
    lost = [i for i in before if after.get(i, 0) - before[i] < 0]
    return gained[0] if len(gained) == 1 and not lost else None


def finish(structure: dict, result: dict) -> dict:
    """Adds what the benchmark computes from one parsed output: the symmetry number of the optimized structure, the Gibbs correction it implies, and the corrected G."""
    mol = connectivity(result["symbols"], result["coordinates"])
    sigma_true = pa_core.rotational_symmetry_number(mol, np.array(result["coordinates"]))
    correction = pa_core.symmetry_correction_eh(sigma_true, result["sigma_orca"])
    out = dict(result, sigma_true=sigma_true, symmetry_correction=correction, gibbs_corrected=result["gibbs"] + correction)
    if structure["role"] == "ion":
        out["site_assigned"] = assigned_site(structure, result)
    return out


# --- selection and the report -------------------------------------------------------------------------------------------------


def accepted(records: list[dict]) -> list[dict]:
    """The records that count: a completed job whose lowest frequency is not imaginary. A structure's retry replaces its first attempt."""
    latest: dict[str, dict] = {}
    for record in records:
        if record.get("completed"):
            latest[record["structure"]] = record
    return [r for r in latest.values() if r["lowest_frequency"] >= IMAGINARY_CM]


def select(records: list[dict], base: str, quantity: str) -> dict | None:
    """PA or GB (Hartree) of one base from its accepted records: the lowest-H (GB: lowest corrected-G) base structure, and the lowest-H (G) conjugate acid over every site; None if either is missing.
    Also says which site won (the base atom and its element)."""
    key = "enthalpy" if quantity == "pa" else "gibbs_corrected"
    bases = [r for r in records if r["base"] == base and r["role"] == "base"]
    ions = [r for r in records if r["base"] == base and r["role"] == "ion" and r.get("site_assigned") is not None]
    if not bases or not ions:
        return None
    best_base = min(bases, key=lambda r: r[key])
    best_ion = min(ions, key=lambda r: r[key])
    if quantity == "pa":
        value = pa_core.proton_affinity(best_base["enthalpy"], best_ion["enthalpy"])
    else:
        value = pa_core.gas_basicity(best_base["gibbs_corrected"], best_ion["gibbs_corrected"])
    return {"value_eh": value, "site_atom": best_ion["site_assigned"], "structures": len(bases) + len(ions)}


def judge_records(records: list[dict], reference: list[dict]) -> list[dict]:
    done = accepted(records)
    out = []
    for ref in reference:
        pa, gb = select(done, ref["name"], "pa"), select(done, ref["name"], "gb")
        out.append({"name": ref["name"], "pa_ref_kj": ref["pa_kj"], "gb_ref_kj": ref["gb_kj"],
                    "pa_kcal": pa["value_eh"] * pa_core.HARTREE_TO_KCAL if pa else None, "gb_kcal": gb["value_eh"] * pa_core.HARTREE_TO_KCAL if gb else None})
    return out


def provenance_problem(records: list[dict]) -> str | None:
    commits = {r["commit"] for r in records}
    if len(commits) > 1:
        return f"the records come from {len(commits)} commits: {sorted(c[:8] for c in commits)}"
    if any(r["dirty"] for r in records):
        return "some records were made with a dirty src/"
    return None


def report_text(records: list[dict], reference: list[dict]) -> tuple[str, dict]:
    problem = provenance_problem(records)
    rows = judge_records(records, reference)
    result = judge.judge(rows, "primary")
    verdicts = {q: result[q]["verdict"] for q in ("pa", "gb")}
    if problem:
        verdicts = {q: judge.NOT_EVALUABLE for q in verdicts}
    done = accepted(records)
    lines = [f"PRIMARY ARM (M062X/def2-TZVPD), {len(done)} accepted structures of {len(records)} jobs" + (f"; REFUSED: {problem}" if problem else "")]
    for quantity in ("pa", "gb"):
        r = result[quantity]
        for label, s in (("deciding (21, above propene)", r["deciding"]), ("low (7, reported only)", r["low"]), ("all 28", r["all"])):
            lines.append(f"{quantity.upper()} {label:30s} n={s.count:2d} missing={s.missing:2d} MAE={'-' if s.mae is None else f'{s.mae:.2f}'} MSE={'-' if s.mse is None else f'{s.mse:+.2f}'} max={'-' if s.max_abs is None else f'{s.max_abs:.2f}'} kcal/mol")
        lines.append(f"{quantity.upper()} VERDICT {verdicts[quantity]}")
    lines += ["", f"{'base':20s} {'PA calc':>9s} {'PA ref':>8s} {'GB calc':>9s} {'GB ref':>8s}   site (kJ/mol)"]
    for row, ref in zip(rows, reference):
        pa, gb = select(done, ref["name"], "pa"), select(done, ref["name"], "gb")
        site = "-"
        if pa:
            base = base_molecule(ref["name"])
            site = f"{base.GetAtomWithIdx(pa['site_atom']).GetSymbol()}{pa['site_atom']}"
        f = lambda kcal: "missing" if kcal is None else f"{kcal * 4.184:.1f}"  # noqa: E731
        lines.append(f"{ref['name']:20s} {f(row['pa_kcal']):>9s} {ref['pa_kj']:8.1f} {f(row['gb_kcal']):>9s} {ref['gb_kj']:8.1f}   {site}")
    differing = [r for r in done if r["sigma_orca"] != r["sigma_true"]]
    lines += ["", f"symmetry number: ORCA's differs from the one used in {len(differing)} of {len(done)} accepted structures"]
    for r in differing[:30]:
        lines.append(f"  {r['structure']}: ORCA {r['sigma_orca']}, used {r['sigma_true']}, G shift {r['symmetry_correction'] * pa_core.HARTREE_TO_KCAL:+.2f} kcal/mol")
    return "\n".join(lines), {"verdicts": verdicts, "problem": problem}


# --- the commands -----------------------------------------------------------------------------------------------------------


def records_of(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def run_stage(out: Path, cores: int, workers: int) -> None:
    structures = json.loads((out / "structures.json").read_text(encoding="utf-8"))
    path = out / "primary" / "runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src"], capture_output=True, text=True, cwd=REPO).stdout.strip())

    def done_ids() -> set[str]:
        return {r["structure"] for r in records_of(path) if r.get("completed") and r["lowest_frequency"] >= IMAGINARY_CM} | {r["structure"] for r in records_of(path) if r.get("final")}

    pending = [s for s in structures if s["id"] not in done_ids()]
    print(f"{len(structures) - len(pending)} done, {len(pending)} to run", flush=True)

    def append(record: dict) -> None:
        with LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def attempt(structure: dict, retry: bool) -> dict:
        scratch = Path(tempfile.mkdtemp(prefix="pa_"))
        record = {"structure": structure["id"], "base": structure["base"], "role": structure["role"], "retry": retry, "commit": commit, "dirty": dirty, "completed": False}
        began = time.time()
        try:
            text = orca_input(structure, cores, retry)
            (scratch / "job.inp").write_text(text, encoding="utf-8")
            completed = subprocess.run([ORCA, "job.inp"], cwd=scratch, capture_output=True, text=True, timeout=JOB_TIMEOUT_SECONDS)
            result = finish(structure, parse_output(completed.stdout or ""))
            record.update(result)
            record["completed"] = True
        except subprocess.TimeoutExpired:
            record["error"] = f"timeout after {JOB_TIMEOUT_SECONDS} s"
        except Exception as error:  # noqa: BLE001 - a failed job is a missing structure, recorded with its reason
            record["error"] = f"{type(error).__name__}: {error}"[:300]
        finally:
            record["seconds"] = round(time.time() - began, 1)
            import shutil

            shutil.rmtree(scratch, ignore_errors=True)
        return record

    def work(structure: dict) -> None:
        record = attempt(structure, retry=False)
        append(record)
        if record["completed"] and record["lowest_frequency"] < IMAGINARY_CM:
            # one re-run from the structure's own final geometry, with an initial Hessian (PREREGISTRATION.md); it replaces the first attempt
            again = dict(structure, symbols=record["symbols"], coordinates=record["coordinates"])
            retried = attempt(again, retry=True)
            retried["final"] = True
            append(retried)
        print(f"{structure['id']}  completed={record['completed']}  {record['seconds']} s  {record.get('error', '')}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, pending))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["structures", "run", "report", "status"])
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--out", default=str(HERE / "artifacts"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.command == "structures":
        structures = build_structures()
        (out / "structures.json").write_text(json.dumps(structures), encoding="utf-8")
        print(f"{len(structures)} structures ({sum(1 for s in structures if s['role'] == 'base')} base, {sum(1 for s in structures if s['role'] == 'ion')} ion) for {len(BASES)} bases")
    elif args.command == "run":
        run_stage(out, args.cores, args.workers)
    elif args.command == "status":
        structures = json.loads((out / "structures.json").read_text(encoding="utf-8"))
        records = records_of(out / "primary" / "runs.jsonl")
        print(f"{len(structures)} structures, {len({r['structure'] for r in records if r.get('completed')})} completed, {len(accepted(records))} accepted")
    else:
        reference = json.loads((HERE / "nist_values.json").read_text(encoding="utf-8"))["bases"]
        records = records_of(out / "primary" / "runs.jsonl")
        text, verdict = report_text(records, reference)
        print(text)
        (out / "report.txt").write_text(text, encoding="utf-8")
        (out / "verdict.json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
