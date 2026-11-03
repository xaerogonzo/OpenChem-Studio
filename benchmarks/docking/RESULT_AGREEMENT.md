# Does agreement among Vina's poses say whether pose 1 is right?

Measured 2026-11-02 with `pose_agreement.py` on the nine-pose redocking of the catalogued
receptors (the `poses.json` files of the PLECscore tests' `dock` stage: Vina, seed 20261029,
exhaustiveness 25, the survey's `app` arm). 46 receptors have a measured pose 1; 15 of them
returned fewer than nine poses.

The idea: a panel could cheaply say how many of the other poses sit where pose 1 sits. If a
pose shared by several runs of the search is more often the right one, that count would be a
usable confidence cue. k is the number of other poses within 2 A (heavy-atom assignment RMSD) of
pose 1; pose 1 is right when it is within 2 A of the crystal pose. One feature, named before the
data were read, no threshold fitted.

| k (others within 2 A of pose 1) | receptors | pose 1 right |
|---|---|---|
| 0 | 20 | 14 (70%) |
| 1 | 9 | 6 (67%) |
| 2 | 9 | 7 (78%) |
| 3 | 6 | 5 (83%) |
| 4 | 2 | 2 (100%) |

| Split | Agree | Without | One-sided Fisher p |
|---|---|---|---|
| k >= 1 | 20/26 | 14/20 | 0.42 |
| k >= 2 | 14/17 | 20/29 | 0.26 |
| k >= 3 | 7/8 | 27/38 | 0.32 |

**Reading: a trend in the hoped-for direction, not distinguishable from chance on 46
receptors.** Pose 1 is right for 70% of receptors where nothing else agrees with it and for
82% to 88% where two or more poses do, but the groups are small and the closest comparison is
p = 0.26. Nothing here supports telling a user "this pose is probably right because others
agree".

## Consequence

- No agreement indicator was added to the Docking panel. The sentence under the pose table
  (PR 508) already says what the evidence supports: pose 1 is the best-SCORING pose, not a
  verified one, and which poses score within the score's own error of it yet sit elsewhere.
- Unlike the other cues tried this month (the four plausibility checks, PLECscore), this one has
  the right sign. A larger redocking (more receptors, more seeds) could settle it; it is a
  measurement to repeat, not a feature to build on 46 receptors.

## Limits

- Redocking into the crystal box, as in the survey, which is optimistic.
- The nine poses of one search are not independent runs, and 15 receptors returned fewer than
  nine, which caps k for them.
- The assignment RMSD between poses is symmetry-blind in the same way as the one to the
  crystal pose (a lower bound).
