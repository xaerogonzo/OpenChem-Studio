"""iupac_namer.diagnostics
====================================================

Opt-in instrumentation for the naming engine.  Off by default, zero cost
when off, and deliberately *not* imported by anything that runs in the
hot path except through :func:`enabled`.

Why this module exists
----------------------
The engine has a failure shape that is worse than an exception: a
perception classifier correctly claims every formal charge in a
molecule, its renderer then fails to compose a surface name, the
dispatcher returns ``None``, and the generic plan search names the
*neutralized* skeleton instead.  The caller gets a confident, wrong
answer -- ``methylbenzene`` for the benzyl cation -- with nothing in the
output to suggest anything went wrong.

Those gaps cannot be found by reading the code, because the code that
produces the wrong answer is working exactly as written.  They have to
be measured: run a corpus, record every point where a renderer declined,
and read off the list.  This module is that recorder.

It is permanent rather than a throwaway script because the next such gap
will surface years from now, and whoever hits it will want the
instrument already in the box.

Usage
-----
Set the environment variable, then name things::

    OPENCHEM_NAMER_DEBUG=1 python -c "..."

Or scope it programmatically, which is what the sweeps and tests do::

    from openchem.vendor.iupac_namer import diagnostics

    with diagnostics.capture() as rec:
        name_smiles("[CH2+]c1ccccc1")
    rec.failures      # -> (RenderFailure(suffix_hint='...', ...),)
    rec.stats         # -> {'...': {'attempted': 1, 'succeeded': 0, 'failed': 1}}

``capture()`` is re-entrant-safe in the sense that nested captures share
one recorder; it is *not* safe to use from two threads at once, which is
fine -- naming is synchronous and the engine is single-threaded.

Architectural note
------------------
``perception.charge_perception`` documents "no module-level mutable
state" as an invariant, and that invariant is worth keeping: the
classifier must stay pure given its input mol.  The mutable counters
therefore live *here*, in a module the classifier only touches through a
boolean check, so the purity property of the perception layer is
unchanged whenever diagnostics are off -- which is always, in
production.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

_ENV_VAR = "OPENCHEM_NAMER_DEBUG"

# Set by capture(); when non-None it overrides the environment so a test
# or sweep can instrument without mutating os.environ for the process.
_active: "Recorder | None" = None


def _env_enabled() -> bool:
    raw = os.environ.get(_ENV_VAR, "")
    return raw.strip().lower() not in ("", "0", "false", "no", "off")


def enabled() -> bool:
    """True when instrumentation should record.

    Called on every charge-perception dispatch, so it stays a dict lookup
    plus a couple of comparisons.  Deliberately re-reads the environment
    rather than caching at import time: the variable is usually set from
    inside a already-running process (a REPL, a test) rather than at
    launch.
    """
    return _active is not None or _env_enabled()


# Why a charged molecule was handed back to the generic plan search.
# Only the reasons below can end in a neutralized name; the dispatcher's
# other early returns (substituent output forms, free valences, radical
# motifs routed to the other entry point) are legitimate routing and are
# deliberately not recorded.
REASONS = (
    "unclaimed",            # no classifier recognised the motif at all
    "ambiguous",            # >1 classification; dispatcher refuses to pick
    "partial_claim",        # classification left some charged atom uncovered
    "charge_sum_mismatch",  # per-site charges do not sum to the net charge
    "render_failed",        # motif claimed, renderer could not compose a name
)


@dataclass(frozen=True)
class NamingGap:
    """One point where a charged molecule fell through to the neutralizer.

    ``reason`` says which gate let it go, which is what tells you whether
    the fix belongs in a classifier or in a renderer -- a distinction that
    is invisible from the wrong name alone.  ``suffix_hint`` is empty for
    the reasons that fire before any classification exists.
    """

    reason: str
    smiles: str
    stage: str
    suffix_hint: str = ""


@dataclass
class Recorder:
    """Accumulates naming outcomes for one capture scope."""

    gaps: list[NamingGap] = field(default_factory=list)
    stats: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(
        self,
        suffix_hint: str,
        *,
        smiles: str,
        succeeded: bool,
        stage: str = "charge_perception.detect",
    ) -> None:
        """Record a render attempt by a classification that passed the gates."""
        bucket = self.stats.setdefault(
            suffix_hint, {"attempted": 0, "succeeded": 0, "failed": 0}
        )
        bucket["attempted"] += 1
        bucket["succeeded" if succeeded else "failed"] += 1
        if not succeeded:
            self.record_gap(
                "render_failed", smiles=smiles, stage=stage, suffix_hint=suffix_hint
            )

    def record_gap(
        self,
        reason: str,
        *,
        smiles: str,
        stage: str = "charge_perception.detect",
        suffix_hint: str = "",
    ) -> None:
        self.gaps.append(
            NamingGap(
                reason=reason, smiles=smiles, stage=stage, suffix_hint=suffix_hint
            )
        )

    def by_reason(self) -> dict[str, list[NamingGap]]:
        out: dict[str, list[NamingGap]] = {}
        for gap in self.gaps:
            out.setdefault(gap.reason, []).append(gap)
        return out

    def report(self) -> str:
        """Human-readable summary, weakest renderer first."""
        lines: list[str] = []
        if self.stats:
            rows = sorted(self.stats.items(), key=lambda kv: (-kv[1]["failed"], kv[0]))
            width = max(max(len(n) for n, _ in rows), len("renderer"))
            lines.append(f"{'renderer'.ljust(width)}  attempted  succeeded  failed")
            for name, c in rows:
                lines.append(
                    f"{name.ljust(width)}  {c['attempted']:9d}  "
                    f"{c['succeeded']:9d}  {c['failed']:6d}"
                )
        if self.gaps:
            grouped = self.by_reason()
            lines.append("")
            lines.append(f"gaps ({len(self.gaps)}) -- charge lost to the neutralizer:")
            for reason in REASONS:
                bucket = grouped.get(reason)
                if not bucket:
                    continue
                lines.append(f"  {reason} ({len(bucket)}):")
                for gap in bucket:
                    hint = f" [{gap.suffix_hint}]" if gap.suffix_hint else ""
                    lines.append(f"     {gap.smiles}{hint}")
        return "\n".join(lines) if lines else "nothing recorded"


# Recorder used when the env var is set but no capture() scope is open.
_ambient = Recorder()


def current() -> Recorder:
    """The recorder that :func:`record` writes to."""
    return _active if _active is not None else _ambient


def record(
    suffix_hint: str,
    *,
    smiles: str,
    succeeded: bool,
    stage: str = "charge_perception.detect",
) -> None:
    """Record one render outcome.  Callers must gate on :func:`enabled`.

    The gate is the caller's job rather than this function's because
    building ``smiles`` costs a canonicalisation, and paying that on every
    successful name just to throw it away would be a real cost in the hot
    path.
    """
    current().record(suffix_hint, smiles=smiles, succeeded=succeeded, stage=stage)


def record_gap(
    reason: str,
    *,
    smiles: str,
    stage: str = "charge_perception.detect",
    suffix_hint: str = "",
) -> None:
    """Record a decline that happened before any render was attempted."""
    current().record_gap(
        reason, smiles=smiles, stage=stage, suffix_hint=suffix_hint
    )


def reset() -> None:
    """Clear the ambient recorder."""
    _ambient.gaps.clear()
    _ambient.stats.clear()


@contextmanager
def capture() -> Iterator[Recorder]:
    """Record into a fresh recorder for the duration of the block.

    Enables instrumentation regardless of the environment variable, so a
    test can measure without touching ``os.environ``.
    """
    global _active
    previous = _active
    recorder = Recorder()
    _active = recorder
    try:
        yield recorder
    finally:
        _active = previous
