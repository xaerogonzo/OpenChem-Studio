# Prep and box survey: is a bad default pose a setup defect?

Run 2026-10-29 on real AutoDock Vina 1.2.7, `prep_box_survey.py` at commit `56ef0655`,
every one of the 49 catalogued receptors, two preparation arms, one pinned seed
(20261029), exhaustiveness 25, nine poses each. The 98 rows are in
`artifacts_prep_box/results.jsonl`. The cutoffs (2.0 A for a correct pose, 3.0 A for
the right pocket) were fixed in `prep_box_core.py` before the run and are not tuned to it.

**The question.** Alex's concern was that Vina's default pose is doubtful. If that is mostly
a setup problem (no site, a wrong box, a ligand that was not built, a badly prepared
receptor), better preparation (Meeko and the like) would fix it. If it is mostly scoring,
it would not.

## Result (the Docking panel's own defaults, 47 receptors where the distance is measurable)

| | receptors | share |
|---|---|---|
| top-ranked pose within 2.0 A | 35 | 74% |
| a pose within 2.0 A exists among the nine, but is not top-ranked | 9 | 19% |
| right pocket, no pose within 2.0 A | 2 | 4% |
| wrong pocket (A2A, 3EML) | 1 | 2% |

Best-of-nine success is 44 of 47 (94%) against 35 of 47 (74%) for the top pose. Two further
receptors are not in the table: 6LQA's ligand would not embed, and 5TGZ's crystal ligand is
incomplete in the structure so no distance can be measured.

## What it says

1. **Setup is not where the misses are.** Box derivation produced a box for all 49, no
   docking run failed, and no receptor landed in the wrong place except the one the earlier
   `redock.py` already reported (3EML, a long ligand that can flip end for end). Of the 12
   misses, 9 had the right pose among the nine and ranked it lower. That is the scoring
   function ordering poses, not preparation.
2. **Keeping or stripping cofactors does not matter here.** The two arms agreed on the
   class of 46 of 49 receptors; the other three moved between neighbouring classes by
   0.0 to 0.77 A on the top pose (median 0.00). With one seed per arm that is the size of
   the search noise, so no cofactor effect is claimed.
3. **The four physical checks do not tell wrong poses from right ones.** Of 25 top poses
   that were not within 2 A, none was flagged. Across all poses, 6 of 527 incorrect ones
   and 2 of 180 correct ones were flagged, all by `receptor_clash`. Vina rarely produces
   impossible poses; it produces wrong ones that are physically fine. The checks stay
   worth having (they caught a real +49 kcal/mol pose when a survey bug docked a ligand
   onto its own crystal copy), but they must not be read as a quality signal, and the
   panel's sentence already says so.

## What would and would not follow

- Meeko or other receptor/ligand preparation is **not** supported as a fix for default
  poses: nothing in the setup layer failed.
- The lever the data points at is **pose ranking**. gnina's CNN rescoring is the only
  candidate with a published docking-power gain, so its feasibility on Windows (binary,
  licence, weights terms) is the next question. Its benefit would need its own
  preregistered test on these same 49 receptors, where the target is the 9 receptors whose
  correct pose Vina already finds but does not rank first.
- Showing more than the top pose is a product option that needs no new engine: for 9 of 47
  receptors the correct pose was already in the list.

## Limits, stated

- **The box is drawn around the crystal ligand.** This measures a well-aimed search, not
  pocket finding. A user who boxes by guesswork will do worse; the survey says nothing
  about that case. 42 of 49 boxes also hit the size floor, so they are larger than the
  ligand implies.
- **The distance is a lower bound** (assignment RMSD by element, no bonds). A ligand
  flipped end for end can score low, so "correct" means at least this close. Receptors
  with a ligand of 13 atoms or fewer (7E2Y, 3HS4) sit near the cutoff and are the least
  reliable.
- **One seed per arm, one ligand conformer.** The per-receptor class is one draw. The two
  arms act as a partial replicate (identical except cofactors) and mostly agree, but no
  noise floor was measured. 4IAR, 4DKL and 3HS4 are within a few tenths of the cutoff.
- **Redocking is optimistic.** The ligand is the one the receptor was crystallised with,
  so its pocket is already shaped for it. It does not show how well a different ligand is
  posed.
