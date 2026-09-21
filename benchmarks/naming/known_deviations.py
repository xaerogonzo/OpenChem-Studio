"""The declared deviations of `known_deviations.toml`, and the one question a scorer asks of them: does this NAME carry one? (naming round 8)

A name that carries a declared legacy locant is reported as a KNOWN DEVIATION and is never counted as an exact PREFERRED match, whatever it round-trips to and
whatever a reference name says. The file's header says why each exists.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

PATH = Path(__file__).parent / "known_deviations.toml"

#: the ring-name stems, as they appear inside a NAME, that a legacy label is only a deviation next to
_RING_STEM = {
    "pyrene": r"pyren",
    "perylene": r"perylen",
    "2,3,3a,4,5,6-hexahydro-1H-benz[de]isoquinoline": r"benz\[de\]isoquinolin",
}


def load() -> list[dict]:
    return tomllib.loads(PATH.read_text(encoding="utf-8"))["deviation"]


def deviation_in(name: str | None) -> str | None:
    """The id of the declared deviation a NAME carries, or None. A legacy label counts only in a name that also names the ring it belongs to."""
    if not name:
        return None
    for dev in load():
        stem = _RING_STEM.get(dev["ring"])
        if stem is None or not re.search(stem, name):
            continue
        for label in dev["engine"]:
            if re.search(rf"(?<![\w.]){re.escape(label)}(?![\w])", name):
                return dev["id"]
    return None
