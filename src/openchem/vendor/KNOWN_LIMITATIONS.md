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

## Naming round 16's open items are closed (2026-09-25, round 17)

D-166 (`nitramide`) and D-167 (N-nitro and N-nitroso carbamates) are fixed, and round 17 changed round 16's own names for the plain nitramines and nitrosamines to the book's
PINs: P-67.1.2.6.3 (pdf p. 708) makes them SUBSTITUTED NITRAMIDES and NITROUS AMIDES (`dimethylnitramide`, `dimethylnitrous amide`), and the `N-methyl-N-nitromethanamine` form round 16
wrote is the book's non-PIN alternative. `CHANGELOG.md`, round 17.

## Open after D-191 and D-192 (2026-10-06)

D-191 (a group past its standard bonding number lost its lambda number) and D-192 (a nuclide on a one-atom prefix was dropped) are closed in `CHANGELOG.md`, 2026-10-06. What they leave open, each measured on the tree that closes them (OPSIN read-back; every target below is read back to its input on canonical SMILES and InChIKey):

* **D-193 (a nuclide the name dropped, wrong molecule) is closed, and what it was is now a refusal (naming round 28, 2026-10-07).** The cause was general, not four cases: `collect_isotope_labels` dropped a label for any atom it could not locate ("drop the label rather than emit a guess") and every route that builds a name from parts of the molecule (a retained parent that numbers nothing, a multi-atom prefix, an ether oxygen, the hypohalous-amide route, a hydroxy or amino prefix) could do the same, so each read back as the UNLABELLED compound. `engine._check_nuclides_named` now refuses any name that cites fewer atoms of a nuclide than the molecule has (`_nuclides_named` reads the isotope brackets, multiplied by the multiplier that encloses them: `1,2-di[(81Br)bromo]ethane` is two atoms), and the routes that can label their atoms do: `(15N)aniline`, `(18O)phenol`, `(15N)benzonitrile`, `(15N)cyanoacetic acid`, `3-[(81Br)bromocarbonyl]propanoic acid`, `(18O)methoxyacetic acid`, `dimethyl(81Br)hypobromous amide`, `3-[(O-2H)hydroxy]propanoic acid`, `3-[(N-2H)amino]propanoic acid`. A bare symbol is used only when the element is ALONE in the group it modifies (P-82.6.1.2): `(13C)benzonitrile` is refused because OPSIN calls it ambiguous among seven carbons, and so are two nitrogens of one retained name, an `[18O-][N+](=O)` nitro oxygen, `CN([2H])CCC(=O)O` and `[2H]N([2H])c1ccccc1`. The application shows a refusal as a `NamingError`. Measured on 400 census molecules with one atom labelled (13C, 15N, 18O, or a deuterium on a heteroatom; fixed seed): master 89 exact, 86 WRONG MOLECULE, 205 OPSIN-unreadable, 20 naming errors; now 290 exact, 2 wrong, 40 unreadable, 20 naming errors and 48 refusals, with no name that was exact before changed; the census (2000 rows) moves 0. **What is still wrong in that sample:** the two are a label's locant on a bridged or polycyclic retained parent (a morphinan, a tetracyclo ring), where the engine's numbering is not OPSIN's and the label now lands on another atom (the same locant was invisible before because the name was unreadable); the application's read-back withholds such a name. A third, an ether prefix with two oxygens, was fixed by requiring the element to be alone. The 40 unreadable are right-molecule names in placements OPSIN cannot read (an amide or ester carbonyl label, `(1-15N)propanamide`, a label inside a hydro-named heterocycle), not changed in this round.
* **Isotopic label placement and labelled rings (naming round 29, phase 2, 2026-10-08).** Of the 40 names OPSIN could not read after round 28, 35 were the label's PLACEMENT (the name with the bracket removed read fine), and a fifth cause sat under them: a nuclide anywhere in a ring made the ring unrecognisable (`ring_naming.common._nuclide_free` now looks a ring up without its nuclides), so labelled benzene was `cyclohexa-1,3,5-triene`, labelled pyridine `azine`, labelled naphthalene a naming error and labelled tetralin a `bicyclo[4.4.0]` name for ANOTHER molecule. The placements: a suffix whose locant is left out is written with it, `butan-1-(18O)amide`, `propan-1-(18O)al`, `propane-1-(15N)nitrile` (a retained name keeps the bare label after the prefixes, `2-chloro-N-phenyl(15N)acetamide`); the bracket follows the hydro prefixes, `3,4-dihydro(4-13C)quinolin-1(2H)-yl`, `2,3-dihydro(1-15N)-1H-indole`; it goes before the `amino` it modifies, `3-[benzoyl(N-2H)amino]propanoic acid`; and before the `oxy` of a compound alkoxy on the uncontracted form, `[(phenylmethyl)(18O)oxy]`. Each form is the one OPSIN reads (tested against its rivals). Measured on the same 400 labelled census molecules (round 28 -> now): exact 290 -> 331, OPSIN-unreadable 40 -> 10, naming errors 20 -> 8, wrong molecule 2 -> 2 (one fixed, one new), refused 48 -> 49, nothing exact regressed; census 0 moved. **Still unreadable (10):** the two oxygens of an ester or acid component (below), a label among two suffix groups (`heptane-2,4-dione`), an N-substituted piperidinyl whose ring nitrogen is also the attachment atom, and a label on a ring with a prefix before `(1-13C)phenyl`. **The two wrong molecules** are a label's locant on a retained or hydro-named ring where the engine's numbering is not OPSIN's: the morphinan (`4,5-epoxy...(4-13C)morphinan-6-one`) and a deuterium on the ring nitrogen of a hydro-purinone (`(9-2H)-5,9-dihydro-2H-purin-6-one`); the second was hidden while its name was unreadable. **D-197, found and NOT fixed:** the carbonyl and the alkoxy oxygen of an ester are one name, `methyl (1-18O)acetate`, for two different molecules, and OPSIN reads neither; pinned open in `tests/test_namer_known_defects.py` with the forms OPSIN does read for each (`-1-(18O)oate`, `-1-(O-18O)oate`), whose agreement with the book is not known. **Corrected in naming round 30 (next entry): D-197 is closed, and two of the diagnoses above were wrong (the morphinan is exact when compared without stereo; the hydro-purinone's label is right and its unlabelled name is the defect).**
* **Carboxyl oxygens, a ketone's neighbours, and a nuclide in a fused ring (naming round 30, 2026-10-08; D-197, D-200, D-201, D-202).** D-197 is closed: the carbonyl and the hydroxyl oxygen of an acid (the latter is also an ester's alkoxy oxygen) are two names, `methyl (18O)acetate` and `methyl (O-18O)acetate`, `methyl prop-2-en-1-(18O)oate` and `methyl prop-2-en-1-(O-18O)oate`, `(18O)acetic acid` and `(O-18O)acetic acid`, each read back exact. D-200 was a WRONG MOLECULE: a ketone's group lists its two neighbours, so the ring nitrogen of `CC(=O)[15N]1CCCCC1` was cited by the ring AND by `-one` (`ethan-1-(15N)one`); only what is double-bonded to the anchor is the suffix's now. D-201: `prop-2-en-1-(18O)amide`, the infix's e before a vowel with the bracket between. D-202: a nuclide in a fused, bridged or spiro ring made the ring a naming error or a von Baeyer name; `ring_naming.name_ring_system` looks every ring up without its nuclides. 300 census molecules with one ring nitrogen labelled, master -> now: exact 269 -> 295, unreadable 16 -> 2, naming errors 11 -> 0, wrong molecule 3 -> 2; the 400 labelled molecules of rounds 28 and 29: exact 331 -> 348, unreadable 10 -> 3, naming errors 8 -> 0; census (2000) and panel (1712) 0 moved. **Still open, found here:** (1) a label on ONE oxygen of a multiplied suffix (`(2-18O)hexane-2,4-dione`) has no form OPSIN reads (only the unconventional `hexane-2-(18O)one-4-one`), so there is no target to pin; (2) the hydro-purinone `[2H]N1C(SC)=NC2C(=O)N=CN=C21` is named `8-(methylsulfanyl)-5,9-dihydro(9-2H)-2H-purin-6-one` and its UNLABELLED name `...-5,9-dihydro-2H-purin-6-one` is already another molecule (OPSIN reads `...-5,9-dihydro-6H-purin-6-one` as the structure): the indicated hydrogen is put at 2, not at the oxo carbon 6; three more unlabelled names OPSIN cannot read turned up (a 6-azauridine, a pentacyclo imide, a bis-dioxolopyran), each its own shape; (3) the morphinan label was never wrong: OPSIN reads a morphinan name WITH stereo the input lacks, so a sweep must compare without stereo for these. The wrong diagnosis `azin-3-yl` was only a labelled pyridine before round 29's ring fix. **Update (naming round 31): item (2), the hydro-purinone's indicated hydrogen, is closed as D-203 (next entry).**
* **The indicated hydrogen of a hydro-named ring ketone (naming round 31, 2026-10-08; D-203).** `8-(methylsulfanyl)-5,9-dihydro-2H-purin-6-one` was another molecule (OPSIN reads a CH2 at C2); it is `...-5,9-dihydro-6H-purin-6-one`. The retained lookup writes the curated parent's DEFAULT indicated hydrogen into its text, and `indicated_hydrogen_p58._resolve` declined the planner's correct answer because that placeholder was not among the atoms the plan described; it now ignores the old indicated labels and still requires the hydro positions to agree. Seven purin-6-one tautomers were wrong, all exact now; census 2 names moved (both mismatch_formula -> exact), panel 0. **Still open, found here:** enol and imidol tautomers (`C(O)=N`, `C(=C(O)O)`) of ring systems are named as hydroxy/azinane parents that OPSIN reads as another molecule or cannot read: 5 wrong and 4 unreadable of 178 odd tautomers, each its own shape and none this defect.
* **A benzo-fused bridged ring system with a ring heteroatom (naming round 32, 2026-10-08; D-204).** `benzo_fused_bridged` names a CARBOCYCLE (`5,9-methanobenzocycloocten-7-one`) and never read an element, so the O and N of a 2,6-methano-1,3-benzoxazocin-4-one were dropped: a different molecule, both census rows of the shape. It declines a system with a ring O, N or S now and the generic bridged path names it (`8-oxa-10-azatricyclo[7.3.1.0^{2,7}]trideca-2,4,6-trien-11-one`, exact). 114 heteroatom variants, wrong 89 -> 0. **Still open:** the PREFERRED name is the fusion-bridged one (P-25.4, `2,6-methano-1,3-benzoxazocine`), not built; and the carbocycle names this module writes carry odd hydro multipliers (`5,6,7,8,9-pentahydro-5,9-methanobenzocycloheptene`) that OPSIN reads but P-31.1.4.2.4 does not allow.
* **The cation of a fused ring system, and a ring fused on purine (naming round 33, 2026-10-09; D-205, D-206).** A protonated fused heteroaromatic (`c1c[n+]2c([nH]1)[nH]c1ccccc12`) was a `NAMING ERROR` because no table holds its cation; a ring system with nothing to offer that has an aromatic nitrogen cation is retried on its neutral twin (`ring_naming._neutral_twin`), and the `-ium` is rendered from the full molecule. D-206: a ring fused on purine was lettered by sorting purine's locants, but its periphery runs 1,2,3,4,9,8,7,5,6, so N7-C8 is `f`, not `g` (`imidazo[2,1-f]purine`, not `imidazo[1,2-g]purine`); `fusion_general._periphery_order` walks the periphery now. 32 purine-fused systems exact 21 -> 32; 300 protonated fused heteroaromatics: naming errors 8 -> 0; census 3 rows `NAMING ERROR` -> exact. **Still open, found here:** (1) the cation is LOST for protonated 2-amidothiazoles, tetrahydrobenzothiazoles and pyrazolo[1,5-a]pyrimidines (9 of 300 protonated molecules are still wrong); (2) a NON-aromatic cation (`C1C[N+]2=C(CCCCC2)NC1`, a bicyclic amidinium) is a visible `NAMING ERROR`, and `C[N+]1=C(C)NCC1` is named `2,3-dimethyl-1,3-diazol-3-ium` without its hydro prefixes (a different molecule); (3) 5 census rows are still `NAMING ERROR`: two neutral tetracyclic fused systems (`Cc1nn(-c2ccccc2)c2c1cc1c(=O)n(C)c(=O)nc-1n2-c1ccccc1F`, `C=CCn1cnc2c(c1=O)c1nc3ccccc3nc1n2CCC1=CCCCC1`), the amidinium, and two spiro-oxindole pyrano[2,3-c]pyrazoles; (4) three `sulfonamidate` census rows are OPSIN reading a correct anion name as the neutral sulfonamide, not an engine defect.
* **P-45.3 and P-45.4 are applied across parents (naming round 29, 2026-10-08); D-194c is closed.** `engine._senior_by_substituent_modification` compares one key in the book's order, between P-45.2.3 and P-45.5: P-45.3.1 the maximum number of prefixes directly bonded through an atom of nonstandard bonding number (then the higher number first, `lambda6` before `lambda4`), P-45.3.2 their lower locants, P-45.4.1 the lowest locants of the isotopically modified prefixes (a nuclide anywhere in the prefix), P-45.4.2 those holding the nuclide of higher atomic number, P-45.4.3 of higher mass number. D-194c's ether `2-bromo-1-{[2-(81Br)bromopentyl]oxy}pentane` was 24 and 16 of 40 spellings and is one name; the book's other examples were 7 and 6 of 13 (P-45.3.1 example 1, example 3 and P-45.4.1), and 8 and 5 and 11 and 2 THE WRONG WAY ROUND for P-45.4.2 and P-45.4.3; each is one name over 16 spellings now, and P-45.5's example 5, which carries nuclides, is the book's name on all 16 (9 and 4 of 13 before). **Not covered:** P-45.3.1 example 2 and P-45.3.2 (`2lambda5-diphosphan-1-yl`) are not reached because the engine drops the lambda number of a MULTI-atom group (`4-diphosphanyl-2-(2-diphosphanylethyl)butanenitrile` for the book's `4-(2lambda5-diphosphan-1-yl)-...`), a defect of its own that the rule cannot show. **Read as text:** a prefix is 'directly bonded through a hypervalent atom' when its leaf text, or its tree's own parent name, starts with `lambdaN-`; and a prefix is 'isotopically modified' when its assembled name cites a nuclide, so a form the engine spells differently from the book is compared on the engine's spelling.
* **D-195 is closed (naming round 28): a hypervalent centre with NO hydrogen and only single bonds takes its lambda number.** `CP(C)(C)(C)C` is `pentamethyl-lambda5-phosphane`, `COP(OC)(OC)(OC)OC` the book's `pentamethoxy-lambda5-phosphane (PIN)` (p. 770), `pentaphenyl-lambda5-phosphane` and `pentamethyl-lambda5-arsane`, and as a substituent `(tetramethyl-lambda5-phosphanyl)acetic acid`. A centre with a double bond (`trimethyl-lambda5-phosphanone`) already said its number, and a sulfur or halogen centre (`(pentamethylsulfanyl)methane`, `FS(F)(F)(F)(F)F`) goes through other routes and is unchanged.
* **D-196 is closed (naming round 28): the parent's nuclide is cited before the part it modifies.** `[13CH3]CCCBr` is `1-bromo(4-13C)butane` and `4-chloro(15N)aniline` (the bracket goes after the prefixes, before the parent name, with a hyphen only where a locant follows); a nuclide on the heteroatom of a suffix group is cited before the suffix word, `1-phenylethan-1-(18O)one` (P-82.2.1, p. 853), when the parent is systematic and the suffix carries a locant. **Still at the front of the name**, as before and OPSIN-unreadable: a suffix with no locant to follow (`(1-18O)ethanol`, `(1-18O)acetaldehyde`, `(1-18O)acetic acid`, where the book prints no place and OPSIN has not been shown to read one). The hypohalous amide and ether routes are listed with D-193 above.
* **A sulfine, `C=S=O`, is a visible naming error before and after** (`[NAMING ERROR: Substitutive plan for parent 'methane' leaves heavy atoms [2] unclaimed]` on the base, `{[NAMING ERROR: No valid naming plan found for O=[SH2]]}methane` now: the group is carved as `=S(=O)` and no plan names it). The application refuses a name that embeds the error.
* **Where the numbering key is shadowed.** `_alphanumerical_locant_key` orders prefixes by `(sort name, isotope key, stereo key, name)`, so as to agree with the order assembly prints them in. The isotope key is shadowed there by the last element: a labelled prefix's name starts with `(` or `[`, which sorts before a letter, so removing the key changed no test (mutant M19 of the matrix in the changelog survived). It is kept so that the numbering criterion cannot disagree with the printed order if a label ever sits later in a name.

## Open after P-14.4 (j) and "R precedes S" elsewhere (2026-10-06)

P-14.4 (j) decides between numberings of ONE parent (`_break_alphanumerical_tie`), which includes the `-diyl` group of a polyol's diester since naming round 26. Three more choices that used to go by atom order are decided now (`CHANGELOG.md`, 2026-10-06, "R precedes S beyond the numbering"): the order two prefixes that differ only in their descriptors are cited in (P-45.6.3), which half of a meso diether or diamide is the parent (P-45.6.2, and like before unlike for a parent that carries two R/S descriptors, P-44.4.1.12.2), and the principal ester of a diester on the acyloxy form (the ester-route tier, back once the session cache was fixed). What is left, each measured:

* **P-45.2.3 is implemented (2026-10-06): see "Open after P-45.2.3" below.** This entry said it was not, and that P-45.6.2 example 3's second name was this gap and not a stereo one; both are settled: `1,2-bis[(1S)-1-chloroethyl]-4-{3-[(1R)-1-chloroethyl]-4-[(1S)-1-chloroethyl]phenoxy}benzene` is now the name on every spelling (`tests/test_namer_parent_citation_locants.py`).
* **P-92.5.2.2 example 5's structure is one name now, and the earlier note about it was wrong in what it concluded** (naming round 26 follow-up, `CHANGELOG.md`, 2026-10-06, "one stereoisomer, one name"). `C[C@H](Cl)[C@@H](C)[C@@]([C@H](O)[C@@]([C@H](C)[C@@H](C)Cl)([C@H](C)[C@@H](C)Cl)[C@@H](C)[C@@H](C)Cl)([C@H](C)[C@H](C)Cl)[C@@H](C)[C@@H](C)Cl`, built from the book's descriptors with RDKit's CIP labeler (OPSIN cannot read the book's name: "Failed to assign CIP stereochemistry"), has 13 stereogenic centres and NINE chains that tie on every criterion of the preference key. It was 8 names over 10 spellings on `66f112ed`, 16 over 30 with the session-cache fix, 4 over 30 with the "R precedes S" follow-up, and is 1 over 40 now, the book's. An earlier note here said "at most one set describes it" and "most are wrong": that held only before the cache fix, which was a real wrong-compound defect (a (2R,3R) arm printed (2S,3R)). Once it was fixed every one of the 16 names was RDKit's label for the atom it describes, per atom, parent and prefixes: sixteen correct names of one molecule, each on a different chain. The defect was the CHOICE of chain, which `_break_parent_stereo_tie` made only for up to four tied parents (there are nine, of which four differ) and only for names that were equal "once the descriptors are set aside" in the finished text (which they are not, because the descriptors decide how prefixes merge). Examples 1 to 3 of the same section were never affected. `tests/test_namer_stereo_parent_choice.py` pins the book's molecule and eight more stereoisomers of its skeleton, each over random spellings, each descriptor checked per atom against RDKit.
* **Like and unlike are judged only for a parent that carries exactly two R/S descriptors.** For three or more the book pairs each centre with a reference descriptor chosen from the digraph (P-92.5.2.1, Mata and Lobo), which a finished name does not hold, so such a parent is compared on E/Z, r over s and R over S, and then on the whole name (`_parent_configuration_key`, `stereo_citation_key`). The one example the book prints for the numbering consequence, P-92.5.2.2 example 5 (p. 900), has a caption ("lowest locants are assigned to the like pair") that its own printed name contradicts: the unlike pair `(2S,3R)` is at the lower locant 4 and the like pair `(2S,3S)` at 6, which is what R-first citation (P-45.6.3) gives. Numbering is criterion (j), R before S; like before unlike is the rule for choosing between PARENT STRUCTURES (P-44.4.1.12.2, p. 413) and is applied there. An earlier note here said like pairs were not implemented and that no output told them apart; the ether `CC(Cl)C(C)OC(C)C(C)Cl` (halves (2S,3R) and (2S,3S)) is the output that does, and is now named on the like half.
* **M and P are not ranked in a prefix's citation order.** `stereo_citation_key` reads the letters assembly's descriptor pattern reads (R, S, E, Z, r, s); a helical descriptor inside a prefix is neither ranked nor stripped from the sort name, and the engine writes none there today.
* **The ester tier compares the alcohol component's own descriptors only.** Descriptors inside that component's substituents are ordered by the citation rule inside its tree. Every stereoisomer of six skeletons that were not tuned on (dipropylene and tripropylene glycol diacetate, the dibenzoate, a tartrate diacetate, hexane-2,5-diyl and hydrobenzoin diacetates) is one name over its spellings and reads back through OPSIN, which is what the tier was removed for failing.
* **The units' locants are compared before their descriptors** (`(2S)-butane-2,3-diol` for a single specified centre, never `(3S)`). That is this change's reading of "lower locants related to the presence of stereogenic centers" in criterion (j), supported by the note under P-92.5.1 (pdf p. 895) that the numbering of the principal chain "is based on lowest locants for stereogenic centers"; the book prints no example in which the two orders of comparison disagree.

## Open after naming round 26 (2026-10-06; D-187 to D-190 closed in round 26 above)

* **Different anions on one polyol keep the accepted (acyloxy) name, not the PIN.** P-65.6.3.3.3.2 method (1) prints `propane-1,2,3-triyl 1,2-diacetate 3-propanoate (PIN)`, `1,4-phenylene acetate dichloroacetate (PIN)` and `methylene acetate formate (PIN)`; the book's five examples and every variant tried (with and without locants, `methanediyl`) are UNPARSEABLE to OPSIN (measured 2026-10-06), so a name built here could not be checked by the one reader this project trusts. They stay on method (2), `2,3-bis(acetyloxy)propyl propanoate`, which OPSIN confirms. Reopen if OPSIN reads the form or another reader is wired in.
* **A polyol whose organyl group is not one parent keeps the acyloxy name.** `_organyl_cites_valences` declines a group the generic path cannot write as one n-valent group: a multiplicative group (`1,2-phenylenedi(propan-3,1-yl)`, `1,4-phenylenebis(methylene)`, `oxydi(ethane-2,1-diyl)`: diethylene glycol diacetate), a ring assembly (`[1,1'-biphenyl]-4,4'-diyl`, bisphenol A diacetate) and valences on a branched skeleton (pentaerythritol: four valences on four carbons). The book prints PINs for all of them; none is built. The first version of the generic path wrote the first of these as `3-(2-propylphenyl)propane-1-diyl`, one locant for two valences, a different molecule: that is what the guard is for.
* **Esters of a polyol AND a polyacid** (P-65.6.3.3.4.1, `dimethyl ethane-1,2-diyl dibutanedioate (PIN)`) are not built; the name is unchanged and OPSIN reads it.
* **A meso group has two equally good descriptor sets and the engine chooses by atom order** -- CLOSED 2026-10-06 for numberings of one parent and of a `-diyl` group (the P-14.4 (j) tie-break, see the section above): `(2R,3S)-butane-2,3-diyl diacetate`, `(1R,2S)-cyclohexane-1,2-diyl diacetate`, meso-butane-2,3-diol, meso-2,3-dichlorobutane and cis-cyclohexane-1,2-diol are one name each in every atom order. The rule is criterion (j) of P-14.4 (pdf p. 79), not P-31.1.4.3.4 as this bullet first said (P-31.1.4 is the von Baeyer section in that PDF). What stays open is listed above, notably a meso compound whose two halves are each a candidate PARENT.
* **The free-valence SET rule (D-190) covers chain and ring parents only.** A heteroatom-chain parent (hydrazine, disulfane) with two valences still reads the first attachment alone.

## Open after the stereo cache fix (2026-10-06)

The naming session's cache no longer answers for two substituents that differ only in an inherited R/S descriptor (`CHANGELOG.md`, 2026-10-06). It leaves these, each measured on the tree before and after and found identical:

* **Prefixes that tie on their letters ALONE are cited in atom order (P-14.5.4).** "When two or more prefixes consist of identical Roman letters, priority for order of citation is given to the group that contains the lowest locant(s) at the first point of difference" (BlueBookV2.pdf p. 82). `derive_sort_name` strips locants and stereodescriptors, and the sort that cites the prefixes is stable on it, so prefixes that tie on their letters keep the order the atoms were written in. The book's own `1-(pentan-2-yl)-4-(pentan-3-yl)benzene` is that name in 20 of 40 random spellings and `4-(pentan-3-yl)-1-(pentan-2-yl)benzene` in the other 20 (no stereo there, so neither the cache key nor the rule below is involved). **The stereo half of this was closed the same day** (`CHANGELOG.md`, 2026-10-06, "R precedes S beyond the numbering"): prefixes that differ only in their descriptors are cited R before S and Z before E (P-45.6.3, p. 427), so the R,S di-sec-butylbenzene is `1-[(2R)-butan-2-yl]-3-[(2S)-butan-2-yl]benzene` in every spelling (it was that or `3-[(2S)-...]-1-[(2R)-...]benzene`, 63 and 57 of 120, once the cache key made it the right molecule), and the E,Z-propenyl pair on a 1,3-phenylene is `1-[(1Z)-prop-1-en-1-yl]-3-[(1E)-prop-1-en-1-yl]benzene` (it was cited either way, 31 and 29 of 60, with E on locant 1 in every spelling, against criterion (j)).
* **A name OPSIN cannot read is checked by CIP, not by read-back.** `CC[C@H](C)[C@H]1CC[C@@H]([C@H](C)CC)CC1` (side chains R and S) was `(1R,4S)-1,4-bis[(2S)-butan-2-yl]cyclohexane`, the same defect, and is now `(1R,4S)-1-[(2R)-butan-2-yl]-4-[(2S)-butan-2-yl]cyclohexane`, each ring centre paired with the side chain RDKit's CIP gives it. OPSIN reads neither (`Could not find atom that: <stereoChemistry locant="1" ...>`), so the sweep that found the rest cannot confirm this one; a name that parses back is not the only way a name can be right, and one that does not parse is not therefore wrong.

## Open after naming round 25 (2026-10-05; D-183 to D-186 closed in round 25 above)

* **Polyesters are written in the accepted (acyloxy) form, never the PIN.** CLOSED in round 26 for the esters of one polyol with one acid (D-187: `ethane-1,2-diyl diacetate`, heroin `...morphinan-3,6-diyl diacetate`); what is left of it is the first three bullets of the round 26 section above.
* **"Senior acid" is ring-before-chain, then skeletal atoms, then substituents** on the executed acid component, not the full P-41/P-44.1 order (class, then the rest). With more than four tied esters, or a retained acid other than formate/acetate/benzoate, or a leaf-named alcohol, the choice falls to a canonical atom rank: stable, but not a rule. Where two esters have the same acid and the alcohols compare equal on locants (two benzoates, two acrylates) the book prints no further criterion this engine implements; the name is stable but its choice among valid names is arbitrary.
* **Tropine and pseudotropine have one name.** The C3 centre is pseudoasymmetric (`3r`/`3s`), OPSIN cannot read it, so it is dropped with a note. Keeping it would give the correct name but one the parser cannot verify.
* **The numbering of a bridged parent depends on the order the SMILES is written in.** `8-azabicyclo[3.2.1]octane` (tropane) with any suffix is numbered so its carboxyl is at 2 in some orderings and 4 in others, with or without stereo (`3-hydroxy-8-methyl-8-azabicyclo[3.2.1]octane-2-carboxylic acid` vs `-4-carboxylic acid`, 10 vs 10 of 20 random SMILES); lowest locants to the principal characteristic group says 2. Cocaine inherits it. Found in round 25 by a test that pinned the wrong form; **not fixed**, it is a von Baeyer numbering tie, outside this round's four items.
* The four natural products of round 24 are no longer open: atropine and scopolamine keep every centre OPSIN reads; galantamine and ibogaine are exact.

## Open after naming round 24 (2026-10-05; D-180, D-181, D-182 closed in round 24 above)

* **Four of 45 complex natural products still lose stereo in the app:** atropine and scopolamine (tropane parents), galantamine (`benzofuro[3a,3,2-ef][2]benzazepine`) and ibogaine (a methano-bridged fused system). Not diagnosed this round: the name is right about connectivity and the engine's own stereo check leaves the descriptors out. Read `_validate_stereo_via_opsin` first.
* **Charged morphinans** (quaternary N-methyl) fall back to a von Baeyer name: `retained_modified` refuses a formally charged ring atom.
* **Only morphinan is eligible for `didehydro`/`epoxy` modification.** Other retained natural-product parents (ergoline, ibogamine, the Amaryllidaceae scaffolds) are not in `_MODIFIABLE`; add one only where the book prints such a name.
* **Which ester carries the suffix depends on input atom order.** For a molecule with two equivalent ester groups (heroin; also `CC(=O)OC1CCC(OC(C)=O)CC1C`), randomised SMILES of the same structure give two names, `...-3-yl acetate` with `6-(acetyloxy)` and the reverse. Both read back to the structure, so neither is wrong about the molecule, but the lower-locant suffix is the expected one and the tie-break is accidental. Found while porting round 24; present before it (the non-morphinan control shows it too), not investigated.
* **The battery was not run on the frozen sets as a population.** It is a 45-molecule drug panel chosen by hand, so it measures the cluster, not a rate.

## Open after naming round 23 (2026-09-27)

D-179 (the chalcogen analogue thiohydrazide) is fixed; see `CHANGELOG.md`, round 23. Still open:

* **Two or more nitramide groups** (ethylenedinitramine, `O=[N+]([O-])NCCN[N+](=O)[O-]`) are a multiplicative parent this route does not build; they keep round 16's amine name
  `N1,N2-dinitroethane-1,2-diamine`, which is NOT the PIN. Round 21 derived and OPSIN-verified a candidate, `ethane-1,2-diylbis(nitramide)`, matching the book's own multiplicative pattern for other functional-parent pairs (p. 527); not implemented, since nitramide is a hand-built functional parent, not an ordinary suffix `multiplicative.py` already knows how to join.
* **A cyano group on the nitramide nitrogen** (`N#CN(C)[N+](=O)[O-]`) is left to the general path, `[methyl(nitro)amino]methanenitrile`. P-66.1.6.2 (pdf p. 664) retains `cyanamide` as the PIN for `NC-NH2`, itself a preselected amide-class parent (class 11) at the same seniority as nitramide; the book prints no example resolving which of two competing class-11 parents on one nitrogen wins, and round 21 found none either, so no target is claimed.
* **Still not measured, so not claimed:** N-nitro or N-nitroso on a thioamide, and any nitro group attached through a heteroatom other than nitrogen (a nitrate ester is `ethyl nitrate`).
* **The standing measures were blind to this class again.** No census row contains a plain nitramine or nitrosamine; the three tuning rows that do are the ones the round moved, and the blind frozen
  set moved on 5 of 1126. The rows in `tests/test_namer_known_defects.py` are the evidence, and the book's own examples were the way to find the defect.


## Open after naming round 22 (2026-09-27; D-179 closed in round 23 above)

## Open after naming round 22 (2026-09-27)

D-171 (hydrazones of a carbon-acid hydrazide) is fixed; see `CHANGELOG.md`, round 22. Still open:

* **Plain thiohydrazides** (`CC(=S)NN` is `(1-thioxoethyl)hydrazine`, not `acetothiohydrazide`): found while fixing D-171, a separate defect. The `fg:hydrazide` SMARTS matches only a carbonyl oxygen (`(=O)`); other suffix families share ONE base FG with a generic O/S/Se/Te infix mechanism, but hydrazide has no such chalcogen-generic path, so the thio analogue is never recognized as a hydrazide at all, hydrazone or not.
* **Two or more nitramide groups** (ethylenedinitramine, `O=[N+]([O-])NCCN[N+](=O)[O-]`) are a multiplicative parent this route does not build; they keep round 16's amine name
  `N1,N2-dinitroethane-1,2-diamine`, which is NOT the PIN. Round 21 derived and OPSIN-verified a candidate, `ethane-1,2-diylbis(nitramide)`, matching the book's own multiplicative pattern for other functional-parent pairs (p. 527); not implemented, since nitramide is a hand-built functional parent, not an ordinary suffix `multiplicative.py` already knows how to join.
* **A cyano group on the nitramide nitrogen** (`N#CN(C)[N+](=O)[O-]`) is left to the general path, `[methyl(nitro)amino]methanenitrile`. P-66.1.6.2 (pdf p. 664) retains `cyanamide` as the PIN for `NC-NH2`, itself a preselected amide-class parent (class 11) at the same seniority as nitramide; the book prints no example resolving which of two competing class-11 parents on one nitrogen wins, and round 21 found none either, so no target is claimed.
* **Still not measured, so not claimed:** N-nitro or N-nitroso on a thioamide, and any nitro group attached through a heteroatom other than nitrogen (a nitrate ester is `ethyl nitrate`).
* **The standing measures were blind to this class again.** No census row contains a plain nitramine or nitrosamine; the three tuning rows that do are the ones the round moved, and the blind frozen
  set moved on 5 of 1126. The rows in `tests/test_namer_known_defects.py` are the evidence, and the book's own examples were the way to find the defect.


## Open after naming round 21 (2026-09-27; D-171 closed in round 22 above)

## Open after naming round 21 (2026-09-27)

D-173 (the retained prefixes `benzylidene`/`benzylidyne`) and D-178 (amides of the halogen oxoacids) are fixed; see `CHANGELOG.md`, round 21. Still open, all investigated this round rather than merely carried forward:

* **Hydrazones of carbon acid hydrazides** (`CC(=O)NN=CCCCCC` is `1-acetyl-2-hexylidenehydrazine`, where P-66.3.3 names the hydrazide, `N'-hexylideneacetohydrazide`) were investigated in round 21 and left open: the FG SMARTS (`fg:hydrazide`, `data/functional_groups.json`) requires both nitrogens at `NX3`, which a hydrazone's terminal `=N-` (`NX2`) fails, and loosening it plus rendering an N'-ylidene alongside the `-ohydrazide` suffix touches the general FG-suffix pipeline broadly enough that a self-contained fix was not found. The census shows the family is common (acyl hydrazones of aldehydes and ketones), where round 20's `2-acylhydrazinylidene` prefix on the aldehyde, ring or phenol parent is what ships instead.
* **Two or more nitramide groups** (ethylenedinitramine, `O=[N+]([O-])NCCN[N+](=O)[O-]`) are a multiplicative parent this route does not build; they keep round 16's amine name
  `N1,N2-dinitroethane-1,2-diamine`, which is NOT the PIN. Round 21 derived and OPSIN-verified a candidate, `ethane-1,2-diylbis(nitramide)`, matching the book's own multiplicative pattern for other functional-parent pairs (p. 527); not implemented, since nitramide is a hand-built functional parent, not an ordinary suffix `multiplicative.py` already knows how to join.
* **A cyano group on the nitramide nitrogen** (`N#CN(C)[N+](=O)[O-]`) is left to the general path, `[methyl(nitro)amino]methanenitrile`. P-66.1.6.2 (pdf p. 664) retains `cyanamide` as the PIN for `NC-NH2`, itself a preselected amide-class parent (class 11) at the same seniority as nitramide; the book prints no example resolving which of two competing class-11 parents on one nitrogen wins, and round 21 found none either, so no target is claimed.
* **Still not measured, so not claimed:** N-nitro or N-nitroso on a thioamide, and any nitro group attached through a heteroatom other than nitrogen (a nitrate ester is `ethyl nitrate`).
* **The standing measures were blind to this class again.** No census row contains a plain nitramine or nitrosamine; the three tuning rows that do are the ones the round moved, and the blind frozen
  set moved on 5 of 1126. The rows in `tests/test_namer_known_defects.py` are the evidence, and the book's own examples were the way to find the defect.


## Open after naming round 20 (2026-09-26; D-173 and D-178 closed in round 21 above)

## Open after naming round 20 (2026-09-26)

D-170 (the substituent `hydrazinylidene`) is fixed; see `CHANGELOG.md`, round 20. Still open:

* **An azine, a triazane or a ring nitrogen on the second nitrogen of an `=N-N` group** keeps the imino form (`3-[(ethylidene)aminoimino]butanoic acid`, `3-(hydrazinylimino)butanoic acid`, `3-(pyrrolidin-1-ylimino)butanoic acid`); the book's names for them were not derived.
* **The book's `hydrazin-1-yl` locant**: it prints `2-nitrohydrazin-1-yl` (p. 717) where the engine writes `2-nitrohydrazinyl`, and elsewhere `hydrazinyl (not hydrazin-1-yl)` (p. 71); the round-20 prefix follows the engine's existing `hydrazinylidene` without a locant, and that spelling is left alone until the book's own convention is settled.
* **Hydrazones of carbon acid hydrazides** (`CC(=O)NN=CCCCCC` is `1-acetyl-2-hexylidenehydrazine`, where P-66.3.3 names the hydrazide, `N'-hexylideneacetohydrazide`) were seen while probing and are not measured; the census shows the family is common (acyl hydrazones of aldehydes and ketones), where round 20 now writes the `2-acylhydrazinylidene` prefix on the aldehyde, ring or phenol parent.
* **The `benzylidene` spelling:** the engine writes `phenylmethylidene` everywhere (`N'-(phenylmethylidene)nitric hydrazide`); the book's retained prefix is `benzylidene`.
* **Two or more nitramide groups** (ethylenedinitramine, `O=[N+]([O-])NCCN[N+](=O)[O-]`) are a multiplicative parent this route does not build; they keep round 16's amine name
  `N1,N2-dinitroethane-1,2-diamine`, which is NOT the PIN.
* **A cyano group on the nitramide nitrogen** (`N#CN(C)[N+](=O)[O-]`) is left to the general path, `[methyl(nitro)amino]methanenitrile`: cyanamide is retained for `NC-NH2` and the book prints no
  nitro derivative, so no target was derived.
* **Hypochlorous and bromous amides** (`ethylhypochlorous amide (PIN)`, `methylbromous amide (PIN)`, pdf p. 529) were seen and not measured.
* **Still not measured, so not claimed:** N-nitro or N-nitroso on a thioamide, and any nitro group attached through a heteroatom other than nitrogen (a nitrate ester is `ethyl nitrate`).
* **The standing measures were blind to this class again.** No census row contains a plain nitramine or nitrosamine; the three tuning rows that do are the ones the round moved, and the blind frozen
  set moved on 5 of 1126. The rows in `tests/test_namer_known_defects.py` are the evidence, and the book's own examples were the way to find the defect.

## Open after naming round 15 (2026-09-24)

Round 15 was one defect (D-163, a nitro group on a RING nitrogen), found on the molecule that motivated the whole post-round-14 program rather than on a scan.
It is fixed (`CHANGELOG.md`). What it leaves open, and what it showed about the instruments:

**A NITRAMINE WAS IN NO CORPUS ROW, and every standing measure was blind to it.** The census scan, ref-compare (1712 structures) and both frozen populations
report 0 names changed for the fix, because none of them contains a ring N-nitro structure. A name that reads back and is silly is exact to all of them
(`oxido(oxo)(pyrrolidin-1-yl)azanium` was `MATCH`). The next class like this will be found the same way this one was, by naming a battery of compounds one
knows the names of (`tools/naming_probe.py`), not by a scan.

**The acyclic N-nitro and N-nitroso cases this section first listed as open are D-164 and D-165, fixed in round 16 (the section above).**

## Open after naming round 13 (2026-09-24)

Round 13 started from a measurement, not a backlog: `tools/naming_census_scan.py` named all 2000 census rows and read each back, which found the
largest wrong-molecule cluster in the census (a wrong ring locant, 1.35%) and a second failure (an ownership error, 0.65%) that no backlog
had recorded, both old. The census went **93.45% -> 94.80% -> 95.70% exact** (W1, then W2); candidate wrong structures **2.40% -> 0.90%**;
embedded errors and refusals **1.90% -> 1.15%**.

**What a user sees, which round 12 got wrong.** The census classes are what the ENGINE emits. The application does not show an embedded
`[NAMING ERROR ...]` name, and it does not show a name whose OPSIN read-back is a different structure:
`naming_providers.derived_name_for_structure` withholds each, with its own stated reason (only a name OPSIN cannot READ is shown, marked
unverified). Every one of this round's 27 + 13 starting rows was WITHHELD (`benchmarks/naming/stages/r13-baseline-reproductions.json`), so the
fixes turn "no name" into a right name; nothing wrong was being shown. Three tests pin each gate on real engine output
(`tests/test_naming_providers.py`, W3). The engine still emits the embedded string on purpose (D-133's target IS one); only the app withholds.

**Fixed this round:**

| item | D-row | mechanism | note |
|---|---|---|---|
| a wrong locant on a 1,3,4-oxa/thiadiazole (and 1,2,5-oxa/thiadiazole) substituent | D-145 (FIXED) | `_lowest_free_valence_numberings` ranked the lowest COMBINED heteroatom locant set ahead of the senior heteroatom at locant 1. A monocyclic hetero ring is numbered by Hantzsch-Widman (senior heteroatom = 1). 1,3,4-thiadiazole (S1,N3,N4) has the alternative N1,N2,S4 with the lower set {1,2,4}, so the substituent was numbered as another heterocycle and its attachment carbon came out `-3-yl` | 21 census rows. Only a ring carrying its OWN second substituent reached this filter (the bare ring goes through `_heteroaryl_substituent_with_locant`, which weights seniority), which is why 4 of 25 such names were right. Fix: for a monocyclic ring the senior heteroatom's locant is ranked first; a fused ring keeps `together` first (its rule, P-25.3.1.3, ranks the combined set first) |
| a hard-coded curated locant returned for every attachment | D-146, D-147 (FIXED) | a ring with no `atom_locants` and a `substituent_form` ending in a digit (`2,3-dihydro-1,4-benzodioxin-2-yl`, `azepan-1-yl`) returned that form verbatim: the locant its author had in mind, for any attachment. The numbering computed just above the early return already knew the real one and was discarded | 6 census rows (benzodioxine). Fix: use the computed locant when it differs from the curated digit; when they agree the curated form stands. Benzodioxine is FUSED and the generic numbering mislabels positions 5 and 8, so it also gets an `atom_locants` table derived from its bond topology, as 1,3-benzodioxole's is |
| a data row keyed on the wrong ring | D-148 (FIXED) | the curated `1,2,5-oxadiazole` row was keyed on `c1conn1`, which is 1,2,3-oxadiazole, so 1,2,3-oxadiazole was named "1,2,5-oxadiazole" and real furazan reached another route and came out `furazan`. The vendored suite had pinned the wrong pair | key corrected to `c1cnon1`; parent and substituent are the systematic `1,2,5-oxadiazole`, which BlueBookV2.pdf p. 263 gives as "1,2,5-oxadiazole (formerly called furazan)" |
| a demoted ketone claimed its aryl carbon | D-149, D-150 (FIXED) | `_compute_prefix_assignments` Pass 1 built the `oxo` prefix of a DEMOTED ketone (anchor already in the parent) from every off-parent atom of the group and dropped only heteroatom context. A ketone matches its two flanking carbons as context; the one off the chain (an aryl or cycloalkyl ipso carbon) was claimed by the `oxo` AND by the `phenyl` the structural pass carved. The ownership invariant (`ownership.py`) was RIGHT and the claim was wrong: the pass above computes it consistently (heteroatoms and the anchor only, into `fg_prefix_atoms`) and Pass 1 read it inconsistently | LOUD half: 13 census rows (0.65%) embedded an error. SILENT half, which no read-back sees: the same double claim killed the plan that named an acid or amide as the parent, and the engine fell to a ketone-parent plan: 4-oxo-4-phenylbutanoic acid was `3-carboxy-1-phenylpropan-1-one`, 4-oxo-4-phenylbutanamide `4-amino-4-oxo-1-phenylbutan-1-one`. Fix: drop a non-anchor carbon still in `remaining` when the anchor is in the parent and the group is suffix-eligible. The ownership check is untouched |

**How the diagnoses were reached, because the hypotheses in the plan were all wrong.** The plan named three suspects for W1 (an index-space
mismatch between the carved fragment and the ring, atom-map loss on canonical renumbering, and the `min()` over symmetric matches). A
per-attachment trace (a spy on `_lowest_free_valence_numberings` and on `render_free_valence_suffix`) refuted all three: the fragment's atom
map was intact, and the filter selected among 10 candidate numberings correctly BY ITS OWN KEY. The key was the defect. Two things made that
findable: the sweep had already separated the rings by table state (all 295 table-backed rings swept at 0 wrong of 5,681 cases, so the defect
was not in the tables), and a spy on `_name_bound` showed the carved ring fragment reaching the substituent path with its own methyl still
inside it, which is what sent the trace to the numbering filter and not the locant lookup. A generic "the fragment lost its context" reading
(round 12's seam) would have been plausible and wrong here.

**The ring-locant sweep** (`tools/naming_ring_locant_sweep.py`; 371 curated rings, 7,372 cases; the population is committed and hashed before any
result). Table state, by the correct definition (every attachable site has a locant): before the fixes 295 full, 6 partial, 70 table-less. The
earlier "104 partial tables" was mostly fusion atoms, which legitimately carry no substituent locant, and is not a defect count.

| | rings | tested | rings with wrong | wrong / cases | engine errors |
|---|---|---|---|---|---|
| table-less, before | 70 | 66 | 23 | 712 / 1578 | 15 |
| table-less, after | 69 | 65 | 15 | 682 / 1558 | 15 |
| partial | 6 | 6 | 4 | 13 / 113 | 6 |
| full (table-backed) | 295 -> 296 | 292 -> 293 | 0 | 0 / 5,681 -> 5,701 | 0 |

The oracle is STRUCTURAL: numbering preference is not independently adjudicated for any table-less ring. Sweep runtime 939 s (naming 889 s);
a rerun under load took 1,328 s. Skipped, never swept: 906 fusion atoms, 651 heteroatom sites, 78 no-free-hydrogen atoms, 73 exocyclic atoms.

**Open, from the sweep (measured, not fixed):**
- **All-carbon table-less fused rings named with a bare `-yl`** (nonacene, octacene, heptacene, the phenes, the helicenes): 11 rings, 638 of the
  682 remaining wrong cases; the fallback returns no locant for a carbocycle ("Benzene -> phenyl"), which is wrong for a fused ring with
  non-equivalent positions. No census row (drug-like molecules do not contain them). A generic fusion numbering is not something topology
  alone gives; the honest fix is a table or a real fusion-numbering routine.
- **Partly hydrogenated fused rings on the generic numbering path** (octahydropyridazino[1,2-a][1,2]diazepine 28/34, corrin 10/33,
  hexahydrothieno[3,4-d]imidazole 3/8, octahydro-1H-indole 3/18, three partial-table polycycles): 7 rings, 0 census rows except
  `[1,2,4]triazolo[3,4-b][1,3]benzothiazole` (a partial table, 1 of 15 cases wrong), which appears twice in the census.
- **The ring-cation family is not explained by the locant tables.** The neutral parents of the failing cations (imidazo[1,2-a]pyridine,
  imidazo[2,1-b]thiazole, quinolizidine) all sweep at 0 wrong; the cation form fails with "no valid naming plan". It is a separate mechanism
  (the cation layer of a fused system), now **14 census rows (0.70%)** across about ten ring systems: the largest remaining cluster, still
  not measured as ONE mechanism. Round 14's first question. (The census has 19 "no valid plan" rows in all; the other 5 are not cations: two
  spiro-oxindole pyrano-pyrazoles, a bis-sulfonyl piperazine and two fused tricycles, each a different shape.)

**Open, found by exposing it (D-151, OPEN):** an ESTER of an acid that also carries a ring-nitrogen sulfonamide is named as a functional-class
ester of the PIPERIDINE, whose "acid" is a `carboxy` prefix (`ethyl 1-(4-carboxyphenylsulfonyl)piperidine` for the ethyl ester of
4-(piperidin-1-ylsulfonyl)benzoic acid): the ester group is attached to a name that is not an acid. A wrong structure. It was already there for
the plain methyl and ethyl esters; W2 only stopped it being masked for the phenacyl ester, which used to die earlier on an ownership error, so
one census row (`census999625`) moved from an embedded error to this wrong structure (both are withheld by the app). The N,N-dimethylsulfonamide
of the same acid is named correctly, so the ring nitrogen is the trigger. Before W2 the census had 4 rows with an "ester on a non-acid parent" name; W2's silent-half
fix repaired three of them (methyl 4-(4-methoxyphenyl)-4-oxobutanamido-benzoate and two others: an ester whose acid was a ketone-parent `carboxy`
prefix), leaving **2 rows (0.1%, under the 0.5% floor)**, both a ring-nitrogen sulfonamide beside the ester. Target (derived, read back MATCH):
`ethyl 4-(piperidine-1-sulfonyl)benzoate`.

**Early-return audit** (every exit of the code this round added, and what pins it):

| change | exit | reachable | owner after the exit | pinned by |
|---|---|---|---|---|
| D-145, `hetero_key` | ring is not monocyclic, or has no heteroatom | yes: every fused ring | `together` first, as before | `test_the_ring_locant_changes_do_not_move_a_right_name` (benzothiazole, 2,1,3-benzoxadiazole) |
| D-145, `hetero_key` | monocyclic, one heteroatom element | yes: thiazole, pyridine | the senior locant is then the only heteroatom's, so the order is unchanged | 1,3-thiazole, pyrimidine converses |
| D-146, computed locant | `_fixed` is None (the form has no trailing `-N-yl`) | rare | the curated form returned, as before | (pre-existing) |
| D-146, computed locant | computed locant == curated digit | yes: azepan-1-yl on the nitrogen | the curated form stands | `O=C(C)N1CCCCCC1`, the diazepane amide |
| D-149, Pass 1 | group not suffix-eligible, or anchor not in the parent | yes: halogens, nitro, a demoted multi-acid | unchanged | amine, aldehyde, amide, substituent-ketone converses |
| D-149, Pass 1 | the context carbon is the anchor, or is not in `remaining` | yes: a methyl ketone in the chain | unchanged | `OC(=O)c1ccc(OCC(C)=O)cc1`, `OC(=O)CCC(=O)CC` |

**Frozen set, blind.** `--frozen-impact r12-final-evaluation` reported `heldout_v6` 1 of 40 and `bluebook_frozen` 1 of 1126 changed. With the
W1-only engine both are 0, so every frozen row that moved is W2's. The frozen set was then scored once (see `BENCHMARK_HISTORY.md`).

**Tooling added this round:** `tools/naming_census_scan.py` (PR #144, before the round) and `tools/naming_ring_locant_sweep.py`. A ref-compare
manifest records the one tuning row W2 moved, an isouronium cation, as STRUCTURALLY_EQUIVALENT (both names read back MATCH; the preferred
name is explicitly not adjudicated, PubChem's `uronium` being a third form).

**Not attempted, carried forward unchanged:** see "Open after naming round 11" (multiparent fusion, second-order attached components, interior
heteroatoms, 7/8-membered rings fused on three or more sides, helicenes as PARENTS, hydro forms of a traditionally numbered retained parent,
chiral amino-acid anion names, deprotonated phosphonic/phosphoric esters).

## Open after naming round 12 (2026-09-23)

Round 12 was deliberately small: one fully diagnosed item (W1) and one census signal that had never been
triaged (W2). Round 11's deferred item is fixed; the fused-cation signal was measured and **not admitted**,
because no single mechanism reaches the admission floor.

**Fixed this round:**

| item | D-row | mechanism | note |
|---|---|---|---|
| charged acid group inside a substituent | D-144 (FIXED, moved from OPEN) | on the carved acid-anion route the OUTER plan already held the right typed fact (a `DetectedFG` with `prefix_form` `carboxylato`/`sulfonato`, from `_carved_acid_group_fgs`), but a group inside a substituent is named by a RECURSIVE call on the carved fragment, whose fresh `Perception()` cannot see a charged chalcogen as an FG, so it composed `oxido` + `oxo` atom by atom | `generate_plans` now adds the same typed FGs for a SUBSTITUENT-form fragment, from the fragment's own atoms (`_substituent_acid_anion_fgs`), for exactly the classes in `_ANIONIC_ACID_PREFIX`. `3-carboxy-4-(2-oxido-2-oxoethyl)benzoate` -> `3-carboxy-4-(carboxylatomethyl)benzoate`; `4-[(oxidosulfonyl)methyl]benzoate` -> `4-(sulfonatomethyl)benzoate` (P-65.6.2.3.1, pdf p. 619) |

**The seam, because it is more reusable than the fix.** The outer path computed the correct typed fact; the
recursive path discarded it by re-perceiving a fragment; each guard was correct in isolation and the
information was lost at the recursion boundary. The rule this suggests: *a recursive naming call inherits
explicit semantic context, and creates fresh perception only for genuinely new local facts.* Here no
context had to be threaded, because everything the fact depends on (the acid group and its attachment
carbon) is inside the fragment, so it is re-derived from the fragment with the SAME helper the outer path
uses rather than passed as a string. A future recursive path whose fact is NOT local to its fragment (a
parent's numbering, a charge balance across components) must inherit instead, and would need the outer
atoms mapped into the fragment's own indices.

**Early-return audit for the new path** (every exit, and what pins it):

| exit | condition | reachable on the carved path | owner after the exit | pinned by |
|---|---|---|---|---|
| `_substituent_acid_anion_fgs` | `mol is None` | no (callers pass a mol) | unchanged path | n/a |
| same | no charged site of a class in `_ANIONIC_ACID_PREFIX` | yes: a phosphonate/other class | the existing `oxido` composition (`DECLARED_UNSUPPORTED["phosphorus_oxoacid"]`) | `test_an_acid_class_with_no_anionic_prefix_is_left_alone` |
| same | the synthesised FG contains an attachment atom (the group IS the substituent) | yes: `[S-]c1ccccc1C(=O)[O-]` | the single-FG path; adding a second FG double-owned the atom | D-121u and `test_a_group_that_is_the_whole_substituent_is_not_touched` |
| `_carved_acid_group_fgs` | `neutral_view` is None / Perception raises | rare | the fragment declines visibly, as on the outer path | (pre-existing) |
| `generate_plans` hook | `output_form != SUBSTITUENT` | yes: STANDALONE / ANION | the ANION-mode synthesis, unchanged | the whole known-defects table |

**Measured impact** (each number is a command in `BENCHMARK_HISTORY.md`): ref-compare over 1712 rows
(r7, r8, mc and the tuning populations) **0 changed, 0 violations**, meaning no corpus row has this shape,
which is why the fix has its own tests; of the 292 charged rows in the census sample **exactly 1 changes**, an
aminophosphonate zwitterion (`{(2R,4E)-6-[dioxido(oxo)phosphanyl]-1-oxido-1-oxohex-4-en-2-yl}azanium` ->
`{(1R,3E)-1-carboxylato-5-[dioxido(oxo)phosphanyl]pent-3-en-1-yl}azanium`, reads back MATCH). That row is
on a route OTHER than the carved one, so the fix is broader than its gate wording: it is a property of the
fragment, which keeps it cache-safe. The blind frozen-impact check (new this round, below) found **1 of 1126
`bluebook_frozen` rows and 0 of 40 `heldout_v6` rows changed**; with the base engine swapped in it reports 0, so
the one row is W1's.

**A tie-break this exposed and did not fix.** `[5-carboxy-2-(carboxylatomethyl)phenyl]acetate` and its
`4-carboxy` twin are the same molecule; which one the engine emits depends on the SMILES atom order (the app names
the RDKit canonical spelling, and the D-144 multi-site test pins that spelling). Both read back; neither is
the book's, since the book prints no row for this exact structure. Not a D-144 defect.

**W2: the fused-aromatic-ring-cation signal, triaged** (36 hits, 36 unique row identities, 36 unique canonical
structures; the query is a coarse ring-fusion PROXY, so 36/2000 = 1.8% is never quoted as a defect frequency).
Every hit was named with the engine and read back; the engine was then run over ALL 292 charged rows of the
sample, because the proxy can miss a shape. 28 of the 36 name and read back MATCH; 8 embed a
`[NAMING ERROR ...]` marker (three of those eight report `clean` from `naming_probe.py`'s plan counters, because
the error is emitted as a NAME, not as a dead plan, so a status counter under-reports it and the name itself
has to be read). The failures are all
visible in the ENGINE's output (an embedded `[NAMING ERROR: No valid naming plan found for <fragment>]`), and the
application does not show such a name: `naming_providers.derived_name_for_structure` withholds any name containing
`NAMING ERROR`, and any name whose OPSIN read-back is a different structure, with a stated reason (corrected in naming
round 13; this paragraph used to say the app shows the name as unverified, which was wrong -- only a name OPSIN
cannot READ is shown unverified). None is a wrong molecule, and they fall into several ring systems, not one:

| ring system of the failing fragment | unique structures | fails standalone too | neutral parent names |
|---|---|---|---|
| imidazo[1,2-a]pyridin-4-ium (bridgehead `[n+]`, ring `[nH]`) | 4 | yes | yes (`imidazo[1,2-a]pyridine`) |
| imidazo[2,1-b][1,3]thiazol-4-ium | 1 | yes | yes |
| imidazo[2,1-f]purinium | 2 | yes | not measured |
| purin-7-ium named as a SUBSTITUENT | 1 | **no** (standalone is fine) | yes |
| saturated/bridged ring N cations (quinolizidinium, thieno[2,3-c]pyridinium, an imidazo-azepine amidinium, a triazolo-triazinium, a pyrano-pyridinium, a spiro-oxindole pyrrolidine) | 6 (each its own ring system) | yes | yes (`quinolizidine` measured) |

The layer is the same for the first three rows (the neutral parent names, the cation of it does not, one plan
executes and none is valid: a fused CATION with no curated entry, exactly round 8's open row), but the rings are
different, each would need its own curated numbering, and the largest single system is **4/2000 = 0.2%**, under
the 10-structure floor (0.5%). Outside the proxy, the charged-row scan also found two rows that are NOT this
mechanism: a 3'-azido nucleoside phosphate triester (`atom ownership under parent 'ethane'`, no cation) and a
steroid carboxylate that the refusal guard correctly RAISES on (`render_failed`). **Decision: recorded, not
admitted.** Nothing here becomes round 12 work; the bridgehead-`[n+]` cation family is the round-13 candidate
if a population ever shows it above the floor.

**A tooling gap closed.** `naming_stage_artifact.py --frozen-impact <sealed stage>` names the frozen
populations with the working tree and compares against a sealed final evaluation, printing ONLY
`unchanged` or `changed_count=N of M` (no label, no name, exit status 3 if anything moved). Ref-compare reaches
the tuning populations only, so it could never say whether a shared-path change moved a frozen row; rounds 10 and
11 decided by hand. If the check reports unchanged, the previous evaluation's score stands and the frozen set is
NOT re-scored.

**Not attempted, carried forward unchanged:** see "Open after naming round 11" (multiparent fusion, second-order
attached components, interior heteroatoms, 7/8-membered rings fused on three or more sides, helicenes, hydro
forms of a traditionally numbered retained parent, chiral amino-acid anion names, deprotonated phosphonic/
phosphoric esters).

## Open after naming round 11 (2026-09-23)

Round 11 re-verified every round-10 census winner and round 7-8 backlog row it touched directly against
the current engine BEFORE admitting or dropping anything -- round 9's own lesson (three of its eight seed
hypotheses were ruled out by live testing) held again here: two of the five candidates this round looked at
turned out to already be fixed, one narrower than assumed, as side effects of other rounds' general
improvements, never reflected back into this document until now.

**Fixed this round** (each own commit; see the commit messages for the full diagnosis):

| item | D-row | mechanism | note |
|---|---|---|---|
| ketone-parent enclosure | D-143 (FIXED) | `assembly.py`'s `_assemble_substitutive` had two existing one-carbon-parent P-16.5.1.3.1 enclosure rules (a heteroatom-center mononuclear parent; a SUBSTITUENT-form compound prefix) but neither reached a one-carbon KETONE parent in STANDALONE form | mirrored the existing heteroatom-center block, scoped to `suffix_groups` base_form `"one"`. Severity C (OPSIN parses the unbracketed form too); the single most common open shape in the backlog, 8.4% of the census |
| carbamimidoyl N'/N,N split | D-091v (FIXED, moved from OPEN) | the existing "N'-substituted carbamimidoyl" special case (`engine.py`) required the amino N to be a bare, unsubstituted NH2, so a substituted amino N fell through to the generic recursive path | generalized to carve 0/1/2 substituents off the amino N too, gated to require the imino N ALSO substituted (an amino-only-substituted, imino-bare fragment is deliberately left on the generic path -- measured live it is APPEARS_AMBIGUOUS to OPSIN when attached to a GUANIDINIUM parent, the exact shape D-103a/c's metformin-cation fixture already avoids on purpose; a first version without this gate regressed both, caught before commit) |

**Re-verified and found ALREADY CORRECT, no fix needed** (a legitimate round-9-style finding, not a shortfall):

| item | what round 10's census found | re-test result |
|---|---|---|
| ring-nitrogen acyl prefix on a ring/chain parent | `ring_nitrogen_acyl_on_chain`, 2.65% of the census; round 8's own documented repro (`OC(=O)c1ccc(cc1)C(=O)N1CCCCC1` -> wrong `4-[(oxo)(piperidin-1-yl)methyl]benzoic acid`) | now emits the correct `4-(piperidine-1-carbonyl)benzoic acid` directly, verified for piperidine, morpholine and pyrrolidine variants. Fixed as a side effect of other rounds' serialization work, never reflected back into this document. The remaining STANDALONE case with no other senior group (`CCC(=O)N1CCCCC1` -> `1-(piperidin-1-yl)propan-1-one`) round-trips correctly too and has no printed target in this document to hold it to a different form -- not a documented defect |
| polyacid-anion charge ledger | round 7's own two findings: citrate's trianion named as a wrong-molecule pentanedioate, and the biguanidium dication misnamed as a monocation | citrate's trianion (`[O-]C(=O)CC(O)(CC([O-])=O)C([O-])=O`) now emits the printed PIN, `2-hydroxypropane-1,2,3-tricarboxylate`, verified bare and as the trisodium salt. The biguanidium dication now correctly RAISES (`partial_claim`) instead of silently naming the wrong molecule -- the same refusal-guard class as D-133, converting a would-be wrong structure into a visible, honest failure. Both fixed as side effects of rounds 9/10's own charge-perception work |

**Re-verified, found NARROWER but still genuinely open, re-deferred with a deeper diagnosis than before:**

| item | seed layer | what is known now |
|---|---|---|
| charged acid group inside a substituent | serialization | **FIXED in naming round 12 (D-144); see "Open after naming round 12". The diagnosis below stands, and its second proposed repair (thread the FG in) was replaced by re-deriving the fact from the fragment's own atoms.** Round 8's own row is about a charged acid group *inside a carved substituent tree*, not "any charged acid substituent present" (the general shape round 9's F1 ruled out) -- and it is STILL broken, confirmed on the exact repro. Traced to root cause: `_carved_acid_group_fgs` (`engine.py`) already computes the CORRECT anionic prefix form (`"carboxylato"`, `"sulfonato"`) for a demoted acid-anion site on the "carved" route (`acid_anion_route(mol) == "carved"`), but that `prefix_form` is never threaded into the RECURSIVE substituent-naming call that renders a nested acid-anion group -- the carved fragment's own fresh `Perception()` call does not detect a charged chalcogen as an FG at all (by design, elsewhere), so it falls back to generic atom-by-atom composition (`oxido` + `oxo`/`sulfonyl`), regardless of what the outer call already knew. **This is broader than round 8's row documented**: measured live, it affects a demoted CARBOXYLATE the same way as a demoted SULFONATE (`3-carboxy-4-(carboxylatomethyl)benzoate` reproduces the exact `"3-carboxy-4-(2-oxido-2-oxoethyl)benzoate"` wrong form round 8 recorded only for sulfonate) -- the earlier "already correct" carboxylate spot-check this round ran first (`4-(carboxylatomethyl)benzoate`) turned out to go through a DIFFERENT mechanism entirely (the homogeneous classifier route's blunt string-level `_balance_the_charge_ledger` regex, which only fires when every deprotonated site is the SAME acid class), not the carved route this row is actually about. A real fix needs either threading the outer FG's `prefix_form` into the recursive call, or a second, gated regex-style repair mirroring `_balance_the_charge_ledger` but keyed to the "carved" route's own known FG list -- deliberately not rushed this round given the architectural reach (touches the same recursive substituent-naming path several other special cases, including this round's own carbamimidoyl fix, already sit beside) |

**Census extension B (discovery only, B3 reused; no fix attempted for anything below):**

| shape | frequency | clears 0.5%? | source |
|---|---|---|---|
| fused aromatic ring cation | 36/2000 = 1.8% | YES, 3.6x, but coarse proxy -- needs manual ring-table triage before it says anything about the real defect | round 8 open list |
| N-alkoxy amide / O-alkylhydroxylamine family | 5/2000 = 0.25% | no | round 8 open list |
| polynitrate ester | 0/2000 | no | round 8 open list |
| condensed guanidine/urea, n>=5, substituted | 0/2000 | no | round 8 open list |
| betaine cationic prefix | 0/2000 | no | round 7 open list |
| zwitterion with a second-class anion | 0/2000 | no | round 7 open list |

Five of the six new queries measured genuinely rare (<=0.25%, several 0 hits) -- real evidence that most of the
remaining round 7-8 backlog's exotic shapes are uncommon, not just unmeasured. The one that clears the floor
(fused-ring cations) needs triage work before it is actionable, not a fix directly.

**Not attempted, needs a new subsystem** (carried forward, unchanged -- listed here in one place so a future
round does not re-discover the shape of this work from scratch): multiparent fusion systems (round 5's open
list; round 10's own census measured this at 1.15%, `multiparent_fusion_hub`), second-order attached fusion
components, interior heteroatoms (P-25.3.3.2), 7/8-membered rings fused on three or more sides, rings of more
than eight members and helicenes, hydro forms of a traditionally numbered retained parent, chiral amino-acid
anion names (needs a stereo policy decision first), deprotonated phosphonic/phosphoric acid esters (declared
unsupported scope). None of these are close to a bounded, narrowly-scoped fix the way this round's items were.

## Open after naming round 10 (2026-09-22)

Round 10 closed all 4 items round 9 deferred (each already diagnosed at round 9's end), then ran a cheap,
discovery-only extension of round 9's B3 frequency census against 6 of the still-open round 5-8 backlog
shapes -- reusing the frozen `census_sample.json` unchanged, no new battery. All 4 fixes are genuinely
verified (OPSIN round-trip as a structure oracle, mutation-checked, ref-compared against the whole
`bluebook_tuning` population with 0 unexpected changes).

**Fixed this round** (each own commit; see the commit messages for the full diagnosis):

| item | D-row | mechanism | note |
|---|---|---|---|
| phenothiazine-dye-locant | D-139/D-140 (FIXED) | `ring_naming/retained_lookup.py`'s `_build_numbering_from_atom_locants` gated its bond-generic substructure-match fallback to "every ring atom aromatic", excluding phenothiazine's N/S bridge (non-aromatic on the isolated curated-key SMILES, but aromatic in methylene blue's actual extended-conjugation form) | round 9's own diagnosis was incomplete: two OTHER curated numbering tables (`fusion_general.py`'s `_TRADITIONAL`, `data_loader.py`'s `_RING_CURATED_SMILES`) were already correct and NOT the bug; the real defect was a third function's aromaticity gate. Fixed by narrowing the gate to "every CARBON aromatic" (heteroatom aromaticity is context-dependent; a ring carbon's is structural). Phenoxazine shares the identical defect and fix, proven by direct testing, not assumed |
| spiro-xanthene-dye-locant | D-141 (FIXED) | xanthene/thioxanthene's curated `atom_locants` covered only 9 of 14 real ring positions (missing the four fusion carbons and the bridge heteroatom's own locant), which is harmless for a bare/substituted parent but broke `spiro.py`'s combined-numbering completeness gate for fluorescein | fixed by completing the table with the four fusion positions (4a, 8a, 9a, 10a) and the bridge heteroatom's locant (10), derived from this table's own bond topology against `fusion_general.py`'s already-verified real xanthene numbering. Reaches fluorescein's real IUPAC name exactly, including a second latent defect (wrong lactone locant) fixed as a side effect |
| charge-polycarbocation | none (no PIN attempted) | `_classify_polycarbon_charge`'s guard checked the WHOLE MOLECULE for any aromatic atom / non-single bond, rather than the charged atoms' own scope, silently excluding a saturated cation substituent attached to an aromatic ring | narrowed the gate to the charged atoms specifically; the classifier now engages and claims both charges, but no renderer exists yet to compose a name for two independently-attached cationic substituents on a shared aromatic parent. Per the project's own "refusal guard" (below), a classifier that engages and cannot finish now RAISES instead of falling through to the wrong neutral name -- the WRONG-MOLECULE defect is fixed (same outcome class as D-133); reaching the PIN itself (PubChem's own name is on file: "2,2'-(1,3-phenylene)di(propan-2-ylium)", `bb-db0d904b9c97`) is separate, still-open render-side work |
| carbamimidate-oxime-swap | D-142 (FIXED) | no existing enclosure rule covered a carbon-centered one-carbon STANDALONE parent with a non-leading "-oxy" prefix; the engine's internal structure was correct, but the unbracketed output string let OPSIN misparse "(hydrazinyl)methoxy" as one nested substituent | fixed by bracketing a non-leading "-oxy" simple prefix on any one-carbon chain parent, any output form. Round 8's own ketone-parent check missed this shape (tested with "phenyl", no adjacency ambiguity; a ketone+oxy case sidesteps it via an ester/carbamate route an imine lacks). A second, independent instance of the same bug (methanamine, not methanimine) was found and fixed as a side effect |

**Census extension (discovery only, B3 reused; no fix attempted for anything below):**

| shape | frequency | clears 0.5%? | source |
|---|---|---|---|
| ring-nitrogen acyl on a chain parent | 53/2000 = 2.65% | YES, 5.3x | round 8 open list |
| multiparent fusion hub | 23/2000 = 1.15% | YES, 2.3x | round 5 open list |
| a(ba)n Si-NH-Si chain | 0/2000 | no | round 5/6 open list, D-089u |
| symmetric 1,2-diketone (benzil) | 0/2000 | no | round 8 open list |
| diacyl peroxide | 0/2000 | no | round 8 open list |
| xanthate ester | 0/2000 | no | round 8 open list |

The two that clear the threshold are strong candidates for a future round's admissions ledger; they are
recorded here, not fixed. This measured only 6 of the many still-open shapes below (round 6-8's own carried-
forward lists) -- a low count on the 4 that didn't clear says those specific shapes are rare, not that the
overall backlog is short.

## Open after naming round 9 (2026-09-22)

Round 9 ran a source-backed battery first (a Blue Book PDF harvest, `bluebook_tuning.json`/`bluebook_frozen.json`, plus an
ordinary-compound battery, `battery_r9.toml`, 306 rows) and a frequency census, then admitted 13 findings from that instrument
stage into a hash-frozen ledger (`benchmarks/naming/admissions_r9.toml`), enforced by `tests/test_admissions_r9.py` on item
count and set-immutability, never on a fixed slot number ("never do those hardcoded guards again" -- Alex, 2026-09-22; the
guard checks structure, not a literal). **9 of the 13 admitted items are fixed this round; 4 are deferred, each with the
mechanism already diagnosed.** Evidence: D-130 to D-138 in `tests/test_namer_known_defects.py`, the stage artifacts
`benchmarks/naming/stages/r9-*.json`, and per-commit ref-compares against the whole Blue Book tuning population (1129 rows)
-- every fixed item's stage comparison showed 0 structural regressions and changed only its own admitted rows.

**Fixed this round** (each own commit; see the commit messages for the full diagnosis):

| item | D-row | mechanism | note |
|---|---|---|---|
| carbodiimide | D-130 (PARTLY: wrong molecule fixed, PIN open) | `_linker_has_imine` (multiplicative.py) declines a C=N linker the same way `_linker_has_carbonyl` already declines a ketone one | DCC no longer names as a saturated bis-amine; reaching "dicyclohexylmethanediimine" (P-62.3.1.4) needs imine FG perception, empty in every context tried |
| carbamimidoyl-locant | D-131 (FIXED) | `_role_primes` (engine.py) orders same-position PCG instances by anchor atom index instead of role alone | two carboximidamide groups at one ring position no longer collide onto the same N/N' pair |
| naphthalene-ring-drop | D-132 (FIXED, no PIN claimed) | `_fused_ring_count` (multiplicative.py) declines a linker whose skeleton spans more than one SSSR ring | `_divalent_linker`'s shortest-path walk crossed a fused ring's ortho bond and silently dropped the OTHER ring; falls back to substitutive naming that keeps every atom |
| sulfinyl-bromide | D-133 (FIXED: wrong molecule -> honest PARSER_FAILED) | `_sulfonyl_sulfinyl_has_single_substituent` (engine.py) declines the `{R}sulfonyl` shortcut when S carries more than one non-oxo substituent | no route exists yet to NAME a sulfinimidoyl/sulfonimidoyl halide; declining beats silently dropping the bromine and the S=N bond |
| phosphine-oxide-trihydrazide | D-134 (FIXED, no PIN claimed) | `_linker_has_phosphine_oxide` (multiplicative.py) mirrors the carbonyl/imine checks for P=O | a P(V) phosphine oxide no longer loses its oxidation state to "phosphanetriyl" |
| peptide-acyl-naming | D-135 (FIXED, target P-103.3.2) | new module `perception/fg/peptide_acyl.py`: a closed, stereo-matched table of the 20 proteinogenic amino acids | reaches the book's own worked example ("glycine + alanine -> glycylalanine"); 14/20 of B2's dipeptide battery now use the retained form, the other 6 all involve threonine or isoleucine whose battery SMILES under-specify a second stereocentre (correctly declined, not a bug) |
| charge-alkynyl-dianion | D-136 (FIXED, no PIN claimed) | `_classify_alkynyl_anion` (charge_perception.py) extended for the symmetric `[C-]#[C-]` case | ethynediide no longer drops both charges to plain ethyne |
| charge-phosphide-anion | D-137 (FIXED, target P-73) | new `_classify_phosphide_anion` / `_render_phosphide_anion`, gated to RING phosphorus only | reaches the printed PIN; the ring gate exists because an acyclic phosphide (`C[P-]C`, "dimethylphosphanide") was already named correctly through a different route, and a first version of this classifier regressed it -- caught by the stage comparison before the commit, see D-137's test for the pinned converse |
| charge-imine-anion | D-138 (FIXED, no PIN claimed) | new `_classify_imine_anion` / `_render_imine_anion` mirror the amine-anion pair exactly, plus a new `("imine", ANION): "iminide"` suffix-variant entry | butaniminide no longer drops its charge to neutral 1-iminobutane |

**Deferred to round 10, each already diagnosed** (no slot escapes the frozen ledger; these are recorded, not re-opened as new
findings):

| item | seed layer | what is known |
|---|---|---|
| carbamimidate-oxime-swap | candidate generation | root cause fully understood -- a prefix-bracketing ambiguity in how "(hydrazinyl)" and "methoxy" concatenate without a locant, reproduced in the minimal case `COC(=N)NN` -- but the fix touches widely-used prefix-assembly logic with real regression risk across every substituent name in the engine. Deliberately not rushed |
| phenothiazine-dye-locant | serialization | methylene blue's phenothiazine core numbers to locant 12, which OPSIN rejects outright ("Cannot find in scope fragment with atom with locant 12") -- phenothiazine's standard numbering (S at 5, N at 10) is registered in `ring_naming/fusion_general.py`'s `POLYCYCLES` for automorphism matching but has NO entry in `_TRADITIONAL` (the atom-mapped-SMILES override table that anthracene, acridine, carbazole, xanthene and their analogues already have), so the general fusion-rule numbering algorithm computes the wrong labels. The fix is an entry in `_TRADITIONAL` with a verified atom-mapped SMILES (S at label "5", N at label "10", matching the anthracene-analogue pattern already used for xanthene/acridine/thioxanthene); not yet built or verified against OPSIN |
| spiro-xanthene-dye-locant | serialization | fluorescein's own xanthene component IS correctly registered in `_TRADITIONAL` (unlike phenothiazine), so this is a DIFFERENT defect: locant 13 (out of xanthene's own valid 1-9 range) appears when the ring is combined with its spiro partner (`1,3-dihydro-2-benzofuran`) in `spiro.py`'s numbering, not a missing table entry. Root cause not yet isolated |
| charge-polycarbocation | charge_ledger | a benzene ring bearing two independent tertiary-carbocation substituents (`c1cc(cc(c1)[C+](C)C)[C+](C)C`, target "2,2'-(1,3-phenylene)di(propan-2-ylium)") needs the multiplicative machinery and the charge-perception machinery to work TOGETHER -- neither alone reaches it. `_classify_simple_carbon_charge`'s `len(charged_carbons) != 1` gate is the immediate block, but simply relaxing it does not compose a correct dual-cation name (two independently-rendered substituent fragments, not one multiplicative construction); the correct architecture is not yet designed |

**Admission rule note, for the next round that reads this ledger.** A wrong molecule outranks frequency for a slot but does
NOT escape the cap, and Alex chose (2026-09-22) to admit all 13 confirmed findings rather than defer 5 to round 10 for the
sake of the plan's original 8-slot estimate -- "I don't think 10 is too much of a creep... whatever is the most comprehensive
and complete." The instruments stage also RULED OUT three of the original eight seed hypotheses by live testing (F1 charged
acid substituent, F5 ketone-parent enclosure, F6 N,N-guanidinium all name correctly already) -- a hypothesis written before
measurement is not thereby true, and that is what the instruments stage is for.

## Open after naming round 8 (2026-09-21)

Round 8 fixed the polyacid parent choice (citrate and its class), the isothiourea wrong molecule and the enclosure rule behind it, condensed guanidines and ureas
(n = 2, 3 and >= 5), protonated azoles and the cation classes around them, imide and acyl hydrazide parents, pseudoketones, and then, in a limitations pass, the defects
below that its own probing found. Its evidence is `tests/test_namer_known_defects.py` (D-100 to D-128), the stage artifacts `benchmarks/naming/stages/r8-*.json`, and the
expected-change manifests beside them. What is left, by layer.

**Found by probing common compounds, not by any corpus.** Six of the pass's fixes had NO corpus row containing them: `prop-2-eneamide` for acrylamide (D-120), `methyl acetylmethylazinite`
for the Weinreb amide (D-125), `3-oxobutan-2-one` for biacetyl (D-127), `dimethoxyoxomethane` for dimethyl carbonate (D-128), and the nitrate and mixed-polyanion names. The corpora
measure the engine on what they contain; a battery of ordinary molecules whose names one knows is a different instrument, and each round should run one.

| layer | case | emits | target | note |
|---|---|---|---|---|
| candidate generation | a THIOLATE beside an acid anion: `[S-]c1ccccc1C(=O)[O-]` | `2-[oxido(oxo)methyl]benzene-1-thiolate` | `2-sulfanidobenzoate`-style (derived) | the carved route now takes an olate beside an acid anion (D-121); a thiolate's anionic prefix is not built. Round-trips |
| serialization | a charged acid group INSIDE a substituent (FIXED in round 12, D-144) | `4-[(oxidosulfonyl)methyl]benzoate`, `3-carboxy-4-(2-oxido-2-oxoethyl)benzoate` | `4-(sulfonatomethyl)benzoate`, `...(carboxylatomethyl)...` (pdf p. 619) | the recursive substituent path names a charged group with 'oxido'; the ledger's 'carboxylato' repair covers the classifier route only. Round-trips |
| candidate generation | an N-alkoxy THIOAMIDE, an N,N-dialkoxy amide, O-alkylhydroxylamines | `N-methoxy-N-methyl-1-thioxoethan-1-amine`, `1-(dimethoxyamino)-1-oxoethane`, `(aminooxy)methane` | `N-methoxy-N-methylethanethioamide`, ..., `O-methylhydroxylamine (PIN)` (pdf pp. 96, 753) | D-125 built the amide and amine; hydroxylamine is a retained parent the engine does not construct |
| candidate generation | several nitrate groups | `1,2,3-tris(nitrooxy)propane` | `propane-1,2,3-triyl trinitrate` | D-123 names ONE nitrate or nitrite ester; a polynitrate needs a multivalent organyl |
| candidate generation | carbonic acid halides and anhydrides: chloroformates, di-tert-butyl dicarbonate, mixed anhydrides | `methoxymethanoyl chloride`, a nine-part prefix name | `methyl carbonochloridate`, `bis(2-methylpropan-2-yl) dicarbonate` | D-128 names the acyclic diester and the hydrogen ester only |
| candidate generation | carbazate esters `CCOC(=O)NN` (D-088b) | `(ethoxycarbonyl)hydrazine` | `ethyl hydrazinecarboxylate` | the stale comment in `types.py` says the anion cannot be named; it can (`hydrazinecarboxylate`). The functional-class carbamate plan assembles `ethyl aminocarbamate`, so the fix is a carbazate assembly, not removing the refusal |
| serialization | peptide-like acyl prefixes | `acetamidoacetamidoacetic acid` (no enclosure), `[(2-amino-1-oxoethyl)amino]acetic acid` (glycyl) | enclosed amido prefixes; a glycyl form | both read back. The book's form for a retained amino acid's acyl is not settled in the pages read, so no target is claimed |
| serialization | the acyl prefix of a RING-nitrogen amide on a ring or a chain parent that is not itself the acid: `OC(=O)c1ccc(cc1)C(=O)N1CCCCC1` | `4-[(oxo)(piperidin-1-yl)methyl]benzoic acid` | `4-(piperidine-1-carbonyl)benzoic acid` (the prefix is printed, p. 667: `(piperidine-1-carbonyl)`) | the carbon-attached ring acyl works (`pyridine-4-carbonyl`); a formyl on a ring NITROGEN is named on the methane parent. A string rewrite cannot tell a ring `-1-yl` from `propan-2-yl` (isobutyryl), so it needs the tree. Round-trips; drug-like amides of piperidine, morpholine and pyrrolidine are this shape |
| serialization | a second prefix on a one-carbon ketone parent: `O=C(c1ccccc1)N1CCOCC1` | `(morpholin-4-yl)phenylmethanone` | `(morpholin-4-yl)(phenyl)methanone` | the book encloses the second and further substituents of a mononuclear parent (P-16.5.1.3.1); the ketone-parent assembly does not. Presentation only, reads back |
| candidate generation | condensed guanidines and ureas with n >= 5 AND substituents | not the bare-chain name (a guard, D-113) but no substituted name either | the skeletal-replacement name with substituent prefixes (P-66.4.1.2, p. 677) | W2 built the unsubstituted chain only; a substituted or tautomeric long chain is refused with an error the provider never shows |
| candidate generation | the imidazo[4,5-d]imidazole cation and other cations of a fused ring with no curated entry | named by the generic route or refused | a retained/fusion cation name | W3's ring carve finds the retained name where a curated ring exists; a fused cation with none has no name to find |
| numbering | curated HYDRO or BRIDGED ring entries with letter labels on atoms in three rings (`12a`/`12b`, `6a`, `13a` in three entries) | the labels as tabled | unknown | `tests/test_known_deviations.py` scans only the fully aromatic entries; in a cage an atom in three rings is a bridgehead, not an interior carbon, and the three were not classified |
| candidate generation | the r8 addendum panel's four remaining NON_PREFERRED rows and its one ENGINE_ERROR (`benchmarks/naming/charged_panel_r8.toml`) | `potassium sodium 2-(carboxymethyl)butanedioate`, `1,1-dimethylguanidinium`, `N,N,N-trimethyl-1-oxo-1-phenylmethanaminium`, `(phenylmethylidyne)azanium`; the biguanide DICATION `NC(=[NH2+])NC(N)=[NH2+]` is REFUSED (no name) | `potassium sodium hydrogen propane-1,2,3-tricarboxylate` (p. 619), `N,N-dimethylguanidinium` (p. 819), `N,N,N-trimethylbenzamidium`, `benzonitrilium` | all four round-trip. The hydrogen-salt method is a construction of its own; the guanidinium locant style `N,N-` and the retained amidinium/nitrilium cation names are not built. The dication is the W2 negative control (a dication name for a MONOcation was the wrong molecule; a true dication has no name yet, and the app withholds it) |
| serialization | benzil | `1,2-diphenylethane-1,2-dione` | `diphenylethanedione (PIN)` (p. 559) | the book omits the locants of a symmetrical ethane; the rule is not built |
| serialization | substituted carbamimidoyl (D-091v) | `4-[(dimethylamino)(ethylimino)methyl]benzoic acid` | `4-(N'-ethyl-N,N-dimethylcarbamimidoyl)benzoic acid` (p. 676) | a string-level rewrite like the carbamoyl one would need to split the N-substituents; not attempted |
| candidate generation | peroxide, sulfur, phosphorus and boron pseudoketones | oxo prefixes on the heteroatom | 'one' names | D-118 built the ring nitrogen, azo and silicon cases |
| candidate generation | diacyl peroxides, xanthate esters | `1-(acetylperoxy)-1-oxoethane`, `O-ethyl (methylsulfanyl)methanethioate` | `diacetyl peroxide`, `O-ethyl S-methyl carbonodithioate` | found by probing; not investigated |

**Not attempted, unchanged from round 5/6** (each keeps its row in "Open after naming round 5"): the remaining P-15.3 multiplicative constructions (D-088f, h, i, j), the silicon
rows (D-089s, u, v; D-090b), the hydrazide prefix spelling (D-088d, partly fixed), and fusion (D-086a to c).

**Carried over UNCHANGED from earlier sections and still open** (each keeps its row and its page there): chiral amino-acid anions (`alaninate`, ... need a stereo policy; "Open after naming round 7"), deprotonated phosphonic
and phosphoric acids (a DECLARED unsupported class), a betaine's cationic prefix (source unresolved), a compound acyl name on `azanide`, and, from round 5: second-order attached components, multiparent systems, interior
heteroatoms (P-25.3.3.2), 7/8-membered rings fused on three or more sides, rings of more than eight members and helicenes, hydro forms of a traditionally numbered retained parent, the P-44.1.2 senior-atom tier between two
rings, and OPSIN's unaudited ring vocabulary. **The one deliberate deviation from the book is now a registry:** `benchmarks/naming/known_deviations.toml` (pyrene 10b/10c, perylene 12c/12d, benz[de]isoquinoline 9b, against
the book's 3a1, 5a1, 6b1), reported as KNOWN_DEVIATION and never counted as a preferred match, guarded by `tests/test_known_deviations.py`.

**Decisions this round that a reader should not have to rediscover.** (1) A new round-trip verdict, `RoundTrip.TAUTOMER` (standard-InChI equal), is shown WITH a note and no longer withheld: PubChem's own metformin drawing was
getting the right PIN and no name, because the PIN reads back as the other tautomer. This amends a recorded decision (`docs/ARCHITECTURE.md`, dated 2026-09-21); it is one commit (`ee20f0a`) if it is to be reverted.
(2) The pseudoketone groups make the engine call a carbonyl on a ring or azo nitrogen a ketone (P-64.3.2) while the v2 vocabulary calls it an amide; declared in `ENGINE_DISAGREEMENTS`. (3) An acid, amide or aldehyde
beside such a group still outranks it (Table 4.1).

**Where round 9 should start.** (a) Run `python tools/naming_probe.py --file <battery>` on a battery of ordinary compounds BEFORE reading any corpus: it found six of this round's fixes and names each plan that failed to execute
(`--failures`), the silent fall-back that hid most of them. The 200-shape snapshot `tests/fixtures/naming_cation_shapes.txt` is the seed (it pins the neighbours of every class fixed here, and the open ones under their own comment).
(b) By likely frequency in drug-like molecules, the open rows above rank roughly: peptide acyl prefixes, a charged acid group inside a substituent, carbazates and chloroformates, then the P-15.3 multiplicative constructions.
(c) Every fix in this round followed one routine, and the routine is what made the numbers trustworthy: D-rows red first, converses that differ by reason, a mutation check with the equivalent mutants written into the code,
`tools/naming_ref_compare.py --base <sha> --manifest ...` BEFORE the commit and never chained to it, and the naming-consumer set (`tools/naming_consumers.py`) before the full gate.

**Checked and NOT a defect:** a carbonyl on a ring nitrogen is a 'ketone' to the naming engine (P-64.3.2) and an amide to the v2 vocabulary. The disagreement is declared in
`ENGINE_DISAGREEMENTS` beside the lactam, imide and urea ones, and the cross-check test found it (indometacin).

**Process notes worth keeping.** (1) A gate can crash for a reason that is not the change: the Windows shard crash (exit 139 in `conftest.dispose`) follows process lifetime, so the
app suite is run in chunks of 25 files with a retry, in a detached worktree. (2) A fix that only re-routes can name a DIANION as a monoanion: check the charge of every name a
new route produces (D-121's first version named `4-sulfobenzoate`). (3) A converse row is the cheapest regression test there is: three of this pass's own regressions
(`(3-amino-3-oxopropyl)tri(methyl)ammonium`, `(methoxyoxy)ethane`, `2-carboxy-N-methoxyacetamide`) were caught by a converse before they were committed.

## Open after naming round 7 (2026-09-20)

**Status after naming round 8 (2026-09-21):** the rows below for the citrate trianion, the biguanidium cation, protonated imidazole and benzimidazole, and the serinate zwitterion are FIXED (the rows of `tests/test_namer_known_defects.py` commented 'naming round 8, W1', 'W2' and 'W3', and D-121); the isothiourea wrong molecule found by the fresh set is fixed with the enclosure rule behind it (W5). What remains of this table is still true as written.

Round 7 fixed the acid-anion class (one decision function, `charge_perception.acid_anion_route`, both
routes ask it), a charge-conservation defect in the zwitterion route, and the retained names, salt
multiplier and amide-anion form the book prints. The panel that measures it is
`benchmarks/naming/charged_panel.toml` (108 rows, built by class, frozen), its baseline and adjudication
beside it. What is left, by layer, with what is known about each.

**The hole this round began with is closed, and its neighbours are declared, not silent:** a charged atom
is now either owned by exactly one route or carries a declared UNSUPPORTED with its reason
(`perception/charge_ownership.py`, `DECLARED_UNSUPPORTED`); `tests/test_charged_panel.py` pins the set of
unowned classes at empty.

| layer | case | emits | preferred / target | note |
|---|---|---|---|---|
| scope unsupported | deprotonated phosphonic and phosphoric acids | `hydroxy(oxido)(oxo)(phenyl)phosphane` | `hydrogen phenylphosphonate`, `phenyl hydrogen phosphate` (pdf p. 808) | the 'hydrogen' method for acid esters of inorganic acids is a construction of its own; structurally correct, not preferred; nothing in the corpora needs it |
| candidate generation | chiral amino-acid anions (`alaninate`, `prolinate`, `tyrosinate`, `cysteinate`, `glutamate`) | `2-aminopropanoate`, `pyrrolidine-2-carboxylate`, ... | `alaninate`, ... (P-103.2.4.2, pdf p. 1047) | OPSIN reads a bare `alaninate` as the L-isomer while P-103.1.3.1 designates configuration by D/L; a whole-molecule retained name needs a stereo policy first. Glycine (achiral) is done |
| retained parents | protonated imidazole: `c1c[nH]c[nH+]1` | `1,3-diazol-1-ium` | `1H-imidazol-3-ium` | the retained ring is found for a fully N-substituted cation and not when `[nH+]` sits beside `[nH]`; `_neutralize_ring_charged_n` reads correct on paper, so the fault is elsewhere in the ring-lookup chain. Abandoned under the round's stop rule after a short look |
| candidate generation, unplanned | protonated benzimidazole: `c1ccc2[nH]c[nH+]c2c1` | `NAMING ERROR: No valid naming plan found` | `1H-benzimidazol-3-ium` (derived) | a refusal rather than a wrong name; same family as the row above; found after the panel was frozen |
| source unresolved | a betaine's cationic prefix | `(trimethylazaniumyl)acetate` | `(N,N-dimethylmethanaminiumyl)acetate` (pdf pp. 362, 837) | both denote the same structure; the pages read do not say whether the azaniumyl form is also permitted |
| candidate generation, unplanned | a zwitterion with an anion of ANOTHER class: `[NH3+]C(C[O-])C([O-])=O` (serinate as drawn) | `2-azaniumyl-3-oxido-3-oxopropan-1-olate` | `2-azaniumyl-3-oxidopropanoate`-style (derived) | `acid_anion_route` returns None for two anion classes, so the carboxylate is not carved; round-trips, not preferred |
| serialization | compound acyl names on `azanide` | `chloroacetylazanide` | `(chloroacetyl)azanide` (derived enclosure) | the enclosure test looks for locant characters and misses a substituent without one; round-trips |
| numbering | pyrene and phenalene interior carbons | `10b`, `10c` | `3a1`, `5a1` (P-25.3.3.3.1, pdf p. 224) | DELIBERATE: the table uses the CAS locants because the round-trip oracle reads those and not the book's; switching would make correct names unverifiable and withheld or annotated in the app |
| candidate generation, unplanned, WRONG MOLECULE | the trianion of a tricarboxylic acid: citrate `[O-]C(=O)CC(O)(CC([O-])=O)C([O-])=O`, and its salts | `3-carboxy-3-hydroxypentanedioate` (`trisodium 3-carboxy-3-hydroxypentanedioate`) | `2-hydroxypropane-1,2,3-tricarboxylate` (from the printed PIN of the acid, P-65.1.1.2.3, pdf p. 578) | found by the driven salt-panel check AFTER the final evaluation, so no fix was made. Two layers: the NEUTRAL acid is named `3-carboxy-3-hydroxypentanedioic acid` (structurally right, not the printed PIN: the chain with two suffix groups beats propane with three), and the classifier route then converts only the suffix groups, leaving the `carboxy` prefix to read as a neutral COOH: two charges for three sites. The same shape gave a wrong name BEFORE the round (`1,5-dioxido-3-oxidooxomethyl-...`). The app's round-trip gate withholds it (`MISMATCH`), so the user sees PubChem's name. A sound fix is a charge ledger on the classifier route (every acid group there IS a deprotonated site, so an acid prefix in the name is a wrong charge) plus the neutral chain choice; the class panel had no three-acid row, which is why it was not found there |
| candidate generation, unplanned, WRONG MOLECULE | the biguanidium cation `CN(C)C(=N)NC(N)=[NH2+]` (metformin's cation, in `metformin pamoate`) | `N-[(dimethylamino)(imino)methyl]-1-iminomethanebis(aminium)` | not searched | a dication name for a monocation; `MISMATCH` before and after round 7 (not an anion, so out of the round's class); found by the same check and withheld by the same gate |

**The rest of the round-5/6 open list was NOT attempted this round**, and none of it was investigated beyond
reading its row, so no diagnosis is recorded for it. Each keeps its row above in "Open after naming round 5"
and its target and page there. In the order the plan named them: N'-acyl hydrazides and the substituted-hydrazide
prefix (D-088a, D-088d; round 4's attempt made a wrong molecule, so it needs its own layer trace), two acyl groups
on one N (D-091u), carbon with two double-bonded suffix groups and C=O between two N= (D-088c), Si-NH-Si (D-089u),
and condensed ureas (D-091t). The reason is budget, not evidence: the charged-species work found three defects the
plan did not contain and each stage carries its own corpus, suite and mutation evidence.

**Two checks on the panel's own targets, kept here so they are not re-derived:** a derived anion name is the
printed rule applied to the neutral acid's PIN; searching the whole book found that neutral name for 22 of 44
rows, so an EXACT_PREFERRED result on a derived row means agreement with a rule-derived target, never that the
book printed it; and one target was corrected after the fix was measured (erratum 2, pdf p. 593), disclosed in
the panel header.

## Naming round 6: open after the cyanic acid work (2026-09-20)

* **Cyanamide as a PREFIX** (`3-(cyanoamino)propanoic acid`): the Blue Book
  prints no name for it (searched: no `cyanoamino`, `cyanamido` or `N-cyano`
  prefix), so none is targeted.
* **`cyanato` is not enclosed** (`3-cyanatopropanoic acid`) while `thiocyanato`
  is: the book prints only the latter's enclosure (`3-(thiocyanato)propanoic
  acid (PIN)`), and a cyanate ester is derived from the rule, not printed.
* **The two new functional-parent routes return a leaf**, so they share the
  ownership blind spot recorded for round 5: the leaf is trusted to name its
  whole fragment.
* **Acyl cyanates and thiocyanates** (`CC(=O)SC#N`, named `acetyl
  thiocyanate` by the acyl route) are not attempted by the ester route.

## Open after naming round 5 (2026-09-20)

**Status after naming round 8 (2026-09-21):** N'-acyl hydrazides (D-088a), two acyl groups on one N (D-091u), carbon with two double-bonded suffix groups and C=O between two N= (D-088c) and the condensed ureas (D-091t) are FIXED; the hydrazide prefix spelling (D-088d) is partly fixed (the acid is the parent, the prefix is still `[(2-methylhydrazinyl)(oxo)methyl]`). Still open here: carbazate esters (D-088b, with the diagnosis in 'Open after naming round 8'), D-088f, h, i, j, D-089s, u, v, D-090b, D-091v, and fusion (D-086a to c). The table below is otherwise unchanged.

Kept by layer, as round 4's list is. Filled in stage by stage; the round's
adjudicated open rows are in `benchmarks/naming/adjudication.toml`, each with
its layer and target stage.

| layer | case | note |
|---|---|---|
| audit reach | a prefix whose NAME denotes an atom it does not CLAIM | measured in N6: "carbamimidoyl" on a chain claimed its nitrogens while the chain also named its carbon, and the guard passed a wrong molecule. The guard compares claims, and a claim is only as good as the code that set it; checking what a name denotes would need a parse, which N2 deliberately does not do |
| audit reach | molecules named with no substitutive level (66/267 on the tuning populations), and the insides of functional-class, multiplicative, ring-assembly and additive nodes | N2's ownership invariant runs where a substitutive tree exists; a leaf is trusted to name its whole fragment. Extending it needs provenance on those node kinds, which do not carry atom maps today |
| candidate generation | fusion names needing a SECOND-ORDER attached component | refused (`NEEDS_UNBUILT_CONSTRUCTION`), von Baeyer name or none | N3 builds one parent plus first-order components; 16 of the book's P-25 examples need more ("pyrido[1'',2'':1',2']imidazo[4',5':5,6]pyrazino[2,3-b]phenazine") |
| candidate generation | multiparent systems | refused, von Baeyer name or NONE | "benzo[1,2-b:4,5-c']difuran" (p. 234): the older fusion route used to stand in with "furo[2,3-f]2-benzofuran"; it no longer may, and the von Baeyer route fails here, so the molecule has no name until multiparent names are built (D-086a) |
| numbering | interior heteroatoms (P-25.3.3.2) | refused | 6 book examples ("6H-quinolizino[3,4,5,6-ija]quinoline", D-086c) |
| numbering | a 7- or 8-membered ring fused on three or more sides | refused | measured: 4 of the book's 8 such systems numbered as OPSIN numbers them, 4 did not -- their drawings need a hexagon on an octagon's horizontal side, a shape the drawing model lacks |
| numbering | rings of more than eight members; helicenes | refused | the book's distorted shapes; a helicene's own orientation rule (hexahelicene itself is retained, and named) |
| numbering | the ring table's pyrene and phenalene | former CAS interior locants (10b, 10c) | P-25.3.3.3.1 (p. 224) numbers interior carbons 3a1, 5a1 in PINs; the table predates that and is not repaired in N3 |
| candidate generation | hydro forms of a TRADITIONALLY numbered retained parent | von Baeyer ("tricyclo[8.4.0.0^{4,9}]tetradeca-1(14),2,10,12-tetraene" for a hexahydrophenanthrene) | general fusion leaves anthracene, phenanthrene, acridine, carbazole, xanthene and purine to the ring table, which carries their traditional numbering but cannot always derive a hydro form; the fusion-rule numbering is not theirs, so the constructor refuses rather than number them its own way |
| data | OPSIN's RING vocabulary: `rings_from_opsin.json` (705 names) and `fusion_components.json` (821) | read as ring parent names, unaudited | N5 gated only what the registry types: a ring name the registry demotes is refused by name (hypoxanthine, guanine), and "quinolizin"-style stems are rehydrated. The rest is the same kind of data the gate exists for, not audited this round, since refusing it outright would drop pyridine along with paracetamol. DECIDED (Alex, 2026-09-19, on the N5 report): left ungated. Of the 44 ring parents that win on the tuning populations, 10 come only from this vocabulary, and all 10 are book names |
| ranking | the P-44.1.2 senior-atom tier between two RINGS | the tier is compared ring against ring, which the book says it is not | agrees with P-44.2.1 wherever one ring has N, or one is a carbocycle; disagrees only for a ring whose senior atom is O/S/Se/Te against one whose is P..B (P-44.2.1 puts O first, P-44.1.2 puts P..B first). No corpus molecule has that pair |
| candidate generation | N'-acyl hydrazides | `1,2-dibenzoylhydrazine` | `N'-benzoylbenzohydrazide (PIN) (not 1,2-dibenzoylhydrazine)` (p. 670) | admitting an acylated N' to the hydrazide pattern reaches it, and turned 4-(2-benzoylhydrazinyl)-4-oxobutanoic acid into a butanedioyl name: the demoted, prefix form of an acylated hydrazide is not built (D-088a) |
| candidate generation | carbazate esters | `(ethoxycarbonyl)hydrazine` | `ethyl hydrazinecarboxylate` | the anion is not nameable ("oxidooxomethylhydrazine"), so no ester plan is offered; the carbamate split is refused (D-088b, D-087s) |
| candidate generation | a C=O between two N= | `1-[(oxo)(phenyldiazenyl)methyl]-2-phenyldiazene` | `bis(phenyldiazenyl)methanone (PIN)` (p. 110) | not perceived as a ketone; the multiplicative constructor counts it as one and declines, as the book requires (D-088c) |
| candidate generation | a substituted hydrazide as a prefix | `4-carboxy-N'-methylbenzohydrazide` | `4-(2-methylhydrazine-1-carbonyl)benzoic acid` (derived) | the acid is senior; the hydrazide stays the suffix because no prefix form exists for it (D-088d) |
| ranking | disilane and its kin as a parent | `methyl(silyl)silane` | `methyldisilane` (derived) | BUILT in N5: a chain of a centre-forming element (and any a(ba)n chain) competes with the one-atom centre on P-44.3's length (D-088e, D-089k) |
| multiplicative, outside the built class | a substituted or branched linker; a ring or an unsymmetrical central group; units joined by a double bond (hydrazinediylidene, ethane-1,2-diylidene); a unit whose attachment N no marker can read | declined, substitutive name stands | book PINs D-088f, h, i, j: `N,N'-oxybis(N-methylmethanamine)`, `4,4'-[(2-methylpropane-1,3-diyl)bis(oxy)]diphenol`, `(benzene-1,3,5-triyl)tris(silane)`, `4,4',4''-(ethane-1,1,2-triyl)tribenzoic acid` |
| multiplicative, needs another stage | `triethanolamine` | the whole-molecule OPSIN registry name wins before the constructor sees a substitutive tree | BUILT in N5: the gate refuses it and `2,2',2''-nitrilotri(ethan-1-ol) (PIN)` (p. 106) is emitted (D-088g) |
| candidate generation | skeletal replacement with a principal group | `(2-{2-[2-(carboxymethoxy)ethoxy]ethoxy}ethoxy)acetic acid` | `3,6,9,12-tetraoxatetradecane-1,14-dioic acid (PIN)` (p. 437) | the 'a' chain route declines on a principal group; multiplication correctly declines too (four heteroatoms) |
| serialization | hydrazide suffix on a systematic acid | `pentanohydrazide` | `pentanehydrazide (PIN)` (p. 667) | BUILT in round 5 (N8): the connecting 'o' stays wherever the stem is not a parent hydride's (D-092o-r) |
| candidate generation | carbon with two double-bonded suffix groups | `dithioxomethane`, `bis(methylimino)methane` | `methanedithione`, `dimethylmethanediimine` (p. 527) | the thione and imine patterns are written for R2C=X |
| serialization | full substitution (P-14.3.4.5) | `1,1,1,3,3,3-hexamethyldisiloxane`, `1,1,1,2,2,2-hexachloroethane` | `hexamethyldisiloxane`, `tetramethyldiboroxane (PIN)` (p. 731) | BUILT in round 5 (N8) for an all-carbon chain or ring and for an a(ba)n chain (D-089q, r, D-092h, i). Deliberately NOT applied elsewhere, because "no atom carries a hydrogen" is not "every substitutable position is substituted": an aromatic ring N or a fusion carbon satisfies the weaker test for free, and the vendored suite measured three names it would have made ambiguous or wrong -- `1,5-dimethyl-1H-tetrazole` (2,5- is another compound), a hexamethyl cyclotriphosphazene whose positions carry different NUMBERS of methyls, and `1,1,2,2-tetramethylhydrazine`, whose locants an expectation pins and whose locant-free form the book does not print. An UNSATURATED parent (`1,1,2,2-tetrachloroethene`) is out for the same want of evidence |
| PCG assignment | -ol on a silicon CHAIN | `1,3-dihydroxy-1,1,3,3-tetramethyldisiloxane` | `...disiloxane-1,3-diol` (derived, P-68.2.5) | silanols reach a suffix only through the pre-plan single-centre route, which N6 extended (bare silanols, N- and O-substituents, counting alcohols) but which cannot see a chain. Widening the alcohol pattern to Si-OH was tried and gave wrong molecules ("2-hydroxyethan-1-ol"): a demoted Si-OH became a bare "hydroxy" that dropped the Si (D-089s) |
| candidate generation | two acyl groups on one N | `N-benzoylacetamide` | `N-acetylbenzamide (PIN)` (p. 654) | only one amide is perceived per shared N, so the senior acyl is never offered as the parent (D-091u) |
| candidate generation | condensed ureas | `N-carbamoylurea`, `N-(carbamoylcarbamoyl)urea` | `2-imidodicarbonic diamide (PIN)`, `2,4-diimidotricarbonic diamide (PIN)` (p. 662) | imidopolycarbonic acids are not built (D-091t) |
| serialization | substituted carbamimidoyl prefixes | `4-[(dimethylamino)(ethylimino)methyl]benzoic acid` | `4-(N'-ethyl-N,N-dimethylcarbamimidoyl)benzoic acid (PIN)` (p. 676) | today's name is the book's second form; before N6 it was a wrong molecule (D-091v) |
| candidate generation | Si-NH-Si | `disilaazane` | `N-silylsilanamine` (p. 145, "not disilazane") | with N the a(ba)n rule gives way to amine names; the organometallic three-atom route still builds the a-term name (D-089u) |
| candidate generation | phosphoramidocyanidate esters | `(dimethylamino)(ethoxy)(oxo)phosphanecarbonitrile` | `ethyl N,N-dimethylphosphoramidocyanidate` (derived from "sulfurocyanidic acid (PIN)", p. 704) | was `tabun`, which the gate refuses; functional replacement of phosphoric acid by -CN is not built (D-089v) |
| candidate generation | a skeletal-replacement name for a siloxane | `2,4-dioxa-1,3,5-trisilahexane` | `1-methyltrisiloxane` (derived) | "-SiH2-O-SiH2-, disiloxane-1,3-diyl" is ONE heterounit (p. 440), so P-51.4.1's four are not reached; the heterounit count predates N5 (D-090b) |
| serialization, oracle | dinuclear 'hypo' boron acid | `hypoboric acid` | `hypodiboric acid (preselected name)` (p. 720) | the engine drops the "di" because OPSIN cannot parse the book's form; recorded here, not as a D-row, since the D-row table requires a target OPSIN parses |
| serialization | a FIRST-cited simple prefix enclosed | `[(hydroxy)di(methyl)silyl]acetic acid` | `[hydroxydi(methyl)silyl]acetic acid` | BUILT in round 5 (N8). CORRECTION to this row as written at N6: it also claimed `di(methyl)` and `(2-hydroxyethyl)di(methyl)silanol` were defects. They are not. P-16.5.1.3.1 (pdf p. 129) prints `ethyldi(methyl)phosphane (PIN)` and `ethyldi(propan-2-yl)silane (PIN)` -- only the first cited substituent goes bare, and the multiplier sits OUTSIDE the parentheses (D-091j, k) |
| candidate generation | a(ba)n chains of chalcogen terminals, and cyclic siloxanes | `{[(methylsulfanyl)oxy]sulfanyl}methane`; the ring names | not built | N5 builds Si, Ge, Sn, Pb, B and P..Bi terminals at standard valence; a carbon-bearing S-O-S is a sulfenic anhydride and was not checked against the book |

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
| candidate generation | multiplicative names | `N''-{14-[(diaminomethylidene)amino]tetradecyl}guanidine` | a multiplicative bis-guanidine | BUILT in round 5 (N4), `multiplicative.py`: the bis-guanidine, methylenebis(phosphonic acid) and N',N'''-methylenediacetohydrazide, and 22 of the book's P-15.3/P-51.3 PINs exact. N'-acyl hydrazides are a different mechanism and stay open (round-5 list) |
| candidate generation | hydrazine as a parent hydride | `1-(hydrazinyl)methanamide` | `hydrazinecarboxamide (PIN)` (p. 645) | BUILT in round 5 (N4) through the P-44.1.2 senior-atom tier. The carbazate ESTERS stay open (round-5 list) |
| candidate generation | N-substituted nitrogen oxoacids | `[(hydroxysulfonyl)amino]methane` | `N-methylsulfamic acid` | BUILT in round 5 (N4). The target was written `methylsulfamic acid` here; P-67.1.2.4.1 cites N-locants ("N,N-dimethylphosphoramidic acid (PIN)", p. 703), so the form is derived with them |
| retained parents | oxamide, oxalohydrazide | `ethanediamide`, `ethanedihydrazide` | `oxamide (PIN)`, `oxalohydrazide (PIN)` (pp. 351, 668) | substitution allowed on both |
| retained parents | silicic acid, disiloxane | `tetrahydroxysilane`, `trimethyl(trimethylsilyloxy)silane` | `silicic acid`, `hexamethyldisiloxane` | the second is round 3's last open row |
| PCG seniority | an amide on a urea N | `N-benzoylurea` | `N-carbamoylbenzamide (PIN)` (p. 661) | BUILT in round 5 (N6): a carbonyl between two acyclic, non-hydrazine nitrogens is a urea, not a carboxamide, and the urea route steps aside for any amide; the book's five P-66.1.6.1.1.5 examples exact (D-078k, D-091a-d) |
| PCG assignment | a chain-terminal amidine carbon | `4-carbamimidoylbutanoic acid` | amino + imino prefixes, as "methyl 4-(dimethylamino)-4-(ethylimino)butanoate (PIN)" (P-66.4.1.3.2, p. 677) | BUILT in round 5 (N6); it was a WRONG MOLECULE, one carbon too many (D-091f, g) |
| PCG assignment | a silanol with an alcohol elsewhere | `2-[(hydroxy)di(methyl)silyl]ethan-1-ol` | a silanol parent (P-44.1.2, Si before C) | BUILT in round 5 (N6): P-44.1.1's count, then Si (D-091i-k) |
| PCG assignment | hydroxamic acids | `cyclohexanecarbohydroxamic acid` | `N-hydroxycyclohexanecarboxamide (PIN)` (p. 587) | BUILT in round 5 (N6), N-substituted ones too (D-091n-p) |
| numbering | tetrahydropyridines | `1,2,5,6-` | `1,2,3,6-tetrahydropyridine-4-carboxylic acid` | BUILT in round 5 (N7): the orientations tied because no hydro locant reached the preference key; P-14.4 (e)(i) now ranks them (D-092a, b) |
| numbering | `pyridin-1(6H)-yl` | the old name | its lowest orientation | BUILT in round 5 (N7): `pyridin-1(2H)-yl` (p. 479). Not the free valence: the same hydro-locant tie as the row above (D-092c, d) |
| data | 32 ring-table entries | -- | -- | they number only some positions; a substituent elsewhere had an empty locant. Guarded (the plan is refused), not repaired |
| prefix construction | `tert-butyl` in a PIN | `(2-methylpropan-2-yl)` | `tert-butyl` (`4-butyl-4-tert-butylcyclohexan-1-ol (PIN)`, pdf p. 80) | classified in N8 and left: it renames the prefix, and 'b' against 'm' moves the alphanumerical citation order (P-14.5.2/3), so it is not the ranking-neutral change N8 admits. With it go Boc (`[(tert-butoxycarbonyl)amino]`), `propane-2-sulfonyl`, `ethanethioamido`, `phosphoryl` and the substituted carbamimidoyl prefix -- each a prefix the engine does not build, not a spelling |
| audit reach | a hydrazide beside a second acid | `OwnershipError: atom 0 owned by prefix[0] and prefix[2]` | a name | found in N8 while probing hydrazides (`NNC(=O)CCC(=O)O`, strict ownership): two prefixes claim the same atom, so N2's guard refuses the plan rather than emitting a wrong molecule. Not diagnosed |
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
* **The registry.** `tools/retained_name_audit.py` fails closed on
  impossible claims; 19 PINs and 27 non-PIN names are typed, 249 entries have
  no audited status. GATED in round 5 (N5): a record that came from OPSIN's
  parse dictionary -- the 1,824-name `retained_names_from_opsin.json`, or one
  of the 174 registry entries copied from it -- is emitted only with
  NORMATIVE_RULE evidence, and an audited demotion binds every table that
  spells the name (`engine.retained_gate_refusal`, `--gate`). Every registry
  entry a tuning-population name reaches (12) is audited. What remains
  unaudited is the OPSIN RING vocabulary (see the round-5 table) and the
  unreached registry backlog. DECIDED (Alex, 2026-09-19, on the N5 report):
  no full audit of the backlog. DONE in N9: all 75 usable, unaudited,
  non-OPSIN entries are typed with a quoted rule -- 33 PIN, 6 demoted because
  the book prints another name as the PIN, 36 demoted because the book never
  prints the name. Three were removed for binding an amino-acid name to the
  WRONG STEREOISOMER, and two new tests check name-against-structure and
  forbid one name under two structures. 171 entries remain untyped; the gate
  refuses every one of them that came from OPSIN.
* **The book contradicts itself twice, and the majority was followed.** Its
  prefix list prints `2,3-dihydro-1H-isoindol-2-yl` (p. 344); P-58.2.3.1.1
  and the worked analysis on p. 499 give `2H-isoindol-2-yl`. The engine emits
  the latter; the test row says why. And an ylidene on a ring position keeps
  that position's added or indicated hydrogen in '2-ethylidene-2H-indene
  (PIN)' (pdf p. 932) and a tricyclic dione (pdf p. 642), but not in
  '3-sulfanylidene-2-benzothiophen-1-one (PIN)' on the same page; the engine
  keeps it (`3-propylidene-2-benzofuran-1(3H)-one`, re-adjudicated in round 5,
  N7, h2cid28500).
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
| serialization | hexamethyldisiloxane | `trimethyl(trimethylsiloxy)silane` | `...silyloxy...` | STALE, re-measured 2026-09-19 (N8): N5's a(ba)n parent names it `hexamethyldisiloxane` and the O-bridge assembly is not reached |
| serialization | cid14000 | `4-{[(ethyl)][...]amino}butyl ...` | `4-{ethyl[...]amino}butyl ...` | STALE, re-measured 2026-09-19 (N8): it emits `2-({4-[(4-aminobenzoyl)oxy]butyl}(ethyl)amino)ethyl 4-aminobenzoate` |

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

## Open after naming round 14 (2026-09-24)

Round 14 took the measured residue of round 13 and worked it as clusters with one root mechanism each. The census went **95.70% -> 97.95% exact**
(1914 -> 1959 of 2000; no row LEFT `exact`, checked row by row against the round-13 reconstruction and every intermediate scan); candidate wrong
structures **0.90% -> 0.60%**; embedded errors and refusals **1.15% -> 0.45%**; the ring-locant sweep's rings with a structurally wrong case **19 -> 9**.

**Definitions (written down this round, because the census classes had been used as if they were self-evident).** `exact`: the InChIKey of the input
equals the InChIKey of OPSIN's read-back of the name. Formula equality is never treated as correctness. `same_connectivity`: the first InChIKey block
(connectivity and formula) is equal and the full key is not; the later blocks carry stereo, isotope and protonation/charge, so the bucket holds
DIFFERENT phenomena. Split by recomputing which InChI layer differs, the 35 round-13 rows were 30 stereo-only, 4 protonation, 1 double-bond stereo. OPSIN
is a STRUCTURAL oracle only: it is never the authority for a preferred numbering or a PIN.

**The census baseline had to be reconstructed.** The round-13 scan was never saved. `benchmarks/naming/stages/census_scan_r13-engine.json` (with
`r14-w0-provenance.json`: engine commit, sample hash, RDKit and py2opsin versions) is that reconstruction, and it was checked against the saved r12
per-row baseline: the same 2000 row labels, 47 rows changed class (exactly the ones round 13 declared: 30 mismatch -> exact, 14 embedded error -> exact,
1 unparsable -> exact, 1 embedded error -> wrong structure (D-151), 1 wrong structure -> same-connectivity), 0 left `exact`, totals 1914/35/13/5/10/22/1.

**Fixed this round** (each cluster's members were all re-run after the fix, not only a representative; the per-row record is the census `--compare`):

| item | D-row | root mechanism | census rows |
|---|---|---|---|
| a sulfonamide on a RING nitrogen | D-151 (FIXED, broadened) | `S(=O)(=O)N<ring>` was detected as a sulfonamide whose demoted prefix claimed S, O, O and N and left the ring's carbons unclaimed, so every plan with the other side as parent died and the engine named the ring as the parent: an acid lost its suffix and an ESTER was named as an ester of the piperidine (a different structure). Left to the structural carve now; the prefix is the sulfonic acid's `<ring>-N-sulfonyl` (P-65.3.2.3; the form of `(propane-1-sulfonyl)benzene`, pdf p. 614) | 7 (+4 silent renames where an acid or amide parent was regained) |
| sulfamoyl with two different N-substituents | D-152 (FIXED) | one shared `N,N-` locant block: `N,N-cyclohexylmethylsulfamoyl`, which no parser reads. Each substituent carries its own locant | 3 |
| ring cations with no name | D-154, D-155, D-156, D-157 (FIXED) | FOUR roots, found by naming the cations alone. (D-154) general fusion nomenclature refused any charged ring atom; now described on a neutral copy with the same atom indices, BICYCLIC systems only. (D-155) a ring-fusion `[n+]` beside an `[nH]` is the same cation as the `[nH+]` drawing and has no name of its own; the charge is moved. (D-156) a charged N with three ring bonds was made an indicated-hydrogen target, so a quaternary bridgehead cation with a substituent had no name; and the curated quinolizidine row gave its nitrogen the locant `4a` (it is 5). (D-157) an acyl or amido prefix derives from a recursive call that names the acid, and `name` promotes STANDALONE to CATION only at depth 0, so a ring cation inside an acyl prefix lost its `-ium` | 9 of 14 |
| stereo lost on a retained ring substituent | D-158 (FIXED) | `(oxolan-2-yl)methyl` comes from a retained LEAF that never reads stereo; the stereo-drop gate for retained names ran for STANDALONE only, and the attachment atom had lost its chiral tag (the descriptor survives as the `_ParentCIPCode` stash, which the gate now reads) | 18 |
| stereo lost on a spiro parent | D-159 (FIXED) | the Stage 6 skip of every spiro parent "pending a separate audit"; admitted at plain-integer locants like a bridged parent, guarded by the existing post-assembly OPSIN validation | 3 (6 unchanged: their centre has a primed locant) |
| fused all-carbon rings with a bare `-yl` | D-160 (FIXED for 7 of 11) | heptacene, octacene, nonacene and pentaphene to octaphene now carry a locant table that is one of the numberings `fusion_general.name_fusion` derives under P-25.3.3; pentacene and hexacene's OPSIN-probed tables are one of those too (a test pins every table to the derivation, so provenance is the rules, not OPSIN) | 0 (sweep: 638 wrong cases -> 0 for these rings) |
| three partial or absent tables | D-161 (FIXED) | octahydro-1H-indole (three attachable positions read as their neighbours), the biotin skeleton, and `[1,2,4]triazolo[3,4-b][1,3]benzothiazole` (the triazole carbon read as `5`); each table is the numbering of the mancude parent carried onto the skeleton | 2 |
| an aromatic non-benzene carbocycle named saturated | D-153 (FIXED) | tropone came out `cycloheptanone`, hinokitiol `2-hydroxy-5-(propan-2-yl)cycloheptan-1-one`: RDKit marks the ring aromatic, the unsaturation detector returns nothing for an aromatic ring, and the carbocycle branch read that as saturated | 1 (and one tuning row) |

**A wrong claim in the round-14 plan, corrected.** It said 11 all-carbon rings and "about 7" partly hydrogenated fused rings, 18 in all, against
"15 table-less rings with wrong cases". The re-run sweep gave 19 rings: 11 all-carbon, 4 other table-less, 4 partial-table. The "about 7" was wrong.

**The residue, cluster by cluster (41 rows, 2.05%), and why each is still here.** The 10-structure floor is a prioritisation rule, not a severity rule:
these are below it or not bounded, and each reason is recorded.

| cluster | rows | why it remains |
|---|---|---|
| spiro parents whose centre has a PRIMED or lettered locant | 8 (7 + the spiro cation 1788) | descriptors at a primed locant stay dropped: OPSIN's anchoring of a primed locant on a spiro parent is not established (the reason letter suffixes on a bridged parent are validated, not trusted) |
| charge or protonation lost (`[S-]` thiolate on a heteroaromatic, `[NH+]=N`) | 4 | the parent is named without its ion; a policy question about the anion path, and only OPSIN's `p` layer differs |
| tricyclic or amidinium ring cations | 4 (1620, 1641, 1847, 1859) | the neutral copy is verified for BICYCLIC systems only: the purine-fused tricyclic cations got a fusion name OPSIN cannot read where the von Baeyer fallback read back exactly (three exact rows would have left `exact`), so they stay on the fallback; an amidinium `N+=C` at a fusion atom has no neutral counterpart with one valence fewer |
| neutral fused or spiro polycycles with "no valid plan" | 4 | four different shapes, none with a second member |
| bridged methano-benzocyclooctenes | 2 | the skeleton is named as the wrong ring system; the same shape twice, not measured further |
| sulfonamide N- anions and one refused carboxylate | 4 | 2 of these (`...benzene-1-sulfonamidate`) are OPSIN reading an anion name as the neutral sulfonamide, a candidate and not a demonstrated engine defect; one drops the charge inside a `sulfamoyl` prefix; one is a refusal from the charge perception (`acidic_anion_carboxylate`) |
| single-row structural misnames | 6 | an N-hydroxy-N-alkyl amide in an ester loses its N-substituent (D-162, OPEN, target derived and read back), an acylamidine, an oxime ether of a thioamidine, a purine hydro-prefix, an N vs N' hydrazide locant, a steroid oxime ether |
| unparsable, other mechanisms | 7 | `N1,N2` oxamide locants, a von Baeyer name, an adamantane, a camphanyl phosphonate, a triazine-dione and a bis-dioxolo: seven different shapes |
| double-bond stereo omitted | 1 | one row |

**The ring-locant sweep after round 14** (371 curated rings, 7,372 cases; the population was regenerated after the table changes): 9 rings with a structurally
wrong case (the four helicenes, octahydropyridazino[1,2-a][1,2]diazepine, corrin, and three partial-table rings: two indolo[4,3-fg]quinolines and a
furo-naphtho-dioxole); 274 wrong cases of 7,372 (from 695). Classified: **STRUCTURAL_FAILURE** (the read-back is a different structure) is the
`wrong_structure` outcome; every structurally correct case on a table-less ring is **NUMBERING_UNADJUDICATED** (a preferred numbering no source here
establishes) and is not counted as a defect. The four helicenes stay unnumbered: the orientation module declines them, "a helicene is oriented and
numbered by its own rule" (P-25.3.3.1.1), which nothing here implements. Sweep runtime about 1,260 s.

**The sweep skips heteroatom sites, and that hid a wrong table.** The curated quinolizidine row gave its bridgehead nitrogen the locant `4a`; every
carbon locant was right and 651 heteroatom sites are never swept, so nothing saw it until the nitrogen took a substituent. A sweep of heteroatom
attachments is the next instrument, and its population is not built.

**Frozen populations.** `--frozen-impact r13-final-evaluation` (blind, counts only) reported **unchanged** for `heldout_v6` and `bluebook_frozen`: no frozen
name moved. The round-13 seal therefore stands and no new `--final-evaluation` was scored (a second exposure of the frozen rows would add nothing).

**One tuning row moved** (ref-compare against the round-13 merge, 1712 structures: 1 name changed, 0 violations): `c1c[cH+][cH+]1`, the printed
cyclobut-3-ene-1,2-bis(ylium) (p. 822), from `cyclobutane` to `cyclobutene` (D-153's mechanism). Neither is the printed target: the two charges are
still dropped, so the row is wrong before and after, one step closer. Manifest `stages/manifests/r14-release-candidate.toml`.

## Open after P-45.2.3 (2026-10-06)

P-45.2.3, "the lower locant set for substituent groups in order of citation in the name" (BlueBookV2.pdf p. 419), is applied ACROSS parent structures that tie on the preference key (`engine._senior_by_citation_locants`, called from `_break_parent_tie`), where it used to be plan order and so the order the SMILES atoms were written in. The book prints fifteen examples (pp. 420-422); fourteen are decided by it (1 to 12, 14, 15; 6 and 9 only since round 27's P-44.4.1.1: the book's name on 13 of 13 spellings, from 4 to 10 of 13 before for the ten that could be named then, and 11 and 12 only since D-191 and D-192 made the engine name a `[PH4]` group with its lambda number and a labelled bromine with its label), 13 was already the book's name on every spelling (the book frames it as a choice between two numberings of one chain). The engine writes `lambda5` where the book prints the glyph. It reaches achiral molecules; `CHANGELOG.md`, 2026-10-06, has the table and the census. What is left, each measured:

* **P-44.4.1.1 is implemented (naming round 27, 2026-10-07): the principal chain has the greater number of multiple bonds.** `strategy._parent_selection_score` counts the bonds the unsaturation infixes name; P-45.2.3 examples 6 and 9 are the book's name on 13 of 13 spellings (`vendor/CHANGELOG.md`, 2026-10-07, has the census, panel and sweep numbers). **P-44.4.1.2 (the greater number of DOUBLE bonds, `hepta-1,6-diene` before `hept-1-en-6-yne`, p. 402) is not:** `C=CCCC(CCC=C)CCC#C` is three names over 12 spellings (`5-(but-3-yn-1-yl)nona-1,8-diene` is the book's), all reading back exact, pinned as a strict xfail in `tests/test_namer_multiple_bonds_parent.py`. P-44.4.1.3 to P-44.4.1.11 (nonstandard bonding numbers across parents, indicated hydrogen, ...) were not examined.
* **P-45.5 is implemented (naming round 27, 2026-10-07): of parents that tie on P-45.2.3, the name earlier in alphanumerical order (`bromo` before `dibromo`).** `engine._senior_by_alphanumerical_order` compares `_alphanumerical_letters`: the finished name's letters in order, with locants, descriptors, element symbols, fusion descriptors and hydro/dehydro prefixes (not alphabetized, pdf p. 75) removed. The book's examples 1, 2 and 4 are its name on 13 of 13 spellings (7, 7 and 10 of 13 before); the numerical-locants half of the rule needs nothing, since P-45.2.3 has made them equal. **Not covered:** example 3 is a cyclophane the engine does not name. Example 5 carries nuclides: it was two names while the rule declined a name with a nuclide, and P-45.3 and P-45.4 are applied since round 29, so it is the book's name now; the rule still declines a name with a BONDING number (how the book alphabetizes the lambda is not stated) or an embedded `NAMING ERROR`.
* **Two parents are compared only when they have the same name once prefixes and descriptors are set aside, and at most twelve DISTINCT hypotheses are named.** The preference key does not hold every criterion that tells two different parents apart, and a lower locant must not stand in for one (the guard `_choose_by_configuration` already had for P-45.6); a molecule with more than `_PARENT_TIE_HYPOTHESES` (12, since #235; hypotheses `_plan_identity` shows to name the molecule identically count once) tied parent choices is left to plan order as before. Over the 2000 census rows the rule was reached on 176 calls (at every recursion depth) and every one was the same parent, so the guard has never declined on that population, and what happens when it does is tested only on made-up trees.
* **P-45.2.3 reads the prefixes' locants with the descriptors set aside (`assembly.descriptors_set_aside`), as the book does ("ignoring the configuration symbols", P-45.6.2, p. 426).** It did not at first, and the two features did not compose: read with their descriptors, the arms of a quaternary carbon merged differently (`4,4-bis[...]` against `4-[...]-4-[...]`), the flattened locants of P-92.5.2.2 example 5's four parent choices were `4,4,6,6` and `4,6,4,6`, and the rule ruled two of the four out before the configuration comparison, which is the one that should choose (found by #235's `test_nine_chains_are_four_choices` reading 2 where it expects 4; the name was still the book's on 40 of 40 spellings, by that artefact). Fixed, and pinned by `test_p_45_2_3_cannot_tell_the_four_choices_apart`. The book's own order is P-45.2.3, then P-45.3 to P-45.5, then P-45.6, and this engine's agrees for P-45.2.3, P-45.5 and P-45.6 (P-45.5 since round 27, and it runs between the other two); P-45.3 and P-45.4 are applied between them since round 29, so all four agree.
* **A partly saturated ring cation (naming round 34, 2026-10-09; D-207).** A cyclic iminium or amidinium lost its hydro prefixes and named the aromatic or the saturated ring (`2,3-dimethyl-1,3-diazol-3-ium` for `C[N+]1=C(C)NCC1`): `monocyclic._collect_hydro_locants` and `retained_lookup._try_derive_hydro_retained` refused a ring at its first charged atom, before asking whether it was in the double bond. 1151 such cations: wrong molecule 1005 -> 0. **Still open, found here:** the names are exact but use the Hantzsch-Widman parent (`3,4-dihydro-2H-azol-1-ium`, `4,5-dihydro-1H-1,3-diazol-3-ium`) where the neutral ring takes the retained one (`pyrrole`, `imidazole`); a ring cation with an exocyclic double bond on a ring carbon (`C=C1CCC[NH+]=C1`) is `5-methylideneazinan-1-ium`, a different molecule.
* **A ring cation on a curated fused parent (naming round 35, 2026-10-09; D-208).** Six curated ring tables listed no locant for their heteroatoms, so the `-ium` had no place and the cation was named as the NEUTRAL parent (`2-methyl-4,5,6,7-tetrahydro-1,3-benzothiazole`); the tables are complete and a cationic ring atom with no locant now fails its plan. 700 cations: wrong molecule 528 -> 0. **Still open:** thirteen more curated entries (octahydro-oxazolo-pyrrolo-pyrazine, hexahydropyrido[2,1-a]isoquinoline and kin, 1,2-benzodithiete, ...) list no locant for a ring heteroatom; their cations are named by the next plan (a von Baeyer name where one exists) rather than by the retained parent.
* **A ring cation with an exocyclic double bond (naming round 36, 2026-10-10; D-209).** `C=C1CCC[NH+]=C1` was the saturated `5-methylideneazinan-1-ium`: the hydro derivation counted the ylidene carbon as sp2 and found an odd number of hydro positions. A ring carbon whose double bond goes out of the ring to a carbon is a hydro position now (`5-methylidene-2,3,4,5-tetrahydropyridin-1-ium`); 231 ylidene ring cations and neutrals: wrong molecule 37 -> 0. **Not covered:** an exocyclic double bond to a heteroatom on a ring cation (`N=C1CCC[NH+]=C1`) goes the oxo / imino way, unchanged.
* **A fused ring system with a bridgehead N+ in a double bond (naming round 37, 2026-10-10; D-210).** Quinolizinium, the hydro-indolizinium and -quinolizinium cations and the bicyclic amidiniums drawn with the charge on the bridgehead (`C1C[N+]2=C(CCCCC2)NC1`) were a `NAMING ERROR`: the fusion namer needs a neutral copy and there is none. The ring is described on a twin (N+=C made single) with the hydrogens planned on a carbon analogue; 288 bicycles: naming error 190 -> 28. **Still open:** the 28 left each contain a four-membered ring (fused azetidinium); a tricyclic bridgehead iminium is declined; the two resonance forms of a bicyclic amidinium (same InChIKey) get two different, both exact, names.
* **A hydroxamic acid that is not the principal group (naming round 38, 2026-10-10; D-211, D-162).** `C(=O)N(R)OH` under an acid, an ester or a ring was written with the prefix "hydroxycarbamoyl", which includes its carbon while the chain also named it, and without its N-substituent: another molecule. `hydroxamic_acid` joins the four lists that split or claim a demoted amide-family group (`_DEMOTED_AMIDE_TYPES_PREPROC`, `_DEMOTED_N_BEARING_FG_TYPES`, `_DEMOTED_AMIDE_TYPES_EXEC` and its N-substituent test), and a substituent chain keeps the carbon of an N-substituted one; 336 variants: wrong molecule 292 -> 0; census row 322625 and the round-14 D-162 fixed. **Still open, found here:** (a) **D-212, OPEN:** `NC(=NC(=O)c1ccccc1)n1cccn1`, an N-acyl amidine on a RING nitrogen, is `benzamido(1H-pyrazol-1-yl)methanamine` (the C=N lost; wrong molecule, census row 325625; the 3,5-dimethyl form's target `N'-benzoyl-3,5-dimethyl-1H-pyrazole-1-carboximidamide` is derived and read back); (b) `CON=C(N=C(N)S)c1ccccc1`, an isothiourea chain with an oxime ether, is read back as another molecule (census row 356625); (c) a steroid with `NOCC(=O)N...` (census row 1786625); (d) a carboxylate on a steroid is refused (census row 1754625); (e) the four census `NAMING ERROR` rows and round 37's list (28 four-ring bridgehead iminiums, a tricyclic bridgehead iminium, 13 curated entries without heteroatom locants). **The frozen populations were not re-scored:** the blind check against the round-22 seal moves 1 of 40 `heldout_v6` names (none on the base engine) and the same 64 of 1126 `bluebook_frozen` names as the base engine, so one frozen row changed its name for a reason this change owns; whether to spend a final evaluation on it is a decision for the owner.
