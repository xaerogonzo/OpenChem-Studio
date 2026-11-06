"""Checks C6, C8 and C9 of `eem_second_models_preregistration.md`: the parts that need no ORCA.

    uv run --no-sync python benchmarks/charges/models/eem_second_models_c6_c8_c9.py

C6  how much the charges move between the raw RDKit embedding and the MMFF-optimised geometry of the census panel's single-component molecules (the plan asks for ORCA-optimised
    geometries "where stored": none are stored, so there are none), per atom type, both models, no threshold;
C8  the largest |q| over the census panel and every Blue Book structure each model covers, per model; for Model N (whose paper's own population is unknown) no bound is shipped and
    the maximum is only reported, as registered;
C9  per-atom spread between Model J, Model N, Ionescu's E model and Bultinck's EEM on the CHNO molecules all four accept; reported, not judged (the four give different charge
    schemes: Merz-Kollman, NPA, Mulliken, Mulliken).

Runs on one core at below-normal priority, writes `eem_second_models_results/c6_c8_c9.json`. Everything uses the default `resonance="averaged"` of `typed_eem_for_molecule`.
"""

from __future__ import annotations

import json
import os
import pathlib
import statistics
import sys
import time
import tomllib
from collections import defaultdict

import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem

ROOT = pathlib.Path(__file__).resolve().parents[3]
RESULTS = pathlib.Path(__file__).resolve().parent / "eem_second_models_results"
SEED = 20261030

from openchem.chem import charge_equilibration as ce  # noqa: E402
from openchem.chem import resonance_forms as rf  # noqa: E402
from openchem.chem import typed_eem as te  # noqa: E402

J, N = te.JIROUSKOVA2009_B3LYP_MK, te.NEEMP2016_CCD_GEN_NPA
IONESCU_SCHEME = "E-MPA/6-31G*/gas"
#: Magnitudes (e) above which the atoms are counted by type in C8, to say what the tail of the distribution is made of.
THRESHOLDS = (1.0, 1.5, 2.0)


def lower_priority() -> None:
    if os.name == "nt":
        import ctypes

        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL_PRIORITY_CLASS


def census_smiles() -> list[str]:
    data = tomllib.loads((ROOT / "tests" / "fixtures" / "census_panel.toml").read_text(encoding="utf-8"))
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if "smiles" in node:
                found.append(node["smiles"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return list(dict.fromkeys(s for s in found if "." not in s))


def bluebook_smiles() -> list[str]:
    rows = json.loads((ROOT / "benchmarks" / "naming" / "bluebook_tuning.json").read_text(encoding="utf-8"))
    return list(dict.fromkeys(r["smiles"] for r in rows if r.get("smiles") and "." not in r["smiles"]))


def embed(smiles: str) -> tuple[Chem.Mol, Chem.Mol] | None:
    """(raw ETKDG embedding, the same optimised with MMFF), or None when it cannot be embedded. MMFF failure keeps the raw coordinates for the second."""
    parsed = Chem.MolFromSmiles(smiles)
    if parsed is None:
        return None
    mol = Chem.AddHs(parsed)
    params = AllChem.ETKDGv3()
    params.randomSeed = SEED
    params.maxIterations = 200
    if AllChem.EmbedMolecule(mol, params) != 0:
        return None
    optimised = Chem.Mol(mol)
    try:
        AllChem.MMFFOptimizeMolecule(optimised, maxIters=500)
    except Exception:  # noqa: BLE001 - an element MMFF has no type for keeps its embedded coordinates
        pass
    return mol, optimised


def charges_of(mol: Chem.Mol, model: str) -> te.TypedEEMResult:
    return rf.typed_eem_for_molecule(mol, model)


# --- C6 ---------------------------------------------------------------------------------------------------------------------------------


def c6(smiles_list: list[str]) -> dict:
    per_type: dict[str, dict[str, list[float]]] = {J: defaultdict(list), N: defaultdict(list)}
    per_molecule: dict[str, list[tuple[str, float]]] = {J: [], N: []}
    counted = {J: 0, N: 0}
    for smiles in smiles_list:
        pair = embed(smiles)
        if pair is None:
            continue
        raw, opt = pair
        for model in (J, N):
            a, b = charges_of(raw, model), charges_of(opt, model)
            if a.status != "converged" or b.status != "converged":
                continue
            counted[model] += 1
            delta = np.abs(b.charges - a.charges)
            for atom_type, d in zip(a.atom_types, delta, strict=True):
                per_type[model][atom_type].append(float(d))
            per_molecule[model].append((smiles, float(delta.max())))
    out = {}
    for model in (J, N):
        rows = {t: {"atoms": len(v), "mean": statistics.fmean(v), "max": max(v)} for t, v in sorted(per_type[model].items())}
        everything = [x for v in per_type[model].values() for x in v]
        worst = sorted(per_molecule[model], key=lambda r: -r[1])[:3]
        out[model] = {"molecules": counted[model], "atoms": len(everything), "mean_all": statistics.fmean(everything), "max_all": max(everything), "by_type": rows, "worst_molecules": worst}
    return out


# --- C8 and C9 --------------------------------------------------------------------------------------------------------------------------


def covered_elements(model: str) -> set[str]:
    return {t.rstrip("0123456789") for t in te.parameters()[model]["types"]}


def c8_c9(census: list[str], bluebook: list[str]) -> tuple[dict, dict]:
    allowed = covered_elements(J) | covered_elements(N)
    biggest = {J: (0.0, "", ""), N: (0.0, "", "")}
    all_abs: dict[str, list[float]] = {J: [], N: []}
    over: dict[str, dict[float, dict[str, int]]] = {J: {x: defaultdict(int) for x in THRESHOLDS}, N: {x: defaultdict(int) for x in THRESHOLDS}}
    statuses: dict[str, dict[str, int]] = {J: defaultdict(int), N: defaultdict(int)}
    spreads: list[dict] = []
    seen = set()
    for source, smiles_list in (("census", census), ("bluebook", bluebook)):
        for smiles in smiles_list:
            if smiles in seen:
                continue
            seen.add(smiles)
            parsed = Chem.MolFromSmiles(smiles)
            if parsed is None or {a.GetSymbol() for a in Chem.AddHs(parsed).GetAtoms()} - allowed:
                continue
            pair = embed(smiles)
            if pair is None:
                continue
            mol = pair[1]
            results = {m: charges_of(mol, m) for m in (J, N)}
            for model, r in results.items():
                statuses[model][r.status] += 1
                if r.status == "converged":
                    magnitudes = np.abs(r.charges)
                    all_abs[model].extend(float(x) for x in magnitudes)
                    for atom_type, magnitude in zip(r.atom_types, magnitudes, strict=True):
                        for x in THRESHOLDS:
                            if magnitude > x:
                                over[model][x][atom_type] += 1
                    k = int(np.argmax(magnitudes))
                    if magnitudes[k] > biggest[model][0]:
                        biggest[model] = (float(magnitudes[k]), smiles, r.atom_types[k])
            elements = [a.GetSymbol() for a in mol.GetAtoms()]
            if set(elements) <= {"H", "C", "N", "O"} and all(r.status == "converged" for r in results.values()):
                coords = mol.GetConformer().GetPositions()
                net = float(sum(a.GetFormalCharge() for a in mol.GetAtoms()))
                bult = ce.eem_charges(elements, coords, net)
                ione = ce.ionescu_charges(elements, coords, IONESCU_SCHEME, net)
                if bult.status != "converged" or ione.status != "converged":
                    continue

                def in_source_order(result):
                    ordered = np.empty(len(elements))
                    for k, original in enumerate(result.solver_to_source):
                        ordered[original] = result.charges[k]
                    return ordered

                four = {"J": results[J].charges, "N": results[N].charges, "Bultinck": in_source_order(bult), "IonescuE": in_source_order(ione)}
                spreads.append({"smiles": smiles, "source": source, "elements": elements, **{k: [float(x) for x in v] for k, v in four.items()}})
    c8 = {}
    for model in (J, N):
        values = np.array(all_abs[model])
        c8[model] = {
            "covered_molecules": int(statuses[model]["converged"]),
            "statuses": dict(statuses[model]),
            "max_abs_charge": biggest[model][0],
            "max_at": {"smiles": biggest[model][1], "atom_type": biggest[model][2]},
            "p99": float(np.percentile(values, 99)) if values.size else None,
            "p999": float(np.percentile(values, 99.9)) if values.size else None,
            "atoms": int(values.size),
            "atoms_over_by_type": {str(x): dict(sorted(over[model][x].items())) for x in THRESHOLDS},
        }
    return c8, summarise_c9(spreads)


def summarise_c9(rows: list[dict]) -> dict:
    names = ["J", "N", "Bultinck", "IonescuE"]
    by_element: dict[str, list[float]] = defaultdict(list)
    signed: dict[str, dict[str, list[float]]] = {n: defaultdict(list) for n in names}
    pair_diffs: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        for i, element in enumerate(row["elements"]):
            values = [row[n][i] for n in names]
            by_element[element].append(max(values) - min(values))
            for n in names:
                signed[n][element].append(row[n][i])
            for a in range(4):
                for b in range(a + 1, 4):
                    pair_diffs[f"{names[a]}-{names[b]}"].append(abs(values[a] - values[b]))
    return {
        "molecules": len(rows),
        "atoms": sum(len(r["elements"]) for r in rows),
        "spread_by_element": {e: {"atoms": len(v), "mean": statistics.fmean(v), "median": statistics.median(v), "max": max(v)} for e, v in sorted(by_element.items())},
        "mean_charge_by_model_and_element": {n: {e: statistics.fmean(v) for e, v in sorted(signed[n].items())} for n in names},
        "mean_abs_difference_between_pairs": {k: statistics.fmean(v) for k, v in sorted(pair_diffs.items())},
    }


def main() -> None:
    lower_priority()
    RDLogger.DisableLog("rdApp.*")
    started = time.time()
    census, bluebook = census_smiles(), bluebook_smiles()
    print(f"census {len(census)} single-component molecules, Blue Book {len(bluebook)}", flush=True)
    result_c6 = c6(census)
    print(f"C6 done in {time.time() - started:.0f} s", flush=True)
    result_c8, result_c9 = c8_c9(census, bluebook)
    print(f"C8 and C9 done in {time.time() - started:.0f} s", flush=True)
    RESULTS.mkdir(exist_ok=True)
    payload = {"seed": SEED, "census_molecules": len(census), "bluebook_molecules": len(bluebook), "c6": result_c6, "c8": result_c8, "c9": result_c9}
    (RESULTS / "c6_c8_c9.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("written", RESULTS / "c6_c8_c9.json", flush=True)


if __name__ == "__main__":
    sys.exit(main())
