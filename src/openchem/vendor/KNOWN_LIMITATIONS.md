# Known limitations — `iupac_namer`

What this engine gets wrong, measured rather than guessed. Every entry was
reproduced, and every "should be" name was verified by parsing it back with
OPSIN and comparing the structure on canonical SMILES **and** full InChIKey.

Severity, used consistently here and in the regression suite:

| | meaning |
|---|---|
| **A** | wrong molecule — the name denotes something else |
| **B** | right molecule, non-preferred name |
| **C** | style / dead code |

The live list is `tests/test_namer_known_defects.py`. Open defects there are
`xfail(strict=True)`, so fixing one **fails** the suite and forces this
document and that table to be updated rather than silently drifting.

## The failure shape worth understanding first

`charge_perception.detect()` returns `None` when no classifier claims a
charged molecule, or when a classifier claims it but the renderer cannot
compose a name. `None` does **not** mean "no name": the engine falls through
to the generic plan search, which *neutralizes* the molecule and names the
neutral skeleton. So a missing rule surfaces as a confident wrong structure —
the benzyl cation as `methylbenzene`, which is toluene — with nothing in the
output to suggest a problem.

This is why these defects cannot be found by reading the code: the code that
produces the wrong answer is working exactly as written. Set
`OPENCHEM_NAMER_DEBUG=1`, or open a `diagnostics.capture()` scope, to record
every such fall-through attributed to the gate that let it go. See
`iupac_namer/diagnostics.py`.

Two of those fall-through reasons now raise instead of neutralizing — see
*The refusal guard* below for which, and why the third must not.

## Open defects (severity A — wrong molecule)

One remains.

| id | input | emits | should be |
|---|---|---|---|
| D-024 | `[CH2+]c1cc[n+]([O-])cc1` | `(pyridin-4-yl)methan-1-ylium 1-oxide` (unparsable) | `(1-oxidopyridin-1-ium-4-yl)methylium` |

**A ring N-oxide in substituent position.** Additive nomenclature is the
engine's only N-oxide renderer, and it works as a top-level wrapper: strip the
exocyclic `[O-]`, name what is left, append ` 1-oxide`. That is right for
`pyridine 1-oxide` and for `pyridine-4-carboxylic acid 1-oxide`, but when the
core carries a charge suffix it produces `…-ylium 1-oxide`, which is not a
valid name — the oxide has to go INLINE, as `1-oxido…-1-ium`.

The fix is a naming capability the engine does not have, not a missing table
entry, and two cheaper routes were tried and rejected:

* A curated ring entry keyed on the N-oxide ring (`[O-][n+]1ccccc1`) with a
  `substituent_form` is **dead data** — the additive path strips the oxide
  *before* ring lookup, so the ring reaching the table is plain pyridine.
* Composing the name by hand from parts the engine does give
  (`pyridinium-4-yl` plus a `1-oxido` prefix) means reimplementing substituent
  assembly for one molecular shape, which is the sort of narrow special case
  this engine has been having removed from it.

What it actually needs is for the additive-versus-substitutive choice to be
made with the output form in view, so a ring N-oxide destined for substituent
position takes the `1-oxido…-1-ium` form. The additive path currently lives
inside plan search and is not output-form aware.

### Observed, no verified target

`[C-]1C=CC=C1` names as `cyclopenta-2,4-dien-1-ide`, dropping the unpaired
electron. This is the cyclopentadienyl **radical anion** — a different species
from cyclopentadienide, with a different InChIKey. `cyclopentadienide` was
tried as the target name and rejected by the round-trip check: it denotes the
closed-shell anion. No name was found that OPSIN parses back to the radical
anion, so none is stated. Not in the defect table, which requires a verified
target.

## Benchmark: the standing 4 of 124

On the original 124-row corpus the engine scores 120/124. All four remaining
rows are now characterised, and **two of them are not engine errors at all**.

(The corpus has since grown to 165 rows; the current score is **163/165**.
Zero wrong structures, zero refusals, zero unparsable names: the only two
failures are the tautomers below, which are not errors. D-024 is not in the
corpus.)

### Tautomers — the engine is defensible

| row | corpus | engine names | verdict |
|---|---|---|---|
| 1,2,3-triazole | `c1cn[nH]n1` (2H) | `1H-1,2,3-triazole` | annular tautomer |
| metformin | `CN(C)C(=N)N=C(N)N` | `1,1-dimethylbiguanide` | proton tautomer |

Each pair shares a full InChIKey, so InChI — which normalises mobile
hydrogens — considers them the same substance. They are reported as
`gate_disagreement` rather than scored as passes, because InChI normalising a
difference away is not proof the difference does not matter. A human should
decide, which is exactly what that outcome class is for.

### Genuine wrong structures

**None remain.** Both rows that used to sit here are fixed: the novel
pyrazolone (D-022) and diazomethane (D-019). Every molecule in the corpus that
the engine names, it names with a name denoting the molecule it was given.

Diazomethane is worth one note. It is named `methanidyldiazonium`, and the
canonical SMILES gate still disagrees with the corpus entry — `[CH2-][N+]#N`
versus `C=[N+]=[N-]` — because those are two Lewis structures of one
substance, identical InChIKey `YXHKONLOYHBTNS-UHFFFAOYSA-N`. The InChIKey gate
sees they are the same and scores it a pass. That is the clearest argument for
keeping the second gate: resonance and tautomer depiction differences are
visible to one gate and invisible to the other, and the disagreement is the
signal.

## Severity B — right molecule, non-preferred name

| input | emits | preferred | rule |
|---|---|---|---|
| `ClC(=O)C(=O)Cl` | `ethane-1,2-dioyl chloride` | `oxalyl dichloride` | `oxalyl` IS the PIN acyl group (P-65.1.7.2.1); the `di` multiplier is also missing |
| `CC(C)C` | `isobutane` | `2-methylpropane` | retained, not a PIN |

The acyl-halide case is **not** a matter of adding a table entry. Instrumenting
`_acid_name_to_acyl` over 200+ molecules showed only two distinct acid names
ever reach it, and the acyl-halide name is not built through it at all — so
routing it through the retained lookup is a structural change to that path, not
a data fix. Deferred rather than attempted.

`malonamide` -> `propanediamide` and `malonaldehyde` -> `propanedial` were
fixed: both came from `retained_pins` in
`data/retained_names_expanded.json` tagged `"source": "algorithm.py", "rule":
"various"` — i.e. unvetted — and both contradicted the engine's own acid path,
which already emitted `butanediamide` and `butanedial` for the next homologue.

**`succinimide` in the same file is a genuine PIN** with a correct P-66.2
citation and must not be "corrected" to match.

### Unaudited data

74 of the 292 `retained_pins` entries carry `"source": "algorithm.py", "rule":
"various"`, meaning no rule was ever cited for them. Two turned out to be
wrong on inspection. The other 72 are unexamined — not known to be wrong, but
not known to be right either, and that is the honest description.

## Severity C

`_RETAINED_ACID_TO_ACYL` (`engine.py`) carries four unreachable non-PIN keys
(`malonic`/`succinic`/`glutaric`/`adipic acid`) that the acid path never
produces, the same dead-key pattern already removed from
`_RETAINED_DIACID_TO_DIACYLIUM`.

## The refusal guard (resolved 2026-08-01)

Two of the dispatcher's decline reasons now **raise** rather than falling
through to the neutralizer. The split was measured over the benchmark corpus
plus the 69-probe charged-species sweep — 193 molecules:

| reason | occurrences | behaviour | why |
|---|---|---|---|
| `render_failed` | 0 | **raises** | a classifier engaged and could not finish; the coverage gate has already proved every charge is claimed, so falling through can only name a different molecule |
| `partial_claim` | 1 | **raises** | as above; the one live case is D-019 |
| `unclaimed` | 35 | falls through | **not** a defect signal — pyridinium, sulfonium, betaine, nitrobenzene and phenylium all land here and are all named correctly by other paths |

Making `unclaimed` fatal would have broken dozens of correct names. Making the
other two fatal cost nothing on the day and converts any future gap from a
wrong molecule into a visible failure.

The visible effect: `name_smiles("[CH2-][N+]#N")` now raises instead of
returning `(azanylidyne)(methyl)azanium`. On the benchmark diazomethane moved
`wrong_structure -> no_prediction`; the score is unchanged at 120/124 because
both are failures, but one of them was lying.

## Not limitations

* The five tests that shipped red are not engine defects. They asserted a
  non-minimal lambda numbering and three general-nomenclature-only acylium
  names; the engine's output is correct in every case. See `CHANGELOG.md`.
