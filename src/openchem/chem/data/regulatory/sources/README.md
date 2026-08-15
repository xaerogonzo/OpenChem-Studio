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
not stylistic. Over the 27 named chemicals of CWC Schedules 2 and 3:

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
