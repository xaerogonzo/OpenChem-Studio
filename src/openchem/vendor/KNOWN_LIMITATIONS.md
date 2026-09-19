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
`tests/test_namer_known_defects.py` holds 491 rows over 77 distinct defect
numbers (measured 2026-09-18, after naming round 4): each defect's own rows,
and the converse and non-regression rows guarding the paths its fix could
have stolen from.

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

No open row. The `oxalyl dichloride` row that stood here was FIXED in round 4
(D-065f); re-measured 2026-09-19 (naming round 5, N1), the engine emits
`oxalyl dichloride`, and the homologues `propanedioyl`/`butanedioyl`/
`hexanedioyl dichloride`.

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

None open. The four unreachable non-PIN keys (`malonic`/`succinic`/
`glutaric`/`adipic acid`) are gone from `_RETAINED_ACID_TO_ACYL`, with a
comment where they stood; this entry outlived the fix and was corrected on
re-measurement in naming round 5 (N1, 2026-09-19).

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

## Substituent locants the tree cannot supply (CLOSED in round 4, A12)

The carve now stamps each fragment atom with the index it was carved from
(`extraction.fragment_origin`, checked injective and element-preserving),
every `PrefixEntry` carries that map, and `structure_annotation` composes the
maps down the tree, so a prefix subtree's own numbering lands on the drawing
as `LocantSource.SUBSTITUENT`, with the prefix it numbers. Over the
187-molecule corpus heavy-atom locant coverage went from 38.5% to 47.5%, and
naproxen's naphthalene -- which the ring table had numbered as its mirror
image, methoxy carbon "2" and attachment "6", against "6-methoxynaphthalen-
2-yl" -- is now numbered as its name says (the only relabelled atoms, in two
rows). The ring-table path reads the engine's built table, which fills
indole's 3a/7a. What remains: special-shape prefixes built as bare strings
(the amide N-substituent compound "amino" forms) carry no numbering, and a
one-atom substituent's "1" is deliberately not drawn. The record of the
problem as it stood follows.


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

## An indicated hydrogen dropped from a substituent name (CLOSED in round 4, D-040)

Fixed with the carbazole numbering: an `[nH]` pins the tautomer, not the
orientation, and the substituent branch that uniquified on it also dropped the
ring's `1H-`. The example below now names `4-(1H-indol-2-yl)benzoic acid`.
The record as it stood follows.


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

## Open after naming round 5 (in progress, from 2026-09-19)

Kept by layer, as round 4's list is. Filled in stage by stage; the round's
adjudicated open rows are in `benchmarks/naming/adjudication.toml`, each with
its layer and target stage.

| layer | case | note |
|---|---|---|
| audit reach | molecules named with no substitutive level (66/267 on the tuning populations), and the insides of functional-class, multiplicative, ring-assembly and additive nodes | N2's ownership invariant runs where a substitutive tree exists; a leaf is trusted to name its whole fragment. Extending it needs provenance on those node kinds, which do not carry atom maps today |
| candidate generation | fusion names needing a SECOND-ORDER attached component | refused (`NEEDS_UNBUILT_CONSTRUCTION`), von Baeyer name or none | N3 builds one parent plus first-order components; 16 of the book's P-25 examples need more ("pyrido[1'',2'':1',2']imidazo[4',5':5,6]pyrazino[2,3-b]phenazine") |
| candidate generation | multiparent systems | refused, von Baeyer name or NONE | "benzo[1,2-b:4,5-c']difuran" (p. 234): the older fusion route used to stand in with "furo[2,3-f]2-benzofuran"; it no longer may, and the von Baeyer route fails here, so the molecule has no name until multiparent names are built (D-086a) |
| numbering | interior heteroatoms (P-25.3.3.2) | refused | 6 book examples ("6H-quinolizino[3,4,5,6-ija]quinoline", D-086c) |
| numbering | a 7- or 8-membered ring fused on three or more sides | refused | measured: 4 of the book's 8 such systems numbered as OPSIN numbers them, 4 did not -- their drawings need a hexagon on an octagon's horizontal side, a shape the drawing model lacks |
| numbering | rings of more than eight members; helicenes | refused | the book's distorted shapes; a helicene's own orientation rule (hexahelicene itself is retained, and named) |
| numbering | the ring table's pyrene and phenalene | former CAS interior locants (10b, 10c) | P-25.3.3.3.1 (p. 224) numbers interior carbons 3a1, 5a1 in PINs; the table predates that and is not repaired in N3 |
| candidate generation | hydro forms of a TRADITIONALLY numbered retained parent | von Baeyer ("tricyclo[8.4.0.0^{4,9}]tetradeca-1(14),2,10,12-tetraene" for a hexahydrophenanthrene) | general fusion leaves anthracene, phenanthrene, acridine, carbazole, xanthene and purine to the ring table, which carries their traditional numbering but cannot always derive a hydro form; the fusion-rule numbering is not theirs, so the constructor refuses rather than number them its own way |
| data | OPSIN "arylGroups" stems read as ring names | 280 stems; those whose parent ends in 'e' by OPSIN's own fusion prefixes are repaired ("quinolizin" -> "4H-quinolizine") | the rest ("caffein", "anisol", "paracetamol") are N5's registry gate |

## Open after naming round 4 (2026-09-18)

Round 3's table below is closed except for one row: chloroquine, warfarin,
caffeine, 1,4-xylene, the sulfoxides, the N-oxide locant and cid14000's double
wrapping are all fixed, each with a `D-0xx` row in
`tests/test_namer_known_defects.py` (D-038..D-082 are round 4's). The float
comparator is gone too (stage 5, `NomenclaturePreferenceKey`), and so is the
strategy that the cache key ignored (A11). What remains, by layer. Every
target here was checked against the book on the page cited; none is guessed.

| layer | case | emits | preferred | note |
|---|---|---|---|---|
| candidate generation | heterofused systems not in the ring table | von Baeyer names | fusion names | BUILT in round 5 (N3) for one parent + first-order components: cid5000 and the v2 rows now fusion names; the book's 78 in-class P-25 examples exact. Its limits are in the round-5 list |
| candidate generation | multiplicative names | `N''-{14-[(diaminomethylidene)amino]tetradecyl}guanidine` | a multiplicative bis-guanidine | also methylenebis(phosphonic acid) and N'-acyl hydrazides (`N'-benzoylbenzohydrazide (PIN)`, p. 671). Admitting an acylated N' into the hydrazide pattern named a WRONG molecule, so it is held out |
| candidate generation | hydrazine as a parent hydride | `1-(hydrazinyl)methanamide` | `hydrazinecarboxamide (PIN)` (p. 645) | and the carbazates, `ethyl hydrazinecarboxylate` |
| candidate generation | N-substituted nitrogen oxoacids | `[(hydroxysulfonyl)amino]methane` | `methylsulfamic acid` | the oxoacid composers decline and the general path names a hydride |
| retained parents | oxamide, oxalohydrazide | `ethanediamide`, `ethanedihydrazide` | `oxamide (PIN)`, `oxalohydrazide (PIN)` (pp. 351, 668) | substitution allowed on both |
| retained parents | silicic acid, disiloxane | `tetrahydroxysilane`, `trimethyl(trimethylsilyloxy)silane` | `silicic acid`, `hexamethyldisiloxane` | the second is round 3's last open row |
| PCG seniority | an amide on a urea N | `N-benzoylurea` | `N-carbamoylbenzamide (PIN)` (p. 661) | the engine ranks urea's carbonic amide WITH carboxylic amides; declining the urea route produced `1-amino-N-benzoylmethanamide`, so the urea gate stops at acids (D-078k holds it) |
| PCG assignment | a chain-terminal amidine carbon | `4-carbamimidoylbutanoic acid` | amino + imino prefixes, as "methyl 4-(dimethylamino)-4-(ethylimino)butanoate (PIN)" (P-66.4.1.3.2, p. 677) | when the amidine carbon terminates a chain |
| PCG assignment | a silanol with an alcohol elsewhere | `2-[(hydroxy)di(methyl)silyl]ethan-1-ol` | a silanol parent (P-44.1.2, Si before C) | the single-centre route declines on any same-class group rather than count them |
| PCG assignment | hydroxamic acids | `cyclohexanecarbohydroxamic acid` | `N-hydroxycyclohexanecarboxamide (PIN)` (p. 587) | |
| numbering | tetrahydropyridines | `1,2,5,6-` | `1,2,3,6-tetrahydropyridine-4-carboxylic acid` | ranks ring double bonds, not hydro locants |
| numbering | `pyridin-1(6H)-yl` | the old name | its lowest orientation | the free valence is not in the preference key, so the P-58.2 route declines |
| data | 32 ring-table entries | -- | -- | they number only some positions; a substituent elsewhere had an empty locant. Guarded (the plan is refused), not repaired |
| serialization | thioacyl amino prefixes | `4-(ethanethioylamino)benzamide` | `4-(ethanethioamido)benzamide (PIN)` (p. 657) | a compound thioacyl is also left unenclosed |
| serialization | phosphoryl prefixes | `[diethyl(oxo)phosphanyl]acetic acid` | `(diethylphosphoryl)acetic acid` | "phosphoryl (preselected prefix)" for -PO< (p. 357), substituted as in "[(dimethoxyphosphoryl)oxy]carbonothioyl (preferred prefix)" (p. 359) |
| serialization | tert-butyl | `dimethyl(2-methylpropan-2-yl)silanol` | `tert-butyldi(methyl)...` (pp. 313, 375) | the book prints tert-butyl in PINs |

Also open, and not a name defect:

* **The atom-drop invariant has gaps.** CLOSED for substitutive trees in
  round 5 (N2, `ownership.py`): every level's tree must own each heavy atom
  exactly once, a suffix may own only elements its form names, and nothing
  outside the parent's component. Both of round 4's drops, re-injected, are
  caught. What it does NOT reach, measured over the tuning populations: 66
  of 267 molecules are named with no substitutive level at all (63 by a
  single leaf -- a retained name or a single-centre route --, 2 by a pre-plan
  string dispatcher, 1 additively), and functional-class, multiplicative,
  ring-assembly and additive nodes are not audited inside. See "Open after
  naming round 5".
* **The registry.** `tools/retained_name_audit.py` now fails closed on
  impossible claims, and 18 PINs, 26 non-PIN retained names and 15 book-absent
  names are typed; 251 entries still have no audited status. Separately,
  `data/opsin_extracted/retained_names_from_opsin.json` holds 1,824 names taken
  from OPSIN's parse dictionary that feed whole-molecule naming unaudited
  (fluorouracil among them): a parser's vocabulary is not evidence of a PIN.
* **The book contradicts itself once, and the rule was followed.** Its prefix
  list prints `2,3-dihydro-1H-isoindol-2-yl` (p. 344); P-58.2.3.1.1 and the
  worked analysis on p. 499 give `2H-isoindol-2-yl`. The engine emits the
  latter; the test row says why.
* **Depiction.** Substituent numbering now reaches the drawing (A12), except
  from compound amino prefixes assembled as strings, which carry no tree.

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

* ~~The preference cascade is still a float with hand-tuned bands.~~ Closed
  in naming round 4 (stage 5): `LegacyScoreKey` first, proved decision-
  identical on both corpora, then `NomenclaturePreferenceKey`, whose every
  reorder was enumerated. It was not only hygiene after all: it found
  cid19000's fusion candidate generated and outranked by locant sums, and the
  alphanumerical tie-break keyed on FG type rather than names (D-038).
* ~~The strategy is not in the session cache key, and `IUPACCanonical()` is
  hard-constructed at 11 sites.~~ Closed in naming round 4 (A11): a
  top-level call binds its strategy, every helper reads `active_strategy()`,
  the cache key carries `cache_key()`, strategies refuse attribute
  assignment, and `tests/test_namer_strategy_propagation.py` guards all of
  it, including a source scan against a new construction site.
* **274 retained-name registry entries have no audited status.** They behave
  exactly as before; `tools/retained_name_audit.py` reports the backlog.
