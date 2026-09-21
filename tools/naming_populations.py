"""The naming populations, and the one door a frozen one may be read through.

`benchmarks/naming/populations.toml` says which populations exist and which are
`tuning` (any tool may read them) or `frozen` (evaluation only). Every tool that
enumerates populations goes through this module, so "can this tool reach the
fresh held-out set" has one answer instead of one per tool.

**The refusal happens BEFORE the file is touched.** `path()` raises for a frozen
population unless `final_evaluation=True`, and it does not `exists()` it or open
it first, so a mistaken call cannot put a row in memory or even confirm the file
is there. This module names no population file: they are all in the registry,
which is the only place the lock test lets a frozen file's name live besides the
script that drew it.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmarks" / "naming"
REGISTRY = BENCH / "populations.toml"

TUNING = "tuning"
FROZEN = "frozen"


class FrozenPopulation(RuntimeError):
    """An evaluation-only population was requested outside the final evaluation."""


@dataclass(frozen=True)
class Population:
    key: str
    short: str
    file: str
    status: str

    @property
    def frozen(self) -> bool:
        return self.status == FROZEN


def registry() -> tuple[Population, ...]:
    """Every population in report order. Validated on every read: a typo in the
    status would otherwise read as 'not frozen', which is the unsafe default."""
    raw = tomllib.loads(REGISTRY.read_text(encoding="utf-8"))["population"]
    populations = tuple(
        Population(key=p["key"], short=p["short"], file=p["file"], status=p["status"])
        for p in raw
    )
    for p in populations:
        if p.status not in (TUNING, FROZEN):
            raise ValueError(f"{p.key}: status {p.status!r} is neither {TUNING!r} nor {FROZEN!r}")
    keys = [p.key for p in populations]
    if len(set(keys)) != len(keys) or len({p.file for p in populations}) != len(keys):
        raise ValueError("population keys and files must each be unique")
    return populations


def get(key: str) -> Population:
    for p in registry():
        if p.key == key:
            return p
    raise KeyError(key)


def path(key: str, *, final_evaluation: bool = False) -> Path:
    """Where a population's rows live, refusing a frozen one outside the final run."""
    population = get(key)
    if population.frozen and not final_evaluation:
        raise FrozenPopulation(
            f"{key} ({population.file}) is evaluation-only; "
            "it loads only through --final-evaluation"
        )
    return BENCH / population.file


def load(key: str, *, final_evaluation: bool = False) -> list[dict]:
    return json.loads(path(key, final_evaluation=final_evaluation).read_text(encoding="utf-8"))


def keys(*, final_evaluation: bool = False) -> list[str]:
    """The populations a caller may read now, in report order and only those whose
    file exists (a population not yet drawn is not an error)."""
    return [
        p.key
        for p in registry()
        if (final_evaluation or not p.frozen) and (BENCH / p.file).exists()
    ]


def tuning() -> tuple[Population, ...]:
    return tuple(p for p in registry() if not p.frozen)
