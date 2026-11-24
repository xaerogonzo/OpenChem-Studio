"""Runner for the preregistered charge-models-on-radicals measurement (the rule, pairs and thresholds are in `charge_models_rule.py`, committed before this was run).

    uv run --no-sync python benchmarks/open_shell/charge_models.py D:/ORCA/orca.exe <scratch folder> [--json results.json]

For every species it builds ONE geometry through the application's own conformer path, hands that same geometry to ORCA (B3LYP/def2-SVP, `IntAcc 6.0`, `Print[P_Hirshfeld] 1`; ORCA chooses UKS by
itself for a multiplicity above 1, and the output's `HFTyp` is checked) and to each model, then prints the per-atom table and the verdicts. A reference table is accepted only when ORCA terminated
normally, the SCF converged, the echoed charge and multiplicity are the ones asked for, the atom count and element order match the input, and the Hirshfeld charges sum to the net charge within 0.02 e.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import rdPartialCharges

RDLogger.DisableLog("rdApp.*")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import charge_models_rule as rule  # noqa: E402
from openchem.chem import geometry_charges as gc  # noqa: E402
from openchem.chem.charge_evaluation import EEM, QEQ, evaluate_charges  # noqa: E402
from openchem.chem.conformer_providers import GenerationOptions, RDKitConformerProvider, search_conformers  # noqa: E402
from openchem.chem.open_shell_geometry import entry_for  # noqa: E402
from openchem.chem.orca_engine import OrcaQuantumEngineProvider, parse_hirshfeld_tables  # noqa: E402

METHOD = "B3LYP def2-SVP"
#: How far the Hirshfeld table's total may sit from the net charge before the table is refused (recorded for every run).
CHARGE_SUM_TOLERANCE = 0.02
_LOEWDIN_HEADER = re.compile(r"^LOEWDIN ATOMIC CHARGES")
_LOEWDIN_ROW = re.compile(r"^\s*(\d+)\s+([A-Za-z]{1,2})\s*:\s*(-?\d+\.\d+)")


def parse_loewdin(output_text: str) -> list[tuple[str, float]] | None:
    """The first Loewdin atomic-charge table (element, charge) in atom order, or None. A closed-shell and an unrestricted run both print it (the latter with a spin column)."""
    lines = output_text.splitlines()
    for index, line in enumerate(lines):
        if _LOEWDIN_HEADER.match(line.strip()):
            rows = []
            for row in lines[index + 2 :]:
                match = _LOEWDIN_ROW.match(row)
                if match is None:
                    break
                rows.append((match.group(2), float(match.group(3))))
            return rows
    return None


def geometry(smiles: str):
    """(3D Mol with hydrogens, where the geometry came from). The open-shell table is a measured geometry; anything else is the ordinary embedded and force-field one."""
    mol = search_conformers(RDKitConformerProvider(random_seed=1), Chem.MolFromSmiles(smiles), True, GenerationOptions(max_embeddings=10, embedding_batch_size=5)).pool[0][0]
    table = entry_for(Chem.MolFromSmiles(smiles))
    return mol, (f"open-shell table ({table.name})" if table is not None else "ETKDG + force field")


def run_orca(orca: str, folder: Path, key: str, mol, charge: int, multiplicity: int) -> dict:
    """Run (or re-read) one ORCA single point and return its validated reference tables."""
    work = folder / key
    work.mkdir(parents=True, exist_ok=True)
    text = OrcaQuantumEngineProvider().build_input(mol, charge, multiplicity, METHOD, "sp")
    head, *rest = text.split("\n")
    text = "\n".join([head, "%method", "  IntAcc 6.0", "end", "%output", "  Print[P_Hirshfeld] 1", "end", *rest])
    (work / "job.inp").write_text(text)
    output = work / "job.out"
    if not output.exists():
        completed = subprocess.run([orca, "job.inp"], cwd=work, capture_output=True, text=True, timeout=1800, env={**os.environ, "PATH": str(Path(orca).parent) + os.pathsep + os.environ["PATH"]})
        output.write_text(completed.stdout)
    out = output.read_text()
    problems = []
    if "ORCA TERMINATED NORMALLY" not in out:
        problems.append("did not terminate normally")
    if "SCF CONVERGED AFTER" not in out:
        problems.append("SCF did not converge")
    echoed = (re.search(r"Total Charge\s+Charge\s+\.\.\.\.\s+(-?\d+)", out), re.search(r"Multiplicity\s+Mult\s+\.\.\.\.\s+(\d+)", out))
    if not echoed[0] or not echoed[1] or (int(echoed[0].group(1)), int(echoed[1].group(1))) != (charge, multiplicity):
        problems.append("echoed charge/multiplicity differ from the request")
    elements = [a.GetSymbol() for a in mol.GetAtoms()]
    tables = parse_hirshfeld_tables(out)
    hirshfeld = tables[0] if tables else None
    if hirshfeld is None or [e for e, _ in hirshfeld] != elements:
        problems.append("Hirshfeld table missing or its atom order differs")
        hirshfeld = None
    total = sum(q for _, q in hirshfeld) if hirshfeld else None
    if total is not None and abs(total - charge) > CHARGE_SUM_TOLERANCE:
        problems.append(f"Hirshfeld charges sum to {total:.4f}, not {charge}")
        hirshfeld = None
    loewdin = parse_loewdin(out)
    if loewdin is not None and [e for e, _ in loewdin] != elements:
        loewdin = None
    s2 = re.findall(r"Expectation value of <S\*\*2>\s+:\s+(-?\d+\.\d+)", out)
    hftyp = re.search(r"HFTyp\s+\.\.\.\.\s+(\w+)", out)
    return {
        "key": key, "input_sha1": hashlib.sha1(text.encode()).hexdigest()[:12], "hftyp": hftyp.group(1) if hftyp else None,
        "s_squared": float(s2[-1]) if s2 else None, "charge_sum": total, "problems": problems,
        "hirshfeld": [q for _, q in hirshfeld] if hirshfeld else None, "loewdin": [q for _, q in loewdin] if loewdin else None,
    }


def model_charges(mol) -> dict[str, dict[int, float | None] | str]:
    """Each measured model's charges on the HEAVY atoms of `mol` (index -> charge, None where undefined), or the text of its refusal."""
    heavy = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() > 1]
    out: dict = {}
    raw = Chem.Mol(mol)
    rdPartialCharges.ComputeGasteigerCharges(raw)
    values = {}
    for index in heavy:
        atom = raw.GetAtomWithIdx(index)
        value = atom.GetDoubleProp("_GasteigerCharge") if atom.HasProp("_GasteigerCharge") else None
        values[index] = None if value is None or not math.isfinite(value) else value  # RAW: a NaN stays undefined, it is not a zero
    out["gasteiger"] = values
    for code in (EEM, QEQ):
        evaluation = evaluate_charges(mol, code, "bench")
        out[code] = f"refused: {evaluation.refusal} {evaluation.message}" if evaluation.charges is None else {i: evaluation.charges.get(i) for i in heavy}
    for code in (gc.EEM_IONESCU2013_E_MPA_631GS_GAS, gc.EEM_IONESCU2013_E_MPA_631GSS_GAS):
        dataset = gc.compute_geometry_charges(mol, "bench", {"method": code})
        refusal = dict(getattr(dataset.provenance, "parameters", {}) or {}).get("refusal", "")
        out[code] = f"refused: {refusal} {dataset.error or ''}" if refusal or getattr(dataset, "inapplicable", False) else {i: dataset.values.get(i) for i in heavy}
    return out


def main(orca: str, folder: str, json_path: str | None) -> None:
    scratch = Path(folder)
    scratch.mkdir(parents=True, exist_ok=True)
    species: dict[str, dict] = {}

    def measure(key: str, smiles: str, charge: int, multiplicity: int) -> dict:
        if key not in species:
            mol, source = geometry(smiles)
            species[key] = {"smiles": smiles, "source": source, "mol": mol, "orca": run_orca(orca, scratch, key, mol, charge, multiplicity), "models": model_charges(mol)}
            s = species[key]["orca"]
            print(f"{key:24} {source:42} HFTyp={s['hftyp']} <S2>={s['s_squared']} sum={s['charge_sum']} {'PROBLEMS: ' + '; '.join(s['problems']) if s['problems'] else 'ok'}", flush=True)
        return species[key]

    results: dict = {"pairs": {}, "descriptive": {}, "verdicts": {}}
    rows_by_scheme: dict[str, dict[str, list]] = {s: {m: [] for m in rule.MEASURED_MODELS} for s in (rule.PRIMARY_SCHEME, rule.SENSITIVITY_SCHEME)}
    for pair in rule.PAIRS:
        radical = measure(f"{pair.name}_radical", pair.radical, 0, pair.multiplicity)
        parent = measure(f"{pair.name}_parent", pair.parent, 0, 1)
        n_heavy = lambda m: sum(1 for a in m.GetAtoms() if a.GetAtomicNum() > 1)  # noqa: E731
        rule.validate_map(pair, n_heavy(radical["mol"]), n_heavy(parent["mol"]))
        for scheme in rows_by_scheme:
            ref_r = radical["orca"][scheme]
            ref_p = parent["orca"][scheme]
            to_map = lambda values: None if values is None else dict(enumerate(values))  # noqa: E731
            ref_r, ref_p = to_map(ref_r), to_map(ref_p)
            for model in rule.MEASURED_MODELS:
                mr, mp = radical["models"][model], parent["models"][model]
                if isinstance(mr, str) or isinstance(mp, str) or ref_r is None or ref_p is None:
                    rows = [rule.AtomRow(r, p, None, None) for r, p in pair.atom_map]
                else:
                    rows = rule.atom_rows(pair, mr, ref_r, mp, ref_p)
                rows_by_scheme[scheme][model].extend(rows)
                if scheme == rule.PRIMARY_SCHEME:
                    for row in rows:
                        er = "-" if row.error_radical is None else f"{row.error_radical:.3f}"
                        ep = "-" if row.error_parent is None else f"{row.error_parent:.3f}"
                        ex = "-" if row.excess is None else f"{row.excess:+.3f}"
                        print(f"  {pair.name:13} {model:40} R-atom {row.radical_atom} e_R={er} e_P={ep} excess={ex}")
    print("\n=== VERDICTS ===")
    for scheme, per_model in rows_by_scheme.items():
        for model, rows in per_model.items():
            outcome, worst = rule.verdict(rows)
            results["verdicts"][f"{scheme}:{model}"] = {"verdict": outcome, "E": worst}
            print(f"{scheme:10} {model:40} {outcome:13} E={'-' if worst is None else f'{worst:+.3f}'}")
    print("\n=== DESCRIPTIVE (heavy atoms; model q vs Hirshfeld q) ===")
    for item in rule.DESCRIPTIVE:
        s = measure(f"desc_{re.sub('[^A-Za-z0-9]+', '_', item.name)}", item.smiles, item.charge, item.multiplicity)
        ref = s["orca"]["hirshfeld"]
        for model, charges in s["models"].items():
            shown = charges if isinstance(charges, str) else {i: (None if ref is None else ref[i], q) for i, q in charges.items()}
            print(f"  {item.name:26} {model:40} {shown}")
        results["descriptive"][item.name] = {"source": s["source"], "hirshfeld": s["orca"]["hirshfeld"], "problems": s["orca"]["problems"]}
    if json_path:
        Path(json_path).write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--json")]
    json_arg = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    if json_arg in args:
        args.remove(json_arg)
    main(args[0], args[1], json_arg)
