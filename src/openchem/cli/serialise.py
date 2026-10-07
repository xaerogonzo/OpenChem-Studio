"""Results as plain data, with nothing dropped and nothing guessed.

Every result type the registry produces (`PerAtomDataset`, `ReportResult`,
`StructureSetResult`, `PhCurveResult`, `TrajectoryResult`, the spectra, `AlertResult`)
is a plain dataclass, so one generic conversion covers all of them and **no field is
quietly left out by a per-type writer that was written before the field existed**.
That is the opposite trade to a hand-written serialiser per shape, and it is
deliberate: a calculator added tomorrow is serialised today.

What is NOT done silently:

* a value of a type the conversion does not know is written as
  `{"unserialisable": "<type name>"}` **and reported in `notes`** -- never
  `str(value)`, which would look like data;
* a non-finite float has no JSON spelling (`NaN` is not JSON), so it is `null`, noted;
* a payload over `max_bytes` is **withheld whole** (`payload: null`,
  `truncated: true`, its size stated) rather than cut mid-structure, because half a
  per-atom table that parses is a plausible wrong answer.

Enum members are written as their value, tuples and sets as lists (a set in sorted
order, so the output is stable), and dataclasses as objects. A dataclass carries no
type tag of its own; the result's class name is written beside it by the caller.
"""

from __future__ import annotations

#: What the reachability guard accepts for a module reached only through the command
#: line. See `cli/commands.py` for what this declares; the same mechanism, one hop
#: further in (this module is imported by `commands`, which the script enters).
REACHED_BY = (
    "console_script: imported only by openchem.cli.commands, which is itself entered "
    "by the `openchem-cli` console script rather than by an import from openchem.main"
)

import dataclasses
import datetime
import json
import math
from enum import Enum
from pathlib import PurePath
from typing import Any

#: Bytes of JSON a result may occupy before it is withheld. One calculator's whole
#: result is normally a few kilobytes; a trajectory or a large per-atom table is the
#: reason there is a limit at all.
DEFAULT_MAX_BYTES = 1_000_000


def to_plain(value: Any, notes: list[str]) -> Any:
    """`value` as JSON-compatible data. Anything it cannot convert is noted."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        notes.append(f"a non-finite value ({value}) is written as null")
        return None
    if isinstance(value, Enum):
        return to_plain(value.value, notes)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_plain(getattr(value, f.name), notes) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): to_plain(v, notes) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        items = [to_plain(v, notes) for v in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, (list, tuple)):
        return [to_plain(v, notes) for v in value]
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, PurePath):
        return str(value)
    # numpy scalars and arrays arrive through RDKit; `item`/`tolist` are their own
    # conversions and are the only duck-typed ones, so nothing else is guessed at.
    for converter in ("item", "tolist"):
        method = getattr(value, converter, None)
        if callable(method):
            try:
                return to_plain(method(), notes)
            except (TypeError, ValueError):
                break
    notes.append(f"a value of type {type(value).__name__} is not serialisable")
    return {"unserialisable": type(value).__name__}


def result_payload(result: Any, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    """One result as `{kind, payload, payload_bytes, truncated, notes}`.

    `payload` is `None` only when the result was withheld for size, and then
    `truncated` is true and `payload_bytes` says how big it was.
    """
    notes: list[str] = []
    payload = to_plain(result, notes)
    size = len(json.dumps(payload, allow_nan=False).encode("utf-8"))
    withheld = size > max_bytes
    if withheld:
        notes.append(
            f"the payload is {size:,} bytes against --max-bytes {max_bytes:,} and was "
            f"withheld whole; raise --max-bytes to receive it"
        )
    return {
        "kind": type(result).__name__,
        "payload": None if withheld else payload,
        "payload_bytes": size,
        "truncated": withheld,
        "notes": sorted(set(notes)),
    }
