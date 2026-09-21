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


def meta_path(key: str) -> Path:
    """`<stem>.json` -> `<stem>.meta.json`: the convention every population's meta file follows."""
    return BENCH / (Path(get(key).file).stem + ".meta.json")


#: Salt for the membership hashes a frozen population's meta carries. The drawing scripts (`build_heldout.py`, and the Blue Book harvest) hash with
#: THIS constant and this function, so the meta can never carry a hash the probe cannot reproduce.
MEMBERSHIP_SALT = "openchem-naming-frozen-membership-v1"


def membership_hash(canonical_smiles: str, salt: str = MEMBERSHIP_SALT) -> str:
    import hashlib

    return hashlib.sha256((salt + canonical_smiles).encode("utf-8")).hexdigest()


def membership_hashes(rows: list[dict]) -> list[str]:
    """Sorted salted SHA-256 of every row's canonical SMILES, for a frozen population's meta file.

    **Why the meta carries hashes of the rows.** A frozen population's rows may not be read, but `tools/naming_probe.py` names any SMILES it is
    handed, so a frozen row could be typed in by hand while debugging something else. A hash lets the probe ask "is this structure in a frozen
    population" without opening the file and without the meta holding a row. It guards an accident, not a secret: the salt is public and a known
    compound is trivially re-hashed.
    """
    return sorted(membership_hash(row["smiles"]) for row in rows)


def frozen_membership() -> dict[str, tuple[str, frozenset[str]]]:
    """For every frozen population: the salt and the set of salted SHA-256 hashes of its rows' canonical SMILES, read from the META
    file only. The frozen file itself is never touched, and the meta holds hashes, not rows.

    A frozen population registered without membership hashes is an ERROR, not an empty set: an empty set would read as "nothing is
    frozen" to the one tool (the probe) that uses this to refuse a structure, which is the unsafe default.
    """
    membership: dict[str, tuple[str, frozenset[str]]] = {}
    for population in registry():
        if not population.frozen:
            continue
        meta = json.loads(meta_path(population.key).read_text(encoding="utf-8"))
        salt, hashes = meta.get("membership_salt"), meta.get("membership_sha256")
        if not salt or not hashes:
            raise ValueError(f"{population.key} is frozen but its meta carries no membership hashes")
        membership[population.key] = (salt, frozenset(hashes))
    return membership


def frozen_key_of(canonical_smiles: str) -> str | None:
    """The key of the frozen population that holds this canonical SMILES, or None.

    A guard against an ACCIDENT (typing a frozen row into the probe while debugging something else), not a secret: the salt is public and
    a known compound is trivially re-hashed. The argument must already be canonical (`Chem.MolToSmiles`), as the rows were when hashed.
    """
    for key, (salt, hashes) in frozen_membership().items():
        if membership_hash(canonical_smiles, salt) in hashes:
            return key
    return None
