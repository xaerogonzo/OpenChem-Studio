"""Calculation results to JSON-safe data and back, losslessly or not at all.

**WHY THIS EXISTS.** A project file used to hold structures and nothing that
was computed from them, so reopening a project reran every calculator. No
result type had a `to_dict`: 283 real results swept across the registry and
the always-on provider, on three molecules, reach 21 dataclasses from six
`openchem.domain` modules, eight enums, tuples, lists, and dicts keyed by
`str` AND by `int` (per-atom values). This is one walker over that shape
rather than 21 hand-written pairs that would each drift on their own.

**WHAT IT REFUSES, AND WHY EACH IS ITS OWN ANSWER.**

    unknown_type          a class not on the allowlist (encode or decode)
    unsupported_version   a known class, written by a NEWER layout
    malformed             the right class, but the fields will not build it

These are kept apart because they mean different things to a reader of a
saved project: "this build does not know that kind of result", "a newer
build wrote this", and "this entry is damaged". Collapsing them would make a
version skew look like corruption.

**THE ALLOWLIST IS THE SECURITY BOUNDARY.** Decoding constructs only classes
defined in `_MODULES`, looked up by a qualified name -- never an import path
read from the file, and never pickle. A project is something people email.

**TYPE VERSIONS.** Every dataclass is written with `__version__`. All are 1
today; a layout change bumps `TYPE_VERSIONS` and registers a migration in
`MIGRATIONS` that rewrites the older field dict before construction.

A NEWER version is refused even when it would happen to construct: a newer
layout may have changed what an existing field MEANS, and "it parsed" is not
"it means the same thing". A field unknown to this build on a version it
DOES support is dropped with a warning -- reachable only from a layout change
that forgot to bump its version, which the warning exists to make visible.
"""

from __future__ import annotations

import dataclasses
import enum
import importlib
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("openchem.result_codec")

#: The modules whose dataclasses and enums a result may contain. Measured,
#: not guessed: these six are exactly the modules the registry sweep reached.
_MODULES = (
    "openchem.domain.common",
    "openchem.domain.descriptor",
    "openchem.domain.report",
    "openchem.domain.scientific_result",
    "openchem.domain.structure_issue",
    "openchem.domain.visualization",
)

#: A class not on the allowlist, met while encoding or decoding.
UNKNOWN_TYPE = "unknown_type"
#: A known class written by a NEWER layout than this build reads.
UNSUPPORTED_VERSION = "unsupported_version"
#: The right class, but its fields will not build it.
MALFORMED = "malformed"
#: Every reason an entry can fail to decode, kept apart on purpose -- see
#: the module docstring for why a version skew must not look like damage.
PROBLEMS = (UNKNOWN_TYPE, UNSUPPORTED_VERSION, MALFORMED)

#: Layout version per type name. Absent means 1.
TYPE_VERSIONS: dict[str, int] = {
    # v2 (2026-09-17) added `structure_molblock` and `structure_fingerprint`, which change
    # what `values`' indices MEAN when present. An older build that dropped them as unknown
    # would draw an acid's pH charges on the wrong atoms, so it must refuse instead.
    "scientific_result.PerAtomDataset": 2,
}

#: (type name, version found) -> a function rewriting that version's field
#: dict into the next version's. Applied repeatedly until current.
MIGRATIONS: dict[tuple[str, int], Callable[[dict[str, Any]], dict[str, Any]]] = {
    # A v1 dataset describes the drawing or its stored conformer; the new fields' empty
    # defaults say exactly that.
    ("scientific_result.PerAtomDataset", 1): lambda fields: dict(fields),
}

#: Key naming a dataclass, by `module.QualName` under `_MODULES`.
_TYPE = "__type__"
#: Key carrying that dataclass's layout version.
_VERSION = "__version__"
#: Key naming an enum; its member is stored by NAME, not value.
_ENUM = "__enum__"
#: A tuple, which JSON would otherwise turn into a list.
_TUPLE = "__tuple__"
#: A set, which JSON has no form for.
_SET = "__set__"
#: A frozenset, kept apart from a set so the type survives.
_FROZENSET = "__frozenset__"
#: A dict written as key/value PAIRS -- how int keys survive JSON.
_DICT = "__dict__"
#: Every marker key: a plain dict using one of these as a key is written as
#: pairs instead, so it cannot be mistaken for a tagged value on the way back.
_MARKERS = (_TYPE, _ENUM, _TUPLE, _SET, _FROZENSET, _DICT)


class CodecError(ValueError):
    def __init__(self, problem: str, detail: str) -> None:
        super().__init__(f"{problem}: {detail}")
        self.problem = problem
        self.detail = detail


def _name_of(cls: type) -> str:
    return f"{cls.__module__.rsplit('.', 1)[-1]}.{cls.__qualname__}"


def _build_allowlist() -> dict[str, type]:
    allowed: dict[str, type] = {}
    for module_name in _MODULES:
        module = importlib.import_module(module_name)
        for value in vars(module).values():
            if not isinstance(value, type) or value.__module__ != module_name:
                continue
            if dataclasses.is_dataclass(value) or issubclass(value, enum.Enum):
                allowed[_name_of(value)] = value
    return allowed


#: The allowlist, built on first use: importing every domain module at this
#: module's import would drag half the domain in for a caller that never
#: decodes anything.
_ALLOWED: dict[str, type] | None = None


def allowed_types() -> dict[str, type]:
    global _ALLOWED
    if _ALLOWED is None:
        _ALLOWED = _build_allowlist()
    return _ALLOWED


def encode(value: Any) -> Any:
    """`value` as JSON-safe data. Raises `CodecError` for anything unlisted."""
    # ENUM FIRST, BEFORE ANY `str` TEST. `Basis`, `FactCategory`, `Detail`
    # and `CacheState` are `str` subclasses, so an `isinstance(value, str)`
    # above this line wrote every one of them as a bare string -- and a
    # str-enum compares EQUAL to its value, so a round trip checked with
    # `==` passed while every restored fact crashed the reader on
    # `fact.basis.value`. Found by replaying into the real window.
    if isinstance(value, enum.Enum):
        name = _name_of(type(value))
        if name not in allowed_types():
            raise CodecError(UNKNOWN_TYPE, name)
        return {_ENUM: name, "name": value.name}
    if value is None or type(value) in (bool, str, int, float):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        name = _name_of(type(value))
        if name not in allowed_types():
            raise CodecError(UNKNOWN_TYPE, name)
        out: dict[str, Any] = {_TYPE: name, _VERSION: TYPE_VERSIONS.get(name, 1)}
        for f in dataclasses.fields(value):
            out[f.name] = encode(getattr(value, f.name))
        return out
    if type(value) is list:
        return [encode(v) for v in value]
    if type(value) is tuple:
        return {_TUPLE: [encode(v) for v in value]}
    if type(value) in (set, frozenset):
        return {(_SET if type(value) is set else _FROZENSET): [encode(v) for v in value]}
    if type(value) is dict:
        # A plain object only when that cannot be mistaken for a marker;
        # otherwise explicit pairs, which is how int keys survive at all.
        if all(type(k) is str and k not in _MARKERS for k in value):
            return {k: encode(v) for k, v in value.items()}
        return {_DICT: [[encode(k), encode(v)] for k, v in value.items()]}
    raise CodecError(UNKNOWN_TYPE, f"{type(value).__module__}.{type(value).__qualname__}")


def decode(data: Any) -> Any:
    """The inverse of `encode`. Raises `CodecError` rather than guessing."""
    if isinstance(data, list):
        return [decode(v) for v in data]
    if not isinstance(data, dict):
        return data
    if _ENUM in data:
        cls = allowed_types().get(data[_ENUM])
        if cls is None or not issubclass(cls, enum.Enum):
            raise CodecError(UNKNOWN_TYPE, str(data[_ENUM]))
        try:
            return cls[data["name"]]
        except KeyError as exc:
            raise CodecError(MALFORMED, f"{data[_ENUM]} has no member {data.get('name')!r}") from exc
    if _TUPLE in data:
        return tuple(decode(v) for v in data[_TUPLE])
    if _SET in data:
        return {decode(v) for v in data[_SET]}
    if _FROZENSET in data:
        return frozenset(decode(v) for v in data[_FROZENSET])
    if _DICT in data:
        try:
            return {decode(k): decode(v) for k, v in data[_DICT]}
        except (TypeError, ValueError) as exc:
            raise CodecError(MALFORMED, f"dict pairs: {exc}") from exc
    if _TYPE in data:
        return _decode_dataclass(data)
    return {k: decode(v) for k, v in data.items()}


def _decode_dataclass(data: dict[str, Any]) -> Any:
    name = data[_TYPE]
    cls = allowed_types().get(name)
    if cls is None or not dataclasses.is_dataclass(cls):
        raise CodecError(UNKNOWN_TYPE, str(name))
    current = TYPE_VERSIONS.get(name, 1)
    version = data.get(_VERSION, 1)
    if not isinstance(version, int) or version > current:
        raise CodecError(UNSUPPORTED_VERSION, f"{name} v{version} (this build reads up to v{current})")
    fields_data = {k: v for k, v in data.items() if k not in (_TYPE, _VERSION)}
    while version < current:
        migrate = MIGRATIONS.get((name, version))
        if migrate is None:
            raise CodecError(UNSUPPORTED_VERSION, f"{name} v{version} has no migration")
        fields_data = migrate(fields_data)
        version += 1

    known = {f.name: f for f in dataclasses.fields(cls)}
    unknown = set(fields_data) - set(known)
    if unknown:
        logger.warning("Ignoring unknown fields on %s: %s", name, sorted(unknown))
    init_kwargs: dict[str, Any] = {}
    late: dict[str, Any] = {}
    for field_name, f in known.items():
        if field_name not in fields_data:
            continue
        value = decode(fields_data[field_name])
        (init_kwargs if f.init else late)[field_name] = value
    try:
        obj = cls(**init_kwargs)
    except TypeError as exc:
        raise CodecError(MALFORMED, f"{name}: {exc}") from exc
    for field_name, value in late.items():
        # `object.__setattr__` because most of these classes are frozen.
        object.__setattr__(obj, field_name, value)
    return obj
