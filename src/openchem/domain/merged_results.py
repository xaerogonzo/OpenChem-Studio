"""Several reports for one molecule, kept whole.

**THE MERGE PRESERVES EVERY PRODUCER-OWNED CHANNEL, NOT JUST THE FACTS.**
`BatchResultStore.merged_report` proved that folding several results' facts
into one `ReportResult` makes batch render like Properties, and that is
where this started. It is not evidence that ONE anonymous report can carry
several producers' charts, spatial annotations, provenance and stale state:
a `ReportResult` has exactly one `report_id`, one `provenance` and one
`structure_version`, so flattening N of them throws away which calculator
each picture, each vector and each staleness verdict belongs to. Measured
before this existed -- `merged_report` silently drops `spatial` entirely.

So the container holds the ORIGINAL REPORTS and a flattened fact view over
them. Charts, spatial annotations, provenance and staleness are READ OFF
`reports`, never copied into a parallel structure, because a second copy of
each is a second thing to keep in step and this project has paid for that
four times.

Nothing here computes and nothing here edits a producer's declaration --
the same two rules `FactView` follows. A chart is not retitled to name its
calculator, a fact's `source` is not overwritten, and no limitation is
rewritten. What the merge DOES add is `Fact.origin`, which is the one thing
a fact cannot know about itself: which of several reports it arrived in.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from openchem.domain.report import ChartAnnotation, Fact, ReportResult, SpatialAnnotation


@dataclass(frozen=True)
class MergedResults:
    """Several reports for one molecule, plus a flattened fact view.

    `facts` is what a `FactView` consumes -- it takes anything with
    `facts`, `by_category()` and `find()`. `reports` is what a WINDOW
    consumes: the charts to draw, the spatial annotations to offer, the
    display names to show, and the versions to compare.
    """

    reports: tuple[ReportResult, ...]
    facts: tuple[Fact, ...]
    #: The molecule's CURRENT structure version at the moment of the merge.
    #: A report describing a different one is stale -- see `is_stale`.
    structure_version: int = 0

    def __bool__(self) -> bool:
        return bool(self.reports)

    def report_for(self, report_id: str) -> ReportResult | None:
        """The report with this id, or None.

        Exists so a view resolves an id ONCE rather than rescanning the
        tuple every time it needs a display name -- and so nothing is
        tempted to infer a human-readable calculator name from an opaque
        id, which is what `Fact.origin` would otherwise invite.
        """
        for report in self.reports:
            if report.report_id == report_id:
                return report
        return None

    def name_for(self, report_id: str) -> str:
        """What to call this report on screen, falling back to its id.

        The fallback is deliberate and is not a display name in disguise:
        an id is at least true, where a prettified id would be a guess.
        """
        report = self.report_for(report_id)
        return report.name if report is not None and report.name else report_id

    def is_stale(self, report: ReportResult) -> bool:
        """Whether `report` describes a structure that has since changed.

        **REPORTED, NEVER DISCARDED.** A stale result is still a record of
        what was computed; silently serving one and silently blanking one
        are the two ways this goes wrong and they look identical from
        outside. `BatchResultStore.stale_for` takes the same position.

        A report stamped 0 against a current version above 0 counts as
        stale, which is the honest answer for "this one does not say when
        it was computed" -- and the reason every calculator result is
        stamped in ONE place rather than left at the default.
        """
        return report.structure_version != self.structure_version

    def stale_report_ids(self) -> tuple[str, ...]:
        return tuple(report.report_id for report in self.reports if self.is_stale(report))

    def charts(self) -> tuple[tuple[str, ChartAnnotation], ...]:
        """Every declared chart, paired with the id of the report that owns
        it, in report order and then in the producer's own order.

        **THE OWNER TRAVELS WITH THE CHART.** Once several calculators can
        contribute one, "the first chart" and "the last chart" stop being
        answers to anything -- a focused view has to be able to ask for
        exactly the charts belonging to one report.
        """
        return tuple(
            (report.report_id, chart)
            for report in self.reports
            for chart in (getattr(report, "charts", ()) or ())
        )

    def charts_for(self, report_id: str) -> tuple[ChartAnnotation, ...]:
        report = self.report_for(report_id)
        return tuple(getattr(report, "charts", ()) or ()) if report is not None else ()

    def spatial(self) -> tuple[tuple[str, SpatialAnnotation], ...]:
        """Every declared spatial annotation with its owner, same rule.

        `merged_report` dropped these on the floor; a view that offers a 3D
        model for one calculator's result among six needs to know which.
        """
        return tuple(
            (report.report_id, annotation)
            for report in self.reports
            for annotation in (getattr(report, "spatial", ()) or ())
        )

    def spatial_for(self, report_id: str) -> tuple[SpatialAnnotation, ...]:
        report = self.report_for(report_id)
        return tuple(getattr(report, "spatial", ()) or ()) if report is not None else ()

    def limitations(self) -> tuple[str, ...]:
        """De-duplicated in order: several calculators legitimately carry
        the same caveat, and printing it five times buries the four that
        differ. `merged_report` already took this position."""
        return tuple(
            dict.fromkeys(
                text
                for report in self.reports
                for text in (getattr(report, "limitations", ()) or ())
            )
        )

    def assumptions(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                text
                for report in self.reports
                for text in (getattr(report, "assumptions", ()) or ())
            )
        )


#: The reader contract, as a membership test. A `FactView` consumes anything
#: with `facts`, `by_category()` and `find()`; `MergedResults` additionally
#: needs a `report_id` to focus and select by, since a report nothing can name
#: cannot be chosen in a selector or linked to from a status chip.
#:
#: Structural rather than `isinstance`, deliberately, and for the reason
#: `_AllResults` exists: the merged view is a VIEW over several producers, and
#: a summary projection of a per-atom dataset or a pH curve satisfies this
#: surface without being a `ReportResult`. Requiring the class would force
#: those to be fabricated as real reports, which is precisely what
#: `MergedResults` refuses to do to its own contents.
_READER_CONTRACT = ("report_id", "facts", "by_category", "find")


def is_report_shaped(result: object) -> bool:
    """Whether `result` can be read by the merged results reader.

    **NOT "does it have facts".** See `merge_reports` for the bug that
    distinction fixes: a FAILED, inapplicable or picture-only report has none
    and is exactly what a reader must show.
    """
    return all(hasattr(result, name) for name in _READER_CONTRACT)


def merge_reports(
    reports, structure_version: int = 0
) -> MergedResults:
    """Fold `reports` into one container, stamping each fact's origin.

    **ONLY RESULTS THAT ARE REPORTS CONTRIBUTE**, which is the rule
    `merged_report` already applied to facts and which now applies to the
    other channels too: a per-atom dataset, a spectrum or a structure set is
    not a report and is reached through its own inspector. Without that, such
    a result could smuggle a chart into a merged view through a door the facts
    are refused at.

    **BUT "IS A REPORT" IS NOT "HAS FACTS", AND CONFLATING THEM WAS A BUG.**
    This gate was `if not getattr(report, "facts", None): continue`, which is
    two rules wearing one test -- reject non-reports, AND reject reports that
    happen to have no facts. The second is wrong the moment Results is the
    canonical reader rather than one of two places a result appears.

    A report legitimately has no facts when it FAILED, when the method does
    not apply to this molecule, or when its whole content is a picture. Those
    are exactly the cases a reader must show. Measured: `compute_lewis_sites`
    returns `report_from_fields(..., matched=[], cache_state=FAILED)` on
    refusal, so a refused Lewis Sites result reached the Properties panel and
    reached this window not at all -- it was rendered as nothing having
    happened.

    So the gate is the READER CONTRACT instead: `report_id` to be focused by,
    plus the `facts`/`by_category`/`find` surface a `FactView` consumes. That
    is the same duck-type `_AllResults` implements, so a summary view of a
    non-report result passes through the same door rather than a side one.

    It still refuses the kinds it always did, and truthiness was never what
    did that: `PhCurveResult` carries a `facts` field (empty by default) and
    no `by_category`, so it was refused for having no facts YET rather than
    for not being a report -- and would have been admitted, chart and all, the
    day a producer declared one. Now it is refused for the honest reason.

    **`Fact.source` IS NEVER TOUCHED.** It is the scientific or
    producer-declared source -- "RDKit", "LewisAnalysis" -- and it answers
    a different question from "which calculator did I run". Overwriting it
    with the report id would destroy real provenance to record different
    provenance. A fact that already carries an origin keeps it, so merging
    a merge changes nothing.
    """
    kept: list[ReportResult] = []
    facts: list[Fact] = []
    for report in reports:
        if not is_report_shaped(report):
            continue
        kept.append(report)
        origin = getattr(report, "report_id", "")
        for fact in report.facts:
            facts.append(fact if fact.origin else dataclasses.replace(fact, origin=origin))
    return MergedResults(
        reports=tuple(kept), facts=tuple(facts), structure_version=structure_version
    )
