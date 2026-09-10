"""What order results are shown in, and which group each one falls into.

**THE SELECTOR IS ARRIVAL-ORDERED TODAY, AND CALCULATIONS ARRIVE
ASYNCHRONOUSLY.** `PropertyPanel._reports` is a dict keyed by `report_id`, so
its values come out in the order results LANDED; `merge_reports` keeps that
order and the "Showing" box is built straight from it. Two runs of the same
six calculators can therefore produce six different selectors, and a result
finishing while somebody is reading the list moves everything below it.

**AND THE ORDER IT PRODUCES IS NOT THE ORDER THE APPLICATION ALREADY USES.**
Measured over the 30 results that reach the merged reader for aspirin, with
every calculator run in registry order: **30 of 30 entries sit in a different
position** from the section order the Properties panel shows them in. The
registry groups by MODULE; `CATEGORY_ORDER` groups by what a reader is
looking for.

The complete key, in order:

    display band   -> the always-on entry first (see ALWAYS_ON)
    category       -> `category_sort_key`, i.e. CATEGORY_ORDER then alphabetical
    display order  -> the calculator's position in the registry
    display name   -> casefolded
    report_id      -> last resort, so the key is TOTAL

**THE LAST TWO ARE NOT DECORATION.** A plugin report, a retired calculator id
read back from a saved project, and the always-on descriptor aggregate all
resolve no registry position, so without them their relative order would be
whatever the arrival order happened to be -- which is the defect this module
exists to remove, surviving in exactly the entries least able to explain
themselves.

**THE REGISTRY POSITION IS REAL EDITORIAL ORDER, NOT AN ACCIDENT.** Dropping
it and sorting by name inside a section changes 5 of the 8 multi-entry
sections this application can show, and the changes are bad ones: Solubility
is registered first in its section and alphabetical order puts **Hansen
Solubility Parameters ahead of it**, "Lewis Sites" before "Lewis Adduct"
inverts, and "BBB Score Descriptors" jumps above "Regulatory Screen". That is
the same editorial judgement `CATEGORY_ORDER` already records between
sections, applied within one.

**THE CATEGORY COMES FROM THE REPORT, NOT FROM A LOOKUP.** `ReportResult`
carries its own `category`, and measured over those same 30 results it agrees
with the registered calculator's category **30 times out of 30**, with no
report falling back to the "other" default. So only the registry POSITION has
to be supplied from outside, which is why `display_order_of` is one small
injected callable rather than a registry dependency in `domain/`.

Nothing here computes, and nothing here decides what a group is CALLED --
`calculator_taxonomy.category_label` does, so the Results selector and the
Properties panel cannot drift into two names for one section.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from openchem.domain.calculator_taxonomy import category_label, category_sort_key

#: An entry that belongs to no single section, shown above the sections.
#:
#: **DECLARED BY THE ENTRY, NEVER INFERRED HERE.** The same rule `charts`,
#: `spatial` and `TOTAL` already follow: a producer states what its result is,
#: and the presentation obeys. Inferring "this one spans everything" from the
#: content would be this module deciding a taxonomy question.
#:
#: **EXACTLY ONE THING IN THIS APPLICATION DECLARES IT**, and the reason is a
#: measurement rather than a preference: `DescriptorAggregate` holds the 41
#: always-computed descriptors, and those descriptors span **ten different
#: calculator categories**. No single section is true of it. Filing it under
#: one would be a lie, and leaving it uncategorised would sort the only entry
#: that is ALWAYS present below every calculator that happens to have run.
ALWAYS_ON = 0

#: Everything else: an entry that belongs to a calculator section.
IN_SECTION = 1

#: Closed, and refused rather than defaulted -- an unknown band would sort
#: somewhere plausible and silently reorder the list, which is the failure
#: this module exists to remove.
DISPLAY_BANDS = frozenset({ALWAYS_ON, IN_SECTION})

#: What the always-on band is called when it is rendered as a group. It is
#: not a category, so `category_label` cannot answer for it.
ALWAYS_ON_LABEL = "Always computed"

#: Where an entry sits when no registered calculator claims its id.
#:
#: **AFTER the ones that do, never before.** A plugin report or a retired id
#: read back from a saved project is still shown, still in its own section,
#: and still deterministic -- it simply cannot claim a position the registry
#: never gave it. Ordering it first would let an unregistered entry displace
#: the calculator a section is named for.
UNORDERED = 1 << 30


def category_of(entry) -> str:
    """The section `entry` belongs to, with an absent one read as the default.

    **`""` AND `"other"` MUST NOT BE TWO SECTIONS.** `ReportResult.category`
    defaults to `"other"`, so a report that omits it means exactly what one
    that spells it out means -- but `category_sort_key` orders unlisted
    categories by the string, which puts them at opposite ends of the
    unlisted tail, while `category_label` renders BOTH as "Other". Left
    alone, a plugin category sorting between them yields two separate groups
    both headed "Other", which reads as a rendering fault and is really a
    normalisation one. Normalising here means the sort and the heading agree
    by construction rather than by coincidence.
    """
    return str(getattr(entry, "category", "") or "") or "other"


def display_band(entry) -> int:
    """Which band `entry` declared, defaulting to IN_SECTION.

    The default is the restrictive one, for the reason `applies_to` defaults
    to molecule-only: an entry registered without a thought belongs to its own
    section, which is the answer that cannot displace anything else.
    """
    band = getattr(entry, "display_band", IN_SECTION)
    if band not in DISPLAY_BANDS:
        raise ValueError(
            f"unknown display band {band!r}; expected one of {sorted(DISPLAY_BANDS)}"
        )
    return band


def report_sort_key(
    entry, display_order_of: Callable[[str], int | None] | None = None
) -> tuple:
    """The complete, total ordering key for one reader entry.

    `display_order_of` answers the ONE thing a report cannot know about
    itself: where its calculator sits in the registry. Absent -- or answering
    None for an id nothing registers -- the entry falls to the end of its own
    section and is ordered by name there.
    """
    report_id = str(getattr(entry, "report_id", "") or "")
    name = str(getattr(entry, "name", "") or "")
    category = category_of(entry)
    position = None if display_order_of is None else display_order_of(report_id)
    return (
        display_band(entry),
        category_sort_key(category),
        UNORDERED if position is None else position,
        name.casefold(),
        report_id,
    )


def ordered_reports(
    reports, display_order_of: Callable[[str], int | None] | None = None
) -> tuple:
    """`reports` in the order a reader should show them.

    **STABLE IN THE INPUT ORDER BY CONSTRUCTION**, which is the property the
    whole module exists for: the key is total, so the same set of results
    sorts identically however they arrived, and a seventh result landing while
    somebody is reading does not move the six already on screen relative to
    each other.
    """
    return tuple(
        sorted(reports, key=lambda entry: report_sort_key(entry, display_order_of))
    )


@dataclass(frozen=True)
class ResultGroup:
    """One heading in the selector, and what sits under it."""

    label: str
    entries: tuple

    def __len__(self) -> int:
        return len(self.entries)


def group_label(entry) -> str:
    """The heading `entry` sits under.

    Sections are named by `calculator_taxonomy.category_label` rather than
    here, because two names for one section is exactly what that function was
    unified to prevent -- it already records a heading rendering as
    "Medicinal Chemistry" on screen and copying as "Medicinal_Chemistry".
    """
    if display_band(entry) == ALWAYS_ON:
        return ALWAYS_ON_LABEL
    return category_label(category_of(entry))


def grouped_reports(
    reports, display_order_of: Callable[[str], int | None] | None = None
) -> tuple[ResultGroup, ...]:
    """The same order, cut into labelled groups.

    **A GROUP IS NEVER EMITTED EMPTY**, and that is the whole invariant rather
    than a tidiness rule. The selector shows what has been COMPUTED, not what
    could be, so the group set genuinely differs per molecule and per session
    -- a reader who has run three calculators must not scroll seventeen
    headings, most of them concealing nothing. It is also what makes a search
    control safe to add later without revisiting this: filtering changes the
    input set, and a set with nothing in a category produces no heading for
    it.

    **A GROUP HOLDING ONE ENTRY IS ORDINARY HERE**, which is the opposite of
    the rule the Properties panel is held to.
    `test_no_category_holds_a_single_calculator` exists because a SECTION
    concealing one button is a taxonomy failure; a group here holds one entry
    whenever you have run one calculator from that section, which is most of
    them. Measured on a full run of everything reachable for aspirin: 30
    entries across 17 groups, **11 of them holding exactly one**. Applying the
    panel's rule to this list would be applying a rule about the taxonomy to a
    statement about what somebody ran.

    Groups are cut from the SORTED sequence rather than collected into a dict
    and re-sorted, so the group order and the order within a group are one
    decision rather than two that have to agree.
    """
    groups: list[ResultGroup] = []
    current_label: str | None = None
    current: list = []
    for entry in ordered_reports(reports, display_order_of):
        label = group_label(entry)
        if current and label != current_label:
            groups.append(ResultGroup(label=current_label or "", entries=tuple(current)))
            current = []
        current_label = label
        current.append(entry)
    if current:
        groups.append(ResultGroup(label=current_label or "", entries=tuple(current)))
    return tuple(groups)
