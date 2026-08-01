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
| D-003 | `c1ccc[c-]c1` | `cyclohexane` | `benzenide` | charged atom is aromatic; a ring carbanion needs indicated hydrogen and ring numbering, which belongs to the retained-ring path |
| D-004 | `[NH2+]=C(N)N` | `iminomethane-1,1-diamine` | `guanidinium` | classifier gate is all-carbon |
| D-013 | `[CH+]=O` | `oxomethane` | `oxomethylium` | classifier gate is all-carbon |
| D-018 | `[CH2+]c1ccncc1` | `4-methylpyridine` | `pyridin-4-ylmethan-1-ylium` | classifier gate is all-carbon |
| D-015 | `[n-]1cccc1` | `1H-pyrrol-2-ide` | `pyrrol-1-ide` | charge relocated from N to C |
| D-016 | `[N-]=[N+]=[N-]` | `diiminoazanium` | `azide` | wrong structure |
| D-019 | `[CH2-][N+]#N` | `(azanylidyne)(methyl)azanium` | `methanidyldiazonium` | protonates the carbanion half of the zwitterion and emits the CH3N2+ **cation** — an invented hydrogen and a charge that is not there |

The all-carbon cluster (D-004, D-013, D-018) has one cause:
`_classify_simple_carbon_charge` requires every atom to be carbon, which is
what keeps the heteroatom motifs (acylium, iminium, amidinium) with the
specific classifiers that know how to name them. Widening it means teaching
the renderer about heteroatom parents.

## Benchmark: the standing 4 of 124

`benchmarks/naming` scores 120/124. All four remaining rows are now
characterised, and **two of them are not engine errors at all**.

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
| `NC(=O)CC(=O)N` | `malonamide` | `propanediamide` | malonic is general-nomenclature-only (P-65.1.1.2.2 / P-66.6.3); the engine already emits `butanediamide` for the next homologue |
| `O=CCC=O` | `malonaldehyde` | `propanedial` | as above |
| `CC(C)C` | `isobutane` | `2-methylpropane` | retained, not a PIN |

The amide/aldehyde entries come from `retained_pins` in
`data/retained_names_expanded.json`, both tagged `"source": "algorithm.py",
"rule": "various"` — i.e. unvetted. `succinimide` in the same file is a
**genuine** PIN with a correct P-66.2 citation and must not be "corrected".

## Severity C

`_RETAINED_ACID_TO_ACYL` (`engine.py`) carries four unreachable non-PIN keys
(`malonic`/`succinic`/`glutaric`/`adipic acid`) that the acid path never
produces, the same dead-key pattern already removed from
`_RETAINED_DIACID_TO_DIACYLIUM`.

## Deliberately open decisions

**Should the neutralizer fall-through become a hard error?** When a
classification has claimed every formal charge and the renderer then declines,
the engine could refuse instead of silently naming the neutral skeleton. That
is the right end state — it converts any future gap from a wrong structure
into a visible failure — but it cannot be switched on blind, because it turns
an unknown number of currently green-but-wrong outputs into errors. The
decision is gated on the diagnostics statistics across a wider corpus than the
~70-probe sweep used so far.

## Not limitations

* The five tests that shipped red are not engine defects. They asserted a
  non-minimal lambda numbering and three general-nomenclature-only acylium
  names; the engine's output is correct in every case. See `CHANGELOG.md`.
