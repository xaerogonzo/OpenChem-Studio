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

Whether that fall-through should become a hard error instead is deliberately
still open — see *Deliberately open decisions* below.

## Open defects (severity A — wrong molecule)

| id | input | emits | should be | why |
|---|---|---|---|---|
| D-013 | `[CH+]=O` | `oxomethane` | `oxomethylium` | classifier gate is all-carbon |
| D-018 | `[CH2+]c1ccncc1` | `4-methylpyridine` | `pyridin-4-ylmethan-1-ylium` | classifier gate is all-carbon |
| D-015 | `[n-]1cccc1` | `1H-pyrrol-2-ide` | `pyrrol-1-ide` | charge relocated from N to C |
| D-016 | `[N-]=[N+]=[N-]` | `diiminoazanium` | `azide` | wrong structure |
| D-019 | `[CH2-][N+]#N` | `(azanylidyne)(methyl)azanium` | `methanidyldiazonium` | protonates the carbanion half of the zwitterion and emits the CH3N2+ **cation** — an invented hydrogen and a charge that is not there |
| D-020 | `CNC(N)=[NH2+]` | `N-(aminoiminomethyl)methanamine` | `methylguanidinium` | N-substituted guanidinium needs prefixes on the guanidine skeleton; the parent (D-004) is fixed |

The all-carbon cluster (D-013, D-018) has one cause:
`_classify_simple_carbon_charge` requires every atom to be carbon, which is
what keeps the heteroatom motifs (acylium, iminium, amidinium) with the
specific classifiers that know how to name them. Widening it means teaching
the renderer about heteroatom parents.

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

(The corpus has since grown to 165 rows; the current score is **160/165**.
The phenyl anion and guanidinium rows that the new charged-species categories
exposed are now fixed; azide (D-016) remains.)

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

| row | cause |
|---|---|
| diazomethane | D-019 above |
| novel pyrazolone | the emitted name omits the indicated hydrogen needed to pin the sp3 C4, so OPSIN resolves it to the aromatic tautomer. Unlike the two rows above, the InChIKey **skeleton blocks differ**, so this is a different species and not a normalisation artifact |

### A scoring artifact worth knowing

Fixing diazomethane will *not* move the score to 121, because canonical SMILES
is sensitive to which Lewis structure is written. `[CH2-][N+]#N` (corpus) and
`C=[N+]=[N-]` (what OPSIN emits for the name `diazomethane`) are the same
substance — identical InChIKey `YXHKONLOYHBTNS-UHFFFAOYSA-N` — but different
canonical SMILES. The correct name therefore scores as `gate_disagreement`.
This is the clearest argument for keeping the second gate: resonance and
tautomer depiction differences are visible to one gate and invisible to the
other, and the disagreement is the signal.

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
