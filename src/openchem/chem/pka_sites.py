"""Mapped pKa sites as persisted result data, not calculator input.

The pKa text list stays an `AlertResult` of lines. The viewer and the species
ladder need the model's atom index, kind, spread, and the two site-state
tuples. Those live here so pKa and Microspecies Distribution can store the
same projection, survive a save, and not depend on the in-process `compute_pka`
cache after restart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openchem.chem.ionisable_sites import UNKNOWN, kind_of

#: Provenance.parameters key. Result data, not a setting the calculator was run with.
SITES_KEY = "pka_site_records"

#: More than this many ionisable sites: pictures are omitted; the chart stays.
MAX_PICTURE_SITES = 8

#: Hide a picture when that species never reaches this percent on the sampled grid.
MIN_PICTURE_PERCENT = 0.01


@dataclass(frozen=True)
class PkaSiteRecord:
    """One predicted centre, ready to label an atom or to rebuild a protonation step."""

    atom_index: int | None
    pka: float
    spread: float
    kind: str
    protonated_site: tuple[int, int] | None
    deprotonated_site: tuple[int, int] | None

    def to_plain(self) -> dict[str, Any]:
        """JSON-compatible dict. Tuples become two-item lists."""
        return {
            "atom_index": self.atom_index,
            "pka": self.pka,
            "spread": self.spread,
            "kind": self.kind,
            "protonated_site": list(self.protonated_site) if self.protonated_site is not None else None,
            "deprotonated_site": list(self.deprotonated_site) if self.deprotonated_site is not None else None,
        }

    @classmethod
    def from_plain(cls, data: object) -> PkaSiteRecord | None:
        if not isinstance(data, dict):
            return None
        try:
            pka = float(data["pka"])
            spread = float(data.get("spread") or 0.0)
        except (KeyError, TypeError, ValueError):
            return None
        index = data.get("atom_index")
        if index is not None:
            try:
                index = int(index)
            except (TypeError, ValueError):
                return None
        kind = str(data.get("kind") or UNKNOWN)
        return cls(
            atom_index=index,
            pka=pka,
            spread=spread,
            kind=kind,
            protonated_site=_pair(data.get("protonated_site")),
            deprotonated_site=_pair(data.get("deprotonated_site")),
        )


def _pair(value: object) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return int(value[0]), int(value[1])
    except (TypeError, ValueError):
        return None


def ordered_predictions(predictions) -> list:
    """Lowest pKa first, then mapped atom index, then original position.

    The same order `read_sites` and the sequential distribution use. Equal
    pKa values stay deterministic: a None index sorts before a mapped one.
    """
    indexed = list(enumerate(predictions or ()))
    indexed.sort(
        key=lambda item: (
            float(item[1].value),
            item[1].atom_index if item[1].atom_index is not None else -1,
            item[0],
        )
    )
    return [prediction for _index, prediction in indexed]


def records_from_predictions(predictions) -> tuple[PkaSiteRecord, ...]:
    """Project `PkaPrediction`s in the shared order. Kind comes only from `kind_of`."""
    return tuple(
        PkaSiteRecord(
            atom_index=prediction.atom_index,
            pka=float(prediction.value),
            spread=float(prediction.stddev or 0.0),
            kind=kind_of(prediction.protonated_site),
            protonated_site=prediction.protonated_site,
            deprotonated_site=prediction.deprotonated_site,
        )
        for prediction in ordered_predictions(predictions)
    )


def dump_records(records: tuple[PkaSiteRecord, ...] | list[PkaSiteRecord]) -> list[dict[str, Any]]:
    return [record.to_plain() for record in records]


def load_records(payload: object) -> tuple[PkaSiteRecord, ...]:
    if not isinstance(payload, list):
        return ()
    records = []
    for item in payload:
        record = PkaSiteRecord.from_plain(item)
        if record is None:
            return ()
        records.append(record)
    return tuple(records)


def records_from_provenance(provenance) -> tuple[PkaSiteRecord, ...]:
    if provenance is None:
        return ()
    parameters = getattr(provenance, "parameters", None) or {}
    return load_records(parameters.get(SITES_KEY))


def with_site_records(parameters: dict[str, Any] | None, records: tuple[PkaSiteRecord, ...]) -> dict[str, Any]:
    """Copy calculator parameters and attach the site projection under `SITES_KEY`."""
    out = dict(parameters or {})
    out[SITES_KEY] = dump_records(records)
    return out


def site_marker(kind: str) -> str:
    """Letter drawn next to a mapped atom. Colour is separate; unknown is never an acid/base hue."""
    from openchem.chem.ionisable_sites import ACID, BASE

    if kind == ACID:
        return "A"
    if kind == BASE:
        return "B"
    return "?"


def species_index_from_name(name: str) -> int | None:
    """`Species 2` or `Species 2 (+1)` -> 2. Anything else is not a sequential species label."""
    text = (name or "").strip()
    if not text.startswith("Species "):
        return None
    rest = text[len("Species "):].split(" ", 1)[0]
    try:
        return int(rest)
    except ValueError:
        return None
