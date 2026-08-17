"""Score non-aqueous solubility, and be honest about what cannot be scored.

    uv run --no-sync --with openpyxl python benchmarks/solubility/nonaqueous.py

**THE LEAKAGE HERE IS STRUCTURAL, NOT INCIDENTAL.** Abraham's solvent
coefficients are, in the source paper's own words, "obtained by linear
regression using experimentally determined partitions and solubilities of
solutes with known Abraham descriptors". The endpoint being scored IS the
endpoint they were fitted to. There is no version of this benchmark that
validates the shift the way the aqueous benchmark validates ESOL.

Two things follow, and the whole design is shaped by them:

  * **The evaluation data carries its own citation column**, so rows
    sourced from Abraham or Acree publications can be identified and
    dropped. That is the only handle on the problem that exists. It is a
    partial defence -- their coefficients may rest on measurements
    published by other people too -- and it is reported as partial.
  * **The composite is what can honestly be scored.** ESOL was never
    fitted to non-aqueous solubility, so `ESOL + shift` against a measured
    non-aqueous value is a fair test of the number the application
    actually shows, and the ESOL-versus-aqueous arm on the SAME compounds
    says how much of the error is the baseline rather than the shift.

So this reports three arms, and only the first two are claims:

    composite   our non-aqueous prediction vs measured   HONEST
    baseline    our ESOL vs measured aqueous, same set   HONEST
    shift only  predicted shift vs measured shift        OPTIMISTIC

DATA [source:ons_solubility]: Bradley et al., "Open Notebook Science Challenge Solubility
Dataset", figshare, doi 10.6084/m9.figshare.1514952, CC BY 4.0.

CAVEATS THAT ARE NOT FIXED HERE, stated rather than buried:
  * No temperature filter. The set is largely ambient but does not say so
    per row, and a solubility is temperature-dependent.
  * Solid form is not recorded, so polymorphs and hydrates are mixed in.
    The aqueous benchmark filters on this; here it is not available.
  * Replicates are reduced by median, and their spread is reported.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import ssl
import statistics
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import certifi

HERE = Path(__file__).resolve().parent
CACHE = HERE / "ons_solubility.xlsx"

_URL = "https://ndownloader.figshare.com/files/2217769"
ATTRIBUTION = (
    "Bradley J-C, Guha R, Hooker B, Koch SJ, Lang ASID, Neylon C, et al. "
    "Open Notebook Science Challenge Solubility Dataset. figshare. "
    "doi:10.6084/m9.figshare.1514952. CC BY 4.0."
)

#: Rows whose citation names either author of the coefficient work. These
#: are the measurements most likely to BE the fitting set.
_LEAK = re.compile(r"abraham|acree", re.I)


@dataclass(frozen=True)
class Case:
    name: str
    smiles: str
    solvent: str
    measured_water_logs: float
    measured_solvent_logs: float
    replicates: int
    spread: float


def fetch() -> Path:
    if CACHE.exists():
        return CACHE
    ctx = ssl.create_default_context(cafile=certifi.where())
    request = urllib.request.Request(_URL, headers={"User-Agent": "openchem-solubility-bench"})
    with urllib.request.urlopen(request, timeout=600, context=ctx) as response:
        CACHE.write_bytes(response.read())
    return CACHE


def load_cases(*, deleak: bool) -> tuple[list[Case], dict]:
    """Every (solute, solvent) we can score, plus the funnel that produced it."""
    import openpyxl
    from rdkit import Chem, RDLogger

    from openchem.chem.abraham import solute_descriptors, solvent_coefficients

    RDLogger.DisableLog("rdApp.*")

    sheet = openpyxl.load_workbook(fetch(), read_only=True)["Sheet1"]
    rows = sheet.iter_rows(values_only=True)
    header = [str(h or "") for h in next(rows)]
    col = {name: i for i, name in enumerate(header)}

    measurements: dict[tuple[str, str], list[float]] = {}
    names: dict[str, str] = {}
    funnel = {"rows": 0, "usable": 0, "leaked_rows_dropped": 0}

    for row in rows:
        funnel["rows"] += 1
        try:
            concentration = float(row[col["concentration (M)"]])
        except (TypeError, ValueError):
            continue
        if concentration <= 0:
            continue
        smiles = row[col["solute SMILES"]]
        solvent = str(row[col["solvent"]] or "").strip().lower()
        if not smiles or not solvent:
            continue
        if deleak and _LEAK.search(str(row[col["sample or citation"]] or "")):
            funnel["leaked_rows_dropped"] += 1
            continue
        funnel["usable"] += 1
        measurements.setdefault((str(smiles), solvent), []).append(math.log10(concentration))
        names.setdefault(str(smiles), str(row[col["solute"]] or "").strip())

    by_solute: dict[str, dict[str, list[float]]] = {}
    for (smiles, solvent), values in measurements.items():
        by_solute.setdefault(smiles, {})[solvent] = values

    cases: list[Case] = []
    for smiles, per_solvent in by_solute.items():
        if "water" not in per_solvent:
            continue
        mol = Chem.MolFromSmiles(smiles)
        if mol is None or solute_descriptors(mol) is None:
            continue
        water = statistics.median(per_solvent["water"])
        for solvent, values in per_solvent.items():
            if solvent == "water" or solvent_coefficients(solvent) is None:
                continue
            cases.append(
                Case(
                    name=names[smiles], smiles=smiles, solvent=solvent,
                    measured_water_logs=water,
                    measured_solvent_logs=statistics.median(values),
                    replicates=len(values),
                    spread=max(values) - min(values),
                )
            )
    funnel["cases"] = len(cases)
    funnel["solutes"] = len({c.smiles for c in cases})
    funnel["solvents"] = len({c.solvent for c in cases})
    return cases, funnel


class ArmStatus(Enum):
    """What a scored arm is entitled to claim.

    **A CLOSED VOCABULARY, and never inferred from the arm's name.** The
    defect this exists to prevent is a number travelling without its
    caveat: the status used to be hand-typed into the printed title while
    the JSON carried none at all, so the two could disagree and a machine
    reader got the figure with nothing attached to it.
    """

    VALIDATED = "validated"
    OPTIMISTIC = "optimistic"
    UNSUPPORTED = "unsupported"


#: Every arm's status and caveat, in ONE place, rendered into both the text
#: table and the JSON. Nothing may be scored without an entry here.
ARM_STATUS: dict[str, tuple[ArmStatus, str]] = {
    "composite": (
        ArmStatus.VALIDATED,
        "Our non-aqueous prediction against a measured non-aqueous solubility. ESOL was never "
        "fitted to this endpoint, so this arm is a fair test of the number the application shows.",
    ),
    "baseline_aqueous": (
        ArmStatus.VALIDATED,
        "Our ESOL prediction against a measured AQUEOUS solubility, on the same compounds. The "
        "comparison that says how much of the composite error is the baseline.",
    ),
    "shift_only": (
        ArmStatus.OPTIMISTIC,
        "NOT a validation. Abraham's coefficients were obtained by regression on measured "
        "solubilities -- the endpoint scored here -- so this is an optimistic bound. Run with "
        "--keep-leaked to see it flatter itself further.",
    ),
}


def _stats(errors: list[float], arm: str) -> dict:
    status, caveat = ARM_STATUS[arm]
    base = {"status": status.value, "caveat": caveat}
    if not errors:
        return {**base, "n": 0}
    return {
        **base,
        "n": len(errors),
        "MAE": statistics.mean(abs(e) for e in errors),
        "RMSE": math.sqrt(statistics.mean(e * e for e in errors)),
        "median": statistics.median(abs(e) for e in errors),
        "max": max(abs(e) for e in errors),
        "bias": statistics.mean(errors),
    }


def score(cases: list[Case]) -> dict:
    """Three arms. Only the first two are claims; see the module docstring."""
    from rdkit import Chem

    from openchem.chem.abraham import solvent_shift
    from openchem.chem.solubility import esol_logs

    composite, baseline, shift_only = [], [], []
    refused = 0

    for case in cases:
        mol = Chem.MolFromSmiles(case.smiles)
        outcome = solvent_shift(mol, case.solvent)
        if isinstance(outcome, str):
            refused += 1
            continue
        aqueous = esol_logs(mol)
        predicted = aqueous + outcome.log_shift

        composite.append(predicted - case.measured_solvent_logs)
        baseline.append(aqueous - case.measured_water_logs)
        shift_only.append(
            outcome.log_shift - (case.measured_solvent_logs - case.measured_water_logs)
        )

    return {
        "composite": _stats(composite, "composite"),
        "baseline_aqueous": _stats(baseline, "baseline_aqueous"),
        "shift_only": _stats(shift_only, "shift_only"),
        "refused_by_uncertainty_bound": refused,
    }


def _table(title: str, stats: dict) -> str:
    """One row, with its status taken from the SAME dict the JSON is built
    from -- so the printed label and the machine-readable one cannot drift."""
    label = f"{title} [{stats['status'].upper()}]"
    if not stats.get("n"):
        return f"{label}: nothing scored"
    return (
        f"{label:<40} n={stats['n']:<5} MAE {stats['MAE']:.2f}  RMSE {stats['RMSE']:.2f}  "
        f"median {stats['median']:.2f}  max {stats['max']:.2f}  bias {stats['bias']:+.2f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-leaked", action="store_true",
        help="do NOT drop rows citing Abraham/Acree, to show what the de-leaking costs",
    )
    parser.add_argument("--json", type=Path, help="write the full result here")
    args = parser.parse_args()

    cases, funnel = load_cases(deleak=not args.keep_leaked)
    results = score(cases)

    print(ATTRIBUTION)
    print()
    print(f"de-leaking: {'OFF (--keep-leaked)' if args.keep_leaked else 'ON'}")
    for key, value in funnel.items():
        print(f"  {key:<22}{value:>7}")
    print(f"  {'refused by the bound':<22}{results['refused_by_uncertainty_bound']:>7}")
    print()
    for arm in ("composite", "baseline_aqueous", "shift_only"):
        print(_table(arm.replace("_", " "), results[arm]))
    print()
    print("The shift arm is NOT a validation: the coefficients were fitted to this")
    print("endpoint, so it is an optimistic bound. Read the composite against the")
    print("baseline -- if they are close, the aqueous prediction dominates the error.")

    if args.json:
        args.json.write_text(
            json.dumps({"funnel": funnel, "results": results}, indent=1), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
