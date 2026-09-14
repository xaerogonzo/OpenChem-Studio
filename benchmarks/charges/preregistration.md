<!-- Written in the session scratchpad on 2026-09-14 before the oracle first ran, and copied here unchanged when the findings were committed. This comment is its only edit. -->

# W5a oracle tolerances, fixed before any oracle runs (2026-09-14)

Written after reading eem.cpp, qeq.cpp and the parameter files, and after the
data-directory probe, but BEFORE any independent solve has been run or its
output seen.

## What each oracle compares

(b) implementation oracle, per method: Open Babel's charges against an
independent solve of the SAME equations Open Babel documents, with the SAME
approximations, parameters and serialized molblock. Differences can then only
come from implementation.

- EEM: Bultinck 2002 II eq 1, which is the matrix eem.cpp builds: diagonal
  B (= 2 eta*, in Hartree), off-diagonal kappa/R with R in angstrom, last
  column -1, last row +1, right-hand side -A and the total formal charge.
  Parameter row chosen by eem.cpp's rule: the first row in file order
  matching (Z, highest bond order), then (Z, *), then (*, *).
- QEq: Rappe-Goddard 1991 eqs 12-13 in the form of qeq.cpp's documented
  energy, E = q.chi + 1/2 q J q with sum(q) = Q. Stationarity gives
  sum_j J_ij q_j - lambda = -chi_i. qeq.cpp's two documented departures are
  applied to both sides: Gaussian Coulomb integrals erf(pR)/R with
  p = sqrt(ab/(a+b)), a = 1/sigma^2 in bohr^-2; and hydrogen's charge-independent
  J and radius. Units: eV x 3.67493245e-2 to Hartree; angstrom / 0.529177249 to bohr.

## Tolerances

- EEM (b): max |dq| <= 1e-4 e over all atoms (the plan's stop rule).
- QEq (b): max |dq| <= 1e-4 e over all atoms. The comparison uses the same
  approximations on both sides, so no method difference is allowed for.
- QEq (c), against Rappe-Goddard Table IV's printed QEq column: informational
  only, NOT a stop condition. Open Babel omits hydrogen's charge dependence
  and uses Gaussian orbitals, and the paper gives no geometries. Recorded as
  the sign of each heavy atom and of H(O), and max |dq|, with no threshold.
- EEM (a2), against Bultinck 2002 II Table 2 (Mulliken): a parameter agrees
  if the file value, converted to the paper's units, rounds to the printed
  two decimals (|diff| <= 0.005 eV). chi* is compared as a difference from H,
  because the table shifts H to 1.00 eV.

## Stop rule (from the plan, unchanged)

Stop a method and bring it back for a decision if either:
- Open Babel cannot compute it on Windows without changing other Open Babel
  behaviour; or
- its charges miss the (b) solve above by more than the stated tolerance.
