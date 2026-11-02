# Result 2: PLECscore on properly built inputs

Run 2026-11-02 under `PREREGISTRATION_PLEC2.md` (with its Amendment 1). Same nine Vina poses per
receptor as `RESULT_PLEC.md`; ODDT 0.7, PLECscore `linear` P5 L1 (PDBbind v2016), its pre-3.8 tuple
hash restored, ligands rebuilt on their chemical-component template with every hydrogen,
receptors written out as Open Babel prepared them (hydrogens at pH 7.4). Per-receptor numbers are
`artifacts_plec2/per_receptor.csv`, the counts `artifacts_plec2/results_2.json`.

**Verdict by the preregistered rule: HARMFUL.** Both new gates passed, so this is a real
measurement of PLECscore, and the answer is that it ranks the poses worse than Vina does.

| Population | Rescored | Vina top pose correct | After PLECscore | Gained | Lost |
|---|---|---|---|---|---|
| Deciding (not in the training set) | 34 of 39 | 23 | 14 | 1 | 10 |
| Reported apart (in the training set) | 8 of 8 | 7 | 5 | 0 | 2 |

One-sided sign test for the harmful direction, 10 lost of 11 changed: p = 0.006.

## The gates

- **Fidelity** (median share of the stored training fingerprint reproduced, eight training-set
  receptors): **59%**, gate 50%. Per receptor: 3EML 84%, 3HS4 68%, 1HSG 66%, 4N6H 62%, 4EA3 56%,
  4DJH 51%, 4M48 42%, 5C1M 39%. Before the hash was restored the share was 0%.
- **Input sanity** (median best predicted pKd over deciding receptors): ok, against 4.0 in the
  first test, where it failed. The crystal-ligand control, a model-side check not used as a gate,
  has a median predicted pKd of **6.3** over 42 receptors (1HSG: 7.55 against a measured 9.42).

## What it means

- **PLECscore does not help here, and the direction is the harmful one.** Of the 11 deciding
  receptors whose top call changed, 10 went from right to wrong. Receptors the survey said Vina
  had right, PLECscore tended to move off the right pose; the one gain was 6BQG.
- **The receptors that could not be scored cannot rescue PLECscore.** Five deciding receptors
  (4PE5, 6DG8, 6JP5, 6X3T, 7B6W) fell out, four with `OverflowError: Python integer 32768 out of
  bounds for int16` inside ODDT on NumPy 2.2 (large receptors) and 7B6W because its ligand would
  not map onto its template (5TGZ has no measured Vina distance and is outside the tally). The
  rule allows up to five. All five have a correct Vina top pose (0.6 to 1.5 A), so rescoring them
  could only add losses or leave them unchanged, never a gain.
- Nothing here supports using PLECscore to choose between poses.

## Consequence

- PLECscore as shipped is closed as a pose-ordering candidate, now on a measured footing rather
  than on broken inputs.
- Separately, **ODDT 0.7's PLECscore returns noise on Python 3.8 and later unless its hash is
  restored**, because its bit positions were made with the pre-3.8 tuple hash and `hash32` calls
  Python's own. That is a real defect for anyone using it, not only this project. It is not
  reported upstream by this work.
- Option 3 (another native Windows docking executable) is the remaining scoring-function route.
  The product-side answer stays the pose-choice sentence of PR 508.

## Limits (beyond those in the preregistration)

- Ligands were scored as the neutral template, not in the state Vina saw.
- Fidelity is 39% to 84% per receptor, not 100%: the training receptors were PDBbind's own
  prepared files (their hydrogens and tautomers), so these inputs are close to the model's, not
  equal to them.
- The unscored receptors are large ones (an ODDT/NumPy int16 overflow) and one ligand that would
  not map onto its template, so the scored set is not a random sample of the catalogue.
