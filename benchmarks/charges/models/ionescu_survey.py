"""Section 9 of `ionescu_src_preregistration.md`: how common are silent errors?

    uv run --no-sync python benchmarks/charges/models/ionescu_survey.py run 6-31G*
    uv run --no-sync python benchmarks/charges/models/ionescu_survey.py run 6-31G**
    uv run --no-sync python benchmarks/charges/models/ionescu_survey.py summarize

`run` is one basis per process, so the two can run concurrently; each writes a JSON of every
molecule's reference and model charges. `summarize` applies section 9.3's registered definitions.

Like-for-like only (section 9.1): RHF Mulliken against the E-MPA gas model at the same basis. ORCA
is invoked as `ionescu_reference.py` invokes it -- a backslash path, a working directory with no
spaces -- and its Mulliken block goes through the same parser, which refuses anything but exactly
n atoms.
"""
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("ionescu_reference", HERE / "ionescu_reference.py")
ref = importlib.util.module_from_spec(_spec)
sys.modules["ionescu_reference"] = ref
_spec.loader.exec_module(ref)
stab = ref.stab

#: The like-for-like model for each reference basis (section 9.1).
MODEL_FOR_BASIS = {"6-31G*": "E-MPA/6-31G*/gas", "6-31G**": "E-MPA/6-31G**/gas"}
#: Section 9.3, primary; then the registered sensitivity.
SIGN_Q, MAGNITUDE = 0.10, 0.50
SIGN_Q_SENS, MAGNITUDE_SENS = 0.05, 1.0
#: Section 9.3's classification cut-offs.
CONFINED, COMMON = 0.10, 0.50
_Z = {"H": 1, "C": 6, "N": 7, "O": 8, "S": 16, "Ca": 20}


def results_path(basis: str) -> pathlib.Path:
    return HERE / f"ionescu_survey_{basis.replace('*', 's')}.json"


def stratum(elements) -> str:
    return "S" if "S" in elements else ("N" if "N" in elements else "CHO")


def run(basis: str) -> None:
    if basis not in MODEL_FOR_BASIS:
        sys.exit(f"basis must be one of {sorted(MODEL_FOR_BASIS)}")
    model = MODEL_FOR_BASIS[basis]
    parameters = stab.ion.table_s1()[model]
    workdir = pathlib.Path(tempfile.mkdtemp(prefix=f"ionescu_survey_{basis.replace('*', 's')}_"))
    if " " in str(workdir) or " " in str(ref.ORCA):
        sys.exit(f"a space in {workdir} or {ref.ORCA} will abort ORCA")

    records = []
    molecules = list(stab.extrapolation())
    for index, (name, elements, coords) in enumerate(molecules, 1):
        record = {"name": name, "stratum": stratum(elements), "elements": elements}
        if sum(_Z[e] for e in elements) % 2:
            record["status"] = "excluded: open-shell (odd electron count), RHF does not apply"
            records.append(record)
            continue
        slug = f"m{index:03d}"
        lines = [f"! RHF {basis} TightSCF", "* xyz 0 1"]
        lines += [f"  {e:2s} {x:14.8f} {y:14.8f} {z:14.8f}" for e, (x, y, z) in zip(elements, coords)]
        lines.append("*")
        (workdir / f"{slug}.inp").write_text("\n".join(lines) + "\n", encoding="ascii")
        done = subprocess.run([str(ref.ORCA), f"{slug}.inp"], cwd=str(workdir), capture_output=True, text=True)
        (workdir / f"{slug}.out").write_text(done.stdout, encoding="utf-8")
        if "ORCA TERMINATED NORMALLY" not in done.stdout:
            record["status"] = f"excluded: ORCA did not terminate normally (exit {done.returncode})"
        elif "SCF CONVERGED" not in done.stdout:
            record["status"] = "excluded: SCF did not converge"
        else:
            mulliken = ref.charges(done.stdout, "MULLIKEN ATOMIC CHARGES", ref._MULLIKEN, len(elements))
            model_q = stab.ion.eem_charges(elements, coords, 0.0, parameters, "R_angstrom")
            record.update({"status": "ok", "reference": mulliken.tolist(), "model": model_q.tolist()})
        records.append(record)
        print(f"[{basis}] {index:3d}/{len(molecules)} {record['status']:8.8s} {name}", flush=True)

    results_path(basis).write_text(json.dumps({"basis": basis, "model": model, "orca_outputs": str(workdir),
                                               "molecules": records}, indent=1), encoding="utf-8")
    print(f"wrote {results_path(basis)}")


def assess(record: dict, sign_q: float, magnitude: float) -> dict:
    q_ref, q_mod = np.array(record["reference"]), np.array(record["model"])
    sign = int(np.sum((np.sign(q_ref) != np.sign(q_mod)) & (np.abs(q_ref) >= sign_q)))
    mag = int(np.sum(np.abs(q_ref - q_mod) >= magnitude))
    refusal_quiet = float(np.max(np.abs(q_mod))) <= stab.POSITIVE_Q
    return {"sign": sign, "magnitude": mag, "silent": bool((sign or mag) and refusal_quiet),
            "max_dq": float(np.max(np.abs(q_ref - q_mod))), "max_q_model": float(np.max(np.abs(q_mod)))}


def classify(rate: float) -> str:
    return "CONFINED" if rate <= CONFINED else ("COMMON" if rate >= COMMON else "INTERMEDIATE")


def summarize() -> None:
    for basis in MODEL_FOR_BASIS:
        path = results_path(basis)
        if not path.exists():
            sys.exit(f"missing {path}; run `run {basis}` first")
        data = json.loads(path.read_text(encoding="utf-8"))
        ok = [r for r in data["molecules"] if r["status"] == "ok"]
        excluded = [r for r in data["molecules"] if r["status"] != "ok"]
        print(f"\n===== {data['model']} against RHF/{basis} Mulliken   ({len(ok)} assessed)")
        for r in excluded:
            print(f"   EXCLUDED {r['name']}: {r['status']}")
        for label, sign_q, magnitude in (("PRIMARY", SIGN_Q, MAGNITUDE), ("sensitivity", SIGN_Q_SENS, MAGNITUDE_SENS)):
            print(f"   -- {label}: sign error needs |q_ref| >= {sign_q}, magnitude error |dq| >= {magnitude}")
            for s in ("S", "N", "CHO"):
                members = [r for r in ok if r["stratum"] == s]
                silent = [r for r in members if assess(r, sign_q, magnitude)["silent"]]
                rate = len(silent) / len(members) if members else float("nan")
                tag = classify(rate) if label == "PRIMARY" else ""
                print(f"      {s:3s} {len(silent):3d}/{len(members):3d} = {100 * rate:5.1f}%  {tag}")
        print("   -- every molecule with a primary silent error, worst first:")
        flagged = sorted(((assess(r, SIGN_Q, MAGNITUDE), r) for r in ok), key=lambda t: -t[0]["max_dq"])
        for a, r in flagged:
            if a["silent"]:
                print(f"      {r['stratum']:3s} max|dq|={a['max_dq']:.3f} sign={a['sign']} mag={a['magnitude']}  {r['name']}")
        dq = sorted(assess(r, SIGN_Q, MAGNITUDE)["max_dq"] for r in ok)
        print(f"   max|dq| distribution: median {np.median(dq):.3f}, 90th pct {np.percentile(dq, 90):.3f}, max {dq[-1]:.3f}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "run" and len(sys.argv) == 3:
        run(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "summarize":
        summarize()
    else:
        sys.exit("usage: ionescu_survey.py run {6-31G*|6-31G**} | summarize")
