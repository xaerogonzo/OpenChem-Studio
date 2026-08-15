# Regulatory benchmark — rules, not runs

```bash
python benchmarks/regulatory/score.py
```

## Result, the historical corpus populated, 165 structures across 4 corpora

`historical` has its first entries. It was empty for the life of the
project, and the reason was recorded here as measured rather than assumed:
there was no per-rule effective-date resolution to test. There is now —
`screen(..., as_of=...)` — so the corpus can finally do the job it was
reserved for.

**Eleven rows, and the three that matter are not the obvious ones.** A
before/after pair on the 2019 additions is the requirement; on its own it is
weaker than it looks.

- **A.13 and A.15 the day before expect `cwc-2-b-4`, not nothing.** The
  withheld Schedule 1 entry sits beside a Schedule 2 rule dated 1997 that
  matches the same structure. A filter working per *ruleset*, or globally,
  empties those rows and still passes a naive before/after test.
- **Sarin at 1997-04-28 and 1997-04-29** exercises the *ruleset*-level date,
  a different resolution branch from A.13's own. All 44 CWC rules withheld,
  then 40 — the four 2019 additions still 23 years out, so both date levels
  resolve independently inside one screen.
- **Acetone at 1900-01-01 still matches `dea-ii-2`.** The guard on the
  default that could have gone the other way: 47 of the 91 shipped rules are
  undated, so "no date means never applicable" would empty half the screen.
  Note what that row does *not* assert — that acetone was listed in 1900. It
  asserts the screen's date constrained those rules not at all, which is what
  that ruleset's coverage note now says in as many words.

**A WITHHELD RULE IS NOT A TRUE NEGATIVE**, and `score.py` no longer counts
it as one. A rule that did not exist on the date being screened made no
prediction; crediting it with a correct rejection would hand every rule in
the file 44 free true negatives on the pre-1997 rows and dilute the one
column that exists to catch an over-broad pattern. Each entry is scored over
the rules that were *applicable* for it, and the withheld ones are printed
beside it.

Nothing is withheld when an entry carries no `as_of`, and that was checked
rather than asserted: run the new scorer against the corpus with `historical`
emptied and the per-rule table is **byte-identical** to the one master
produces. Worst per-rule precision is unchanged at 0.50 (`cwc-1-a-6`), with
the same two known mismatches.

**One shipped claim went stale the moment this landed**, and it was found by
a test assertion that was too loose rather than by review: Schedule 1's
`known_limitations` said the 2019 additions' effective date "is recorded on
the rules rather than enforced". It is enforced now. Rewritten to say what
remains true instead — no entry here records repeal or expiry, so a dated
screen answers when a rule *started* applying. The DEA ruleset gained the
matching admission that it records no dates at all.

## Result, four rulesets in two domains, 148 structures across 4 corpora

`drug_precursors` is the second domain to be populated — 21 CFR 1310.02,
the US DEA listed chemicals, 47 rules over 49 entries.

**IT COULD NOT BE ANCHORED THE WAY THE CWC RULESETS ARE.** The CWC Annex
prints a CAS number beside every named chemical; three drug-precursor
statutes were checked and none prints an identifier at all — the DEA uses
its own chemical codes, the EU annex uses CN codes, the UN 1988 Tables give
names only. So each identity rests on two independent derivations agreeing:
32 by OPSIN and PubChem resolving the name alike, 14 by routing around
OPSIN's inability to parse a trivial name (PubChem's own systematic name for
the structure, parsed back through OPSIN), 1 on connectivity alone, 2
refused. Every rule records its route, and the ruleset says the anchoring is
weaker.

Three findings, each caught by something different:

- **Both permanganates matched nothing at all** — including their own
  chemicals. The engine strips counter-ions before an identity comparison
  and a permanganate's identity *is* its salt, so the stored key never
  matched; storing the anion's key would have collapsed the regulation's two
  separate entries into one. They are expressions now, which are evaluated
  on the structure as drawn. Caught by the every-rule-has-a-positive guard.
- **Three diastereomer pairs cross-match.** The entries say "optical
  isomers" and this engine matches every stereoisomer, which reaches
  diastereomers too. Each member matches its own entry exactly and its
  partner's as an isomer, saying which. All six are listed, so the answer
  stays correct while the attribution is broader than the text.
- **Red and white phosphorus are refused.** Allotropes are not
  distinguishable by structure, and PubChem's systematic name for both
  records is "phosphane" — PH₃, not elemental phosphorus.

## Result, all three CWC schedules, 93 structures across 4 corpora

Schedule 1 now carries its own precursors (B.9–B.12) and the four entries
added in 2019, in force 7 June 2020 — both of which the ruleset had named
as gaps against itself since it was written. Three of the four 2019 entries
are families; **A.15 is a single named chemical**, which is why its central
carbon carrying two dialkylamino groups keeps it out of A.13's alkylidene
family.

**Two licensed medicines are the sharpest cases in the file.** Entry A.16
covers quaternary dimethylcarbamoyloxypyridines, and pyridostigmine and
neostigmine each fail one half of it — pyridostigmine quaternises the ring
nitrogen and has no exocyclic ammonium, neostigmine has the ammonium but
carries its carbamate on a benzene. Either feature alone would flag a
medicine.

**Choline matched Schedule 2 B.11 until the pattern was tightened.**
Entries B.10–B.12 reach "and corresponding *protonated* salts"; reading
that as any four-coordinate cationic nitrogen also reaches quaternary
ammoniums, which are *alkylated* salts. Choline is present in every cell
and sold as a supplement. Found because Schedule 1's A.16 example is itself
a quaternary ammonium and turned up matching B.11 as well — one new
ruleset exposing a defect in another.

**A CORPUS OF MATCHES CANNOT CATCH A BAD NEAR MISS, and this happened
twice.** A near miss needs only ONE satisfied predicate, so a rule pairing a
discriminating clause with a common one reports half of chemistry as one
feature from a listing — while matching nothing, and therefore scoring
perfectly here. Entry A.16's bare quaternary nitrogen did it to choline,
betaine and carnitine; the permanganates' "a sodium counter-ion" did it in
the very next commit to table salt, MSG and every sodium-salt medicine.
Both were caught by a person reading the screen.

`test_no_everyday_substance_is_NEAR_any_shipped_rule` is the check that
should have found them: twenty everyday substances, and any near miss on
that panel is a predicate too common to carry information. It catches both
historical instances, including the one it was not written for.

**A RULE CAN MATCH NOTHING AND STILL MISLEAD.** Entry A.16's second
feature was a bare quaternary nitrogen. It matched no ordinary chemical
outright — but it satisfied one of the rule's two predicates, and one
satisfied predicate is enough to be reported as a NEAR MISS. So choline,
betaine, carnitine, acetylcholine and benzalkonium surfactants were each
shown as one feature away from a chemical-weapons entry. Found by driving
the app with the whole suite green, and the corpus could not have caught it:
every one of those scores as a correct no-match.

The fix requires the α-picolinyl methylene the entry's own text describes,
which both its examples carry. Pyridostigmine KEEPS its near miss, and that
is the control — the cheap way to silence a false near miss is to weaken
near-miss reporting, which would discard the most useful thing this screen
tells a legitimate user.

**The pattern prototypes' must-reject cases are corpus negatives now.**
Twice a clause was load-bearing and untested because its case lived only in
the throwaway prototype: B.4's "but not further carbon atoms" and B.9's
alkyl restriction both survived a mutation for that reason.

## Result, CWC Schedules 1, 2 and 3, 76 structures across 4 corpora

Schedule 2 is the interesting one: six generic families with alkyl
restrictions, and three exemptions the treaty grants by name. Every family
pattern hits its own exemption, so without them fonofos,
N,N-dimethylaminoethanol and N,N-diethylaminoethanol — all in ordinary
commerce — would be false positives. Each exemption is a skeleton plus an
exact carbon count, which covers the chemical and its salts without
excusing a larger molecule that merely contains the fragment. All four
cases are in `edge_cases`.

**Adding Schedule 2 falsified three corpus entries, and all three were the
corpus being stale rather than a rule being wrong.** Worth recording,
because "a test failed" was the wrong first reading each time:

- **thiodiglycol** sat in `negatives` labelled "Schedule 2, not Schedule 1".
  It meant *must not match Schedule 1*, and asserted *must match nothing*.
  It is a Schedule 2 chemical and now matches B.13.
- **the C12 O-alkyl homologue** and **IMPA** were Schedule 1 edge cases
  expecting no match. Both are correctly Schedule 2 B.4 chemicals: the long
  chain hangs off the oxygen, and losing sarin's fluorine still leaves a
  phosphorus with one methyl and no other carbon.
- **sarin, soman, VX** and one homologue now match B.4 as well as their own
  Schedule 1 entries, because B.4 opens "except for those listed in
  Schedule 1" and no rule here can exclude another ruleset's members. It
  over-reports and never under-reports, the rule carries that limitation in
  its own text, and an edge case pins it.

## Result, CWC Schedules 1 and 3, 52 structures across 4 corpora

Schedule 3 adds 17 entries, 16 of them encoded, and every one scores
1.00/1.00. That is less impressive than it sounds and is stated plainly:
they are **identity** rules matched by InChIKey, so they cannot be
over-broad the way a structural family can. The interesting rows are still
Schedule 1's.

**Every shipped rule now has at least one positive case.** Sixteen of the
twenty-two did not when Schedule 3 landed, and a rule with no positive
scores a perfect 1.00 while testing nothing — the same vacuous pass this
file already warns about for a rule matching every organophosphate.
`test_every_shipped_rule_is_exercised_by_the_benchmark_corpus` fails if a
future rule ships without one.

Three Schedule 3 edge cases carry the weight:

- **triethanolamine hydrochloride** matches, and the entry's text does not
  say it should. Schedule 3 carries no "and corresponding salts" wording;
  the engine strips counter-ions anyway. Declared in that ruleset's
  `known_limitations` rather than applied silently.
- **`[S]Cl`** — the structure a name lookup returns for "Sulphur
  monochloride" — must NOT match. Entry B.12 is Cl2S2. The shipped key
  being right only means something if the wrong structure also fails.
- **diethyl phosphite** is scored as no-match because entry B.11 is
  deliberately unencoded: PubChem's record for its CAS is a cation and
  OPSIN returns an anion, where the entry lists a neutral substance. If it
  ever starts matching, the entry was encoded and the case moves.

## Result, CWC Schedule 1, 29 structures across 4 corpora

| rule | TP | FP | FN | TN | precision | recall |
|---|---|---|---|---|---|---|
| `cwc-1-a-1` alkylphosphonofluoridates | 3 | 0 | 0 | 26 | 1.00 | 1.00 |
| `cwc-1-a-2` phosphoramidocyanidates | 1 | 0 | 0 | 28 | 1.00 | 1.00 |
| `cwc-1-a-3` aminoethyl phosphonothiolates | 1 | 0 | 0 | 28 | 1.00 | 1.00 |
| `cwc-1-a-4` sulfur mustards | 3 | 0 | 0 | 26 | 1.00 | 1.00 |
| `cwc-1-a-5` lewisites | 1 | 0 | 0 | 28 | 1.00 | 1.00 |
| **`cwc-1-a-6` nitrogen mustards** | 2 | **2** | 0 | 25 | **0.50** | 1.00 |

## The 0.50 is the point of the whole benchmark

`cwc-1-a-6` matches **chlorambucil** and **melphalan**, both licensed
cytotoxic medicines. Neither is among the HN1/HN2/HN3 the treaty entry
enumerates, so both are genuine false positives of a pattern that keys on
the bis(2-chloroethyl)amine motif.

They are recorded in `edge_cases` as expecting **no match**, so the
benchmark scores them as the failures they are rather than blessing the
current behaviour. The rule ships anyway, marked `approximate`, carrying a
limitation that says this in as many words — the alternative is to say
nothing about nitrogen mustards at all, which is worse. What is not
acceptable is shipping it while pretending precision is 1.00.

The score is **reported, not enforced**. A gate failing the build here
would push someone to delete the honest edge case rather than fix the rule.

## Why four corpora

**`positives`** alone are worthless. A rule matching every organophosphate
scores perfect recall on sarin, soman and tabun.

**`negatives`** are ordinary chemicals — aspirin, glucose, malathion,
triethyl phosphate — that must match nothing.

**`edge_cases`** carry the weight, and the sharpest is **diisopropyl
fluorophosphate**: sarin's phosphoryl, fluorine and alkoxy, no P–C bond,
not Schedule 1. Also here: a P-butyl homologue (outside the entry's
"Methyl, Ethyl, n-Propyl or Isopropyl" restriction), a C12 homologue
(outside "equal to or less than C10"), and sarin's hydrolysis product
(no fluorine, so outside the entry despite being a famous marker).

**`historical`** holds structures whose status *changed*, each screened at
its own `as_of` date — the only way to test that effective-date resolution
works. It was empty until `screen()` grew a date to resolve against; see the
top of this file for what its eleven rows are shaped to catch.

Every structure in it appears at **two** dates. Testing only that a later
date gains the new rules would pass just as happily against a ruleset that
had quietly become permanently current, because there would be nothing to
compare the "after" against.
