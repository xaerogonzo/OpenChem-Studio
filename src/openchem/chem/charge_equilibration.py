"""Geometry-dependent partial charges: Rappé–Goddard QEq and Bultinck EEM.

Both are implemented here from their papers, in numpy, on explicit
coordinates. Open Babel ships both, and neither of its implementations could
be used: its QEq returns charges of the wrong sign and replaces the paper's
Slater orbitals and hydrogen treatment, and its EEM parameter file matches
neither part of the Bultinck paper it is labelled with. Open Babel survives
only as a compatibility benchmark (`benchmarks/charges/`).

EVERY CHOICE THE PAPERS LEAVE OPEN IS PRE-REGISTERED, not decided here:
`benchmarks/charges/rappe_goddard/preregistration.md`, committed before this
file existed. The four readings of Rappé & Goddard that the paper leaves
ambiguous are `QEqReadings`. `PREREGISTERED` is the one fixed in advance, and
the others exist so they can be reported beside it. `ADOPTED` is the one the
solver uses by default: lambda = 1/2 for every element (eq 17'), chosen by
Alex on 2026-09-14 AFTER the tables had been compared (amendment A6). It is
the reading the paper's text describes, and it is recorded as a post-hoc
choice, not as the pre-registered result.

Pure by design: element symbols, coordinates in angstrom and a net charge
in, charges out. No RDKit and no molecule model, so the solver's atoms are
exactly its input's, in its input's order, and nothing here can reorder or
drop one.

Units follow the papers: QEq in eV and angstrom with a0 = 0.52917 A (Rappé &
Goddard, under eq 17) [source:rappe1991]; EEM in atomic units, as its eq 2
requires [source:bultinck2002a]. EEM itself is Mortier, Ghosh & Shankar's
formalism [source:mortier1986], which Bultinck re-parameterised.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

#: eV per hartree, the one conversion both methods use (pre-registration section 2).
HARTREE_EV = 27.211386
#: Rappé & Goddard state a0 = 0.52917 A under eq 17; QEq uses exactly that.
QEQ_BOHR_ANGSTROM = 0.52917
#: Bultinck part I states no value; CODATA 2018 (pre-registration amendment A1).
EEM_BOHR_ANGSTROM = 0.529177210903

#: Atoms closer than this are refused before any integral is taken: two
#: centres that coincide are a broken structure, not a chemistry question.
OVERLAP_ANGSTROM = 0.1

# --- Rappé & Goddard 1991, Table I ------------------------------------------
#: element: (n, chi eV, J eV, R angstrom, zeta bohr^-1), as printed. n is not
#: printed: it is the valence shell's principal quantum number, which eq 15
#: needs. Transcribed from the page rendered at 300 dpi; the test holds this
#: table equal to tests/fixtures/charges/rappe1991_table1.csv.
QEQ_TABLE_I: dict[str, tuple[int, float, float, float, float]] = {
    "Li": (2, 3.006, 4.772, 1.557, 0.4174),
    "C": (2, 5.343, 10.126, 0.759, 0.8563),
    "N": (2, 6.899, 11.760, 0.715, 0.9089),
    "O": (2, 8.741, 13.364, 0.669, 0.9745),
    "F": (2, 10.874, 14.948, 0.706, 0.9206),
    "Na": (3, 2.843, 4.592, 2.085, 0.4364),
    "Si": (3, 4.168, 6.974, 1.176, 0.7737),
    "P": (3, 5.463, 8.000, 1.102, 0.8257),
    "S": (3, 6.928, 8.972, 1.047, 0.8690),
    "Cl": (3, 8.564, 9.892, 0.994, 0.9154),
    "K": (4, 2.421, 3.84, 2.586, 0.4524),
    "Br": (4, 7.790, 8.850, 1.141, 1.0253),
    "Rb": (5, 2.331, 3.692, 2.770, 0.5162),
    "I": (5, 6.822, 7.524, 1.333, 1.0726),
    "Cs": (6, 2.183, 3.422, 2.984, 0.5663),
    "H": (1, 4.5280, 13.8904, 0.371, 1.0698),
}

#: How Table I's zeta column was produced, as DATA rather than a conditional
#: (eq 17, zeta = lambda (2n+1) / (2 R/a0)). Checked while transcribing: 0.4913
#: regenerates every heavy atom but O; hydrogen's 1.0698 needs 1/2 (eq 17');
#: O's printed 0.9745 follows from neither and is kept as printed (reading R3).
ZETA_PARAMETERIZATION = "rappe_table_I"
#: Eq 17's lambda for every heavy atom's printed zeta (Table II footnote b).
LAMBDA_HEAVY = 0.4913
#: Eq 17' (lambda = 1/2), which hydrogen's printed 1.0698 needs.
LAMBDA_HYDROGEN = 0.5

#: Hydrogen's charge-free parameters (Table III footnotes b and d; eqs 22, 24).
HYDROGEN_SETS: dict[str, tuple[float, float]] = {
    "experimental": (4.5280, 13.8904),
    "hf": (4.7174, 13.4725),
}
#: zeta_H at Q = 0 (eq 20), and the constant eqs 21 and 23 divide by.
ZETA_H0 = 1.0698

#: Valence electrons, for the charge bounds. Eq 5 prints Li, C and O; the rule
#: -(8 - v) <= Q <= v reproduces those three and is DERIVED for the rest.
VALENCE_ELECTRONS = {
    "Li": 1, "Na": 1, "K": 1, "Rb": 1, "Cs": 1,
    "C": 4, "Si": 4, "N": 5, "P": 5, "O": 6, "S": 6,
    "F": 7, "Cl": 7, "Br": 7, "I": 7,
}

# --- Bultinck et al. 2002 part I, Table 1 -----------------------------------
#: element: (chi* eV, eta* eV), the PRINTED eta*. Eq 3 puts 2 eta* on the
#: diagonal; that factor lives in `eem_system`, never in this table.
EEM_BULTINCK2002_PART1: dict[str, tuple[float, float]] = {
    "H": (1.00, 17.95),
    "C": (5.25, 9.00),
    "N": (8.80, 9.39),
    "O": (14.72, 14.34),
    "F": (15.00, 19.77),
}
#: Recorded in provenance: eq 3 with 2 eta* on the diagonal, in atomic units.
EEM_EQUATION_CONVENTION = "bultinck2002_eq3_atomic_units"

# --- Refusal codes -----------------------------------------------------------
#: The method's own table has no parameters for an element in the molecule.
REFUSE_ELEMENT_NOT_PARAMETERISED = "REFUSE_ELEMENT_NOT_PARAMETERISED"
#: Two centres closer than OVERLAP_ANGSTROM.
REFUSE_OVERLAPPING_ATOMS = "REFUSE_OVERLAPPING_ATOMS"
#: QEq's hydrogen loop did not settle; no charges are returned.
REFUSE_NOT_CONVERGED = "REFUSE_NOT_CONVERGED"


# =============================================================================
# The Coulomb integral between two normalised ns Slater densities
# =============================================================================
#
# rho(r) = a^(2n+1) r^(2n-2) e^(-a r) / (4 pi (2n)!), a = 2 zeta  (eq 15, squared)
#
# Production evaluation, pre-registered in section 5: spherical shells with
# closed-form potentials, integrated over the second density by quadrature.
# The tests hold it against a momentum-space integral and a 30-digit mpmath
# table that share none of this code.

#: How often the near-zero shell-average branch has been taken. O1 asserts the
#: pre-registered near-zero points really reach it: a branch no test enters
#: is a branch no test checks.
NEAR_ZERO_BRANCH_USES = {"count": 0}
#: Below this ratio of s to R (or R to s) the shell difference cancels.
_NEAR_ZERO_RATIO = 1e-3
#: Terms of the lower incomplete gamma series; x < m + 1 <= 15 converges well inside it.
_SERIES_TERMS = 80


def _upper_gamma(m: int, x: np.ndarray) -> np.ndarray:
    """Regularised upper incomplete gamma Q(m, x) = e^-x sum_{k<m} x^k/k!.

    Every term is positive, so there is nothing to cancel.
    """
    x = np.asarray(x, dtype=float)
    term = np.ones_like(x)
    total = np.ones_like(x)
    for k in range(1, m):
        term = term * x / k
        total = total + term
    return np.exp(-x) * total


def _lower_gamma(m: int, x: np.ndarray) -> np.ndarray:
    """Regularised lower incomplete gamma P(m, x).

    **THE SERIES BELOW x = m + 1, BECAUSE 1 - Q CANCELS THERE.** Near the
    nucleus P(2n+1, ar) is of order (ar)^(2n+1), and computing it as one minus
    a number within 1e-16 of one returns noise that the potential then divides
    by r. The series e^-x sum_{k>=m} x^k/k! has only positive terms.
    """
    x = np.asarray(x, dtype=float)
    result = np.empty_like(x)
    small = x < m + 1
    if np.any(small):
        xs = x[small]
        term = np.exp(-xs + m * np.log(np.where(xs > 0, xs, 1.0)) - math.lgamma(m + 1))
        term = np.where(xs > 0, term, 0.0)
        total = term.copy()
        for k in range(m + 1, m + _SERIES_TERMS):
            term = term * xs / k
            total = total + term
        result[small] = total
    if np.any(~small):
        result[~small] = 1.0 - _upper_gamma(m, x[~small])
    return result


def slater_density(n: int, zeta: float, r: np.ndarray) -> np.ndarray:
    a = 2.0 * zeta
    r = np.asarray(r, dtype=float)
    return a ** (2 * n + 1) * r ** (2 * n - 2) * np.exp(-a * r) / (4.0 * math.pi * math.factorial(2 * n))


def slater_potential(n: int, zeta: float, r: np.ndarray) -> np.ndarray:
    """V(r) = P(2n+1, ar)/r + (a/2n) Q(2n, ar), hartree for r in bohr."""
    a = 2.0 * zeta
    r = np.asarray(r, dtype=float)
    safe = np.where(r > 0, r, 1.0)
    inner = np.where(r > 0, _lower_gamma(2 * n + 1, a * r) / safe, 0.0)
    return inner + (a / (2 * n)) * _upper_gamma(2 * n, a * r)


def _potential_primitive(n: int, zeta: float, r: np.ndarray) -> np.ndarray:
    """W(r) = integral_0^r V(t) t dt, in closed form.

    By parts, with P and Q regularised:
        integral_0^r P(m, at) dt   = r P(m, ar) - (m/a) P(m+1, ar)
        integral_0^r t Q(m, at) dt = (r^2/2) Q(m, ar) + m(m+1)/(2a^2) P(m+2, ar)
    so W(r) = r P(2n+1, ar) + (a r^2 / 4n) Q(2n, ar) - ((2n+1)/(2a)) P(2n+2, ar).
    """
    a = 2.0 * zeta
    r = np.asarray(r, dtype=float)
    x = a * r
    return (
        r * _lower_gamma(2 * n + 1, x)
        + (a * r * r / (4 * n)) * _upper_gamma(2 * n, x)
        - ((2 * n + 1) / (2 * a)) * _lower_gamma(2 * n + 2, x)
    )


def shell_average(n: int, zeta: float, s: np.ndarray, R: float) -> np.ndarray:
    """The potential of density (n, zeta) at the origin, averaged over a sphere
    of radius s whose centre is R away.

    [W(R+s) - W(|R-s|)] / (2sR), except where one of s and R is a thousandth of
    the other: there the difference cancels, and the mean-value expansion
    (with Poisson's del^2 V = -4 pi rho) is used instead.
    """
    s = np.asarray(s, dtype=float)
    R = float(R)
    out = np.empty_like(s)
    small_s = s < _NEAR_ZERO_RATIO * R
    small_r = R < _NEAR_ZERO_RATIO * s
    regular = ~(small_s | small_r)
    if np.any(regular):
        sr = s[regular]
        out[regular] = (_potential_primitive(n, zeta, R + sr) - _potential_primitive(n, zeta, np.abs(R - sr))) / (2.0 * sr * R)
    if np.any(small_s):
        NEAR_ZERO_BRANCH_USES["count"] += int(np.count_nonzero(small_s))
        ss = s[small_s]
        out[small_s] = slater_potential(n, zeta, np.full_like(ss, R)) - (2.0 * math.pi / 3.0) * ss * ss * slater_density(n, zeta, np.full_like(ss, R))
    if np.any(small_r):
        NEAR_ZERO_BRANCH_USES["count"] += int(np.count_nonzero(small_r))
        sr = s[small_r]
        out[small_r] = slater_potential(n, zeta, sr) - (2.0 * math.pi / 3.0) * R * R * slater_density(n, zeta, sr)
    return out


#: Gauss-Legendre nodes by order, built once.
_LEGENDRE = {}
#: Gauss-Laguerre nodes by order, built once.
_LAGUERRE = {}


def _legendre(order: int):
    if order not in _LEGENDRE:
        _LEGENDRE[order] = np.polynomial.legendre.leggauss(order)
    return _LEGENDRE[order]


def _laguerre(order: int):
    if order not in _LAGUERRE:
        _LAGUERRE[order] = np.polynomial.laguerre.laggauss(order)
    return _LAGUERRE[order]


def coulomb_pair_integral(
    n_a: int, zeta_a: float, n_b: int, zeta_b: float, R: float,
    panel_order: int = 32, tail_order: int = 64,
) -> float:
    """The Coulomb integral between two normalised ns Slater densities, hartree,
    for centres R bohr apart.

    integral_0^inf 4 pi s^2 rho_b(s) <V_a>(s, R) ds, split at the kink s = R:
    composite Gauss-Legendre on [0, R] (panels no wider than 1/a_b) and
    Gauss-Laguerre in t = a_b (s - R) on [R, inf). The orders are parameters
    only so the pre-registered doubling check can raise them.
    """
    a_b = 2.0 * zeta_b
    total = 0.0
    if R > 0:
        panels = max(1, math.ceil(R * a_b))
        x, w = _legendre(panel_order)
        edges = np.linspace(0.0, R, panels + 1)
        half = (edges[1:] - edges[:-1]) / 2.0
        mid = (edges[1:] + edges[:-1]) / 2.0
        s = (mid[:, None] + half[:, None] * x[None, :]).ravel()
        weights = (half[:, None] * w[None, :]).ravel()
        total += float(np.sum(weights * 4.0 * math.pi * s * s * slater_density(n_b, zeta_b, s) * shell_average(n_a, zeta_a, s, R)))
    t, w = _laguerre(tail_order)
    s = R + t / a_b
    # rho_b without its exponential: the weight supplies e^-t, and e^(-a_b R) is
    # the rest of e^(-a_b s).
    radial = a_b ** (2 * n_b + 1) * s ** (2 * n_b - 2) / (4.0 * math.pi * math.factorial(2 * n_b))
    total += float(np.sum(w * 4.0 * math.pi * s * s * radial * shell_average(n_a, zeta_a, s, R))) * math.exp(-a_b * R) / a_b
    return total


# -----------------------------------------------------------------------------
# The same integral for many pairs at once (amendment A8, Stage 1)
# -----------------------------------------------------------------------------
#
# A PURE OPTIMISATION OF `coulomb_pair_integral`, NOT A SECOND METHOD. Each
# pair gets exactly the nodes the scalar routine would give it: its own panel
# count ceil(R a_b), its own panel edges from its own R, the same Legendre and
# Laguerre orders, and the same near-zero shell branches decided element by
# element. Pairs are grouped only by what fixes an array's shape (n_a, n_b
# and the panel count); every per-pair quantity (R, zeta_a, zeta_b) stays on
# its own row, and nothing is summed across rows. The scalar routine is kept
# as the reference a test holds this to, pair by pair.

#: Nodes per flat evaluation, so one call never builds arrays much past this.
_BATCH_NODES = 100000


def _primitive_gammas(n: int, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """P(2n+1, x), Q(2n, x) and P(2n+2, x) in one pass, for the potential primitive.

    Each value takes the branch its own scalar call would take: the series for
    P(m, x) exactly where x < m + 1, and 1 - Q(m, x) elsewhere. The two series
    share one loop because P(2n+2) is P(2n+1)'s sum without its first term,
    accumulated separately so nothing is subtracted. The loop stops once every
    new term is below 1e-17 of its running total, a change far under the
    1e-11 Ha pair-by-pair gate A8 sets against the scalar routine.
    """
    m = 2 * n + 1
    ex = np.exp(-x)
    # Q(2n, x) = e^-x sum_{k<2n} x^k/k!; Q(2n+1) and Q(2n+2) add the next terms.
    term = np.ones_like(x)
    total = np.ones_like(x)
    for k in range(1, 2 * n):
        term = term * x / k
        total = total + term
    q_2n = ex * total
    last = term * x / (2 * n)
    after = last * x / m
    p_m = 1.0 - ex * (total + last)
    p_m1 = 1.0 - ex * (total + last + after)
    small = x < m + 2  # the series region of P(m+1); P(m)'s is the part below m + 1
    if np.any(small):
        xs = x[small]
        first = np.exp(-xs + m * np.log(np.where(xs > 0, xs, 1.0)) - math.lgamma(m + 1))
        first = np.where(xs > 0, first, 0.0)
        term = first * xs / (m + 1)
        sum_m1 = term.copy()
        sum_m = first + term
        for k in range(m + 2, m + _SERIES_TERMS):
            term = term * xs / k
            sum_m = sum_m + term
            sum_m1 = sum_m1 + term
            if np.all(term <= 1e-17 * sum_m1):
                break
        idx = np.flatnonzero(small)
        below = xs < m + 1
        p_m[idx[below]] = sum_m[below]
        p_m1[idx] = sum_m1
    return p_m, q_2n, p_m1


def _potential_primitive_batch(n: int, a: np.ndarray, r: np.ndarray) -> np.ndarray:
    p_m, q_2n, p_m1 = _primitive_gammas(n, a * r)
    return r * p_m + (a * r * r / (4 * n)) * q_2n - ((2 * n + 1) / (2 * a)) * p_m1


def _slater_density_batch(n: int, a: np.ndarray, r: np.ndarray) -> np.ndarray:
    return a ** (2 * n + 1) * r ** (2 * n - 2) * np.exp(-a * r) / (4.0 * math.pi * math.factorial(2 * n))


def _slater_potential_batch(n: int, a: np.ndarray, r: np.ndarray) -> np.ndarray:
    safe = np.where(r > 0, r, 1.0)
    inner = np.where(r > 0, _lower_gamma(2 * n + 1, a * r) / safe, 0.0)
    return inner + (a / (2 * n)) * _upper_gamma(2 * n, a * r)


def _shell_average_flat(n: int, a: np.ndarray, s: np.ndarray, R: np.ndarray) -> np.ndarray:
    """`shell_average` on flat, equal-length arrays: element i is one node of one pair."""
    small_s = s < _NEAR_ZERO_RATIO * R
    small_r = R < _NEAR_ZERO_RATIO * s
    regular = ~(small_s | small_r)
    if np.all(regular):
        return (_potential_primitive_batch(n, a, R + s) - _potential_primitive_batch(n, a, np.abs(R - s))) / (2.0 * s * R)
    out = np.empty(s.shape)
    if np.any(regular):
        ar, sr, rr = a[regular], s[regular], R[regular]
        out[regular] = (_potential_primitive_batch(n, ar, rr + sr) - _potential_primitive_batch(n, ar, np.abs(rr - sr))) / (2.0 * sr * rr)
    if np.any(small_s):
        NEAR_ZERO_BRANCH_USES["count"] += int(np.count_nonzero(small_s))
        ar, ss, rr = a[small_s], s[small_s], R[small_s]
        out[small_s] = _slater_potential_batch(n, ar, rr) - (2.0 * math.pi / 3.0) * ss * ss * _slater_density_batch(n, ar, rr)
    if np.any(small_r):
        NEAR_ZERO_BRANCH_USES["count"] += int(np.count_nonzero(small_r))
        ar, sr, rr = a[small_r], s[small_r], R[small_r]
        out[small_r] = _slater_potential_batch(n, ar, sr) - (2.0 * math.pi / 3.0) * rr * rr * _slater_density_batch(n, ar, sr)
    return out


def coulomb_pair_integrals(n_a: int, n_b: int, zeta_a, zeta_b, R, panel_order: int = 32, tail_order: int = 64) -> np.ndarray:
    """`coulomb_pair_integral` for arrays of pairs sharing (n_a, n_b): one
    hartree value per pair, in input order.

    Every pair's nodes are laid end to end in one flat array. Pair i
    contributes ceil(R_i a_b,i) panels of `panel_order` nodes on its own
    [0, R_i], with panel edges k R_i / count_i exactly as the scalar routine's
    linspace, and then its own Laguerre tail on [R_i, inf). Values are summed
    back per pair through a pair index, never across pairs.
    """
    zeta_a = np.asarray(zeta_a, dtype=float).ravel()
    zeta_b = np.asarray(zeta_b, dtype=float).ravel()
    R = np.asarray(R, dtype=float).ravel()
    pairs = len(R)
    out = np.zeros(pairs)
    a_a, a_b = 2.0 * zeta_a, 2.0 * zeta_b
    counts = np.where(R > 0, np.maximum(1, np.ceil(R * a_b)), 0).astype(np.int64)
    x, w = _legendre(panel_order)
    chunk_start = 0
    while chunk_start < pairs:
        nodes = np.cumsum(counts[chunk_start:] * panel_order)
        chunk_end = chunk_start + max(1, int(np.searchsorted(nodes, _BATCH_NODES, side="right")))
        c = counts[chunk_start:chunk_end]
        panel_row = np.repeat(np.arange(chunk_start, chunk_end), c)
        if len(panel_row):
            k = np.arange(len(panel_row)) - np.repeat(np.cumsum(c) - c, c)
            Rp = R[panel_row]
            step = Rp / counts[panel_row]
            lo = k * step
            hi = np.where(k + 1 == counts[panel_row], Rp, (k + 1) * step)
            half = (hi - lo) / 2.0
            mid = (hi + lo) / 2.0
            s = (mid[:, None] + half[:, None] * x[None, :]).ravel()
            weights = (half[:, None] * w[None, :]).ravel()
            node_row = np.repeat(panel_row, panel_order)
            integrand = weights * 4.0 * math.pi * s * s * _slater_density_batch(n_b, a_b[node_row], s)
            integrand = integrand * _shell_average_flat(n_a, a_a[node_row], s, R[node_row])
            out[chunk_start:chunk_end] += np.bincount(node_row - chunk_start, weights=integrand, minlength=chunk_end - chunk_start)
        chunk_start = chunk_end
    t, wt = _laguerre(tail_order)
    s = (R[:, None] + t[None, :] / a_b[:, None]).ravel()
    node_row = np.repeat(np.arange(pairs), tail_order)
    ab = a_b[node_row]
    radial = ab ** (2 * n_b + 1) * s ** (2 * n_b - 2) / (4.0 * math.pi * math.factorial(2 * n_b))
    tail = np.tile(wt, pairs) * 4.0 * math.pi * s * s * radial * _shell_average_flat(n_a, a_a[node_row], s, R[node_row])
    out += np.bincount(node_row, weights=tail, minlength=pairs) * np.exp(-a_b * R) / a_b
    return out


# =============================================================================
# Bounded linear solve: eqs 10-13, fix-and-re-solve
# =============================================================================


@dataclass
class BoundedSolve:
    charges: np.ndarray
    #: One entry per pass: the atoms fixed at the END of that pass, with their bounds.
    passes: list[dict[int, float]]


def solve_bounded(
    hardness: np.ndarray, chi: np.ndarray, net_charge: float,
    lower: np.ndarray, upper: np.ndarray,
) -> BoundedSolve:
    """Minimise chi.q + 1/2 q.C.q subject to sum q = net_charge and the bounds,
    by the paper's procedure repeated until nothing is out of range.

    Rappé & Goddard, eq 13: solve; fix every atom outside its range AT the
    boundary; move the fixed atoms' J_AB Q_B to the right-hand side and their
    charge out of the total; solve the reduced set. The paper describes one
    such pass. Repeating it is the pre-registered extension, and the caller
    flags any case that needed it. Fixed atoms are never released.

    **NEVER CLIP AND RENORMALISE.** Clipping the charges of one unconstrained
    solve and rescaling the rest is a different answer; O9 holds a case where
    they differ.
    """
    count = len(chi)
    fixed: dict[int, float] = {}
    passes: list[dict[int, float]] = []
    while True:
        free = [i for i in range(count) if i not in fixed]
        charges = np.zeros(count)
        for index, value in fixed.items():
            charges[index] = value
        if free:
            fixed_idx = np.array(sorted(fixed), dtype=int)
            fixed_q = np.array([fixed[i] for i in fixed_idx]) if len(fixed_idx) else np.zeros(0)
            size = len(free)
            matrix = np.zeros((size + 1, size + 1))
            rhs = np.zeros(size + 1)
            free_idx = np.array(free, dtype=int)
            matrix[:size, :size] = hardness[np.ix_(free_idx, free_idx)]
            matrix[:size, size] = -1.0
            matrix[size, :size] = 1.0
            # eq 13: chi^0F = chi^0 + sum_{B fixed} J_AB Q_B; the sign is -chi.
            shifted = chi[free_idx] + (hardness[np.ix_(free_idx, fixed_idx)] @ fixed_q if len(fixed_idx) else 0.0)
            rhs[:size] = -shifted
            rhs[size] = net_charge - fixed_q.sum()
            solution = np.linalg.solve(matrix, rhs)
            charges[free_idx] = solution[:size]
        crossed = {
            i: (upper[i] if charges[i] > upper[i] else lower[i])
            for i in free
            if charges[i] > upper[i] or charges[i] < lower[i]
        }
        fixed.update(crossed)
        passes.append(dict(fixed))
        if not crossed:
            return BoundedSolve(charges=charges, passes=passes)


# =============================================================================
# QEq
# =============================================================================


@dataclass(frozen=True)
class QEqReadings:
    """The four places Rappé & Goddard leave a choice open (pre-registration
    section 3). `PREREGISTERED` was fixed before any solve; each alternate
    differs from it in exactly one field, and `ADOPTED` is alternate R4."""

    #: R1: does zeta_H(Q) (eq 20) enter the two-centre integrals?
    zeta_h_in_pairs: bool = True
    #: R2: hydrogen's diagonal: "eq21" (section IV's solving procedure) or
    #: "eq23_gradient" (Table III footnote a).
    hydrogen_self_term: str = "eq21"
    #: R3: oxygen's zeta: "printed" (0.9745) or "from_radius" (eq 17, 0.9715).
    oxygen_zeta: str = "printed"
    #: R4: "table_i" (the printed zeta column) or "eq17_prime" (lambda = 1/2 for all).
    zeta_source: str = "table_i"


#: The readings fixed in advance ("P" in the benchmark). Kept so the
#: pre-registered result stays reproducible: it misses 39 of 76 Table III/IV cells.
PREREGISTERED = QEqReadings()
#: Each alternate differs from PREREGISTERED in one field.
ALTERNATES = {
    "R1": replace(PREREGISTERED, zeta_h_in_pairs=False),
    "R2": replace(PREREGISTERED, hydrogen_self_term="eq23_gradient"),
    "R3": replace(PREREGISTERED, oxygen_zeta="from_radius"),
    "R4": replace(PREREGISTERED, zeta_source="eq17_prime"),
}
#: The default: R4, lambda = 1/2 for every element (eq 17'). Adopted 2026-09-14
#: after the tables were compared, so a POST-HOC choice (amendment A6). The
#: paper's text supports it -- "Rounding off to lambda = 1/2 ... (17) becomes
#: (17')" -- and Table II prints a lambda = 1/2 column, which it reproduces;
#: Table II's other column (Table I's zeta) is PREREGISTERED's.
ADOPTED = ALTERNATES["R4"]


def charge_bounds(element: str) -> tuple[float, float]:
    """Eq 5 and 5': -(8 - v) <= Q <= v, and -1 <= Q_H <= +1."""
    if element == "H":
        return -1.0, 1.0
    valence = VALENCE_ELECTRONS[element]
    return -(8.0 - valence), float(valence)


def valence_zeta(element: str, readings: QEqReadings = ADOPTED) -> float:
    """The eq-15 exponent this reading uses for `element` at zero charge."""
    n, _chi, _j, radius, printed = QEQ_TABLE_I[element]
    radius_bohr = radius / QEQ_BOHR_ANGSTROM
    if readings.zeta_source == "eq17_prime":
        return 0.5 * (2 * n + 1) / (2.0 * radius_bohr)
    if element == "O" and readings.oxygen_zeta == "from_radius":
        return LAMBDA_HEAVY * (2 * n + 1) / (2.0 * radius_bohr)
    return printed


@dataclass
class QEqResult:
    status: str  # "converged", or a REFUSE_* code
    charges: np.ndarray | None = None
    #: solver index -> source index. The identity by construction, recorded
    #: rather than assumed so a caller writes charges back through it.
    solver_to_source: list[int] = field(default_factory=list)
    iterations: int = 0
    trace: list[dict] = field(default_factory=list)
    trace_class: str = ""
    bound_extension_used: bool = False
    bound_passes_max: int = 0
    #: The atoms fixed at a bound in the CONVERGED final solve, with their
    #: bounds (amendment A8). This, and only this, decides a bound refusal.
    final_active_atoms: dict[int, float] = field(default_factory=dict)
    #: Whether any pass of any hydrogen iteration fixed an atom. An iterate
    #: clamped mid-loop whose final solve is bound-free is still a valid result.
    ever_clamped: bool = False
    message: str = ""
    final_metrics: dict[str, float] = field(default_factory=dict)

    @property
    def clamped(self) -> dict[int, float]:
        """The name this field had before A8; the final active set, as it always was."""
        return self.final_active_atoms


def _distances_bohr(coords: np.ndarray, bohr_angstrom: float) -> np.ndarray:
    diff = coords[:, None, :] - coords[None, :, :]
    return np.sqrt(np.sum(diff * diff, axis=-1)) / bohr_angstrom


def _overlap(coords: np.ndarray) -> tuple[int, int] | None:
    if len(coords) < 2:
        return None
    diff = coords[:, None, :] - coords[None, :, :]
    dist = np.sqrt(np.sum(diff * diff, axis=-1))
    np.fill_diagonal(dist, np.inf)
    i, j = np.unravel_index(np.argmin(dist), dist.shape)
    return (int(min(i, j)), int(max(i, j))) if dist[i, j] < OVERLAP_ANGSTROM else None


class _QEqSystem:
    """Everything about one molecule's QEq matrix that the hydrogen loop does
    not change, built once; `build` adds what it does.

    A pair is invariant when neither atom's zeta depends on a hydrogen charge:
    under R1's "no" every pair is, otherwise every pair with a hydrogen varies.
    ONLY invariant pairs are reused across iterations. Caching a
    hydrogen-involving integral would freeze zeta_H(Q), the very quantity the
    adopted reading says moves with the charge (amendment A8).
    """

    def __init__(self, elements: list[str], coords: np.ndarray, hydrogen: str, readings: QEqReadings):
        self.elements = list(elements)
        self.readings = readings
        count = len(elements)
        self.chi_h, self.j_h = HYDROGEN_SETS[hydrogen]
        self.distance = _distances_bohr(np.asarray(coords, dtype=float).reshape(-1, 3), QEQ_BOHR_ANGSTROM)
        self.shells = np.array([QEQ_TABLE_I[e][0] for e in elements], dtype=int)
        self.zetas = np.array([valence_zeta(e, readings) for e in elements])
        self.hydrogens = [i for i, e in enumerate(elements) if e == "H"]
        self.chi = np.array([self.chi_h if e == "H" else QEQ_TABLE_I[e][1] for e in elements])
        variable = set(self.hydrogens) if readings.zeta_h_in_pairs else set()
        upper_i, upper_j = np.triu_indices(count, k=1)
        moves = np.array([i in variable or j in variable for i, j in zip(upper_i, upper_j)], dtype=bool)
        self.fixed = np.zeros((count, count))
        for i in range(count):
            if elements[i] != "H":
                self.fixed[i, i] = QEQ_TABLE_I[elements[i]][2]
        self._fill(self.fixed, upper_i[~moves], upper_j[~moves], self.zetas)
        self.moving_i, self.moving_j = upper_i[moves], upper_j[moves]

    def _fill(self, matrix: np.ndarray, rows: np.ndarray, cols: np.ndarray, zetas: np.ndarray) -> None:
        # coulomb_pair(i, j), i < j with i as the scalar routine's first density:
        # Table I's diagonal J is an atom's own idempotential; off it, the Slater integral.
        if len(rows) == 0:
            return
        keys = self.shells[rows] * 10 + self.shells[cols]
        for key in np.unique(keys):
            sel = keys == key
            r, c = rows[sel], cols[sel]
            values = coulomb_pair_integrals(int(key // 10), int(key % 10), zetas[r], zetas[c], self.distance[r, c]) * HARTREE_EV
            matrix[r, c] = values
            matrix[c, r] = values

    def build(self, hydrogen_charges: dict[int, float]) -> tuple[np.ndarray, np.ndarray, dict[int, tuple[float, float]]]:
        hardness = self.fixed.copy()
        zetas = self.zetas.copy()
        factor = 1.0 if self.readings.hydrogen_self_term == "eq21" else 1.5
        state: dict[int, tuple[float, float]] = {}
        for i in self.hydrogens:
            q = hydrogen_charges.get(i, 0.0)
            # hardness_diag_H: eq 21, J_HH(Q) = (1 + Q/zeta0) J0; or the diagonal
            # whose fixed point is eq 23's gradient, J0 (1 + 1.5 Q/1.0698).
            hardness[i, i] = self.j_h * (1.0 + factor * q / ZETA_H0)
            zeta_h = ZETA_H0 + q  # eq 20
            if self.readings.zeta_h_in_pairs:
                zetas[i] = zeta_h
            state[i] = (zeta_h, hardness[i, i])
        self._fill(hardness, self.moving_i, self.moving_j, zetas)
        return hardness, self.chi.copy(), state


def qeq_hardness_matrix(
    elements: list[str], coords: np.ndarray, hydrogen_charges: dict[int, float],
    hydrogen: str = "experimental", readings: QEqReadings = ADOPTED,
) -> tuple[np.ndarray, np.ndarray, dict[int, tuple[float, float]]]:
    """C (eV) and chi (eV) at the given hydrogen charges, plus each hydrogen's
    (zeta_H, hardness_diag_H). Public so the R1-isolation test can compare the
    matrices two readings build, not only their answers."""
    return _QEqSystem(elements, coords, hydrogen, readings).build(hydrogen_charges)


def _trace_class(deltas: list[float], signed: list[float]) -> str:
    recent = signed[-4:]
    flips = sum(1 for a, b in zip(recent, recent[1:]) if a * b < 0)
    if len(recent) >= 4 and flips >= 3:
        return "oscillating"
    if len(deltas) >= 5 and deltas[-1] > 0.9 * deltas[-5]:
        return "stalled"
    return "monotone"


def qeq_charges(
    elements: list[str], coords_angstrom, net_charge: float = 0.0,
    hydrogen: str = "experimental", readings: QEqReadings = ADOPTED,
    max_outer: int = 50, tolerance: float = 1e-8,
) -> QEqResult:
    """Rappé–Goddard charge equilibration on explicit coordinates.

    Outer loop: hydrogen self-consistency from Q = 0. Inner: a complete
    fix-and-re-solve for the hydrogen parameters of that iteration, rebuilt
    from nothing every time. Converged only when Q_H, zeta_H and
    hardness_diag_H all stop moving AND the fixed set stops changing; anything
    else is `REFUSE_NOT_CONVERGED` with no charges (pre-registration 4).
    """
    coords = np.asarray(coords_angstrom, dtype=float).reshape(-1, 3)
    count = len(elements)
    result = QEqResult(status="", solver_to_source=list(range(count)))
    missing = sorted({e for e in elements if e not in QEQ_TABLE_I})
    if missing:
        result.status = REFUSE_ELEMENT_NOT_PARAMETERISED
        result.message = f"Rappé–Goddard 1991 Table I has no parameters for {', '.join(missing)}."
        return result
    if hydrogen not in HYDROGEN_SETS:
        raise ValueError(f"Unknown hydrogen parameter set {hydrogen!r}; expected one of {sorted(HYDROGEN_SETS)}")
    pair = _overlap(coords)
    if pair is not None:
        result.status = REFUSE_OVERLAPPING_ATOMS
        result.message = f"Atoms {pair[0]} and {pair[1]} are closer than {OVERLAP_ANGSTROM} A."
        return result

    bounds = [charge_bounds(e) for e in elements]
    lower = np.array([b[0] for b in bounds])
    upper = np.array([b[1] for b in bounds])
    hydrogens = [i for i, e in enumerate(elements) if e == "H"]
    previous_q = {i: 0.0 for i in hydrogens}
    #: (zeta_H, hardness_diag_H) as the PREVIOUS build actually used them. The
    #: deltas are read off what each build used, not recomputed from Q, so a
    #: build that failed to update either one shows as not having moved.
    previous_state: dict[int, tuple[float, float]] | None = None
    previous_active: frozenset | None = None
    deltas: list[float] = []
    signed: list[float] = []
    system = _QEqSystem(elements, coords, hydrogen, readings)
    for outer in range(1, max_outer + 1):
        hardness, chi, state = system.build(previous_q)
        solved = solve_bounded(hardness, chi, net_charge, lower, upper)
        charges = solved.charges
        active = frozenset(solved.passes[-1].items())
        result.bound_passes_max = max(result.bound_passes_max, len(solved.passes))
        result.ever_clamped = result.ever_clamped or bool(solved.passes[-1])
        # The last pass always fixes nothing new. More than one pass that DID
        # fix something exceeds the paper's one-pass procedure.
        if len(solved.passes) > 2:
            result.bound_extension_used = True
        dq = max((abs(charges[i] - previous_q[i]) for i in hydrogens), default=0.0)
        if previous_state is None:
            dzeta = dhard = math.inf if hydrogens else 0.0
        else:
            dzeta = max((abs(state[i][0] - previous_state[i][0]) for i in hydrogens), default=0.0)
            dhard = max((abs(state[i][1] - previous_state[i][1]) for i in hydrogens), default=0.0)
        worst = max(hydrogens, key=lambda i: abs(charges[i] - previous_q[i]), default=None)
        signed.append(charges[worst] - previous_q[worst] if worst is not None else 0.0)
        deltas.append(dq)
        for number, fixed in enumerate(solved.passes, start=1):
            result.trace.append({
                "hydrogen_iteration": outer, "active_set_pass": number,
                "fixed": dict(fixed), "dQ_H": dq, "dzeta_H": dzeta, "dhardness_diag_H": dhard,
            })
        result.iterations = outer
        result.final_metrics = {"dQ_H": dq, "dzeta_H": dzeta, "dhardness_diag_H": dhard}
        if not hydrogens or (
            previous_active == active and dq <= tolerance and dzeta <= tolerance and dhard <= tolerance
        ):
            result.status = "converged"
            result.charges = charges
            result.final_active_atoms = dict(solved.passes[-1])
            return result
        previous_active = active
        previous_state = state
        previous_q = {i: float(charges[i]) for i in hydrogens}
    result.status = REFUSE_NOT_CONVERGED
    result.trace_class = _trace_class(deltas, signed)
    result.message = (
        f"QEq did not converge in {max_outer} hydrogen iterations "
        f"(last dQ_H {result.final_metrics.get('dQ_H', 0.0):.2e} e; {result.trace_class})."
    )
    return result


# =============================================================================
# EEM
# =============================================================================


@dataclass
class EEMResult:
    status: str
    charges: np.ndarray | None = None
    solver_to_source: list[int] = field(default_factory=list)
    equalized_electronegativity_ev: float | None = None
    message: str = ""


def eem_system(elements: list[str], coords_angstrom, net_charge: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Bultinck part I eq 3, in atomic units: the (N+1)x(N+1) matrix and its
    right-hand side. Diagonal 2 eta*, off-diagonal 1/R, last column -1, last
    row the charge constraint; right-hand side -chi* and Q."""
    coords = np.asarray(coords_angstrom, dtype=float).reshape(-1, 3)
    count = len(elements)
    distance = _distances_bohr(coords, EEM_BOHR_ANGSTROM)
    matrix = np.zeros((count + 1, count + 1))
    rhs = np.zeros(count + 1)
    for i, element in enumerate(elements):
        chi_star, eta_star = EEM_BULTINCK2002_PART1[element]
        matrix[i, i] = 2.0 * eta_star / HARTREE_EV
        rhs[i] = -chi_star / HARTREE_EV
        for j in range(count):
            if j != i:
                matrix[i, j] = 1.0 / distance[i, j]
    matrix[:count, count] = -1.0
    matrix[count, :count] = 1.0
    rhs[count] = net_charge
    return matrix, rhs


def eem_charges(elements: list[str], coords_angstrom, net_charge: float = 0.0) -> EEMResult:
    """Bultinck et al. 2002 part I EEM with its own Table 1 parameters.

    H, C, N, O and F only: any other element is refused by name, never given a
    neighbour's parameters or hydrogen's (which is what Open Babel's `* *` row
    does)."""
    coords = np.asarray(coords_angstrom, dtype=float).reshape(-1, 3)
    count = len(elements)
    result = EEMResult(status="", solver_to_source=list(range(count)))
    missing = sorted({e for e in elements if e not in EEM_BULTINCK2002_PART1})
    if missing:
        result.status = REFUSE_ELEMENT_NOT_PARAMETERISED
        result.message = f"Bultinck et al. 2002 part I Table 1 has no parameters for {', '.join(missing)}."
        return result
    pair = _overlap(coords)
    if pair is not None:
        result.status = REFUSE_OVERLAPPING_ATOMS
        result.message = f"Atoms {pair[0]} and {pair[1]} are closer than {OVERLAP_ANGSTROM} A."
        return result
    matrix, rhs = eem_system(elements, coords, net_charge)
    solution = np.linalg.solve(matrix, rhs)
    result.status = "converged"
    result.charges = solution[:count]
    result.equalized_electronegativity_ev = float(solution[count] * HARTREE_EV)
    return result
