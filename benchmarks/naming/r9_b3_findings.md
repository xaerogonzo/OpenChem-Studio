# B3: the frequency census's counts

Source: `benchmarks/naming/census_sample.json` (2000 unenriched PubChem-stride structures), counted via
`tools/naming_census_count.py` against `census_queries.toml`. Threshold `natural_frequency_min = 0.005`
(10/2000) was committed in R0, before this census or its counts existed.

## Results

| query | hits | frequency | clears threshold? |
|---|---:|---:|---|
| `any_formal_charge` | 292/2000 | 14.60% | **yes** |
| `diaryl_or_dialkyl_enclosed_ketone` | 168/2000 | 8.40% | **yes** |
| `charged_acid_substituent` | 142/2000 | 7.10% | **yes** |
| `substituted_carbamimidoyl` | 81/2000 | 4.05% | **yes** |
| `naphthalene_2_3_disubstituted` | 7/2000 | 0.35% | no (below by 3 hits) |
| `guanidinium_cation` | 3/2000 | 0.15% | no |
| `carbazate_ester` | 0/2000 | 0.00% | no |
| `chloroformate_or_carbonate_anhydride` | 0/2000 | 0.00% | no |
| `isocyanide_or_nitrilium_carbanion` | 0/2000 | 0.00% | no |
| `carbodiimide` | 0/2000 | 0.00% | no |
| `tetrahydroborate_or_aluminate_anion` | 0/2000 | 0.00% | no |
| `large_fused_polycyclic_aromatic` | 0/2000 | 0.00% | no |

## Reading the zeroes: NATURAL_FREQUENCY is not the only route to a slot

Three of B in this round's most notable structural findings measure at **exactly 0/2000** here:

- **`carbodiimide`** (0%): DCC's own functional group -- the round's clearest wrong-molecule finding (B2)
  -- essentially never appears in an unenriched PubChem stride sample. This makes sense on reflection:
  carbodiimides are REAGENTS used to make other things, not the kind of structure PubChem's general
  compound space is dominated by. Its admission, if it happens, has to rest entirely on being a diagnosed
  wrong molecule (`diagnosed_against_fixture = true`), never on frequency -- exactly what the admissions
  rule already says: "a wrong molecule outranks frequency for a slot. It does not escape the cap."
- **`tetrahydroborate_or_aluminate_anion`** (0%): BH4-/AlH4-, for which B2 found no naming plan at all.
  Also absent from ordinary PubChem structures. This one is a genuine judgment call for the freeze: it is
  not a WRONG structure (no name was produced at all, so there is nothing to diagnose as wrong against a
  fixture) and it does not clear frequency either. Whether "no naming plan exists" counts as admissible
  under the letter of the rule is Alex's call, not mine to decide by writing code around it.
- **`large_fused_polycyclic_aromatic`** (0%): the coronene-class shape that both hung the engine (fixed
  defensively, no slot consumed) and made the von Baeyer fallback drop ring unsaturation (B1 bucket B).
  Confirms this is genuinely rare, consistent with treating it as excluded ("fusion") rather than as a
  frequency-qualified candidate.

**`naphthalene_2_3_disubstituted`** sits at 7/2000 (0.35%), 3 hits short of the 10-hit threshold. B1's
`bb-3e0b412fafed` finding (an entire fused ring dropped) is a diagnosed wrong molecule, so it does not need
this frequency reading to qualify -- but it is worth recording precisely rather than rounding to "rare",
since 7 is a real, measured count, not noise at this sample size.

## What clears comfortably

`any_formal_charge` at 14.6% is the headline number for B1's dominant finding: charged species are not an
edge case in ordinary chemistry, so a charge-perception gap (wherever its root cause turns out to be) has
wide reach by construction. `diaryl_or_dialkyl_enclosed_ketone` (F5), `charged_acid_substituent` (F1) and
`substituted_carbamimidoyl` (F7 / B1 buckets C and F) all clear too, giving three of the plan's original
seed items a measured frequency floor rather than an assumed one.

## REGRESSION_COVERAGE is a separate, uncombined measurement

Per the plan, NATURAL_FREQUENCY (above) is never combined with REGRESSION_COVERAGE (how often a shape
appears in the tuning populations, i.e. whether it matters to the existing scored workload). That second
number is read from the tuning populations directly when the admissions ledger is assembled, not from this
census.

## Next: assembling the admissions ledger

This closes the B stage's three instruments (B1, B2, B3). Per the plan, the ledger is filled in ONE step
from the seed list plus every B-stage finding, admitting at most 8 items, wrong molecules first, frequency
second, and the set does not move after that commit. That step has deliberately not been taken yet --
it is a real decision, not a mechanical one, especially for the two zero-frequency cases above.
