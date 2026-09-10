"""Turn a calculator result into text you can paste somewhere useful.

**THE DISPATCH MOVED TO `ui/result_adapters.py`; THIS IS ITS CLIPBOARD ENTRY
POINT.** The formatting rules and every adapter travelled with it, comments
intact -- what changed is ownership. This module grew a type-keyed table and
described itself as "the third registry in this codebase to use it", and three
registries over one vocabulary is three chances to disagree about what a result
IS. They did disagree, identically, three times: a `VibrationalSpectrumResult`
was rendered as an NMR spectrum by all three, because it subclasses
`SpectrumResult`. See `result_adapters` for the measurement.

The clipboard is a CONSUMER of that vocabulary, not its owner. Re-exported
rather than moved outright so the five importers of `result_to_text` -- two
production, three test files -- are untouched, which is what makes the move
behaviour-neutral by construction rather than by re-testing. `ui/visualization.py`
re-exports the moved domain types for exactly the same reason.

The formatting conventions still hold and are documented where the adapters
now live: tabular results are TAB-SEPARATED so they paste into Excel, Sheets
or Origin as real columns, while a prettily-aligned block pastes as a single
ruined column. Text results stay plain lines.
"""

from __future__ import annotations

from openchem.ui.result_adapters import result_to_text

__all__ = ["result_to_text"]
