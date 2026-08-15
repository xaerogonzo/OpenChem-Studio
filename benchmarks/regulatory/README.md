# Regulatory benchmark — rules, not runs

```bash
python benchmarks/regulatory/score.py
```

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

**`historical`** is reserved for structures whose status *changed*, the
only way to test that effective-date resolution works. Empty until a
superseding ruleset ships, and documented as such rather than omitted.
