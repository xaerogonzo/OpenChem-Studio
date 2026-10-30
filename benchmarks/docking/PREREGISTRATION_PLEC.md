# Preregistration: does PLECscore put the correct pose on top more often than Vina?

Written 2026-10-30, before any receptor was rescored. The rules below are `plec_core.py`; a
test (`tests/test_plec_core.py`) holds their boundaries. Nothing here may change after the first
rescored number is seen. A change is an Amendment at the end, dated, with its reason.

## Why this test

`PREP_BOX_RESULT.md` found that Vina's default pose is the right one for 35 of 47 catalogued
receptors (74%), and that for 9 more a pose within 2 A of the crystal pose is among the nine but
not ranked first. Setup was not the problem; the ordering is. This asks whether a different
scoring function, run on the SAME nine poses, orders them better.

**The candidate is ODDT's PLECscore** (`linear` model, depths P5 L1, trained on PDBbind v2016,
ODDT 0.7, BSD-3-Clause), because it ships a trained model (1.4 MB JSON) and needs no GPU. It
predicts a binding affinity (pKd) from the protein-ligand fingerprint. It was built for scoring
and ranking power, not docking power, and nobody has shown that ordering one ligand's poses by
it tracks pose accuracy. **The expected result is a null.** The test is cheap, and a null is a
result.

## What is run

1. `dock`: the prep-and-box survey's "app" arm, repeated exactly (every catalogued receptor,
   box from the crystal ligand, waters stripped, cofactors kept, the box-defining residue
   stripped, pH 7.4, exhaustiveness 25, seed 20261029, nine poses). It also SAVES each pose and
   the prepared receptor, which the survey did not.
2. `rescore`: ODDT's shipped PLECscore predicts a pKd for each of the nine poses, in the ODDT
   environment's own Python (a sidecar; it imports nothing from openchem). No model is retrained
   or refitted.
3. `report`: poses are re-ordered by predicted pKd, highest first, ties kept in Vina's order.

The baseline for each receptor is THIS run's Vina order, not the survey's, so the comparison is
paired on identical poses. The survey's recorded class is compared and any receptor where the
top-1 call differs is printed, not hidden.

**Three shims, recorded because each is a place the released ODDT 0.7 (2019) meets a modern
library, and a user's install would meet the same three:** `six` must be present at build time
(`--no-build-isolation`); NumPy must be below 2.3 (`np.in1d` is gone); and the runner converts
a lazy `map` to a list before SciPy's `vstack`. Poses are read with RDKit's valence check
relaxed, because Vina's charge-free PDBQT writes a protonated amine as a four-bond nitrogen.
None changes a number; each was found by running the first receptor.

## Populations

- **Deciding:** receptors with a measurable distance (47 in the survey) that are NOT entries of
  PLECscore's training set. Eight are (`plec_core.TRAINED_ON`: 1HSG, 3EML, 3HS4, 4DJH, 4EA3,
  4M48, 4N6H, 5C1M, found by reading the training ids in ODDT's `plecscore_descs_p5_l1.csv.gz`,
  13,232 complexes, 2026-10-30). That leaves 39. None of the nine receptors where the correct pose
  was ranked lower is among the eight.
- **Reported apart, never counted toward the verdict:** the eight training-set receptors. The
  model has seen their crystal complexes and affinities.

Residual leakage that this does NOT remove: PDBbind very likely holds other ligands bound to the
same proteins as some of the 39, which could help the model. Stated as a limit, not corrected.

## Rules

- A pose is correct when its assignment RMSD to the crystal ligand is at most **2.0 A** (the
  survey's cutoff). The RMSD is a lower bound (element-matched, no bonds).
- Per deciding receptor: **gained** = top pose wrong in Vina's order, correct after re-ranking;
  **lost** = correct before, wrong after.
- Verdict over the deciding receptors, in this order:
  - **INCONCLUSIVE** if more than 5 deciding receptors could not be rescored, or if the inputs
    are implausible: the median over deciding receptors of the highest predicted pKd among a
    receptor's nine poses is below 4.0. Fixed after the one-receptor smoke test (4IAR) gave
    predictions of about 0 to 2.5 for a drug-like ligand and BEFORE any other receptor was run:
    the model is being shown input unlike its training data (poses through a charge-free PDBQT,
    a receptor rebuilt from one), and an ordering of such numbers is not a finding.
  - **PASS** if gained minus lost is at least 3 AND the one-sided exact sign test on the gained
    and lost receptors is at most 0.05 (5 gained against 0 lost is the smallest PASS).
  - **HARMFUL** by the mirror rule: lost minus gained at least 3 and the same test.
  - **NULL** otherwise.
- Not counted toward the verdict, reported beside it: the eight training-set receptors, the
  rank of the best pose before and after, and which receptors changed.

## What each outcome would mean

- **PASS** would justify a second, larger and wider test (more receptors, more ligands, different
  seeds) before any product use. It would not justify shipping, and the install problem below
  would still have to be solved.
- **NULL or HARMFUL** closes this candidate. Option 3 (another Windows executable) is then the
  only remaining scoring-function route, and the product-side answer stays the pose-choice
  sentence of PR 508.

## Limits stated now

- **The test can gain at most the clean ranked-lower receptors** (at most 18% of 39).
- **One seed and one ligand conformer**, as in the survey; no noise floor was measured. The
  re-ranking itself is deterministic given the poses.
- **Redocking is optimistic**, box around the crystal ligand, ligand from the crystal's own
  chemical definition.
- **Install burden:** ODDT 0.7 does not install with a plain `pip install` (it uses `six`
  without declaring it), and it lives in its own environment. A pass would not make it
  shippable as it stands.

## Amendments

**Amendment 1 (2026-10-30, input handling only; no outcome had been looked at).** The first
full rescoring pass failed to load 43 of the 49 prepared receptors: ODDT's RDKit reader refuses
a PDB whose proximity bonding gives some carbons five bonds (the receptor is rebuilt from Open
Babel's PDBQT). The protein is now read with the same relaxation as the ligand (RDKit's property
check skipped, everything else kept), and a receptor whose docking never ran (6LQA) is skipped
by the runner instead of ending it. The four receptors that did score under the old read (1HSG,
4IAR, 5HK1, 5HK2) were not examined and are rescored. No rule, cutoff or population changes.
