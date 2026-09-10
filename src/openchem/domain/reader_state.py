"""What the results reader is showing, and what it was showing last time.

**A WINDOW KEYED ON A MOLECULE CAN BE THROWN AWAY; A DOCK CANNOT.**
`MergedResultsDialog` is opened for one molecule and closed when the selection
moves, so "which report was focused" has never had to survive anything. A
persistent reader follows the selection instead, which turns the same question
into state somebody has to keep -- and getting it wrong is not neutral: a
reader that silently jumps back to "All results" every time you glance at
another molecule is worse than the window it replaces.

Nothing here is Qt, a widget, or a chemistry question. It is two things:

    ReaderMemory   what each molecule was showing, by uuid
    reader_state   which of the three empty-or-not states a reader is in

**THE RESTORE RULE, AND THE ONE THING IT MUST NOT DO.** A remembered report is
restored whenever it still EXISTS -- including when it is stale. A stale result
is a record of what was computed, and this project already refuses to discard
one; jumping away from a stale selection would discard it in the one place a
reader is looking. So this module is not told about staleness at all, which is
a stronger guarantee than remembering not to consult it: `recall` is handed the
ids that exist, and a stale report is one of them.

**FALLING BACK KEEPS THE FILTER.** Only the report is forgotten when it is
gone. The search text and the depth are about what somebody is looking FOR, and
dropping "lewis" out of the box because a report vanished would answer a
question nobody asked. The memory is per uuid, so no molecule ever inherits
another's filter.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, replace

#: No molecule is selected, so there is nothing a reader could be about.
#:
#: **NOT THE SAME AS AN EMPTY RESULT SET**, which is the distinction this
#: vocabulary exists for: "pick a molecule" and "nothing has been computed for
#: this molecule yet" send a reader to two different places, and rendering both
#: as blankness is the failure `_render` already refuses for the second one.
NO_MOLECULE = "no_molecule"

#: A molecule is selected and nothing has been computed for it.
NOTHING_COMPUTED = "nothing_computed"

#: There is something to show.
SHOWING = "showing"

#: Closed, and every member is a real screen a reader can be looking at.
READER_STATES = frozenset({NO_MOLECULE, NOTHING_COMPUTED, SHOWING})


def reader_state(molecule_uuid: str | None, result_count: int) -> str:
    """Which of the three states a reader is in.

    Pure, and separate from any widget, because `MergedResultsDialog` cannot
    reach NO_MOLECULE today -- the panel refuses to open it without a
    selection, so that branch has no route through the application until the
    reader is a dock that is always present. An unreachable branch is a
    question about where to assert, not a reason to leave the state undefined.
    """
    if not molecule_uuid:
        return NO_MOLECULE
    return SHOWING if result_count else NOTHING_COMPUTED


@dataclass(frozen=True)
class ReaderView:
    """One molecule's reader position: which report, and which filter."""

    #: The focused `report_id`, or "" for all of them -- the same vocabulary
    #: `MergedResultsDialog.focus()` already uses, so nothing has to translate.
    report_id: str = ""
    #: The fact search text, verbatim.
    search: str = ""
    #: Whether the depth filter is off.
    #:
    #: **A BOOL, NOT A `Detail`.** The control offers "Standard" and
    #: "Everything", and Everything is not a `Detail` member -- it is the
    #: ABSENCE of a depth filter, which is why `FactView` stores it as empty
    #: data and asks `not currentData()`. Mirroring that here would make `""`
    #: mean "showing everything" in a dataclass where every other empty string
    #: means "nothing remembered", and those must not be one value.
    everything: bool = False


#: What a molecule nobody has looked at opens on: all results, no filter,
#: standard depth. Named so the fallback is one value rather than three
#: defaults repeated at each call site.
DEFAULT_VIEW = ReaderView()


class ReaderMemory:
    """What each molecule's reader was showing, by uuid.

    Keyed on the molecule UUID rather than on a model object, for the reason
    `MergedResultsDialog` already is: a rebuilt `MoleculeModel` is the same
    molecule, and object identity would forget a position for a reason a
    reader cannot see.

    Small by construction -- one report id and two filter values per molecule
    somebody has actually looked at -- so nothing here evicts. A project with
    two hundred molecules that have each been read costs a few kilobytes.
    """

    def __init__(self) -> None:
        self._views: dict[str, ReaderView] = {}

    def __len__(self) -> int:
        return len(self._views)

    def remember(self, molecule_uuid: str, view: ReaderView) -> None:
        """Record where this molecule's reader is.

        A falsy uuid records nothing rather than filing every no-molecule
        reader under one key -- see NO_MOLECULE.
        """
        if not molecule_uuid:
            return
        self._views[molecule_uuid] = view

    def recall(
        self, molecule_uuid: str, available: Collection[str] = ()
    ) -> ReaderView:
        """Where to put this molecule's reader, given what exists now.

        `available` is every `report_id` the reader can show -- **stale ones
        included**, which is what makes "restore a stale selection" a property
        of the caller's input rather than a rule this has to remember.
        """
        view = self._views.get(molecule_uuid)
        if view is None:
            return DEFAULT_VIEW
        if view.report_id and view.report_id not in available:
            # The report is genuinely gone -- retired, or never recomputed for
            # this structure. Fall back to all results, and ONLY that: the
            # filter is a separate question and is kept.
            return replace(view, report_id="")
        return view

    def forget(self, molecule_uuid: str) -> None:
        self._views.pop(molecule_uuid, None)

    def clear(self) -> None:
        """Drop everything -- a new project's readers start fresh.

        Uuids are uuid4 so a stale entry could never be READ by another
        project's molecule, which makes this housekeeping rather than
        correctness. It is here so a long session does not accumulate the
        positions of molecules nothing can reach any more.
        """
        self._views.clear()
