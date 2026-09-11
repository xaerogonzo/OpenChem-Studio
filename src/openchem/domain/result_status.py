"""What a launcher says about a calculator it has (or has not) run.

**THE STATUS IS A PROPERTY OF THE RESULT, NEVER OF WHAT A READER MADE OF
IT.** Once the Properties panel stops rendering values it still has to say
whether there is anything to read, and the tempting shortcut is to ask the
reader -- "does this report have facts?". That is wrong in a way that looks
right: a successful `StructureSetResult` with zero structures, and a report
whose calculator ran and had nothing to say, are **READY**. Reading
emptiness as failure would paint two correct answers as broken, which is
the confusion `AlertResult.severity` had to be introduced to end one layer
along.

**SIX STATES, CLOSED, AND THE ORDER THEY ARE TESTED IN IS THE DESIGN.**
Every pair below is one this application can genuinely be in at once, and
the order says which the launcher reports:

    RUNNING before everything      a re-run in flight is what is happening
                                   NOW; the previous answer is about to be
                                   replaced, so reporting it invites
                                   somebody to read a value that is being
                                   recomputed.
    INAPPLICABLE before FAILED     an inapplicable result CARRIES
                                   `cache_state == FAILED` -- that is how
                                   the refusal travels -- so testing FAILED
                                   first would paint every correct,
                                   permanent refusal as a fault. This
                                   repository has shipped that once already
                                   and reported it as "some calculator
                                   failures" when neither had.
    FAILED before STALE            a stale failure is both, and only one
                                   glyph fits. "It did not run" is the more
                                   actionable of the two, and re-running is
                                   the answer either way.

**NOT_RUN IS NOT AN ERROR AND MUST NOT LOOK LIKE ONE.** It is the state
every one of ~60 calculators is in when a molecule is selected, so it is
the panel's resting appearance rather than an exception.
"""

from __future__ import annotations

from openchem.domain.common import CacheState
from openchem.domain.structure_resolution import is_stale

#: Nothing has been asked of this calculator for this molecule.
NOT_RUN = "not_run"
#: It was asked, and has not answered yet.
RUNNING = "running"
#: It ran and succeeded. Says nothing about how MUCH it produced -- a
#: result with no values in it is still a result.
READY = "ready"
#: It succeeded, for a version of the structure that has since changed.
STALE = "stale"
#: It ran and did not produce an answer. A fault, and actionable.
FAILED = "failed"
#: The method does not cover this molecule. Correct, permanent, and NOT a
#: fault -- the distinction `DescriptorValue.inapplicable` already carries.
INAPPLICABLE = "inapplicable"

#: The closed vocabulary, so a consumer can be total over it. A status
#: absent from this is a programming error rather than a new kind of
#: outcome, which is the fail-closed rule `RESULT_KINDS` and
#: `VISUALIZATION_KINDS` already follow.
RESULT_STATUSES = (NOT_RUN, RUNNING, READY, STALE, FAILED, INAPPLICABLE)


def status_of(result, *, running: bool = False, structure_version: int = 0) -> str:
    """Which of `RESULT_STATUSES` describes `result`.

    `running` is the caller's own answer, because only the thing that
    DISPATCHED a calculation knows one is in flight -- a result cannot say
    that it is being replaced. In this application it comes from
    `CalculationFinished`, which carries the CALCULATOR's id where no
    result event can.

    Read with `getattr` throughout: this is asked of every result kind the
    reader admits, and `inapplicable`, `error` and `structure_version` are
    optional fields that most producers never set.
    """
    if running:
        return RUNNING
    if result is None:
        return NOT_RUN
    if getattr(result, "inapplicable", False):
        return INAPPLICABLE
    if getattr(result, "cache_state", None) is CacheState.FAILED:
        return FAILED
    # **`structure_resolution.is_stale`, NEVER A REPEAT OF THE COMPARISON.**
    # Staleness already decides whether a badge is shown and whether a
    # PICTURE is drawn; a third rule meant to agree with those two would be
    # a bug nobody could see, because all three answers look reasonable in
    # isolation. `MergedResults.is_stale` makes the same call for the same
    # reason.
    if is_stale(getattr(result, "structure_version", 0), structure_version):
        return STALE
    return READY
