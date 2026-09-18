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

**None.** Every severity-A defect found by the sweeps, the benchmark, the
corpus extension and the held-out corpus has been fixed; the table in
`tests/test_namer_known_defects.py` holds 86 of them plus 50 non-regression
rows guarding the paths those fixes could have stolen from, over 26 distinct
defect numbers.

That is a statement about what has been *looked for*, not a claim that none
exists. The instrument that found most of them is still in the box: set
`OPENCHEM_NAMER_DEBUG=1`, or open a `diagnostics.capture()` scope, and sweep a
corpus. The `OPEN` list in the defect table is deliberately kept, empty, so a
newly found defect can be added as `xfail(strict=True)` — fixing it then FAILS
the suite and forces this document and that table to be updated together.

**AND THAT CAVEAT WAS EARNED, IMMEDIATELY.** A held-out corpus was added in
naming round 3 — 40 rows drawn by a fixed CID stride, admitted by a filter
settled in advance, with the engine never consulted during selection
(`benchmarks/naming/build_heldout.py`). Its FIRST run found a severity-A
defect, D-030:

```
CNC(C)CC12CC3CC(CC(C3)C1C1CCCCC1)C2
  emitted  1-(2-cyclohexyladamantan-5-yl)-N-methylpropan-2-amine
           -> HQMBUZVFGUDZCC-UHFFFAOYSA-N
  correct  1-(2-cyclohexyladamantan-1-yl)-N-methylpropan-2-amine
           -> RNYOSRZCHQLRMT-UHFFFAOYSA-N
```

In adamantane numbering locant 2 is adjacent to 1 and 3 but not to 5, so the
emitted name is a constitutional isomer rather than a non-preferred name. The
187-row regression corpus scores 187/187 both before and after the fix and
could not have caught it: it carries adamantane and norbornane as whole
molecules, never as substituents, and the defect needs a SECOND ring
substituent to appear at all. Bare adamantyl was always correct.

The rule is the one D-029 already fixed once — a substituent's free valence
takes the lowest locant consistent with the ring numbering (P-31.1.4.2.4) —
and D-030 is its third ring class. D-029 fixed monocyclic heterocycles by
FILTERING the candidate numberings; bridged rings kept an older branch that
only SORTED them so the wanted one landed last and won on "later-generated
wins a tie". Any competing ring prefix outscores a tie-break. The fix was to
delete that branch, so bridged rings take the same filter as everything else.

Correcting the locant then exposed a second latent defect, which is why this
is worth reading rather than just counting: the `-yl` suffix elided locant 1
on stems that cannot absorb it, giving `adamantan-yl`. Elision is only well
formed where the stem contracts (`cyclohexan` → `cyclohexyl`), and that was
decided by a DIFFERENT predicate from the one performing the elision, so the
two could disagree. They are now one decision
(`assembly.render_free_valence_suffix(stem_contracts=...)`). It had never
surfaced because D-030 meant a bridged substituent never reached locant 1.
Fixing it also corrected five organoelement names in the regression corpus
that were quietly malformed the same way (`(trimethylsilan-yl)benzene` →
`(trimethylsilan-1-yl)benzene`, and four like it) — still not the preferred
names, which are `trimethyl(phenyl)silane` and friends, but well formed.

The third and last ring class went the same way, as D-031, and it is worth
recording that the plan for it predicted the wrong cause. The prediction was
that a ring numbered from the curated table exposes a single canonical map,
so there would be nothing to choose between; measured, naphthalene offers
FOUR numberings placing the attachment at 2, 3, 7 or 6, and the correct one
is offered first. The branch filtered for "attachment at locant 1", found
none -- locant 1 is not reachable on a fused ring -- and fell back to
yielding every numbering, which is falling back to no rule at all. The
prefix band then chose, giving naproxen `2-methoxynaphthalen-6-yl` instead
of `6-methoxynaphthalen-2-yl`. The fallback now applies the same rule to
what is reachable, and both naproxen rows moved from `equivalent` to
`exact`.

Generalised across five ring systems with the locant verified per skeleton
rather than assumed constant: naphthalene and anthracene take 2,
phenanthrene 3, quinoline 2 because its nitrogen holds 1. A substituted
monocyclic phenyl still reaches locant 1 and is unchanged.

The last one to go, D-024, is worth keeping as a worked example because the
two obvious fixes were both wrong:

> A ring N-oxide in substituent position came out as
> `(pyridin-4-yl)methan-1-ylium 1-oxide`, which OPSIN cannot parse. Additive
> nomenclature produces a two-word name, and a substituent has to end in
> `-yl` for its parent to attach to it — there is nothing to attach to the end
> of the word "oxide".
>
> A curated ring entry keyed on the N-oxide ring is **dead data**: the
> additive path strips the exocyclic `[O-]` *before* ring lookup, so the ring
> reaching the table is plain pyridine. Composing the name by hand from parts
> the engine does give means reimplementing substituent assembly for one
> molecular shape.
>
> What actually worked was one condition: the additive path declines in
> SUBSTITUENT output form. The substitutive path already knew how to render
> it — `1-(oxido)pyridin-1-ium-4-yl` — it was simply never reached. Standalone
> output is untouched, so `pyridine 1-oxide` and
> `pyridine-4-carboxylate 1-oxide` keep the additive form correct for them.

### Observed, no verified target

`[C-]1C=CC=C1` names as `cyclopenta-2,4-dien-1-ide`, dropping the unpaired
electron. This is the cyclopentadienyl **radical anion** — a different species
from cyclopentadienide, with a different InChIKey. `cyclopentadienide` was
tried as the target name and rejected by the round-trip check: it denotes the
closed-shell anion. No name was found that OPSIN parses back to the radical
anion, so none is stated. Not in the defect table, which requires a verified
target.

## Benchmark: the standing 4 of 124

On the original 124-row corpus the engine scores 120/124. All four rows were
characterised; two were called "not engine errors at all", and that turned out
to be **true of one of them and wrong about the other** — see below.

(The corpus has since grown to 181 rows and now covers ring N-oxides,
substituted guanidiniums and tautomer pairs — the families the last few fixes
landed in, none of which the corpus could previously see. Current score
**181/181**: zero wrong structures, zero refusals, zero unparsable names, and
one `tautomer` (metformin, below) -- an outcome class added after this was
first written, which is why the number moved without the engine changing.)

### Tautomers — three different situations, not one

An earlier version of this document said the two standing tautomer failures
were "not engine errors at all". That was **wrong for one of them**, and the
mistake is worth recording: a matching InChIKey was read as proof the engine
was right, when all it proves is that InChI declines to distinguish mobile
hydrogens. Agreement from a gate that cannot see the difference is not
evidence.

Tested properly, the three cases separate:

**1,2,3-triazole — a real defect, fixed (D-026).** The ring table entry for
`c1cn[nH]n1` was labelled `1H-1,2,3-triazole`, which is the *other* tautomer
(OPSIN parses 1H- to `c1c[nH]nn1`), and the 1H form had no entry at all. So
both inputs came back as the 1H structure: the indicated hydrogen the caller
supplied was discarded. Same class as silently flattening stereochemistry.
The 1,2,4-triazole and tetrazole entries beside it already distinguished their
tautomers correctly, so this was an outlier rather than a policy.

The corroboration was sitting in the corpus the whole time: that row's PubChem
ground truth reads `2H-triazole`. An independent source had the tautomer right
while the engine, the ring table and a vendored test all agreed on the wrong
one — they agreed because the test was written from the table. Agreement
between things with a common ancestor is not corroboration.

**Purine — deliberate, and left alone.** All four tautomers are labelled
`9H-purine`, the IUPAC preferred parent, with `atom_locants` built so N9 gets
locant 9 whatever the canonical SMILES does. `data_loader.py` states the
reasoning, and the whole xanthine/caffeine family is numbered off it. Giving
`c1ncc2nc[nH]c2n1` the name `9H-purine` does lose which tautomer was supplied,
and that is a known consequence of a decision taken on purpose.

**Metformin — not a defect, and not fixable by naming.** The engine emits
`1,1-dimethylbiguanide`. `biguanide` is an IUPAC retained name for the
substance and carries no tautomer information at all — `1H-biguanide` and
`2H-biguanide` do not parse, unlike `1H-`/`2H-triazole`. OPSIN simply has to
pick a depiction when it emits SMILES. Both depictions share an InChIKey, and
both get the same correct name. This is precisely what `gate_disagreement`
exists to surface: same substance, different depiction, a human decides.

### Genuine wrong structures

**None remain.** Every row that used to sit here is fixed: the novel
pyrazolone (D-022), diazomethane (D-019), and the triazole above (D-026).
Every molecule in the corpus that the engine names, it names with a name
denoting the molecule it was given.

Diazomethane is worth one note in the other direction. It is named
`methanidyldiazonium`, and the canonical SMILES gate *disagrees* with the
corpus entry — `[CH2-][N+]#N` versus `C=[N+]=[N-]` — because those are two
Lewis structures of one substance, identical InChIKey
`YXHKONLOYHBTNS-UHFFFAOYSA-N`. Here the InChIKey gate is the one that sees
correctly and the SMILES gate is fooled; with the triazole it was the reverse.
Neither gate is the stronger one, which is the whole argument for running two:
where they disagree, something needs a human, and that is the only reliable
signal either of them gives about its own blind spot.

## Severity B — right molecule, non-preferred name

| input | emits | preferred | rule |
|---|---|---|---|
| `ClC(=O)C(=O)Cl` | `ethane-1,2-dioyl chloride` | `oxalyl dichloride` | `oxalyl` IS the PIN acyl group (P-65.1.7.2.1); the `di` multiplier is also missing |
The `isobutane` row that stood here is FIXED (D-036c). P-61.2.1 says in as
many words that "the names 'isobutane', 'isopentane' and 'neopentane' are
no longer recommended", and gives `2-methylpropane (PIN) (not isobutane)`.
It survived because `CC(C)C` is not in the benchmark corpus at all, so
nothing measured it -- the defect table now carries it.

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

## Substituent locants the tree cannot supply (open, 2026-09-17)

A ring system inside a SUBSTITUENT gets no locants on the depiction, so
fentanyl's piperidine and both its phenyls are unnumbered while its acetyl
chain is numbered. Three measured reasons, and they are separate:

* The nested prefix subtree DOES carry a numbering, and it is FRAGMENT-LOCAL.
  Measured on acetyl fentanyl: the piperidinyl subtree numbers its own atoms
  `{13: 1, 9: 2, 6: 3, 5: 4, 7: 5, 10: 6}`, and those indices belong to the
  carved fragment, not to the molecule.
* The tree exposes NO fragment-to-parent map. `named_parent.candidate`
  carries fragment-local atom indices too, and nothing on the node holds the
  carved mol, so the mapping would have to be re-derived by inference.
* The curated ring table cannot fill the gap either: 302 of its 371 entries
  carry an `atom_locants` map, and PIPERIDINE and BENZENE are not among them
  (pyrrolidine has no entry keyed by its ring SMILES at all). For benzene a
  skeleton numbering would be arbitrary anyway -- every position is
  equivalent until a substituent breaks the tie.

Not guessed at, deliberately: `structure_annotation._retained_ring_locants`
records what happened the last time locants were inferred from an assumed
atom order -- a full set of confident, WRONG numbers with nothing raised.
Fixing it properly means having the carve return its map, which is a change
inside the engine's extraction layer rather than in the annotation.

Indole is a smaller instance of the same shape: its table entry numbers 7 of
9 ring atoms, so 3a and 7a are missing from the depiction even though the
fusion positions are exactly what a reader looks for. That one IS a data gap
in `atom_locants` rather than an algorithm.

## An indicated hydrogen dropped from a substituent name (open, 2026-09-17)

`OC(=O)c1ccc(cc1)c1cc2ccccc2[nH]1` is named `4-(indol-2-yl)benzoic acid`,
where the PIN carries the indicated hydrogen: `4-(1H-indol-2-yl)benzoic acid`.
Severity B -- OPSIN resolves a bare `indol-2-yl` to the 1H form, so the name
round-trips and denotes the right molecule. The N-substituted case is already
correct (`4-(1-methyl-1H-indol-2-yl)benzoic acid`), which places the gap in
the unsubstituted-N path rather than in the indicated-hydrogen machinery.
Found while checking D-029; predates it.

## Not limitations

* The five tests that shipped red are not engine defects. They asserted a
  non-minimal lambda numbering and three general-nomenclature-only acylium
  names; the engine's output is correct in every case. See `CHANGELOG.md`.

## Open after naming round 3 (2026-09-17)

Each of these is adjudicated -- the target is known and quoted in
`benchmarks/naming/adjudication.toml` -- and not yet implemented. They are
listed by LAYER, because the round's main finding was that defects which
all look like "the comparator picked wrong" live in different places.

| layer | case | emits | preferred | note |
|---|---|---|---|---|
| candidate generation | chloroquine | `...quinolin-4-amine` | `...pentane-1,4-diamine` | no candidate carries two PCGs, so the diamine parent is never proposed (P-44.1.1) |
| PCG assignment | warfarin | `4-(4-hydroxycoumarin-3-yl)-...butan-2-one` | `4-hydroxy-3-(...)chromen-2-one` | the ring is offered with a `phenol` suffix, never its ring ketone |
| PCG assignment | caffeine | `1,3,7-trimethyl-2,6-dioxo-1H-purine` | `1,3,7-trimethylpurine-2,6-dione` | exposed by demoting the retained name (D-036): ring ketones become `oxo` prefixes |
| data | p-xylene | `1,4-dimethylbenzene` | `1,4-xylene` | P-22.1.3 names the xylene isomers PINs; the registry needs an entry ADDED |
| functional class | dimethyl sulfoxide, dimethyl sulfone, omeprazole | `dimethyl sulfoxide` | `(methanesulfinyl)methane` | P-63.6: the class names are not preferred, and neither is PubChem's alkylsulfinyl prefix |
| additive | trimethylamine N-oxide | `N,N-dimethylmethanamine oxide` | `N,N-dimethylmethanamine N-oxide` | the book's PIN carries the `N-` locant |
| serialization | hexamethyldisiloxane | `trimethyl(trimethylsiloxy)silane` | `...silyloxy...` | the O-bridge assembly drops the `yl` of a contracted stem |
| serialization | cid14000 | `4-{[(ethyl)][...]amino}butyl ...` | `4-{ethyl[...]amino}butyl ...` | a tertiary-amine prefix path wraps a simple prefix twice |

Architecture, deliberately deferred rather than half-done:

* **The preference cascade is still a float with hand-tuned bands.** None of
  the four flagship defects turned out to be a ranking error, so replacing it
  with a lexicographic key is hygiene rather than a fix -- still worth doing,
  and planned as its own change with an ordering-equivalence proof.
* ~~The strategy is not in the session cache key, and `IUPACCanonical()` is
  hard-constructed at 11 sites.~~ Closed in naming round 4 (A11): a
  top-level call binds its strategy, every helper reads `active_strategy()`,
  the cache key carries `cache_key()`, strategies refuse attribute
  assignment, and `tests/test_namer_strategy_propagation.py` guards all of
  it, including a source scan against a new construction site.
* **274 retained-name registry entries have no audited status.** They behave
  exactly as before; `tools/retained_name_audit.py` reports the backlog.
