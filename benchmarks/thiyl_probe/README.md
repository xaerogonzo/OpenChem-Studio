# The thiyl probe (exploratory, 2026-10-25 and 2026-10-26; NOT a benchmark record)

Why do the thiyl radicals keep an imaginary vibration? The bond-dissociation benchmark lost methanethiol's S-H to a mode of -1328 cm-1 on the methanethiyl radical; the restart-v2 stress set lost the two ethanethiyl conformers (-332 and -370 cm-1); and the displaced restart (`benchmarks/restart_diagnosis/`, then `benchmarks/restart_v2/`) made the methyl radical *worse* (-1743 and -1553) and left its energy where it was. A mode that deep at an ordinary-looking geometry (C-S 1.787 A, three C-H near 1.09 A) is not a soft direction of the structure.

**Nothing here changes a verdict, and nothing here was written before the data was seen.** It is the evidence a preregistration (`benchmarks/restart_v3/PREREGISTRATION.md`) can then be written on.

## What was run

`probe.py` takes the benchmark's own final geometry of a radical (the committed `runs.jsonl`) and changes ONE thing from the benchmark's setting (`! M062X def2-TZVPD TightSCF DefGrid3 Freq`, 4 cores, ORCA 6.1.1):

| variant | change |
|---|---|
| `freq_analytic` | none: must reproduce the failure |
| `freq_numerical` | `NumFreq`: finite differences of gradients, so no coupled-perturbed SCF step |
| `sp_stability` | a single point with `%scf StabPerform true`: is the unrestricted solution a minimum in orbital space, and how soft is its softest direction |
| `sp_guess_hcore`, `_hueckel`, `_patom`, `sp_default` | other starting orbitals: do they reach another SCF solution |
| `freq_b3lyp` | B3LYP for the analytic Freq, at the same geometry: is it the functional |

`artifacts/<case>/summary.json` holds each case's numbers and `<variant>/job.inp` and `job.out` the ORCA input and output.

## What it found

| radical | analytic lowest modes (cm-1) | numerical lowest modes | smallest stability eigenvalue (Eh), then the next two | analytic to numerical enthalpy |
|---|---|---|---|---|
| CH3S (methanethiyl) | **-1331.8**, 742.5, 870.1 | 600.8, 741.2, 860.0 | **0.00047**, 0.134, 0.192 | +1.57 mEh (+0.99 kcal/mol) |
| C2H5S, conformer 0 | **-332.0**, 255.4, 336.0 | 247.5, 336.1, 525.8 | **0.0015**, 0.123, 0.195 | +1.65 mEh (+1.03) |
| C2H5S, conformer 1 | **-369.9**, 251.8, 335.5 | 229.8, 337.6, 447.6 | **0.0015**, 0.124, 0.195 | +1.35 mEh (+0.85) |

1. **The imaginary mode is spurious.** The analytic and the numerical runs agree on every other mode to about 10 cm-1; the analytic run has replaced exactly one real mode (CH3S: the +601; C2H5S: the +526 and +448) with an imaginary one. The numerical run has no imaginary mode in any of the three. B3LYP's analytic Freq at the same geometry has none either (methylthiyl's lowest is +538).
2. **The wavefunction is stable, but its softest orbital-rotation direction is 100 times softer than the next.** An analytic Hessian divides by that number in its coupled-perturbed step, so an ill-conditioned one is the natural suspect. The probe shows the association (all three failing radicals have it) and does not isolate the cause inside ORCA.
3. **There is no second SCF state to chase.** Four starting guesses reach energies that agree to about 10 microhartree (CH3S: -438.041431 to -438.041442), the 0.007 kcal/mol that separates two near-degenerate components. The restart that moved along the "imaginary mode" had nothing to leave, which is why it failed.
4. **The enthalpy is wrong by about 1 kcal/mol even where no number is refused.** The analytic radical enthalpy differs from the numerical one by 0.85 to 1.03 kcal/mol for these three. With the numerical value, methanethiol's S-H is **84.97 kcal/mol** against 87.4 (Blanksby and Ellison; error -2.4); with the benchmark's analytic record it is 83.98 (error -3.4). *This was computed after the data was seen, and supports no verdict.*

## The controls, and why the rule cannot be "an imaginary mode appeared"

The same variants on three radicals that PASSED the benchmark:

| radical | smallest stability eigenvalue | largest analytic-numerical mode difference | enthalpy shift |
|---|---|---|---|
| CH3O (methoxy, methanol's O-H) | 0.0049 | **208 cm-1** | **+0.27 kcal/mol** |
| HOO (hydrogen peroxide's O-H) | 0.036 | 2.8 cm-1 | +0.01 |
| CH2SH (methanethiol's C-H) | 0.128 | 45.7 cm-1 | +0.03 |

Methoxy shows a **quiet analytic error**: one mode 208 cm-1 off and 0.27 kcal/mol in enthalpy, with no imaginary mode to flag it. A rule that computes numerical frequencies only when an imaginary mode survives the one re-run would miss it, and `calibrate.py` exists to find out how much it would miss.

## Cost

`NumFreq` is 6N gradients: about 2 times the analytic Freq on the 5-atom radical and 2.7 times on the 8-atom one (25 minutes at 4 cores for ethanethiyl), and it needs 6N gradients, so it grows at least linearly with the atom count on top of the cost of each gradient (only these two sizes were timed). It is a fallback for a flagged radical, not a default for every one.

## `calibrate.py`

Measures how the smallest stability eigenvalue relates to the analytic-numerical enthalpy shift, on the radicals the first run and the held-out arm ALREADY computed (their results are spent: nothing here is held out and nothing can change a verdict). Phase one runs the stability analysis on every accepted radical at its recorded final geometry; phase two runs analytic and numerical frequencies on a selection fixed in `select_for_numfreq` before the jobs run (all with eigenvalue below 0.05 Eh, all of at most 6 atoms, and 6 of the rest by a seeded draw), **capped at 9 atoms** because a numerical Hessian of a 14-atom radical is hours; radicals of 11 to 15 atoms (the propoxyls, tert-butoxyl, phenoxyl, benzoyloxyl) are therefore NOT measured, and whatever it says is about radicals of 9 atoms or fewer. The result is in `calibration/` and read in `benchmarks/restart_v3/PREREGISTRATION.md`.
