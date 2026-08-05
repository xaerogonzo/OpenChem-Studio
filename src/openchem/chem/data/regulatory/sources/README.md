# Ruleset sources — hand-edited, reviewed

Everything here is written and reviewed by a person. The build
(`tools/build_regulatory_rulesets.py`) reads these and writes
`../generated/`, which is machine-owned and must not be edited.

## The `quote` field is the gate, not a nicety

A rule's confidence is **capped by whether `legal.quote` holds the
regulation's actual words**. No quote means the primary text was never
checked against this pattern, and the build forces such a rule to
`requires_review` no matter what confidence the source file claims.

This is mechanical on purpose. "I am confident about the chemistry" and "I
have read the statute" are different claims, and only the second can be
verified by someone else later. Filling in a quote is how a rule graduates.

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
