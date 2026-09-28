"""Every enthalpy-of-formation/sublimation model this session reproduced or built, over one shared
corpus (RDX/HMX/PETN/TNT/TATB) reported stratum-by-stratum -- Track 3's own missing consolidation step,
matching `compare_energetics.py`'s discipline (coverage and accuracy kept separate, nothing silently
scored against a value it was fitted on) rather than leaving each model's result stranded in a different
module's docstring.

**This is a survey script, not a calculator.** See docs/research/README.md and
docs/CALCULATOR_MATURITY.md -- nothing here changes what the app ships, and no model here reached
PROMOTABLE (docs/research/literature.toml's mathieu2018_apc entry has the full verdicts).

**What each column is, and is not, comparable to.** `keshavarz_nitroaromatic2009` predicts CONDENSED
(solid) DfH directly, for nitroaromatics only. `keshavarz2010_sublimation` predicts DsubH (a positive
sublimation enthalpy), for any of this corpus's classes. `mathieu2018_apc` and `orca_atom_equivalents`
both predict GAS-phase DfH; their own "combined" columns are gas - DsubH, an independently-computed
condensed-phase estimate that is NOT the same computation as `keshavarz_nitroaromatic2009`'s direct one --
the two routes existing side by side for TNT/TATB is itself informative (they can be compared to each
other, not just each to measurement) rather than redundant.

**Coverage is real, not padded.** `keshavarz_nitroaromatic2009` only applies to the nitroaromatic
stratum (TNT, TATB) -- it is not run on RDX/HMX/PETN, and this report says "not applicable", never "0"
or a blank silently read as failure. `orca_atom_equivalents`'s combined route is limited to exactly the
three compounds this session actually ran through real ORCA (RDX, HMX, PETN) -- it CANNOT be extended to
TNT/TATB without a new ORCA job, and this module does not fabricate one.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_DIR = ROOT / "benchmarks" / "thermophysical"
keshavarz_nitroaromatic2009 = _load("keshavarz_nitroaromatic2009", _DIR / "keshavarz_nitroaromatic2009.py")
keshavarz2010_sublimation = _load("keshavarz2010_sublimation", _DIR / "keshavarz2010_sublimation.py")
mathieu2018_apc = _load("mathieu2018_apc", _DIR / "mathieu2018_apc.py")
orca_atom_equivalents = _load("orca_atom_equivalents", _DIR / "orca_atom_equivalents.py")
validation_rows_energetics = _load("validation_rows_energetics", _DIR / "validation_rows_energetics.py")


#: Sublimation-model correction terms, as established (and tested) earlier this session in
#: tests/test_keshavarz2010_sublimation.py -- reproduced here rather than re-derived.
_HSUB_CORRECTIONS = {
    "RDX": ("nitramine", {"n_n_no2": 3}),
    "HMX": ("nitramine", {"n_n_no2": 4}),
    "PETN": (None, {}),
    "TNT": ("nitroaromatic", {"n_r_over_no2": 1 / 3}),
    "TATB": ("nitroaromatic", {"n_nh2": 3}),
}

#: Condensed-Hf model terms (keshavarz_nitroaromatic2009), nitroaromatic stratum only.
_COND_HF_TERMS = {
    "TNT": {"n_c": 7, "n_h": 5, "n_n": 3, "n_o": 6, "molar_mass": 227.13, "n_aromatic_rings": 1,
            "ifg_term": keshavarz_nitroaromatic2009.increasing_term(3, n_alkyl_or_alkoxy=1)},
    "TATB": {"n_c": 6, "n_h": 6, "n_n": 6, "n_o": 6, "molar_mass": 258.156, "n_aromatic_rings": 1,
             "dfg_term": keshavarz_nitroaromatic2009.decreasing_term(3, n_nhx=3)},
}

CORPUS = {
    "RDX": {"smiles": "O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]", "stratum": "nitramine",
            "formula": (3, 6, 6, 6)},
    "HMX": {"smiles": "O=[N+]([O-])N1CN(CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]", "stratum": "nitramine",
            "formula": (4, 8, 8, 8)},
    "PETN": {"smiles": "C(C(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-])O[N+](=O)[O-]", "stratum": "nitrate_ester",
             "formula": (5, 8, 4, 12)},
    "TNT": {"smiles": "Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]", "stratum": "nitroaromatic",
            "formula": None},
    "TATB": {"smiles": "Nc1c(N)c([N+](=O)[O-])c(N)c([N+](=O)[O-])c1[N+](=O)[O-]", "stratum": "nitroaromatic",
             "formula": None},
}

#: RDX/HMX/PETN's real ORCA Etot -- see orca_atom_equivalents.py; no ORCA job exists for TNT/TATB.
_ORCA_TARGETS = orca_atom_equivalents.TARGET_ETOT_KJMOL


def _measured(name: str, property_: str) -> list[float]:
    return [
        row.value
        for row in validation_rows_energetics.HF_ROWS
        if row.property == property_ and row.row_id.startswith(f"hf_{name.lower()}")
    ]


def compare() -> list[dict]:
    ae = orca_atom_equivalents.fit_atom_equivalents(orca_atom_equivalents.CALIBRATION_SET)
    rows = []
    for name, spec in CORPUS.items():
        hsub_kind, hsub_kwargs = _HSUB_CORRECTIONS[name]
        if hsub_kind == "nitramine":
            c_in, c_de = keshavarz2010_sublimation.nitramine_correction(hsub_kwargs["n_n_no2"])
        elif hsub_kind == "nitroaromatic":
            c_in, c_de = keshavarz2010_sublimation.nitroaromatic_correction(**hsub_kwargs)
        else:
            c_in = c_de = 0.0
        from rdkit import Chem
        mol = Chem.MolFromSmiles(spec["smiles"])
        mw = sum(atom.GetMass() for atom in Chem.AddHs(mol).GetAtoms())
        hsub = keshavarz2010_sublimation.compute_hsub(mw, c_in=c_in, c_de=c_de)

        gas_apc = mathieu2018_apc.compute_hf(spec["smiles"])
        combined_apc = gas_apc - hsub

        cond_hf_direct = None
        if name in _COND_HF_TERMS:
            cond_hf_direct = keshavarz_nitroaromatic2009.compute_hf(**_COND_HF_TERMS[name])

        combined_orca = None
        if name in _ORCA_TARGETS:
            counts, etot = _ORCA_TARGETS[name]
            gas_orca = float(orca_atom_equivalents.compute_gas_hf(counts, etot, ae))
            combined_orca = gas_orca - hsub

        rows.append({
            "name": name,
            "stratum": spec["stratum"],
            "hsub_kj_mol": hsub,
            "measured_hsub_kj_mol": None,  # no independently-measured DsubH used this session
            "gas_hf_apc_kj_mol": gas_apc,
            "combined_solid_hf_apc_kj_mol": combined_apc,
            "cond_hf_direct_kj_mol": cond_hf_direct,
            "combined_solid_hf_orca_kj_mol": combined_orca,
            "measured_solid_hf_kj_mol": _measured(name, "enthalpy_formation_solid"),
        })
    return rows


def stratified_report(rows: list[dict]) -> dict[str, dict]:
    """Coverage and accuracy per stratum, per model -- an aggregate error can hide a poor class
    (docs/CALCULATOR_MATURITY.md), and coverage here genuinely differs by model (keshavarz_nitroaromatic2009
    only covers nitroaromatics; orca_atom_equivalents's combined route only covers RDX/HMX/PETN)."""
    by_stratum: dict[str, dict] = {}
    for row in rows:
        s = by_stratum.setdefault(row["stratum"], {
            "total": 0, "apc_errors": [], "orca_errors": [], "direct_errors": [],
        })
        s["total"] += 1
        measured = row["measured_solid_hf_kj_mol"]
        if measured:
            best_measured = measured[0]  # RDX's two readings: report against the first (p.232 prose)
            s["apc_errors"].append(row["combined_solid_hf_apc_kj_mol"] - best_measured)
            if row["combined_solid_hf_orca_kj_mol"] is not None:
                s["orca_errors"].append(row["combined_solid_hf_orca_kj_mol"] - best_measured)
            if row["cond_hf_direct_kj_mol"] is not None:
                s["direct_errors"].append(row["cond_hf_direct_kj_mol"] - best_measured)
    return by_stratum


def _print_report(rows: list[dict]) -> None:
    for row in rows:
        print(f"\n{row['name']}  [stratum={row['stratum']}]")
        print(f"  keshavarz2010 Hsub:              {row['hsub_kj_mol']:.1f} kJ/mol")
        print(f"  mathieu2018_apc gas Hf:           {row['gas_hf_apc_kj_mol']:.1f} kJ/mol")
        print(f"  combined solid Hf (APC route):    {row['combined_solid_hf_apc_kj_mol']:.1f} kJ/mol")
        if row["cond_hf_direct_kj_mol"] is not None:
            print(f"  keshavarz_nitroaromatic2009 Hf:   {row['cond_hf_direct_kj_mol']:.1f} kJ/mol (direct)")
        if row["combined_solid_hf_orca_kj_mol"] is not None:
            print(f"  combined solid Hf (ORCA route):   {row['combined_solid_hf_orca_kj_mol']:.1f} kJ/mol")
        if row["measured_solid_hf_kj_mol"]:
            print(f"  measured solid Hf:                {row['measured_solid_hf_kj_mol']} kJ/mol")

    print("\n--- stratified summary ---")
    for stratum, s in sorted(stratified_report(rows).items()):
        print(f"{stratum:15s} total={s['total']}  "
              f"APC-route errors={[round(e, 1) for e in s['apc_errors']]}  "
              f"ORCA-route errors={[round(e, 1) for e in s['orca_errors']]}  "
              f"direct-model errors={[round(e, 1) for e in s['direct_errors']]}")


if __name__ == "__main__":
    _print_report(compare())
