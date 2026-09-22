# B2: the ordinary-compound battery's first probe

Source: `benchmarks/naming/battery_r9.toml` (306 rows, all 9 categories including `approved_drugs_chembl`),
probed via `tools/naming_battery_build.py probe` (`naming_probe.probe_structure` + the app's own
`RoundTrip` verdict, timeout-protected per row). No row here carries a preferred-name target -- B2 is
discovery and regression, never a preference oracle, per the protocol's own header.

## Headline

- **306/306 rows completed with no timeout and no worker crash**, across two probe runs (268 rows before
  ChEMBL's API recovered, 306 after).
- Silent-fallback status: 306 `clean` (0 `fallback`, 0 `no_plan`, 0 `all_plans_failed`) -- **but see the
  instrument finding below: this undercounts by at least 2.**
- RoundTrip verdict: **298 MATCH, 2 MISMATCH, 4 PARSER_FAILED, 2 STEREO_OMITTED.**

This is a far cleaner hit rate than B1's Blue Book tuning half (23/1129 wrong-structure, ~2%), which is
expected: B2 deliberately covers ordinary, common chemistry the engine has already been tuned against
across rounds, where B1 deliberately covers the Blue Book's own (often obscure or retained-name-heavy)
worked examples.

## approved_drugs_chembl, once ChEMBL's API recovered

38/50 sampled approved drugs resolved (12 dropped for legitimate reasons -- see the B2 protocol commit).
Two of the 38 add new verdicts, both consistent with what a genuinely complex real-world structure should
produce rather than looking like new defect classes:

- **Two STEREO_OMITTED** (moxifloxacin hydrochloride; a complex macrolide-class natural product with a
  spiroketal and many stereocenters) -- the engine's name round-trips to the right CONNECTIVITY but does
  not fully specify every stereocenter. An existing, already-understood RoundTrip class, not a new one;
  recorded as a rate (2/306) rather than investigated row by row.
- **One additional MISMATCH**: a large cyclic lipopeptide (CHEMBL4594248, a daptomycin-class antibiotic --
  a macrocyclic ring closed by a Cys-Cys-like bridge, well over a dozen amino-acid-style residues). Genuinely
  wrong per the RoundTrip verdict, but at this size and complexity, diagnosing exactly which of its many
  stereocenters or ring-closure locants the engine's name gets wrong would take effort disproportionate to
  the admission rule's "one dominant defect mechanism" requirement -- flagged, not pursued as a ledger
  candidate this round.

## Instrument finding: a multi-component name can hide a `no_plan` failure as `clean`

`reagents_and_protecting_groups-010` (sodium borohydride, `[BH4-].[Na+]`) and `-011` (lithium aluminium
hydride, `[AlH4-].[Li+]`) both show `status: clean, attempted: 0` in the raw probe record -- `attempted=0`
means no plan was EVER tried for the hydride-anion component. The engine's own composite name for each is
`"sodium [NAMING ERROR: No valid naming plan found for [BH4-]]"` and
`"lithium [NAMING ERROR: No valid naming plan found for [AlH4-]]"` -- the salt's cation named successfully
and the failure message for the anion got embedded AS TEXT inside the overall string, rather than replacing
it outright. `naming_probe.probe_structure`'s status classifier (`str(name).startswith(NAMING_ERROR)`)
checks the whole string, so an embedded failure mid-string is invisible to it: `"sodium [NAMING ERROR: ..."`
does not start with `"NAMING ERROR"`. Only the independent RoundTrip verdict (`PARSER_FAILED`, since OPSIN
correctly refuses to parse a string containing "NAMING ERROR" as an IUPAC name) caught what the status
counter missed -- the value of checking two separate dimensions rather than trusting either alone, exactly
as this round's plan intends. **Not fixed this round** (out of scope for a probe-instrument tweak
discovered mid-battery); recorded for round 10's instrument backlog.

## The one MISMATCH: a whole functional group not recognised

**`reagents_and_protecting_groups-007`**: `C(=NC1CCCCC1)=NC1CCCCC1` -- N,N'-dicyclohexylcarbodiimide (DCC),
one of the most widely used coupling reagents in organic chemistry. The engine names it
`1,1'-[methylenebis(azanediyl)]dicyclohexane` -- a SATURATED bis-amine with a CH2 bridge
(Cy-NH-CH2-NH-Cy). The actual structure is a carbodiimide: a cumulated diene, Cy-N=C=N-Cy, whose central
carbon has NO hydrogens and two C=N double bonds. The engine appears not to recognise the carbodiimide
functional group at all, and instead treats the central sp carbon as an ordinary sp3 methylene -- a defect
on an extremely common, practically important reagent, not an obscure edge case. Strong candidate for the
admissions ledger: high severity (wrong molecule, not just non-preferred), high reach (DCC is standard
vocabulary across synthesis), narrow and well-defined (one functional group, carbodiimide, entirely
missing from perception).

## No naming plan at all: main-group tetrahydride anions -- DEFERRED to round 10 (Alex's decision, 2026-09-22)

Both `[BH4-]` (sodium borohydride) and `[AlH4-]` (lithium aluminium hydride) get `attempted=0` -- the
engine produces no name at all for either. 0/2000 in B3's census. A follow-up check found the general
salt/anion-naming MECHANISM is not missing: `disodium sulfate` and `trisodium phosphate` both name
correctly and cleanly (`clean` status, `MATCH`), so this is not "inorganic anion naming was never built" --
it is specifically that no rule covers hydride-count anions (a chemically distinct class from oxoanions),
narrower than first read but still genuinely undiagnosed: nobody has traced *why* the existing anion path
doesn't extend to this class, which every other F-item got before a slot was ever considered.

**Decision: not admitted this round.** It fits neither admission route as written (no name was produced at
all, so there is nothing to diagnose as a wrong molecule against a fixture; frequency is 0/2000, same as
DCC's carbodiimide) -- admitting it would mean a third, ad-hoc justification outside the ledger's own
mechanical rule. The cap is also genuinely competitive this round (charge loss at 14.6%, F5 at 8.4%, F1 at
7.1%, F7 at 4.05%, DCC on the wrong-molecule route), so a zero-frequency, undiagnosed, off-seed-list item
found incidentally is a weaker use of a scarce slot than what's already measured. Recorded here, with the
sulfate/phosphate contrast, so round 10 starts partly scoped rather than from nothing.

## Two PARSER_FAILED dyes: locant or serialization defects, not yet individually verified

- **`dyes-002`** (methylene blue): engine's name is
  `[12-(dimethylamino)phenothiazin-4-ylidene]di(methyl)azanium chloride`. Locant "12" on a phenothiazine
  ring system (whose standard numbering runs 1-10, with heteroatoms at 5 and 10) looks out of range --
  plausibly a numbering defect in how the engine locants a phenothiazine-based substituent, though this has
  not been individually confirmed the way B1's rows were (no direct OPSIN diff was run to pin down which
  specific token OPSIN rejects).
- **`dyes-008`** (fluorescein): engine's name is
  `7,13-dihydroxyspiro[1,3-dihydro-2-benzofuran-1,9'-xanthene]-1-one`. Spiro-compound numbering is
  notoriously easy to get wrong; also not yet individually confirmed.

Both are recorded as candidates needing the same individual-row verification B1's triage applied before
either is treated as confirmed.

## Summary for the eventual admissions ledger

| finding | rows | severity | reach (this battery) | in scope for round 9? |
|---|---:|---|---|---|
| DCC / carbodiimide not recognised | 1 | high (wrong molecule) | 1 seen; DCC is common vocabulary; 0/2000 in B3's census (see r9_b3_findings.md) | strong candidate on wrong-molecule grounds, not frequency |
| BH4-/AlH4- have no naming plan | 2 | high (no name at all) | 2 seen; 0/2000 in B3's census | **deferred to round 10** (2026-09-22) -- fits neither admission route, undiagnosed, weaker than the competing candidates |
| phenothiazine dye locant (methylene blue) | 1 | unconfirmed | 1 seen | needs individual verification first |
| fluorescein spiro serialization | 1 | unconfirmed | 1 seen | needs individual verification first |
| large cyclic lipopeptide MISMATCH | 1 | unconfirmed, too complex to isolate cheaply | 1 seen | not pursued this round |
| probe status classifier misses embedded failures | instrument, not structure | -- | -- | round 10 instrument backlog |
