# B2: the ordinary-compound battery's first probe

Source: `benchmarks/naming/battery_r9.toml` (268 rows; `approved_drugs_chembl` pending, see below),
probed via `tools/naming_battery_build.py probe` (`naming_probe.probe_structure` + the app's own
`RoundTrip` verdict, timeout-protected per row). No row here carries a preferred-name target -- B2 is
discovery and regression, never a preference oracle, per the protocol's own header.

## Headline

- **268/268 rows completed with no timeout and no worker crash.**
- Silent-fallback status: 268 `clean` (0 `fallback`, 0 `no_plan`, 0 `all_plans_failed`) -- **but see the
  instrument finding below: this undercounts by at least 2.**
- RoundTrip verdict: **263 MATCH, 1 MISMATCH, 4 PARSER_FAILED.**

This is a far cleaner hit rate than B1's Blue Book tuning half (23/1129 wrong-structure, ~2%), which is
expected: B2 deliberately covers ordinary, common chemistry the engine has already been tuned against
across rounds, where B1 deliberately covers the Blue Book's own (often obscure or retained-name-heavy)
worked examples.

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

## No naming plan at all: main-group tetrahydride anions

Both `[BH4-]` (sodium borohydride) and `[AlH4-]` (lithium aluminium hydride) get `attempted=0` -- the
engine has no naming path whatsoever for these common reducing-agent anions. This may be squarely inorganic
nomenclature (IUPAC P-7, additive/compositional naming) that this engine has never implemented, in the same
excluded category as "silicon rows" and "fusion" this round -- flagged rather than scoped in, pending a
frequency read from B3 and Alex's call on whether inorganic anion naming belongs in round 9's cap at all.

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

## approved_drugs_chembl: still pending

ChEMBL's public REST API was down for every filtered query as of this probe run (confirmed broad, not
query-specific: even an exact `molecule_chembl_id=CHEMBL25` lookup failed the same way). Alex chose to
proceed with the other 268 rows now; `assemble` and `probe` both re-run cleanly once the ChEMBL sample is
fetchable, and this file will be updated with that category's results when it is.

## Summary for the eventual admissions ledger

| finding | rows | severity | reach (this battery) | in scope for round 9? |
|---|---:|---|---|---|
| DCC / carbodiimide not recognised | 1 | high (wrong molecule) | 1 seen; DCC is common vocabulary | strong candidate |
| BH4-/AlH4- have no naming plan | 2 | high (no name at all) | 2 seen; possibly inorganic-nomenclature scope | undecided, needs B3 |
| phenothiazine dye locant (methylene blue) | 1 | unconfirmed | 1 seen | needs individual verification first |
| fluorescein spiro serialization | 1 | unconfirmed | 1 seen | needs individual verification first |
| probe status classifier misses embedded failures | instrument, not structure | -- | -- | round 10 instrument backlog |
