"""Where an ORCA geometry optimization is, read from its stdout as it arrives.

The application used to show only the last line of each stdout chunk, so a person watching a long optimization
saw a random sample of ORCA's lines and no cycle number, energy or convergence table. This module reads the whole
stream and keeps a small immutable snapshot of what it can say: the cycle, the energy and its change, the five
convergence criteria with their thresholds, and how often ORCA rebuilt its optimizer state.

**Nothing here is invented.** A field ORCA has not printed yet is ``None`` (or empty), never zero: "no energy
change yet" and "an energy change of 0" are different statements. A line this parser does not recognise is
skipped, so a changed ORCA message costs a missing field and never a wrong one.

Pure text in, dataclass out: no Qt, no RDKit, so it can sit in the chemistry layer and be tested on real output.
The formats were read from ORCA 6.1.1 transcripts (``tests/fixtures/orca/bde_hcn_parent_optfreq.out``).

Two traps measured on that output, both worth knowing before changing a regex:

* ``(2022 redundants)`` in ORCA's "Making the new internal coordinates" line is the NAME of the coordinate scheme,
  not a count of coordinates (a three-atom molecule prints it too). It is deliberately not parsed as a number.
* The first cycle's convergence table has no "Energy change" row (there is no previous energy), so the table
  holds four criteria then and five afterwards; ``ConvergenceItem`` rows are whatever the table printed.
"""

from __future__ import annotations

import re

from openchem.domain.opt_progress import CRITERIA_NAMES, ConvergenceItem, OptProgress

__all__ = ["CRITERIA_NAMES", "ConvergenceItem", "OptProgress", "OrcaProgressParser"]

_NUMBER = r"[-+]?\d+\.\d+(?:[eE][-+]?\d+)?"
_CYCLE_RE = re.compile(r"GEOMETRY OPTIMIZATION CYCLE\s+(\d+)")
_MAX_CYCLES_RE = re.compile(r"Max\. no of cycles\s+MaxIter\s+\.\.\.\.\s+(\d+)")
_FINAL_ENERGY_RE = re.compile(r"FINAL SINGLE POINT ENERGY\s+(" + _NUMBER + ")")
_TABLE_HEADER_RE = re.compile(r"\|Geometry convergence\|")
_TABLE_ROW_RE = re.compile(
    r"^\s*(" + "|".join(re.escape(name) for name in CRITERIA_NAMES) + r")\s+(" + _NUMBER + r")\s+(" + _NUMBER + r")\s+(YES|NO)\s*$"
)
# An SCF iteration row: index, energy (many decimals), delta-E in exponent form. The energy column is what keeps this
# from matching the many other indented integer-first lines in ORCA's output.
_SCF_ROW_RE = re.compile(r"^\s{1,4}(\d+)\s+-\d+\.\d{6,}\s+[-+]?\d\.\d+e[-+]\d+")
_RESET_MARK = "Reseting .opt file and rebuilding internals"  # ORCA's own spelling
_BACK_TRANSFORM_MARKS = ("RMS(Cart) too big", "RMS(Cart) increases")
_CONVERGED_MARK = "THE OPTIMIZATION HAS CONVERGED"
# NOT verified against a real transcript: the wording ORCA prints on hitting MaxIter was not available when this
# was written, so both likely phrasings are accepted and a test pins only what a real run was seen to print.
_NOT_CONVERGED_RE = re.compile(r"OPTIMIZATION DID NOT CONVERGE|did not converge but reached the maximum", re.IGNORECASE)


class OrcaProgressParser:
    """Incremental reader: ``feed`` stdout chunks as they arrive, read ``snapshot`` at any time.

    ``readyReadStandardOutput`` promises nothing about where a chunk ends, so a trailing partial line is held back
    and completed by the next chunk; reading it early would match half a number.
    """

    #: Longest energy history kept. A 1000-cycle optimization is already far outside normal use.
    MAX_HISTORY = 5000

    def __init__(self) -> None:
        self._pending = ""
        self._cycle: int | None = None
        self._max_cycles: int | None = None
        self._energies: list[float] = []
        self._criteria: list[ConvergenceItem] = []
        self._building: list[ConvergenceItem] | None = None
        self._scf_iteration: int | None = None
        self._resets = 0
        self._failures = 0
        self._converged = False
        self._reached_max = False

    def feed(self, chunk: str) -> OptProgress:
        """Read `chunk` and return the snapshot after it."""
        text = self._pending + chunk.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        # The last element is an unterminated line (or "" when the chunk ended on a newline).
        self._pending = lines.pop()
        for line in lines:
            self._line(line)
        return self.snapshot()

    def finish(self) -> OptProgress:
        """Read a final unterminated line, for use when the process has ended."""
        if self._pending:
            line, self._pending = self._pending, ""
            self._line(line)
        if self._building:  # the output ended inside the table: what it printed is all there will be
            self._criteria, self._building = self._building, None
        return self.snapshot()

    def snapshot(self) -> OptProgress:
        change = self._energies[-1] - self._energies[-2] if len(self._energies) >= 2 else None
        return OptProgress(
            cycle=self._cycle,
            max_cycles=self._max_cycles,
            energy=self._energies[-1] if self._energies else None,
            energy_change=change,
            criteria=tuple(self._criteria),
            energy_history=tuple(self._energies),
            scf_iteration=self._scf_iteration,
            resets=self._resets,
            back_transform_failures=self._failures,
            converged=self._converged,
            reached_max_cycles=self._reached_max,
        )

    # -- one line ------------------------------------------------------------------------------------------------

    def _line(self, line: str) -> None:
        if self._building is not None:
            row = _TABLE_ROW_RE.match(line)
            if row:
                self._building.append(
                    ConvergenceItem(row.group(1), float(row.group(2)), float(row.group(3)), row.group(4) == "YES")
                )
                return
            if self._building and not line.lstrip().startswith(("Item", "-", ".")):
                # The first line after the rows ends the table; publish it whole, never a half-read one.
                self._criteria, self._building = self._building, None
            elif not self._building and not line.strip():
                self._building = None  # a header with no rows: leave the previous table in place
        if _RESET_MARK in line:
            self._resets += 1
            return
        if any(mark in line for mark in _BACK_TRANSFORM_MARKS):
            self._failures += 1
            return
        match = _CYCLE_RE.search(line)
        if match:
            self._cycle = int(match.group(1))
            self._scf_iteration = None
            return
        match = _MAX_CYCLES_RE.search(line)
        if match:
            self._max_cycles = int(match.group(1))
            return
        match = _FINAL_ENERGY_RE.search(line)
        if match:
            self._energies.append(float(match.group(1)))
            if len(self._energies) > self.MAX_HISTORY:
                del self._energies[0]
            return
        if _TABLE_HEADER_RE.search(line):
            self._building = []
            return
        if _CONVERGED_MARK in line:
            self._converged = True
            return
        if _NOT_CONVERGED_RE.search(line):
            self._reached_max = True
            return
        match = _SCF_ROW_RE.match(line)
        if match:
            self._scf_iteration = int(match.group(1))
