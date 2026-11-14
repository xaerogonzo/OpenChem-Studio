"""Find a NaN or infinity anywhere in a result before it is shown, stored or sent to a model.

WHY THIS EXISTS. Measured 2026-11-13 (`benchmarks/hypervalent/defect_scan.py`): RDKit's Gasteiger charges are NaN for P with
five bonds, for xenon and for iodine(III), and the application published them, in Properties and in the per-atom data,
for PF5, XeF2, XeF4, IF5, PCl5, phenyl-iodine diacetate and CH3-PF4. A calculator that does not cover an element used to
say so only when its author remembered to; this is the one place that catches the ones that did not.

WHAT COUNTS. Any float (a Python one or a NumPy scalar or array) that is NaN or infinite, anywhere inside a result's
fields, dicts, lists, tuples and sets. A string such as "nan" is text, not a number, and is left alone: a display value
is produced FROM a number, so a non-finite number is caught where it is stored.

It reads and never changes a result, has no Qt and no chemistry, and walks a bounded amount (a result is not a graph; a
cycle or a very large array would otherwise be a hazard).
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openchem.domain.calculator import CalculationRefusal

#: Deepest nesting walked: a result is a shallow record, so more means something other than a result was handed in.
MAX_DEPTH = 8
#: Most values looked at in one result, so a very large array of objects cannot hang a worker; the walk stops there.
MAX_ITEMS = 200_000


@dataclass(frozen=True)
class NonFinite:
    """One non-finite number: where it sits, and which atom it belongs to when that is knowable."""

    path: str
    #: The atom index, for a per-atom dataset (`values[3]`); None otherwise.
    atom: int | None = None


def non_finite_in(result: Any) -> list[NonFinite]:
    """Every non-finite number inside `result`, in the order met; empty when there is none."""
    found: list[NonFinite] = []
    budget = [MAX_ITEMS]
    _walk(result, "", None, 0, found, budget, set())
    return found


def _is_number_array(value: Any) -> bool:
    return hasattr(value, "dtype") and hasattr(value, "shape") and hasattr(value, "tolist")


def _walk(value: Any, path: str, atom: int | None, depth: int, found: list[NonFinite], budget: list[int], seen: set[int]) -> None:
    if budget[0] <= 0 or depth > MAX_DEPTH:
        return
    budget[0] -= 1
    if isinstance(value, bool) or value is None or isinstance(value, (str, bytes, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            found.append(NonFinite(path or "value", atom))
        return
    if _is_number_array(value):
        try:
            import numpy as np

            array = np.asarray(value)
            if array.dtype.kind in "fc" and not np.all(np.isfinite(array)):
                found.append(NonFinite(path or "value", atom))
        except Exception:  # noqa: BLE001 - an odd array is not a reason to lose the result
            return
        return
    identity = id(value)
    if identity in seen:
        return
    seen.add(identity)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            _walk(getattr(value, field.name, None), f"{path}.{field.name}" if path else field.name, atom, depth + 1, found, budget, seen)
    elif isinstance(value, dict):
        for key, item in value.items():
            index = key if isinstance(key, int) and not isinstance(key, bool) else None
            # `values` of a per-atom dataset is {atom index: number}; any other int-keyed dict is still reported by path.
            _walk(item, f"{path}[{key!r}]", index if index is not None else atom, depth + 1, found, budget, seen)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for position, item in enumerate(value):
            _walk(item, f"{path}[{position}]", atom, depth + 1, found, budget, seen)
    seen.discard(identity)


def refusal_for(result: Any, what: str, element_of: Any = None) -> CalculationRefusal | None:
    """A `CalculationRefusal` (a LIMIT, `ELEMENT_OUTSIDE_PARAMETER_SET`) when `result` holds a non-finite number, else None.

    `what` names the calculation in the sentence. `element_of(atom_index)` returns an element symbol, or None, so a
    per-atom dataset can name the elements it failed on; without it the sentence says only that a number was not finite.
    A non-finite number from a method means the method has no parameters for something in the structure, which is
    a limit of the method, not a fault in the application and not an answer.
    """
    from openchem.domain.calculator import ELEMENT_OUTSIDE_PARAMETER_SET, CalculationRefusal

    bad = non_finite_in(result)
    if not bad:
        return None
    elements: list[str] = []
    if element_of is not None and getattr(result, "values", None) is not None:
        for item in bad:
            if item.atom is not None:
                try:
                    symbol = element_of(item.atom)
                except Exception:  # noqa: BLE001 - naming an element is a courtesy
                    symbol = None
                if symbol and symbol not in elements:
                    elements.append(symbol)
    where = f" on {', '.join(elements)}" if elements else ""
    return CalculationRefusal(
        ELEMENT_OUTSIDE_PARAMETER_SET,
        "Method has no parameters for part of this structure",
        f"{what} produced a number that is not finite{where}, which means the method has no parameters for that part of the "
        f"structure. No value is shown rather than one that cannot be right.",
    )
