# Salt composition slice 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Mode A for two molecular neutrals: proton-transfer accounting, `balance_two` on the product ions, multiplicity-weighted formula-unit conservation, and the two v1 refusals (NaOH neutralization; neutral + supplied ion with no proton source).

**Architecture:** Policy stays in `domain/salt_stoichiometry.py` (opaque identities, integer charges, frozen element-count maps). `chem/salt_mode_a.py` turns four molecules into those maps, classifies a metal hydroxide, and calls the domain function. No pKa, no ionization ladder, no Mode C, no UI. The caller supplies the four structures (two parents, two product ions); this slice does not invent a microspecies.

**Tech Stack:** Python 3.11+, existing `balance_two`, RDKit only in `chem/` and tests, pytest. Worktree pytest: set `PYTHONPATH` to this worktree `src` and use the main-checkout venv if `uv run pytest` cannot import PySide6.

## Global Constraints

- Work on `cursor/salt-composition-slice-2` (this worktree), from `origin/master` after #579. Not `claude/vendoring-fork-100-squash`.
- No UI, no calculator registry, no pKa, no Mode C, no ionic-species JSON, no CIF/COD, no ion-pair 3D, no hydrates as first-class, no `balance_many`, no NaOH neutralization path (it is a **refusal**, not an implementation).
- Domain must not import `rdkit`, `openbabel`, `PySide6`, or `openchem.chem.lattice_energy`.
- Conservation is multiplicity-weighted over the complete formula unit: `n_base * counts(B) + n_acid * counts(HA) == n_C * counts(cation) + n_A * counts(anion)` where `(n_C, n_A)` come from `balance_two`. A 1:1 check of B against BH2²⁺ is the wrong check.
- Both parents in workflow 1 are `molecular_neutral` with charge 0. A `metal_hydroxide` parent is `hydroxide_neutralization`. Mixing `molecular_neutral` with `ion` is `missing_proton_source`.
- `charge_valid` on a successful Mode A result is True (`sum n_i z_i == 0` at assigned multiplicities).
- Changelog is a fragment (`tools/changelog.py new`), not an edit of `CHANGELOG.md`.
- New test files: `python tools/suite_shards.py --pin-new` with **no** `--splits=3` (default is the 8-way table CI uses).
- Tests that would pass if identity were formula+charge must use two different constitutions with the same formula.
- New `src/openchem` modules need `REACHED_BY = ("tooling: ...")` until something reachable from `openchem.main` imports them. Adding functions to `salt_stoichiometry.py` keeps its existing declaration.
- After adding a `chem/*.py` file, update `docs/ARCHITECTURE.md` chem count and name the module in the package map.

---

### Task 1: Domain formula-unit conservation

**Files:**
- Modify: `src/openchem/domain/salt_stoichiometry.py`
- Test: `tests/test_salt_stoichiometry.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `formula_unit_conserved(left: Sequence[tuple[Mapping[str, int], int]], right: Sequence[tuple[Mapping[str, int], int]]) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
from openchem.domain.salt_stoichiometry import formula_unit_conserved


def test_one_base_and_two_acids_match_the_dication_formula_unit() -> None:
    # B + 2 HA → BH2^2+ + 2 A−  (ethylenediamine + 2 acetic, as counts)
    base = {"C": 2, "H": 8, "N": 2}
    acid = {"C": 2, "H": 4, "O": 2}
    cation = {"C": 2, "H": 10, "N": 2}
    anion = {"C": 2, "H": 3, "O": 2}
    assert formula_unit_conserved(
        [(base, 1), (acid, 2)],
        [(cation, 1), (anion, 2)],
    )


def test_a_one_to_one_check_of_the_base_against_the_dication_is_the_wrong_test() -> None:
    base = {"C": 2, "H": 8, "N": 2}
    cation = {"C": 2, "H": 10, "N": 2}
    assert not formula_unit_conserved([(base, 1)], [(cation, 1)])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONPATH = "D:\_scratch\OpenChem-Studio-salt-slice-2\src"; & "D:\Random Projects\OpenChem Studio\.venv\Scripts\python.exe" -m pytest tests/test_salt_stoichiometry.py::test_one_base_and_two_acids_match_the_dication_formula_unit -v`

Expected: FAIL with `ImportError` for `formula_unit_conserved`.

- [ ] **Step 3: Write minimal implementation**

```python
from collections.abc import Mapping, Sequence


def formula_unit_conserved(
    left: Sequence[tuple[Mapping[str, int], int]],
    right: Sequence[tuple[Mapping[str, int], int]],
) -> bool:
    def _total(parts: Sequence[tuple[Mapping[str, int], int]]) -> dict[str, int]:
        out: dict[str, int] = {}
        for counts, n in parts:
            if n <= 0:
                return {"__invalid__": 1}
            for element, count in counts.items():
                out[element] = out.get(element, 0) + n * count
        return out

    return _total(left) == _total(right)
```

Empty maps with n>0 are conserved against each other. Do not import RDKit.

- [ ] **Step 4: Run the two new tests**

Run: same interpreter, `tests/test_salt_stoichiometry.py::test_one_base_and_two_acids_match_the_dication_formula_unit tests/test_salt_stoichiometry.py::test_a_one_to_one_check_of_the_base_against_the_dication_is_the_wrong_test -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/domain/salt_stoichiometry.py tests/test_salt_stoichiometry.py
git commit -m "Check salt formula units with multiplicity, not a 1:1 parent-ion pair."
```

---

### Task 2: Domain Mode A refusals (hydroxide and missing proton source)

**Files:**
- Modify: `src/openchem/domain/salt_stoichiometry.py`
- Test: `tests/test_salt_stoichiometry.py`

**Interfaces:**
- Consumes: `ChargedSpecies`, `balance_two`, `formula_unit_conserved`
- Produces:

```python
KIND_MOLECULAR_NEUTRAL = "molecular_neutral"
KIND_ION = "ion"
KIND_METAL_HYDROXIDE = "metal_hydroxide"

@dataclass(frozen=True)
class ModeASpecies:
    identity: str
    charge: int
    kind: str
    element_counts: tuple[tuple[str, int], ...]

@dataclass(frozen=True)
class ModeAComposition:
    cation_count: int
    anion_count: int
    charge_valid: bool

@dataclass(frozen=True)
class ModeARefusal:
    code: str
    reason: str

def compose_mode_a(
    base: ModeASpecies,
    acid: ModeASpecies,
    cation: ModeASpecies,
    anion: ModeASpecies,
) -> ModeAComposition | ModeARefusal
```

Refusal codes used in this task: `hydroxide_neutralization`, `missing_proton_source`.

- [ ] **Step 1: Write the failing tests**

```python
from openchem.domain.salt_stoichiometry import (
    KIND_ION,
    KIND_METAL_HYDROXIDE,
    KIND_MOLECULAR_NEUTRAL,
    ModeARefusal,
    ModeASpecies,
    compose_mode_a,
)


def _species(identity: str, charge: int, kind: str, counts: dict[str, int]) -> ModeASpecies:
    return ModeASpecies(
        identity=identity,
        charge=charge,
        kind=kind,
        element_counts=tuple(sorted(counts.items())),
    )


def test_naoh_plus_acetic_is_refused_as_hydroxide_neutralization() -> None:
    result = compose_mode_a(
        _species("NaOH", 0, KIND_METAL_HYDROXIDE, {"H": 1, "Na": 1, "O": 1}),
        _species("AcOH", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 4, "O": 2}),
        _species("Na+", 1, KIND_ION, {"Na": 1}),
        _species("AcO-", -1, KIND_ION, {"C": 2, "H": 3, "O": 2}),
    )
    assert isinstance(result, ModeARefusal)
    assert result.code == "hydroxide_neutralization"


def test_neutral_base_plus_sulfate_without_a_proton_source_is_refused() -> None:
    result = compose_mode_a(
        _species("B", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 7, "N": 1}),
        _species("SO4", -2, KIND_ION, {"O": 4, "S": 1}),
        _species("BH+", 1, KIND_ION, {"C": 2, "H": 8, "N": 1}),
        _species("SO4", -2, KIND_ION, {"O": 4, "S": 1}),
    )
    assert isinstance(result, ModeARefusal)
    assert result.code == "missing_proton_source"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `... pytest tests/test_salt_stoichiometry.py::test_naoh_plus_acetic_is_refused_as_hydroxide_neutralization -v`

Expected: FAIL with `compose_mode_a` not defined.

- [ ] **Step 3: Write `compose_mode_a` refusals first** (success path in Task 3)

```python
KIND_MOLECULAR_NEUTRAL = "molecular_neutral"
KIND_ION = "ion"
KIND_METAL_HYDROXIDE = "metal_hydroxide"


@dataclass(frozen=True)
class ModeASpecies:
    identity: str
    charge: int
    kind: str
    element_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ModeAComposition:
    cation_count: int
    anion_count: int
    charge_valid: bool


@dataclass(frozen=True)
class ModeARefusal:
    code: str
    reason: str


def compose_mode_a(
    base: ModeASpecies,
    acid: ModeASpecies,
    cation: ModeASpecies,
    anion: ModeASpecies,
) -> ModeAComposition | ModeARefusal:
    if (
        base.kind == KIND_METAL_HYDROXIDE
        or acid.kind == KIND_METAL_HYDROXIDE
    ):
        return ModeARefusal(
            code="hydroxide_neutralization",
            reason=(
                "Metal-hydroxide neutralization is not two-neutral proton "
                "transfer; v1 does not form water and a spectator cation."
            ),
        )
    kinds = {base.kind, acid.kind}
    if KIND_MOLECULAR_NEUTRAL in kinds and KIND_ION in kinds:
        return ModeARefusal(
            code="missing_proton_source",
            reason=(
                "A molecular neutral plus a supplied ion does not provide "
                "the protons for the product ions."
            ),
        )
    return ModeARefusal(
        code="not_implemented",
        reason="Success path is the next task.",
    )
```

Replace the `not_implemented` stub in Task 3; do not leave it in the commit if Task 2 and 3 are separate — Task 2 may return that stub for two neutrals. Tests in this task must not call two-neutral success.

- [ ] **Step 4: Run the two refusal tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/domain/salt_stoichiometry.py tests/test_salt_stoichiometry.py
git commit -m "Refuse NaOH neutralization and a neutral plus ion with no proton source."
```

---

### Task 3: Domain Mode A success — monoprotic and B + 2 HA

**Files:**
- Modify: `src/openchem/domain/salt_stoichiometry.py`
- Test: `tests/test_salt_stoichiometry.py`

**Interfaces:**
- Consumes: `compose_mode_a` from Task 2, `balance_two`, `formula_unit_conserved`
- Produces: `ModeAComposition` with `charge_valid is True` when both parents are `molecular_neutral`, charges are 0, `balance_two` succeeds, and conservation holds at those multiplicities.

- [ ] **Step 1: Write the failing tests**

```python
from openchem.domain.salt_stoichiometry import ModeAComposition, TwoIonBalance


def test_ethylamine_and_acetic_acid_is_one_to_one() -> None:
    result = compose_mode_a(
        _species("EtNH2", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 7, "N": 1}),
        _species("AcOH", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 4, "O": 2}),
        _species("EtNH3+", 1, KIND_ION, {"C": 2, "H": 8, "N": 1}),
        _species("AcO-", -1, KIND_ION, {"C": 2, "H": 3, "O": 2}),
    )
    assert result == ModeAComposition(
        cation_count=1, anion_count=1, charge_valid=True
    )


def test_ethylenediamine_and_two_acetic_acids_is_one_to_two() -> None:
    result = compose_mode_a(
        _species("en", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 8, "N": 2}),
        _species("AcOH", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 4, "O": 2}),
        _species("enH2+2", 2, KIND_ION, {"C": 2, "H": 10, "N": 2}),
        _species("AcO-", -1, KIND_ION, {"C": 2, "H": 3, "O": 2}),
    )
    assert isinstance(result, ModeAComposition)
    assert result.cation_count == 1 and result.anion_count == 2
    assert result.charge_valid is True


def test_broken_hydrogen_count_is_not_a_composition() -> None:
    result = compose_mode_a(
        _species("EtNH2", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 7, "N": 1}),
        _species("AcOH", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 4, "O": 2}),
        _species("wrong", 1, KIND_ION, {"C": 2, "H": 9, "N": 1}),
        _species("AcO-", -1, KIND_ION, {"C": 2, "H": 3, "O": 2}),
    )
    assert isinstance(result, ModeARefusal)
    assert result.code == "conservation_failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL — two-neutral path still `not_implemented` or missing success return.

- [ ] **Step 3: Complete `compose_mode_a`** after the refusal branches from Task 2:

```python
    if base.kind != KIND_MOLECULAR_NEUTRAL or acid.kind != KIND_MOLECULAR_NEUTRAL:
        return ModeARefusal(
            code="unsupported_parents",
            reason="Mode A workflow 1 needs two molecular neutrals.",
        )
    if base.charge != 0 or acid.charge != 0:
        return ModeARefusal(
            code="unsupported_parents",
            reason="Mode A workflow 1 parents must be uncharged.",
        )
    balanced = balance_two(
        ChargedSpecies(cation.identity, cation.charge),
        ChargedSpecies(anion.identity, anion.charge),
    )
    if isinstance(balanced, BalanceRefusal):
        return ModeARefusal(code=balanced.code, reason=balanced.reason)
    left = [
        (dict(base.element_counts), balanced.cation_count),
        (dict(acid.element_counts), balanced.anion_count),
    ]
    right = [
        (dict(cation.element_counts), balanced.cation_count),
        (dict(anion.element_counts), balanced.anion_count),
    ]
    if not formula_unit_conserved(left, right):
        return ModeARefusal(
            code="conservation_failed",
            reason=(
                "Element counts of the parents at the balanced multiplicities "
                "do not match the product ions."
            ),
        )
    return ModeAComposition(
        cation_count=balanced.cation_count,
        anion_count=balanced.anion_count,
        charge_valid=True,
    )
```

Delete any `not_implemented` return. Parent multiplicities are the ion multiplicities from `balance_two` (`n_base = n_C`, `n_acid = n_A`).

- [ ] **Step 4: Run all `test_salt_stoichiometry.py` Mode A tests plus existing `balance_two` tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/domain/salt_stoichiometry.py tests/test_salt_stoichiometry.py
git commit -m "Compose two-neutral Mode A only when the formula unit is conserved."
```

---

### Task 4: Chem wrapper — molecules to Mode A

**Files:**
- Create: `src/openchem/chem/salt_mode_a.py`
- Test: `tests/test_salt_mode_a.py`

**Interfaces:**
- Consumes: `fragment_key`, `fragment_formal_charge`, `compose_mode_a`, `ModeASpecies`, kinds
- Produces: `def compose_from_mols(base, acid, cation, anion) -> ModeAComposition | ModeARefusal | IdentityRefusal`

- [ ] **Step 1: Write the failing tests**

```python
"""Mode A from four molecules: two parents and two product ions.

Contract: docs/SALT_COMPOSITION_DESIGN.md.
"""

from rdkit import Chem

from openchem.chem.salt_mode_a import compose_from_mols
from openchem.domain.salt_stoichiometry import ModeAComposition, ModeARefusal


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None
    return mol


def test_ethylamine_and_acetic_acid_mols_are_one_to_one() -> None:
    result = compose_from_mols(
        _mol("CCN"),
        _mol("CC(=O)O"),
        _mol("CC[NH3+]"),
        _mol("CC(=O)[O-]"),
    )
    assert result == ModeAComposition(
        cation_count=1, anion_count=1, charge_valid=True
    )


def test_sodium_hydroxide_and_acetic_acid_mols_are_refused() -> None:
    result = compose_from_mols(
        _mol("[Na]O"),
        _mol("CC(=O)O"),
        _mol("[Na+]"),
        _mol("CC(=O)[O-]"),
    )
    assert isinstance(result, ModeARefusal)
    assert result.code == "hydroxide_neutralization"


def test_ethylamine_and_sulfate_mols_are_refused() -> None:
    result = compose_from_mols(
        _mol("CCN"),
        _mol("S(=O)(=O)([O-])[O-]"),
        _mol("CC[NH3+]"),
        _mol("S(=O)(=O)([O-])[O-]"),
    )
    assert isinstance(result, ModeARefusal)
    assert result.code == "missing_proton_source"
```

- [ ] **Step 2: Run to verify ImportError**

Run: `... pytest tests/test_salt_mode_a.py::test_ethylamine_and_acetic_acid_mols_are_one_to_one -v`

- [ ] **Step 3: Write `salt_mode_a.py`**

```python
"""Mode A: two parent molecules and two product ions, no pKa.

Does not invent a microspecies. Metal hydroxide is a refusal, not a path.
"""

from __future__ import annotations

from collections import Counter

from rdkit import Chem

from openchem.chem.salt_components import (
    IdentityRefusal,
    fragment_formal_charge,
    fragment_key,
)
from openchem.domain.salt_stoichiometry import (
    KIND_ION,
    KIND_METAL_HYDROXIDE,
    KIND_MOLECULAR_NEUTRAL,
    ModeAComposition,
    ModeARefusal,
    ModeASpecies,
    compose_mode_a,
)

REACHED_BY = (
    "tooling: consumed by tests/test_salt_mode_a.py; Mode A is not "
    "on the window yet"
)

_ALKALI = frozenset({"Li", "Na", "K", "Rb", "Cs"})


def _counts(mol: Chem.Mol) -> tuple[tuple[str, int], ...]:
    tallies: Counter[str] = Counter()
    for atom in mol.GetAtoms():
        tallies[atom.GetSymbol()] += 1
        tallies["H"] += atom.GetTotalNumHs()
    return tuple(sorted((el, n) for el, n in tallies.items() if n))


def _kind(mol: Chem.Mol, charge: int) -> str:
    symbols = [atom.GetSymbol() for atom in mol.GetAtoms()]
    metals = [s for s in symbols if s in _ALKALI]
    oxygens = [s for s in symbols if s == "O"]
    others = [s for s in symbols if s not in _ALKALI and s != "O" and s != "H"]
    if metals and oxygens and not others and len(metals) == 1 and len(oxygens) == 1:
        return KIND_METAL_HYDROXIDE
    if charge != 0:
        return KIND_ION
    return KIND_MOLECULAR_NEUTRAL


def _species(mol: Chem.Mol) -> ModeASpecies | IdentityRefusal:
    key = fragment_key(mol)
    if isinstance(key, IdentityRefusal):
        return key
    charge = fragment_formal_charge(mol)
    return ModeASpecies(key, charge, _kind(mol, charge), _counts(mol))


def compose_from_mols(
    base: Chem.Mol,
    acid: Chem.Mol,
    cation: Chem.Mol,
    anion: Chem.Mol,
) -> ModeAComposition | ModeARefusal | IdentityRefusal:
    parts = [_species(base), _species(acid), _species(cation), _species(anion)]
    for part in parts:
        if isinstance(part, IdentityRefusal):
            return part
    return compose_mode_a(parts[0], parts[1], parts[2], parts[3])
```

If `[Na]O` does not classify as hydroxide in a RED run, adjust `_kind` to also treat a disconnected `[Na+].[OH-]` (two fragments, alkali cation + hydroxide) as `KIND_METAL_HYDROXIDE`. Do not implement the water-forming neutralization.

- [ ] **Step 4: Run `tests/test_salt_mode_a.py -v`**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/chem/salt_mode_a.py tests/test_salt_mode_a.py
git commit -m "Wrap Mode A so four molecules hit the same refusals as the domain."
```

---

### Task 5: Changelog, shards, architecture, design status

**Files:**
- Create: `changelog.d/YYYYMMDDHHMM-salt-composition-slice-2-<hex>.md` via the tool
- Modify: `docs/SALT_COMPOSITION_DESIGN.md` status line (slice 2 in progress for Mode A; Mode C/UI still not authorized)
- Modify: `docs/ROADMAP.md` salt-composition bullet — slice 1 is in master; slice 2 is Mode A
- Modify: `CLAUDE.md` Key Files — extend the salt line to mention Mode A
- Modify: `docs/ARCHITECTURE.md` — chem count 164 → 165, name `salt_mode_a.py` next to `salt_components.py`
- Modify: `tools/suite-shard-pins.json` via `--pin-new` **without** `--splits=3`

**Interfaces:** none

- [ ] **Step 1: Changelog fragment**

Run: `python tools/changelog.py new salt-composition-slice-2`

Edit the printed file to:

```markdown
### Salt composition (library, no UI)

- Mode A for two molecular neutrals: `balance_two` on the product ions,
  multiplicity-weighted formula-unit conservation, and refusals for
  metal-hydroxide neutralization and a neutral plus a supplied ion with
  no proton source. Still not a claim that a salt exists. No panel.
```

Run: `python tools/changelog.py check` — expected exit 0.

- [ ] **Step 2: Pin new tests**

Run: `python tools/suite_shards.py --pin-new`

Expected: `tests/test_salt_mode_a.py` appears in the **8-way** table. Do not pass `--splits=3`.

- [ ] **Step 3: Architecture + CLAUDE.md + design status + ROADMAP** as listed. Stage `src/openchem/chem/salt_mode_a.py` before docs tests if the architecture line cites the path.

- [ ] **Step 4: Guards**

Run: `... pytest tests/test_docs_are_current.py::test_the_architecture_module_count_is_live tests/test_docs_are_current.py::test_every_chem_module_is_named_in_the_package_map tests/test_docs_are_current.py::test_every_file_a_doc_cites_still_exists tests/test_layering.py tests/test_calculator_reachability.py::test_every_module_is_statically_reachable_or_declares_why_not tests/test_suite_shards.py::test_the_workflow_runs_exactly_the_shards_the_committed_pins_cover tests/test_salt_stoichiometry.py tests/test_salt_mode_a.py -q --tb=line`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add changelog.d docs/SALT_COMPOSITION_DESIGN.md docs/ROADMAP.md docs/ARCHITECTURE.md CLAUDE.md tools/suite-shard-pins.json
git commit -m "Record slice 2 of salt composition in the changelog and the file map."
```

---

## Later slices (not this plan)

- Slice 3: fully specified ionization states; polyprotic/polybasic pKa as evidence only.
- Slice 4: Mode C enumeration with generated/returned/omitted.
- Slice 5: UI beside the pKa view; remove `REACHED_BY` when `openchem.main` can reach these modules.

## Spec coverage (slice 2)

| Contract item | Task |
|---|---|
| Multiplicity-weighted formula-unit conservation | 1, 3 |
| 1:1 B vs BH2²⁺ is the wrong check | 1 |
| NaOH + HA refused | 2, 4 |
| Neutral + supplied ion, no proton source | 2, 4 |
| Monoprotic B + HA | 3, 4 |
| B + 2 HA → BH2²⁺ + 2 A− | 3 |
| Conservation failure is not a composition | 3 |
| pKa / Mode C / UI / `balance_many` | deferred |

## Execution

Plan saved to `docs/superpowers/plans/2026-11-11-salt-composition-slice-2.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks
2. **Inline Execution** — execute the plan in this session with checkpoints

Which approach?
