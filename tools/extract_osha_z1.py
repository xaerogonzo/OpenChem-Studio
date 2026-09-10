"""Turn the official 29 CFR 1910.1000 Table Z-1 XML into a ruleset source.

Run from the repo root:

    uv run --no-sync python tools/extract_osha_z1.py            # write
    uv run --no-sync python tools/extract_osha_z1.py --check    # verify

**IT READS THE REGULATION, NOT OSHA'S ANNOTATED PEL PAGES.** Those present
NIOSH, Cal/OSHA and ACGIH values alongside the statutory ones, and a row
lifted from there would enter under OSHA's name carrying another body's
number. The committed XML beside this script is what eCFR served for
section 1910.1000, and its sha256 travels into the source document so a later
rebuild can say *same source, different code* rather than guessing.

## What the table provides, and what it does not

Five columns -- Substance, CAS, ppm, mg/m3, Skin designation -- and **no
averaging-period column**. Footnote 1 carries the period for the whole
table ("The PELs are 8-hour TWAs unless otherwise noted; a (C) designation
denotes a ceiling limit") and the marker lives INSIDE the value as
`(C)10`.

## THE INDENTATION IS LOAD-BEARING, AND MISSING IT SHIPS NONSENSE

110 of the 610 data rows are INDENTED continuations of the substance
above, marked in the source's own markup as `primary-indent-hanging-*`.
Read as substances they would become 110 rules named "Total dust" and
"Respirable fraction", and **104 limits would be attached to the wrong
thing or lost entirely**, because their parent row carries no limit of its
own.

**AND ONE INDENT MEANS TWO DIFFERENT THINGS**, told apart by whether the
sub-row carries a value:

    a value      a QUALIFIED LIMIT on the parent, and the sub-row's label
                 is the qualifier -- "Total dust", "Respirable fraction",
                 "Soluble compounds", "(as Cr)"
    no value     an additional IDENTITY for the parent's single limit --
                 "(ortho)", "(meta)", "o-isomer" enumerate the isomers a
                 parent like "Dinitrobenzene (all isomers)" covers, and
                 each supplies its own CAS

Modelling the second as a limit would invent limits the table does not
print; modelling it as a substance would lose the isomer's CAS.

## Identity comes from the NAME here, and the regulation says so

Footnote (c): "The CAS number is for information only. **Enforcement is
based on the substance name.**" 176 rows print no CAS at all. That is the
opposite of the rule the CWC rulesets follow, and both are right for their
own regulation -- see `sources/README.md`.

So the source document carries `names` for the build to resolve and the
printed CAS as a `cited_identifier`, never the other way round.

## Refusals are countable, and they are not all the same thing

A row without a limit is not a failure to read one. Four outcomes, kept
apart because collapsing them turns missing coverage into apparent parser
failure:

    HAS_LIMIT          the row states a limit
    NO_LIMIT_PRINTED   a real substance the table lists with no PEL
    CROSS_REFERENCE    "; see 1910.1028", "see Ethanolamine." -- the limit
                       lives elsewhere, or the row is an alias
    ELSEWHERE          the value is `(2)` or `(3)`: Table Z-2 or Z-3 holds
                       the number, and this table says so
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCES = REPO / "src" / "openchem" / "chem" / "data" / "regulatory" / "sources"
XML = SOURCES / "osha_1910_1000.xml"
OUT = SOURCES / "osha_table_z1.json"

CITATION_URL = (
    "https://www.ecfr.gov/current/title-29/subtitle-B/chapter-XVII/part-1910"
    "/subpart-Z/section-1910.1000"
)

#: The value forms this table uses. A bare number is an 8-hour TWA by
#: footnote 1; `(C)` makes it a ceiling. Anything else is not a limit.
_CEILING = re.compile(r"^\(C\)\s*(?P<number>[0-9.]+)$")
_NUMBER = re.compile(r"^[0-9.]+$")
_ELSEWHERE = re.compile(r"^\((?P<table>[234])\)$")

#: Footnote (b), verbatim, because it is what makes the same column carry
#: two epistemic statuses.
_FOOTNOTE_B = (
    "Milligrams of substance per cubic meter of air. When entry is in this "
    "column only, the value is exact; when listed with a ppm entry, it is "
    "approximate."
)
_FOOTNOTE_1 = (
    "The PELs are 8-hour TWAs unless otherwise noted; a (C) designation "
    "denotes a ceiling limit. They are to be determined from breathing-zone "
    "air samples."
)


def _cells(tr) -> list[str]:
    return ["".join(c.itertext()).strip() for c in tr.findall("TD")]


def _is_continuation(tr) -> bool:
    tds = tr.findall("TD")
    return bool(tds) and "primary-indent-hanging" in (tds[0].get("class") or "")


def read_rows(xml_text: str) -> list[dict]:
    """Every Table Z-1 data row, with its parent resolved.

    The table is the SECOND in the section -- Z-2 and Z-3 follow it -- and
    is identified by row count rather than by position alone, so a future
    reordering fails loudly instead of silently reading Z-2.
    """
    root = ET.fromstring(xml_text)
    tables = list(root.iter("TABLE"))
    candidates = [t for t in tables if len(t.findall(".//TR")) > 500]
    if len(candidates) != 1:
        raise SystemExit(
            f"expected exactly one table with >500 rows (Z-1); found {len(candidates)}"
        )
    rows: list[dict] = []
    parent: dict | None = None
    for tr in candidates[0].findall(".//TR"):
        values = _cells(tr)
        if len(values) != 5:
            continue
        name, cas, ppm, mg, skin = (v.strip() for v in values)
        row = {
            "name": name,
            "cas": cas,
            "ppm": ppm,
            "mg": mg,
            "skin": skin,
            "children": [],
        }
        if _is_continuation(tr) and parent is not None:
            parent["children"].append(row)
            continue
        rows.append(row)
        parent = row
    return rows


def classify(row: dict) -> str:
    values = [row["ppm"], row["mg"]] + [
        v for child in row["children"] for v in (child["ppm"], child["mg"])
    ]
    stated = [v for v in values if v]
    if any(_ELSEWHERE.match(v) for v in stated):
        return "ELSEWHERE"
    if any(_CEILING.match(v) or _NUMBER.match(v) for v in stated):
        return "HAS_LIMIT"
    if re.search(r"\bsee\b", row["name"], re.IGNORECASE):
        return "CROSS_REFERENCE"
    return "NO_LIMIT_PRINTED"


def _limit(value: str, unit: str, qualifier: str, companion: str) -> dict | None:
    """One printed cell as a limit, or None if it states none.

    `companion` is the OTHER unit's cell for the same row, and it is what
    decides `precision`: footnote (b) says a mg/m3 entry standing alone is
    exact and one listed beside a ppm entry is approximate.
    """
    if not value:
        return None
    ceiling = _CEILING.match(value)
    if ceiling:
        limit_type, notation = "ceiling", "(C)"
    elif _NUMBER.match(value):
        limit_type, notation = "twa_8h", ""
    else:
        return None
    if unit == "mg/m3":
        precision = "approximate" if companion else "exact"
    else:
        precision = "unstated"
    return {
        "source": {
            "value": value,
            "unit": unit,
            "raw_notation": notation,
            "qualifier": qualifier,
        },
        "limit_type": limit_type,
        "precision": precision,
    }


def limits_for(row: dict) -> list[dict]:
    """Every limit this substance carries, its sub-rows included."""
    out: list[dict] = []
    for source_row, qualifier in [(row, "")] + [
        (child, child["name"]) for child in row["children"]
    ]:
        for value, unit, companion in (
            (source_row["ppm"], "ppm", source_row["mg"]),
            (source_row["mg"], "mg/m3", source_row["ppm"]),
        ):
            limit = _limit(value, unit, qualifier, companion)
            if limit is not None:
                out.append(limit)
    return out


#: Characters the regulation prints that a Windows console cannot.
#:
#: Table Z-1 writes `4,4-Thiobis...` with U+2032 PRIME, and a display name
#: is rendered onto report lines that reach Qt, logs and console streams --
#: where this project has already recorded cp1252 raising on a tick and
#: cp437 on a superscript three. One row today; the map exists so the next
#: revision's typography is a decision rather than a crash.
#:
#: WRITTEN AS ESCAPES, not as the characters themselves. A file whose
#: point is that non-ASCII text is hazardous should not carry any, and an
#: escape survives a tool that re-encodes this file where a literal prime
#: silently becomes a question mark.
_ASCII_SUBSTITUTES = {
    "\u2032": "'",  # PRIME
    "\u2019": "'",  # RIGHT SINGLE QUOTATION MARK
    "\u2014": " - ",  # EM DASH
    "\u2013": "-",  # EN DASH
    "\u00b0": " deg ",  # DEGREE SIGN
}


def _ascii_display(name: str) -> str:
    """A name that can be printed, from one that may not be.

    **THE QUOTE IS NOT PUT THROUGH THIS**, and the split is the point:
    `legal.quote` is the regulation in its own words and stays byte-
    faithful, while `display_name` is presentation and is rendered onto
    lines that reach a cp1252 console. Changing the quote to make it
    printable would be editing the evidence.

    FAILS CLOSED. An unmapped non-ASCII character raises rather than being
    dropped or transliterated by guesswork -- a silently mangled substance
    name is a wrong identity that looks like a right one, and this is the
    same refusal the `**OPNE**` marker parse makes.
    """
    for source, replacement in _ASCII_SUBSTITUTES.items():
        name = name.replace(source, replacement)
    if not name.isascii():
        offending = sorted({c for c in name if not c.isascii()})
        raise ValueError(
            f"{name!r} carries unmapped non-ASCII characters "
            f"{[hex(ord(c)) for c in offending]}; add them to "
            f"_ASCII_SUBSTITUTES rather than dropping them"
        )
    return " ".join(name.split())


def _clean_name(name: str) -> str:
    """The substance, without the table's cross-reference tail.

    "Benzene; see 1910.1028" names benzene; the tail is a pointer to
    another standard and is not part of the name a resolver should see.
    Nothing else is stripped -- "(as Mn)" and "(all isomers)" are part of
    what the regulation listed, and removing them would silently widen the
    entry.
    """
    return re.sub(r";\s*see\b.*$", "", name, flags=re.IGNORECASE).strip()


def build() -> dict:
    xml_text = XML.read_text(encoding="utf-8")
    digest = hashlib.sha256(XML.read_bytes()).hexdigest()
    rows = read_rows(xml_text)

    rules = []
    counts: Counter[str] = Counter()
    for index, row in enumerate(rows, start=1):
        outcome = classify(row)
        counts[outcome] += 1
        if outcome != "HAS_LIMIT":
            continue
        name = _clean_name(row["name"])
        cited = {}
        # The printed CAS travels as a CITED identifier -- what the
        # regulation shows -- and never as the identity, because footnote
        # (c) says enforcement is on the name.
        for candidate in [row] + row["children"]:
            if candidate["cas"] and re.match(r"^\d{2,7}-\d{2}-\d$", candidate["cas"]):
                label = candidate["name"] if candidate is not row else name
                cited[f"CAS ({label})"] = candidate["cas"]
        skin = any(c["skin"] for c in [row] + row["children"])
        rules.append(
            {
                "rule_id": f"osha-z1-{index}",
                "display_name": (
                    f"{_ascii_display(name)} (29 CFR 1910.1000 Table Z-1)"
                ),
                "match_type": "identity",
                "confidence": "verified",
                # ASCII HERE TOO, and for a different reason from the
                # display name. This list is what the build hands to
                # OPSIN, and py2opsin writes it to a temp file in the
                # console encoding -- so a name carrying U+2032 failed
                # with `UnicodeEncodeError` and was recorded as
                # unresolved, which reads as a chemistry failure and was
                # an environment one. Transliterated it fails with
                # `NamingError` instead, because "6-tert, Butyl" is not
                # valid nomenclature -- an honest reason for the same
                # outcome, and no future typography can crash the build.
                #
                # The name is NOT rewritten into something OPSIN accepts.
                # `4,4'-thiobis(6-tert-butyl-m-cresol)` does resolve, and
                # supplying it would be guessing a structure by editing
                # the regulation's own name, which is the one thing this
                # pipeline exists to prevent.
                "names": [_ascii_display(name)],
                "legal": {
                    "authority": "US OSHA",
                    "instrument": "29 CFR 1910.1000",
                    "section": "Table Z-1",
                    "quote": row["name"],
                    "citation_url": CITATION_URL,
                    "cited_identifiers": cited,
                },
                "assumptions": [
                    "The substance is identified by the NAME the regulation "
                    "prints. Footnote (c): 'The CAS number is for information "
                    "only. Enforcement is based on the substance name.'",
                    "An unmarked value is an 8-hour TWA and a (C) value is a "
                    "ceiling, per footnote 1.",
                ]
                + (
                    [
                        "The limits below the substance's own row are its "
                        "indented sub-rows, whose label is carried as the "
                        "limit's qualifier."
                    ]
                    if row["children"]
                    else []
                ),
                # THE SKIN DESIGNATION IS A LIMITATION, NOT AN ASSUMPTION,
                # and the difference is whether anybody ever sees it.
                # `MachineInterpretation.assumptions` is rendered by
                # NOTHING on the regulatory path -- measured, `.assumptions`
                # has no reader outside the Lewis and interactions reports
                # -- while `limitations` reaches every finding line. So for
                # the 95 substances the table flags, an assumption is a
                # fact filed where no reader can reach it.
                #
                # It belongs there on the merits as well: the table prints
                # the designation, so it is not something we assumed, and
                # what it says is that the airborne number does not account
                # for absorption through the skin. That is a limit on how
                # the PEL may be read, which is what `limitations` is for.
                "limitations": [
                    "A permissible exposure limit is an AIRBORNE CONCENTRATION "
                    "for an occupational setting. It is not a property of the "
                    "molecule and says nothing about any other route or "
                    "population.",
                    _FOOTNOTE_1,
                    _FOOTNOTE_B,
                ]
                + (
                    [
                        "The table carries a SKIN DESIGNATION for this entry: "
                        "the substance can be absorbed through the skin, and "
                        "the airborne limit above does not account for that "
                        "route."
                    ]
                    if skin
                    else []
                ),
                "quantitative_limits": limits_for(row),
            }
        )

    return {
        "ruleset_id": "osha-table-z1",
        "display_name": "US OSHA permissible exposure limits (Table Z-1)",
        "domain": "occupational_exposure",
        "jurisdiction": "us",
        "version": "1",
        "source_citation": (
            "United States Code of Federal Regulations, Title 29, Part 1910, "
            "Section 1910.1000, Table Z-1. Text as served by eCFR."
        ),
        "citation_url": CITATION_URL,
        "source_snapshot": {
            "document": XML.name,
            "sha256": digest,
            "retrieved": "2026-09-09",
            "status": "current as of retrieval",
        },
        # EVERY ROW OF TABLE Z-1, IN ITS FOUR CLASSES, AS DATA.
        #
        # 110 of the table's 500 rows become no rule at all, and until
        # this block existed that fact reached a reader only as a
        # sentence -- one whose number was TYPED. It said 26 where the
        # table has 22 `(2)`/`(3)` rows and 87 cross-references, so a
        # claim inside shipped data disagreed with the shipped data and
        # nothing could see it. The prose below is now DERIVED from this
        # census, so the two cannot drift.
        #
        # IT LIVES IN THE SOURCE ARTEFACT AND REACHES THE GENERATED
        # RULESET AS PROSE, deliberately. `known_limitations` already
        # flows loader -> `Ruleset` -> the screen, so a reader gets the
        # numbers today; carrying the census itself through would mean a
        # field on `Ruleset` and a migration for four rulesets that have
        # no census, which is a model change this branch did not need to
        # make in order to stop the sentence lying.
        "row_census": {
            "total_rows": sum(counts.values()),
            "encoded": counts.get("HAS_LIMIT", 0),
            "no_limit_printed": counts.get("NO_LIMIT_PRINTED", 0),
            "cross_reference": counts.get("CROSS_REFERENCE", 0),
            "limit_in_another_table": counts.get("ELSEWHERE", 0),
        },
        "known_limitations": [
            "THIS IS NOT A SAFETY ASSESSMENT. A permissible exposure limit "
            "constrains airborne concentration in an occupational setting; it "
            "is not a property of the substance and does not speak to any "
            "other exposure route, to the general population, or to whether a "
            "given use is safe.",
            f"Table Z-1 lists {sum(counts.values())} rows and "
            f"{counts.get('HAS_LIMIT', 0)} of them state a limit here. "
            f"{counts.get('ELSEWHERE', 0)} give their value as (2) or (3), "
            "meaning Table Z-2 or Z-3 of the same section holds it, and "
            f"{counts.get('CROSS_REFERENCE', 0)} name another section or "
            "another entry instead. Neither Z-2 nor Z-3 is encoded, so this "
            "ruleset is silent about those substances rather than saying "
            "they are unlimited.",
            f"{counts.get('NO_LIMIT_PRINTED', 0)} row is listed with no PEL "
            "printed at all, and is encoded as no rule rather than as a "
            "limit of zero.",
            "Values are carried exactly as printed. No ppm to mg/m3 "
            "conversion is performed: it needs the substance's molar mass as "
            "well as the stated 25 C and 760 torr, so a converted number "
            "would carry an assumption the regulation does not make.",
        ],
        "rules": rules,
    }, counts


def main() -> int:
    if not XML.is_file():
        print(f"missing {XML}", file=sys.stderr)
        return 2
    source, counts = build()
    text = json.dumps(source, indent=1, ensure_ascii=False) + "\n"

    if "--check" in sys.argv:
        if not OUT.is_file():
            print(f"{OUT.name} has not been generated")
            return 1
        if OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.name} is stale -- re-run this script")
            return 1
        print(f"{OUT.name} is current ({len(source['rules'])} rules)")
        return 0

    OUT.write_text(text, encoding="utf-8")
    total = sum(counts.values())
    print(f"Wrote {OUT.relative_to(REPO)}")
    print(f"  {total} substances in Table Z-1")
    for outcome in ("HAS_LIMIT", "NO_LIMIT_PRINTED", "CROSS_REFERENCE", "ELSEWHERE"):
        print(f"    {counts.get(outcome, 0):4d}  {outcome}")
    print(f"  {len(source['rules'])} rules written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
