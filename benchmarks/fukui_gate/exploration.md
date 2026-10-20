# The Fukui exploration: what was run before the gate, and what it showed

**This is exploration, not the gate.** It was run on 2026-10-18, before the preregistration (`PREREGISTRATION.md`) was written, to choose
the charge scheme and to see what the calculation does at an ordinary basis set. Its molecules (formaldehyde, propene, pyridine) are
**not** in the gate's decided set; formaldehyde is in the gate's reported arm and in its published reference values, and is disclosed
there as a case whose ORCA numbers were seen first.

## What was run

ORCA 6.1.1, B3LYP, three molecules, each at two basis sets: def2-SVP and def2-SVPD. For each: an RDKit embedding (seed 7), one ORCA
`B3LYP def2-SVP Opt`, then three single points at that geometry (neutral, cation as a doublet, anion as a doublet), each with
`! B3LYP <basis> MBIS CHELPG` and `Print[P_Hirshfeld] 1`. The atomic charges of five schemes were read from each output (Mulliken, Loewdin,
Hirshfeld, MBIS, CHELPG) and differenced as `f+ = q(N) - q(N+1)`, `f- = q(N-1) - q(N)`. The same geometry was used at both bases.

## What it showed

The largest change in any atom's value when only the basis changes from def2-SVP to def2-SVPD:

| scheme | f+ moved (formaldehyde, propene, pyridine) | f- moved | negative values |
|---|---|---|---|
| Hirshfeld | 0.014, 0.023, 0.011 | 0.009, 0.004, 0.003 | none in any of the six runs |
| Loewdin | 0.107, 0.103, 0.067 | 0.104, 0.097, 0.055 | none |
| Mulliken | 0.106, 0.222, 0.138 | 0.030, 0.079, 0.073 | one f- (propene) |
| MBIS | 0.185, 0.210, 0.051 | 0.032, 0.032, 0.023 | f- negative in all three, f+ in one (propene) |
| CHELPG | 0.042, 0.279, 0.172 | 0.045, 0.056, 0.077 | f- negative in all three, f+ in two |

Formaldehyde, Hirshfeld, B3LYP/def2-SVP (the application's default level): carbon f+ 0.395, f- 0.228; oxygen 0.296, 0.426; each
hydrogen 0.154, 0.173. At def2-SVPD: carbon 0.381, 0.226; oxygen 0.289, 0.435; hydrogen 0.165, 0.169. Mulliken at def2-SVP put 0.229 on each
hydrogen and 0.260 on the oxygen against 0.283 on the carbon; its carbon charge went from +0.167 to +0.581 on adding diffuse functions.

The electron affinity from the three energies was negative in all six cases: formaldehyde -2.02 and -1.20 eV, propene -3.02 and -2.46,
pyridine -1.48 and -1.06 (def2-SVP, then def2-SVPD). Every one of the six sets of three states converged and every run satisfied the sum
rule (each of f+ and f- summed to 1.000).

## Disclosures

* **One run died and was repeated unchanged.** Propene at def2-SVPD: the anion's job ended on `Error MatrixLife: cannot recover matrix
  (...VXC0.tmp)` and ORCA then reported the wavefunction as not fully converged, though its SCF had been settling normally (energy change
  4e-6 Eh at iteration 6). A rerun of the same input passed. A scratch-file fault, not a chemistry result.
* **A rerun in a used working directory gave a different energy, and I first took it for the calculation.** Formaldehyde at def2-SVP had
  E(N) = -114.356440 Eh in the first run and -114.356274 Eh in a second run of the same input in the same directory; three runs of the
  input in fresh directories all gave -114.356440003665 Eh. The second run had reused a directory holding the first run's files. The
  application runs every job in a fresh scratch directory, so this is not what it does. The numbers above are from a clean rerun of that case
  (they differ from the used-directory ones by at most 0.001 in any scheme).
* **Formaldehyde's ORCA Hirshfeld numbers above were seen BEFORE the published tables were read**, so they were not tuned to them. They
  agree with Thanikaivelan et al.'s Hirshfeld table (BLYP/dnd, DMol3) to within 0.008. That agreement is the reported arm's, and is not a
  blind result.
* The test fixture `tests/fixtures/orca/water_fukui.out` is verbatim extracts of a real HF/STO-3G run on water, and a three-species plumbing check of the gate's machinery was run at HF/STO-3G, which is not a gate level; for it only the molecule's charge,
  atom order, method, ORCA version, geometry flag and the sum rule were looked at, no f value.
* No ORCA job at 6-31G** or 6-311+G** of any gate species has been run before the preregistration.
