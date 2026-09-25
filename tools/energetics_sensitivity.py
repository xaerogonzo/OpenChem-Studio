"""How much does the Kamlet-Jacobs estimate move when its two inputs are wrong?

The application's detonation calculator takes two numbers it cannot estimate for the user -- a loading
density and a condensed-phase enthalpy of formation -- and every candidate method the survey compares
predicts one of them with an error. Before deciding which of the two is worth the effort, this measures how
the estimate propagates each one's error, through the module's OWN equations (`chem/energetics.py`), so it
cannot disagree with what the calculator would say.

**THREE THINGS, KEPT SEPARATE, BECAUSE THEY ANSWER THREE DIFFERENT QUESTIONS**

1. *Local sensitivity* -- the analytic elasticity at the nominal point. With Phi = N sqrt(M Q):

       P = K rho^2 Phi          d ln P / d ln rho = 2
       D = A sqrt(Phi) (1 + B rho)   d ln D / d ln rho = B rho / (1 + B rho)
       Q = 1000 (28.9 b + 47 (d - b/2) + H) / FW         d Q / d H = 1000 / FW  (cal/g per kcal/mol)

   so d ln P / d H = 0.5 (dQ/dH) / Q and d ln D / d H = 0.25 (dQ/dH) / Q. A slope, valid for a small step.
2. *A finite perturbation* through the real equation (nominal, minus sigma, plus sigma), because P goes as
   rho squared and a slope understates a step of realistic size.
3. *Realistic input uncertainty* -- what a particular method's error actually is. **NOT computed here.**
   `--sigma-rho` and `--sigma-h` are what the caller says they are; the defaults are ILLUSTRATIVE
   magnitudes and are labelled so in the output. A validation RMSE is never a per-molecule interval.

**IT ANSWERS FOR ONE COMPOUND.** "Density dominates the error budget" is a claim about a SET, and the set
(a sourced known-explosives table) does not exist yet. What this gives is the worked example, honestly
scoped, and the machinery to run over the set when it does.

    python tools/energetics_sensitivity.py --preset rdx-table-iii
    python tools/energetics_sensitivity.py --smiles "<SMILES>" --rho 1.80 --enthalpy 14.7
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

from rdkit import Chem

from openchem.chem import energetics as E

#: Illustrative magnitudes for the two input errors, used ONLY when the caller gives none. Kim et al. 2008
#: (J. Comput. Chem., held; see docs/research/literature.toml) say, from their own preliminary work, that
#: performance needs a density "within an error of 0.03 g/cc" and a heat of formation "within 5 kcal/mol".
#: These are not those figures and not any method's error: they are round numbers of the size the
#: literature discusses, chosen so the two inputs are perturbed by comparable-looking amounts.
ILLUSTRATIVE_SIGMA_RHO = 0.04
ILLUSTRATIVE_SIGMA_H = 9.3

#: The Kamlet-Jacobs 1968 Table III row for RDX, as `tests/test_energetics.py` records it: the four inputs
#: to Eqs. (8) and (9) and the printed results. The enthalpy is not printed; it is what the paper's Q
#: implies through Eq. (15b), which is how the module's own tests treat the same table.
RDX_TABLE_III = {
    "smiles": "O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]",
    "rho": 1.712, "q_cal_per_g": 1496.0, "printed_p_kbar": 311.9, "printed_d_mm_us": 8.512,
}


@dataclass(frozen=True)
class Point:
    """One evaluation of the estimate, in the units the calculator reports."""

    rho: float
    enthalpy: float
    q: float
    p: float
    d: float


def _counts(mol: Chem.Mol) -> tuple[int, int, int, int]:
    balance = E.oxygen_balance(mol)
    return balance.carbon, balance.hydrogen, E._nitrogen_count(mol), balance.oxygen


def enthalpy_implied_by_q(mol: Chem.Mol, q_cal_per_g: float) -> float:
    """The condensed enthalpy (kcal/mol) that Eq. (15b) turns into `q_cal_per_g`."""
    a, b, c, d = _counts(mol)
    formula_weight = 12 * a + b + 14 * c + 16 * d
    return q_cal_per_g * formula_weight / 1000.0 - E._Q_WATER_PER_HYDROGEN * b - E._Q_CARBON_DIOXIDE * (d - b / 2)


def evaluate(mol: Chem.Mol, rho: float, enthalpy: float) -> Point:
    """The estimate at one (density, enthalpy), through the calculator's own function."""
    result = E.detonation(mol, rho, enthalpy)
    if not result.applicable:
        raise ValueError(f"Kamlet-Jacobs does not apply: {result.refusal.value} {result.detail}".strip())
    return Point(rho, enthalpy, result.heat_of_detonation, result.pressure_kbar, result.velocity_mm_per_us)


def local_sensitivity(mol: Chem.Mol, rho: float, enthalpy: float) -> dict[str, float]:
    """The analytic elasticities at the nominal point (see the module docstring)."""
    a, b, c, d = _counts(mol)
    formula_weight = 12 * a + b + 14 * c + 16 * d
    nominal = evaluate(mol, rho, enthalpy)
    dq_dh = 1000.0 / formula_weight
    b_rho = E.DETONATION_VELOCITY_B * rho
    return {
        "dlnP_dlnrho": 2.0,
        "dlnD_dlnrho": b_rho / (1.0 + b_rho),
        "dlnP_dH_per_kcal": 0.5 * dq_dh / nominal.q,
        "dlnD_dH_per_kcal": 0.25 * dq_dh / nominal.q,
        "dlnQ_dH_per_kcal": dq_dh / nominal.q,
    }


def perturb(mol: Chem.Mol, rho: float, enthalpy: float, sigma_rho: float, sigma_h: float) -> list[dict]:
    """Nominal, then minus and plus one sigma in each input alone, as relative changes."""
    nominal = evaluate(mol, rho, enthalpy)
    rows = []
    for label, dr, dh in (
        (f"rho -{sigma_rho:g}", -sigma_rho, 0.0), (f"rho +{sigma_rho:g}", sigma_rho, 0.0),
        (f"H -{sigma_h:g}", 0.0, -sigma_h), (f"H +{sigma_h:g}", 0.0, sigma_h),
    ):
        moved = evaluate(mol, rho + dr, enthalpy + dh)
        rows.append({
            "label": label,
            "dQ_pct": 100.0 * (moved.q / nominal.q - 1.0),
            "dP_pct": 100.0 * (moved.p / nominal.p - 1.0),
            "dD_pct": 100.0 * (moved.d / nominal.d - 1.0),
        })
    return rows


def report(mol: Chem.Mol, rho: float, enthalpy: float, sigma_rho: float, sigma_h: float, *, sigmas_are_defaults: bool) -> str:
    nominal = evaluate(mol, rho, enthalpy)
    slopes = local_sensitivity(mol, rho, enthalpy)
    lines = [
        f"nominal: rho = {rho:g} g/cm3, H(condensed) = {enthalpy:.2f} kcal/mol  ->  "
        f"Q = {nominal.q:.0f} cal/g, P = {nominal.p:.1f} kbar, D = {nominal.d:.3f} mm/us",
        "",
        "1. local sensitivity (analytic elasticities at the nominal point)",
        f"   d ln P / d ln rho = {slopes['dlnP_dlnrho']:.2f}      d ln D / d ln rho = {slopes['dlnD_dlnrho']:.3f}",
        f"   d ln P / dH = {100 * slopes['dlnP_dH_per_kcal']:.3f} % per kcal/mol      "
        f"d ln D / dH = {100 * slopes['dlnD_dH_per_kcal']:.3f} % per kcal/mol      "
        f"d ln Q / dH = {100 * slopes['dlnQ_dH_per_kcal']:.3f} % per kcal/mol",
        "",
        "2. finite perturbation through the real equation (one input at a time)"
        + ("   [ILLUSTRATIVE sigmas, not any method's error]" if sigmas_are_defaults else ""),
        f"   {'step':<16}{'dQ %':>9}{'dP %':>9}{'dD %':>9}",
    ]
    for row in perturb(mol, rho, enthalpy, sigma_rho, sigma_h):
        lines.append(f"   {row['label']:<16}{row['dQ_pct']:>+9.2f}{row['dP_pct']:>+9.2f}{row['dD_pct']:>+9.2f}")
    lines += [
        "",
        "3. realistic input uncertainty: NOT computed here. It is each method's measured validation error,",
        "   on a leakage-checked set, and a validation RMSE is never a per-molecule interval.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--preset", choices=["rdx-table-iii"], help="the Kamlet-Jacobs 1968 Table III RDX row")
    parser.add_argument("--smiles")
    parser.add_argument("--rho", type=float, help="loading density, g/cm3")
    parser.add_argument("--enthalpy", type=float, help="condensed-phase enthalpy of formation, kcal/mol")
    parser.add_argument("--sigma-rho", type=float)
    parser.add_argument("--sigma-h", type=float)
    args = parser.parse_args(argv)

    if args.preset == "rdx-table-iii":
        mol = Chem.MolFromSmiles(RDX_TABLE_III["smiles"])
        rho = RDX_TABLE_III["rho"]
        enthalpy = enthalpy_implied_by_q(mol, RDX_TABLE_III["q_cal_per_g"])
        print(f"RDX, Kamlet-Jacobs 1968 Table III: rho {rho}, Q {RDX_TABLE_III['q_cal_per_g']:.0f} cal/g "
              f"(printed P {RDX_TABLE_III['printed_p_kbar']}, D {RDX_TABLE_III['printed_d_mm_us']}); "
              f"H implied by Eq. (15b) = {enthalpy:.2f} kcal/mol\n")
    else:
        if not (args.smiles and args.rho is not None and args.enthalpy is not None):
            parser.error("give --preset, or --smiles with --rho and --enthalpy")
        mol = Chem.MolFromSmiles(args.smiles)
        rho, enthalpy = args.rho, args.enthalpy
    defaults = args.sigma_rho is None and args.sigma_h is None
    sigma_rho = args.sigma_rho if args.sigma_rho is not None else ILLUSTRATIVE_SIGMA_RHO
    sigma_h = args.sigma_h if args.sigma_h is not None else ILLUSTRATIVE_SIGMA_H
    print(report(mol, rho, enthalpy, sigma_rho, sigma_h, sigmas_are_defaults=defaults))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
