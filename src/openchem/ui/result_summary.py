"""A result in the shape the reader consumes, without pretending to be one.

**ONE CANONICAL READER, NOT ONE CANONICAL RESULT MODEL.** A trajectory, a
per-atom dataset and a fact report are not the same scientific object, and the
`ScientificResult` hierarchy exists for that reason. What they can share is a
READING SURFACE -- `facts`, `by_category()`, `find()` -- which is exactly what
`FactView` already duck-types on.

So the bridge produces a VIEW rather than converting a producer's result into a
report. `MergedResults` already refuses the conversion for the same reason its
own docstring gives: a `ReportResult` has one `report_id`, one `provenance` and
one `structure_version`, so flattening several producers into one throws away
which calculator each fact, picture and staleness verdict belongs to.

**THE NAME IS THE POINT.** This is called a VIEW so that nobody, six months
from now, stores one and treats its facts as a producer's own declaration.
Two different things would be lost by doing so:

    the merged view      several producers' facts under ONE id, which is
                         precisely what `MergedResults` refuses
    a single-result view facts DERIVED by presentation -- a peak count, a
                         value range -- attributed to a producer that never
                         declared them

The refusals are structural rather than a note: there is no `to_dict`, no
`from_dict`, and this is not a `ReportResult`, so the project writer has
nothing to call and `isinstance` says no.

**DERIVED FACTS MUST SAY THEY ARE DERIVED**, which is the rule the per-kind
summaries in `result_adapters` are held to when they land: a presentation
summary may be deterministically projected from declared result data and must
be identified as one, and it never introduces a new scientific claim.
`len(peaks)` is a projection; a curve crossing found by interpolation is a
claim and belongs to a producer. The merged view below derives nothing -- it
passes the producers' own facts through, with `Fact.origin` already stamped by
the merge.

It lives beside `result_adapters` rather than in `domain/` because it is what
the presentation adapters PRODUCE, and because the alternative reading -- that
it is a domain container like `DescriptorAggregate` -- is the confusion the
name exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openchem.domain.report import Fact, FactCategory, find_facts, group_facts_by_category


@dataclass(frozen=True)
class ResultSummaryView:
    """Something the results reader can show, that is not a report.

    Satisfies both contracts a reader entry meets, which are NOT the same
    one and are easy to confuse:

        `merge_reports`   `report_id` + `facts` + `by_category` + `find`
        `FactView`        `facts` + `by_category` + `find`, with
                          `charts` / `limitations` read by `getattr`

    plus the two fields the ORDERING reads (`category`, `name`) and the two
    `ui/report_format.py` needs to export one (`molecule_uuid`,
    `structure_version`). Missing either of the last pair is not cosmetic --
    see the module docstring in `report_format` for what a type outside its
    dispatch used to do.
    """

    #: The id a reader focuses and orders by. Empty for a view over the WHOLE
    #: merge, which names no single producer -- and `is_report_shaped` asks
    #: `hasattr`, so an empty one still passes the admission door.
    report_id: str = ""
    name: str = ""
    #: The calculator section this sits in, for `result_ordering`. "other" is
    #: `ReportResult`'s own default, so an unplaced view lands where an
    #: unplaced report does rather than in a section of its own.
    category: str = "other"
    facts: tuple[Fact, ...] = ()
    charts: tuple = ()
    #: Which dedicated viewer opens the WHOLE result this summarises, or
    #: `NO_RICH_VIEW`.
    #:
    #: **DECLARED HERE BECAUSE A SUMMARY IS A DEAD END WITHOUT IT.** Measured
    #: over the registry on aspirin: 60 entries reach the reader and **30 of
    #: them declare a viewer**, which is precisely the half 1a admitted -- so
    #: without this a reader shows a count and a range for thirty results and
    #: offers no way to see any of them.
    #:
    #: It is the ADAPTER's answer, copied once at projection time rather than
    #: re-derived by asking `kind_of` again later: a view is not the result,
    #: so a consumer holding one cannot ask it what kind the result was, and
    #: a second derivation is a second place for the two to disagree.
    rich_view: str = ""
    #: What the button opening it should SAY, or "" for the
    #: destination's own label. Carried beside `rich_view` and for the
    #: same reason: the adapter's answer, copied once, never re-derived.
    rich_view_label: str = ""
    limitations: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    molecule_uuid: str = ""
    structure_version: int = 0
    #: The producer's own status, carried rather than re-derived.
    #:
    #: **A REFUSED RESULT MUST NOT READ AS ONE THAT RAN AND HAD NOTHING TO
    #: SAY**, which is the whole reason `merge_reports` stopped gating on
    #: facts. `MergedResultsDialog._status_line` reads `cache_state`, `error`,
    #: `error_summary` and `inapplicable` off the entry, so a summary that
    #: dropped them would turn every refusal into a silent blank -- and a
    #: refused calculator has FEWER facts to project, so it is exactly the
    #: case a summary is most likely to render as nothing.
    #:
    #: `Any` rather than `CacheState` so this stays a view over whatever a
    #: producer declared, and defaulting to None keeps a view built without
    #: one indistinguishable from today's behaviour.
    cache_state: Any = None
    error: str | None = None
    error_summary: str | None = None
    #: A refusal is not a fault -- the same field, and the same distinction,
    #: `DescriptorValue` already carries.
    inapplicable: bool = False

    def by_category(self) -> dict[FactCategory, tuple[Fact, ...]]:
        return group_facts_by_category(self.facts)

    def find(self, text: str) -> tuple[Fact, ...]:
        return find_facts(self.facts, text)


def summary_of_merge(merged, molecule_uuid: str = "", name: str = "All results"):
    """Every merged fact and every chart, as one thing a reader can show.

    **A VIEW OVER `MergedResults`, NOT A COPY OF IT.** The container keeps the
    original reports; this is the flattened reading surface over them, and the
    facts are the producers' own -- `merge_reports` has already stamped each
    with the `origin` that says which report it arrived in.

    `report_id` is deliberately EMPTY: this names no single producer, and
    giving it one would make the merged view focusable as a calculator that
    contains everybody else's results.
    """
    return ResultSummaryView(
        name=name,
        facts=merged.facts,
        charts=tuple(chart for _report_id, chart in merged.charts()),
        limitations=merged.limitations(),
        assumptions=merged.assumptions(),
        molecule_uuid=molecule_uuid,
        structure_version=merged.structure_version,
    )
