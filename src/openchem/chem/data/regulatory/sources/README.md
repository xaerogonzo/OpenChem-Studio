# Ruleset sources — hand-edited, reviewed

Everything here is written and reviewed by a person. The build
(`tools/build_regulatory_rulesets.py`) reads these and writes
`../generated/`, which is machine-owned and must not be edited.

**"Must not be edited" is now enforced rather than asked for.** `--check`
verifies each generated file against its own recorded `ruleset_sha256`
(catching a hand edit) and against what its source currently builds
(catching a source that moved on without a rebuild). Both are needed: a
hand-edited file is perfectly consistent with its source-document hash,
and a stale file hashes correctly to its own older content, so neither
check sees the other's case. Until this existed, either could ship
through CI untouched.

## The `quote` field is the gate, not a nicety

A rule's confidence is **capped by whether `legal.quote` holds the
regulation's actual words**. No quote means the primary text was never
checked against this pattern, and the build forces such a rule to
`requires_review` no matter what confidence the source file claims.

This is mechanical on purpose. "I am confident about the chemistry" and "I
have read the statute" are different claims, and only the second can be
verified by someone else later. Filling in a quote is how a rule graduates.

## RESOLVE AN IDENTITY FROM THE STATUTE'S CAS, NOT FROM ITS NAME

For a rule that names a substance, the InChIKey must come from the
identifier the regulation itself prints -- `legal.cited_identifiers` --
and a name lookup is corroboration, never the source. This is measured,
not stylistic. Over the 27 named chemicals of CWC Schedules 2 and 3
([source:cwc_annex_on_chemicals]; the DEA list is
[source:dea_listed_chemicals]):

    the statute's CAS resolved                    27 of 27
    OPSIN resolved the name                       25 of 27
    PubChem resolved the name                     27 of 27
    a name resolver AGREED with the CAS           26 of 27

**Two entries would have shipped a wrong structure**, and both look
perfectly successful if you only ask whether the name resolved:

    Sulphur monochloride   (CAS 10025-67-9, Schedule 3.B.12)
      OPSIN            [S]Cl        ClS      a radical
      PubChem by name  SCl          HClS     sulfenyl chloride
      by CAS           S(SCl)Cl     Cl2S2    <- the listed substance

    Dimethyl phosphite     (CAS 868-85-9, Schedule 3.B.10)
      OPSIN            P(OC)(OC)[O-]  C2H6O3P-  an ANION, P(III)
      by CAS           COP(=O)OC      C2H7O3P   the H-phosphonate

The "mono" in the traditional name means one chlorine PER SULFUR, and
both parsers read it as one chlorine in total -- so neither reaches the
right molecular formula, and they are wrong in two different ways. An
identity rule built on either would never match the chemical the treaty
lists, and would match something the treaty does not.

So "the name resolved" is not evidence of correct legal identity.
**Anchoring and resolution are separate questions and must be reported
separately.** Where a name resolver disagrees with the statute's CAS,
the CAS wins and the disagreement is worth recording; where no resolver
corroborates it at all -- one entry in 27 -- that is a human check
against the primary text, not something to wave through.

A method note that cost a measurement: the first version of this asked
whether the CAS appeared among PubChem's synonyms, and
`pubchem_identify` caps synonyms at 8 for display. Every entry reported
exactly 8, which is the tell. Resolving the CAS itself and comparing
structures has no cap in it.

## AND OSHA TABLE Z-1 SAYS THE OPPOSITE, IN ITS OWN FOOTNOTE

The rule above is measured and it is REGULATION-SPECIFIC, which was not
apparent until a regulation contradicted it. 29 CFR 1910.1000 Table Z-1
footnote (c), verbatim:

> The CAS number is for information only. **Enforcement is based on the
> substance name.** For an entry covering more than one metal compound,
> measured as the metal, the CAS number for the metal is given—not CAS
> numbers for the individual compounds.

So for this table the CAS is explicitly demoted, and **176 of its 610 rows
print no CAS at all**. An identity anchored on the CAS here would be
anchored on something the regulation itself calls informational, and would
silently drop a quarter of the table.

**Neither rule is wrong.** The CWC Annex prints a CAS beside every named
chemical and treats it as part of the listing; Table Z-1 prints one as a
convenience and says so. **The rule is: anchor on what the regulation
treats as the identifier, and let the regulation say which that is.** Both
are recorded on the rule, so a reader can see which route an entry took.

## WHAT TABLE Z-1 ACTUALLY PROVIDES

Read from the official eCFR XML
(`/api/versioner/v1/full/{date}/title-29.xml?part=1910&section=1910.1000`,
which requires an `Accept-Encoding` permitting compression or answers 406),
**not** from OSHA's annotated PEL pages, which present NIOSH, Cal/OSHA and
ACGIH values alongside the statutory ones.

**FIVE COLUMNS, AND NO AVERAGING-PERIOD COLUMN:**

    Substance | CAS No. (c) | ppm (a) 1 | mg/m3 (b) 1 | Skin designation

610 data rows and 14 footnote rows. The averaging period is NOT a column:
footnote 1 carries it for the whole table --

> The PELs are 8-hour TWAs unless otherwise noted; a **(C)** designation
> denotes a ceiling limit.

-- and the `(C)` lives INSIDE the value, as `(C)10`, not as a separate
field and not as a bare `C` prefix.

**THE VALUE COLUMN HAS FOUR FORMS, AND THEY ARE DIFFERENT STATEMENTS:**

| form | rows | means |
| --- | --- | --- |
| a bare number | most | an 8-hour TWA |
| `(C)n` | 28 | a ceiling |
| `(2)` / `(3)` | 26 | the limit is in Table Z-2 / Z-3, not here |
| `1 ppm/5 ppm STEL` | 1 | butadiene: a TWA and a STEL in one cell |

**THE mg/m³ VALUE'S EXACTNESS DEPENDS ON WHETHER ppm IS PRESENT**, which
nothing about the column's own contents reveals. Footnote (b):

> Milligrams of substance per cubic meter of air. When entry is in this
> column only, the value is **exact**; when listed with a ppm entry, it is
> **approximate**.

Measured: **223 exact, 234 approximate.** A model that carried the number
without that flag would present half of them as more precise than the
regulation claims.

**ROW CLASSES**, which is why "a row with no limit" must not be a refusal:

    458   carry at least one limit
     91   cross-references and aliases -- "; see 1910.1028",
          "see Ethanolamine." -- with no limit of their own
     61   no PEL printed

**Skin designation** is one value, `X`, on 95 rows.

**THE CONVERSION CONDITIONS ARE IN THE SOURCE**, footnote (a): "Parts of
vapor or gas per million parts of contaminated air by volume at 25 °C and
760 torr." That documents the assumptions a ppm ↔ mg/m³ conversion would
need; it does not supply the molar mass such a conversion also needs, which
is why a normalized value is refused rather than computed.

## Adding a regulation

1. Add or edit a `*.json` here, with `legal.citation_url` pointing at the
   primary text.
2. Run the build. It resolves any `name` entries through OPSIN, validates
   every predicate against the supported ops, and writes the ruleset plus a
   coverage report.
3. The build FAILS if `requires_review` entries exceed the threshold, so
   review debt cannot quietly become the shipped product.

## What must never go in here

Redistribution-restricted data. Specifically: the CAS Registry (proprietary
to ACS), DrugBank (CC BY-NC, incompatible with this GPL application),
ACGIH TLVs (copyrighted -- OSHA PELs are public and may be used instead),
and the IATA DGR (commercial -- the UN Model Regulations are public).

A CAS number **printed in the text of a regulation** may be carried in
`legal.cited_identifiers`, because that number is part of the statute being
cited. That is the only permitted use, and it must never accumulate into a
lookup table.
