"""TRIAGE 2.10 part 2: recompute Chen's Table 2.2 Gaussian exponents from thesis section 2.4.

    uv run --no-sync python benchmarks/charges/models/qtpie_exponent_check.py

For each of the 16 elements, alpha* minimises the L2 norm over R in [0, inf) of J_G(R; alpha) - J_S(R;
zeta, n) (eqs 2.13, 2.16), and the error column is max_R |J_G - J_S| (eq 2.17). J_S is the shipped exact
ns-Slater Coulomb integral; J_G is the thesis appendix's own `sGTOCoulInt`. Everything is in hartree and
bohr. Writes `qtpie_exponents.json` beside this file and prints the registered verdicts.
"""
from __future__ import annotations

import json
import math
import pathlib

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import erf

from openchem.chem import charge_equilibration as ce

HERE = pathlib.Path(__file__).resolve().parent
#: Table 2.2 (thesis p 69), as printed: element, Slater exponent, Gaussian exponent, error column.
TABLE_2_2 = [
    ("H", 1.0698, 0.5434, 0.01696), ("Li", 0.4174, 0.1668, 0.00148), ("C", 0.8563, 0.2069, 0.00162),
    ("N", 0.9089, 0.2214, 0.00166), ("O", 0.9745, 0.2240, 0.00167), ("F", 0.9206, 0.2313, 0.00169),
    ("Na", 0.4364, 0.0959, 0.00085), ("Si", 0.7737, 0.1052, 0.00088), ("P", 0.8257, 0.1085, 0.00089),
    ("S", 0.8690, 0.1156, 0.00092), ("Cl", 0.9154, 0.1137, 0.00091), ("K", 0.4524, 0.0602, 0.00125),
    ("Br", 1.0253, 0.0701, 0.00133), ("Rb", 0.5162, 0.0420, 0.00121), ("I", 1.0726, 0.0686, 0.00127),
    ("Cs", 0.5663, 0.0307, 0.00114),
]
#: Appendix A (thesis p 201), `GaussianExponent`, in the same element order.
APPENDIX = [
    0.534337523756312, 0.166838519142176, 0.206883838259186, 0.221439796025873, 0.223967308625516,
    0.231257590182828, 0.095892938712585, 0.105219608142377, 0.108476721661715, 0.115618357843499,
    0.113714050615107, 0.060223294377778, 0.070087547802259, 0.041999054745368, 0.068562697575073,
    0.030719481189777,
]
R_MAX = 80.0  # bohr; both integrands' differences are below 1e-25 there for the most diffuse element
PANELS, ORDER = 800, 16
REL = 1e-4


def grid() -> tuple[np.ndarray, np.ndarray]:
    x, w = np.polynomial.legendre.leggauss(ORDER)
    # Denser near the origin, where both integrals vary fastest.
    edges = R_MAX * (np.linspace(0.0, 1.0, PANELS + 1) ** 2)
    half, mid = (edges[1:] - edges[:-1]) / 2, (edges[1:] + edges[:-1]) / 2
    return (mid[:, None] + half[:, None] * x).ravel(), (half[:, None] * w).ravel()


def j_gauss(alpha: float, r: np.ndarray) -> np.ndarray:
    p = math.sqrt(alpha * alpha / (2 * alpha))
    out = np.empty_like(r)
    small = r < 1e-12
    out[small] = 2 * p / math.sqrt(math.pi)
    out[~small] = erf(p * r[~small]) / r[~small]
    return out


def main() -> None:
    r, w = grid()
    dense = np.concatenate([[0.0], np.geomspace(1e-6, R_MAX, 20000)])
    rows, gate = [], []
    for (element, zeta, table_alpha, table_error), appendix in zip(TABLE_2_2, APPENDIX):
        n = ce.QEQ_TABLE_I[element][0]
        assert abs(ce.QEQ_TABLE_I[element][4] - zeta) < 1e-12, f"{element}: Table 2.2 zeta is not Table I's"
        js = ce.coulomb_pair_integrals(n, n, np.full(r.size, zeta), np.full(r.size, zeta), r)
        js_dense = ce.coulomb_pair_integrals(n, n, np.full(dense.size, zeta), np.full(dense.size, zeta), dense)

        def l2(alpha: float) -> float:
            return float(np.sum(w * (j_gauss(alpha, r) - js) ** 2))

        fit = minimize_scalar(l2, bounds=(0.005, 3.0), method="bounded", options={"xatol": 1e-13, "maxiter": 500})
        alpha = float(fit.x)

        def mae(a: float) -> float:
            return float(np.max(np.abs(j_gauss(a, dense) - js_dense)))

        row = {
            "element": element, "n": n, "zeta": zeta, "alpha_fit": alpha,
            "appendix": appendix, "table": table_alpha, "table_error": table_error,
            "rel_to_appendix": abs(alpha - appendix) / appendix, "rel_to_table": abs(alpha - table_alpha) / table_alpha,
            "mae_at_appendix": mae(appendix), "mae_at_table": mae(table_alpha), "mae_at_fit": mae(alpha),
            "l2_at_fit": l2(alpha), "l2_at_appendix": l2(appendix), "l2_at_table": l2(table_alpha),
        }
        row["gate_a"] = row["rel_to_appendix"] <= REL
        row["gate_b"] = round(alpha, 4) == table_alpha
        row["gate_c"] = round(row["mae_at_appendix"], 5) == table_error
        rows.append(row)
        if element != "H":
            gate.append(row["gate_a"] and row["gate_b"] and row["gate_c"])
        print(f"{element:2} n={n} alpha*={alpha:.9f} appendix={appendix:.9f} table={table_alpha:.4f} "
              f"rel(app)={row['rel_to_appendix']:.2e} rel(tab)={row['rel_to_table']:.2e} "
              f"MAE(app)={row['mae_at_appendix']:.5f} MAE(tab)={row['mae_at_table']:.5f} printed={table_error:.5f} "
              f"a={row['gate_a']} b={row['gate_b']} c={row['gate_c']}")

    validated = all(gate)
    h = rows[0]
    if not validated:
        verdict = "READING-NOT-VALIDATED"
    elif h["rel_to_appendix"] <= REL and h["rel_to_table"] > REL:
        verdict = "TABLE-TRANSPOSITION"
    elif h["rel_to_table"] <= REL and h["rel_to_appendix"] > REL:
        verdict = "APPENDIX-DIFFERS"
    else:
        verdict = "NEITHER"
    summary = {"reading_gate_passed": f"{sum(gate)}/{len(gate)}", "reading_validated": validated, "hydrogen_verdict": verdict}
    print(json.dumps(summary))
    (HERE / "qtpie_exponents.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
