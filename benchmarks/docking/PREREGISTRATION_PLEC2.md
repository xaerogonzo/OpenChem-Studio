# Preregistration 2: PLECscore on poses built the way the model was trained

Written 2026-11-02, before any deciding receptor was rescored with the inputs described here.
The rules are `plec_core.py` (the first test's, plus the fidelity gate below); `tests/test_plec2.py`
holds the gate's boundaries, the restored hash and the template rebuild. Nothing here may change
after the first deciding receptor is rescored. A change is a dated Amendment at the end.

## Why a second test

`RESULT_PLEC.md`: the first run was INCONCLUSIVE because its inputs were implausible (median
best predicted pKd under 4.0, 1 receptor gained and 18 lost). Chasing that found that the first
test never measured PLECscore at all. Three defects, each checked by running, not assumed:

1. **ODDT 0.7's fingerprint hash is not stable across Python versions.** `hash32` is
   `hash(tuple) & 0xffffffff`, documented as platform independent. CPython changed the tuple
   hash in 3.8; the model's 65,536 coefficients are indexed by bits made under the old one. On
   Python 3.11 the same atoms fall in other bits and the linear model reads noise. Measured: the
   stored training fingerprint of a training complex (1HSG, 1,356 bits, unfolded) shares **0**
   bits with the one ODDT computes from the same complex on this Python, though the number of
   contacts agrees to the bit. The pre-3.8 function, reimplemented and checked against the value
   CPython 3.7 gives for `(1, 2, 3)`, brings the share to 66%.
2. **The poses were not the molecules the model knows.** Vina's PDBQT keeps no bond orders, no
   formal charges and no non-polar hydrogens, and ODDT's atom description reads the hydrogen
   count, the charge and the aromatic flag of every atom. The first test fed it those poses.
3. **The receptor was rebuilt from a PDBQT too**, which loses the same things on the protein side.

So the first test's 18-lost figure is the answer to a different question and says nothing about
PLECscore. This test asks the original question again.

## What changes, and what does not

The poses are the same ones the first test ranked (its `dock` stage; Vina, seed 20261029,
exhaustiveness 25, nine poses, box from the crystal ligand, `app` arm), so Vina's order and the
2.0 A / assignment-RMSD scoring are identical and the two tests are paired on identical poses.

Changed, all in `run_plec_test_2.py` / `plec_rescore_runner_2.py`:

- **Hash:** the CPython 3.7 tuple hash is installed over ODDT's `hash32` inside the sidecar.
- **Ligand poses:** heavy-atom coordinates from Vina; bond orders, formal charges and every
  hydrogen from the RCSB chemical-component SMILES of the ligand (`AssignBondOrdersFromTemplate`,
  then `AddHs`). This is the neutral form, which is also what most of the model's training
  ligands were. It is NOT the protonation state Vina docked (the PDBQT carried pH 7.4 protons);
  that choice is made once here, for all receptors, and is a limit stated below. A pose that
  will not map onto its template makes its receptor "not rescored".
- **Receptor:** the molecule Open Babel prepared (waters and the box-defining residue stripped,
  hydrogens at pH 7.4), written as a PDB before it becomes a PDBQT, read by ODDT's RDKit toolkit
  with the property check relaxed (as in Amendment 1 of the first test).
- **Crystal control:** the crystal ligand, built the same way from its own coordinates, scored
  against the same receptor. Reported, not a gate.

Not changed: the model (`linear`, P5 L1, PDBbind v2016, loaded, never retrained or refitted),
the deciding and training-set populations (`TRAINED_ON`, 8 receptors apart), the cutoff,
gained/lost, the sign test, PASS needing net +3 and p <= 0.05, the HARMFUL mirror, the
INCONCLUSIVE rule for more than 5 unscored, and the input-sanity rule (median over deciding
receptors of the highest predicted pKd >= 4.0).

## What was looked at before this was frozen

- 4IAR (deciding): scored only under the FIRST test's inputs (0 to 2.5 for the poses, and 3.06 for
  its crystal ligand rebuilt without its hydrogens, a half-fixed pipeline). It has not been
  scored under the inputs described here.
- 1HSG (a training-set receptor, reported apart): its crystal ligand and nine poses were scored
  under the fixed inputs to see whether the pipeline now produces plausible numbers: crystal
  7.55 against a measured 9.42, poses 5.6 to 7.6, the fingerprint share 66%. The pose that is
  within 2 A (1.2 A) was predicted 7.32 against a best of 7.60 for a pose 3.5 A away. One
  receptor, one observation; no rule was tuned to it except the gate threshold below.
- No other receptor has been rescored under these inputs.

## New gate: fidelity

For each training-set receptor (these are the only ones whose model inputs are stored), the
share of the stored training fingerprint (unfolded sparse bits, counted with multiplicity)
that this pipeline reproduces from the crystal ligand and the prepared receptor. **The median
over the measured training-set receptors must be at least 0.5, with at least 4 of the 8
measured**, else the verdict is INCONCLUSIVE whatever the counts are. The threshold was fixed
after seeing 66% for 1HSG and before any other receptor; 0.5 is "most of what the model learned
from is also what it is shown". A pass does not mean the inputs equal the model's (the training
receptors were PDBbind's own prepared files, with their own hydrogens and tautomers); it means
they are close enough that a prediction is a prediction.

## Verdict

As the first test, in this order: INCONCLUSIVE (more than 5 deciding receptors not rescored, the
input sanity fails, or the fidelity gate fails), PASS, HARMFUL, NULL. Reported beside it, never
counted: the eight training-set receptors, the crystal-control median, the receptors whose top
call changed, and any mismatch with the survey's recorded class.

## Expectation and what each outcome means

The expectation is still a null: PLECscore was built to predict affinity, and one ligand's
poses differ in contacts, not in what the ligand is. A PASS would justify a larger test, not
shipping: ODDT 0.7 does not install on a plain `pip install` (undeclared `six`, NumPy below
2.3), needs its hash restored to give meaningful numbers on a current Python, and lives in its
own environment. A NULL or HARMFUL result closes this candidate for good, now on a measured
footing, and leaves the pose-choice sentence of PR 508 as the product answer.

## Limits stated now

- **Protonation:** the neutral template, not the state Vina saw. Ligands with groups ionised at
  pH 7.4 (the amines and acids of many catalogued ligands) are scored as neutral, as most
  training ligands were; a charged variant is not tested.
- **Same-protein leakage** beyond the eight stored receptors remains (PDBbind holds other
  ligands for many of the 39), as before.
- One seed, one ligand conformer, redocking into the crystal box, as before; the re-ranking
  itself is deterministic.
- **Fidelity is measured only on the eight training-set receptors**, whose crystal ligands are
  also the ones the model memorised.

## Amendments

(none)

**Amendment 1 (2026-11-02, input handling only; no deciding receptor had been rescored).** The
first full `inputs` pass built the ligands for only about half of the receptors: `on_template`
reset every atom's explicit hydrogen count, which removes the hydrogen of an aromatic `[nH]`
and makes the ring impossible to kekulize (and left some poses unmappable). The reset is
removed; the radical and implicit-hydrogen clearing stays. A pyrrole case is added to
`tests/test_plec2.py`. Every receptor's inputs are rebuilt from scratch with the corrected
function, so none carries the earlier build. No rule, gate, cutoff or population changes.

**Amendment 1, continued (same day, still before any deciding receptor was rescored).** Removing
the reset let the pose's own leftovers through (the extra proton Vina put on an amine, a
radical flag from the unchecked read), so no pose mapped onto its template. The rule is now the
one this test meant from the start: the template decides the protonation, so the pose's explicit
hydrogen counts, formal charges and radical flags are cleared before the match (`heavy_pose`), and
the `[nH]` of an aromatic ring comes from the template. The tests now start from a pose that
disagrees with its template in exactly those ways. Inputs are rebuilt from scratch again.

**Amendment 1, last part (same day, still before any deciding receptor was rescored).** With
those two fixes 38 receptors built and 10 did not: the ligand of an aromatic `[nH]` could not be
kekulized because `AssignBondOrdersFromTemplate` did not carry the template's explicit hydrogen
onto the result in the RDKit used here. `on_template` now matches the template back onto the
result and copies each atom's formal charge and explicit hydrogen count from it. Inputs for all
receptors are rebuilt once more with the final function.
