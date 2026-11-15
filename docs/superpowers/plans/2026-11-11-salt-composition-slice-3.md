# Salt composition slice 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship fully specified user ionization, proton-source rules for an already-ionic counter-species, a small cited ion catalog, and `pka_compatible` as an independent evidence claim that never feeds `balance_two`.

**Architecture:** Domain owns selection uniqueness, two-ion composition from supplied ions, and pKa arithmetic (opaque identities, named steps, comparable conditions). `chem/salt_ionization.py` turns a parent molecule plus a site transform into a structure whose hydrogen count and formal charge both move. `chem/ionic_species.py` loads cited JSON rows. No Mode C enumeration, no ladder adapter, no UI, no live pKa sidecar in tests.

**Tech Stack:** Python 3.11+, existing `balance_two` / `compose_mode_a`, RDKit only in `chem/` and tests, pytest. Worktree: `D:\_scratch\OpenChem-Studio-salt-slice-3`. After `uv sync`, `uv run --no-sync pytest`. If that cannot import PySide6, set `PYTHONPATH` to this worktree `src` and use `D:\Random Projects\OpenChem Studio\.venv\Scripts\python.exe`.

## Global Constraints

- Work on `cursor/salt-composition-slice-3` in `D:\_scratch\OpenChem-Studio-salt-slice-3`, from `origin/master` after #583. Not `claude/vendoring-fork-100-squash`.
- No UI, no calculator registry, no Mode C (no 50-cap cartesian product), no `pka_species_ladder` adapter, no CIF/COD, no ion-pair 3D, no hydrates as first-class, no `balance_many`, no NaOH neutralization path.
- Domain must not import `rdkit`, `openbabel`, `PySide6`, or `openchem.chem`.
- Keep pKa out of `balance_two`. Never name a claim `acid_base_supported`.
- `pka_compatible` is optional evidence. Already-charged / supplied-ion input is **not assessed**. Missing or incomparable conditions are recorded, not guessed.
- `pka_compatible` must name the protonation/dissociation **step that matches the proposed microspecies**. Hydrogen sulfate is not sulfuric acid's second pKa; `BH2^2+` is not the first conjugate-acid pKa of B.
- User-selected ionization must identify a **structure**. A desired net charge alone is refused. Several structures at one charge are listed, never auto-picked.
- Protonation/deprotonation updates **both** hydrogen count and formal charge.
- Presence in the ion catalog is not pharmaceutical acceptability. `HSO4-` and `SO4^2-` are different rows. No DOIs in the JSON (the DOI guard sweeps `.json`).
- Changelog is a fragment (`tools/changelog.py new`), not an edit of `CHANGELOG.md`.
- New test files: `python tools/suite_shards.py --pin-new` with **no** `--splits=3`.
- New `src/openchem` modules need `REACHED_BY = ("tooling: ...")` until `openchem.main` imports them.
- New constants in a file that already uses `#:` need a `#:` block on each (see `KIND_*` on slice 2).
- After adding a `chem/*.py` file, update `docs/ARCHITECTURE.md` chem count (165 → 167 if two modules) and name each module next to `salt_mode_a.py`.
- Tests must not call `compute_pka` / the pkasolver sidecar. Inject `PkaValue` records.
- A charge-valid composition is never an isolable salt. `experimentally_established` stays unset.

---

### Task 1: Domain ionization uniqueness

**Files:**
- Modify: `src/openchem/domain/salt_stoichiometry.py`
- Test: `tests/test_salt_stoichiometry.py`

**Interfaces:**
- Consumes: opaque identity strings (canonical SMILES from chem, treated as opaque here)
- Produces:

```python
@dataclass(frozen=True)
class IonizationRefusal:
    code: str
    reason: str


def choose_ionization(candidates: Sequence[str]) -> str | IonizationRefusal:
    ...
```

- [ ] **Step 1: Write the failing tests**

```python
from openchem.domain.salt_stoichiometry import choose_ionization


def test_one_structure_at_the_requested_state_is_accepted() -> None:
    assert choose_ionization(["CC(=O)[O-]"]) == "CC(=O)[O-]"


def test_a_net_charge_with_no_structure_is_refused() -> None:
    refused = choose_ionization([])
    assert refused.code == "net_charge_only"


def test_two_structures_at_the_same_charge_are_not_auto_picked() -> None:
    refused = choose_ionization(["CC(=O)[O-]", "[O-]C=O"])
    assert refused.code == "ambiguous_microspecies"
    assert isinstance(refused, IonizationRefusal)
```

Need `from openchem.domain.salt_stoichiometry import IonizationRefusal` with the other import. Two different identity strings at one conceptual charge; domain does not know chemistry, so any two distinct strings suffice.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest tests/test_salt_stoichiometry.py::test_one_structure_at_the_requested_state_is_accepted tests/test_salt_stoichiometry.py::test_a_net_charge_with_no_structure_is_refused tests/test_salt_stoichiometry.py::test_two_structures_at_the_same_charge_are_not_auto_picked -v`

Expected: FAIL with `ImportError` for `choose_ionization`.

- [ ] **Step 3: Write minimal implementation**

Add `#:` comments. Empty `candidates` is `net_charge_only` (a charge request with no identified structure). One unique string is returned. Two or more **distinct** strings is `ambiguous_microspecies`. Duplicate identical strings count as one (canonicalization already collapsed them).

```python
@dataclass(frozen=True)
class IonizationRefusal:
    code: str
    reason: str


#: Pick among fully specified ionic structures. An empty list is a net-charge
#: request with no structure; several distinct graphs at one charge are not ranked.
def choose_ionization(candidates: Sequence[str]) -> str | IonizationRefusal:
    unique = list(dict.fromkeys(candidates))
    if not unique:
        return IonizationRefusal(
            code="net_charge_only",
            reason="A net charge is not an ionization state; name a structure.",
        )
    if len(unique) > 1:
        return IonizationRefusal(
            code="ambiguous_microspecies",
            reason="Several structures share this charge; v1 does not pick one.",
        )
    return unique[0]
```

Do not import RDKit.

- [ ] **Step 4: Run the three new tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/domain/salt_stoichiometry.py tests/test_salt_stoichiometry.py
git commit -m "Refuse a salt ionization that is only a net charge or several microspecies."
```

---

### Task 2: Domain pKa evidence (annotation only)

**Files:**
- Create: `src/openchem/domain/salt_evidence.py`
- Test: `tests/test_salt_evidence.py`

**Interfaces:**
- Consumes: nothing from `balance_two`
- Produces:

```python
ORIGIN_MEASURED = "measured"
ORIGIN_PREDICTED = "predicted"

VERDICT_NOT_ASSESSED = "not_assessed"
VERDICT_MISSING = "missing"
VERDICT_INCOMPARABLE = "incomparable"
VERDICT_WRONG_STEP = "wrong_step"
VERDICT_RECORDED = "recorded"

@dataclass(frozen=True)
class PkaValue:
    value: float
    origin: str
    medium: str
    temperature_k: float | None
    ionic_strength: float | None
    uncertainty: float | None
    step_id: str

@dataclass(frozen=True)
class PkaCompatibility:
    verdict: str
    delta: float | None
    acid: PkaValue | None
    conjugate_acid: PkaValue | None
    reason: str

@dataclass(frozen=True)
class EvidenceRecord:
    charge_valid: bool
    structurally_consistent: bool
    pka_compatible: PkaCompatibility
    experimentally_established: None

def assess_pka_compatible(
    *,
    already_charged: bool,
    proposed_acid_step_id: str,
    proposed_conjugate_acid_step_id: str,
    acid: PkaValue | None,
    conjugate_acid: PkaValue | None,
) -> PkaCompatibility:
    ...
```

`ΔpKa = pKa(BH+) − pKa(HA)` when both values are recorded under comparable conditions and each `step_id` matches the proposed microspecies. Store `delta`; do not turn it into `supported`.

Comparable: same `medium` string, and `temperature_k` equal (including both `None`). Ionic strength may differ without forcing `incomparable` (the record still carries both values). Mixed `measured`/`predicted` origin is still `recorded` if conditions match; the origins stay on the values.

- [ ] **Step 1: Write the failing tests**

```python
from openchem.domain.salt_evidence import (
    ORIGIN_MEASURED,
    VERDICT_INCOMPARABLE,
    VERDICT_MISSING,
    VERDICT_NOT_ASSESSED,
    VERDICT_RECORDED,
    VERDICT_WRONG_STEP,
    PkaValue,
    assess_pka_compatible,
)


def _acetic() -> PkaValue:
    return PkaValue(4.76, ORIGIN_MEASURED, "water", 298.15, None, None, "acetic_acid_h1")


def _pyridinium() -> PkaValue:
    return PkaValue(5.23, ORIGIN_MEASURED, "water", 298.15, None, None, "pyridine_bh1")


def test_already_charged_input_is_not_assessed() -> None:
    result = assess_pka_compatible(
        already_charged=True,
        proposed_acid_step_id="acetic_acid_h1",
        proposed_conjugate_acid_step_id="pyridine_bh1",
        acid=_acetic(),
        conjugate_acid=_pyridinium(),
    )
    assert result.verdict == VERDICT_NOT_ASSESSED
    assert result.delta is None


def test_missing_pka_is_missing_not_invented() -> None:
    result = assess_pka_compatible(
        already_charged=False,
        proposed_acid_step_id="acetic_acid_h1",
        proposed_conjugate_acid_step_id="pyridine_bh1",
        acid=_acetic(),
        conjugate_acid=None,
    )
    assert result.verdict == VERDICT_MISSING
    assert result.delta is None


def test_delta_is_conjugate_acid_minus_acid() -> None:
    result = assess_pka_compatible(
        already_charged=False,
        proposed_acid_step_id="acetic_acid_h1",
        proposed_conjugate_acid_step_id="pyridine_bh1",
        acid=_acetic(),
        conjugate_acid=_pyridinium(),
    )
    assert result.verdict == VERDICT_RECORDED
    assert result.delta == pytest.approx(0.47)


def test_sulfate_must_not_reuse_the_first_sulfuric_pka() -> None:
    sulfuric_h1 = PkaValue(-3.0, ORIGIN_MEASURED, "water", 298.15, None, None, "sulfuric_h1")
    pyridine = _pyridinium()
    result = assess_pka_compatible(
        already_charged=False,
        proposed_acid_step_id="sulfuric_h2",
        proposed_conjugate_acid_step_id="pyridine_bh1",
        acid=sulfuric_h1,
        conjugate_acid=pyridine,
    )
    assert result.verdict == VERDICT_WRONG_STEP
    assert result.delta is None


def test_bh2_must_not_reuse_the_first_conjugate_acid_pka() -> None:
    bh1 = PkaValue(9.9, ORIGIN_MEASURED, "water", 298.15, None, None, "en_bh1")
    acetic = _acetic()
    result = assess_pka_compatible(
        already_charged=False,
        proposed_acid_step_id="acetic_acid_h1",
        proposed_conjugate_acid_step_id="en_bh2",
        acid=acetic,
        conjugate_acid=bh1,
    )
    assert result.verdict == VERDICT_WRONG_STEP


def test_different_media_are_incomparable() -> None:
    dmso = PkaValue(12.3, ORIGIN_MEASURED, "DMSO", 298.15, None, None, "acetic_acid_h1")
    result = assess_pka_compatible(
        already_charged=False,
        proposed_acid_step_id="acetic_acid_h1",
        proposed_conjugate_acid_step_id="pyridine_bh1",
        acid=dmso,
        conjugate_acid=_pyridinium(),
    )
    assert result.verdict == VERDICT_INCOMPARABLE
    assert result.delta is None
```

Add `import pytest` at the top of the test file.

The numbers 4.76 / 5.23 / 0.47 are **fixtures for the arithmetic**, not handbook claims. Do not write them into shipped JSON.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest tests/test_salt_evidence.py -v`

Expected: FAIL with `ModuleNotFoundError` for `openchem.domain.salt_evidence`.

- [ ] **Step 3: Write minimal implementation**

```python
"""pKa as an independent salt-composition claim, never a solver input."""

from __future__ import annotations

from dataclasses import dataclass

REACHED_BY = (
    "tooling: consumed by tests/test_salt_evidence.py; evidence is not "
    "on the window yet"
)

#: Measured value supplied by the caller. Not a model output.
ORIGIN_MEASURED = "measured"
#: Predicted value supplied by the caller. This module does not run a model.
ORIGIN_PREDICTED = "predicted"

#: Already ionic; the drawing is the state.
VERDICT_NOT_ASSESSED = "not_assessed"
#: A required pKa was not supplied.
VERDICT_MISSING = "missing"
#: Media or temperatures do not match, so ΔpKa is not a constant.
VERDICT_INCOMPARABLE = "incomparable"
#: A value's step_id is not the proposed microspecies.
VERDICT_WRONG_STEP = "wrong_step"
#: Both values named the proposed steps under comparable conditions.
VERDICT_RECORDED = "recorded"


@dataclass(frozen=True)
class PkaValue:
    value: float
    origin: str
    medium: str
    temperature_k: float | None
    ionic_strength: float | None
    uncertainty: float | None
    step_id: str


@dataclass(frozen=True)
class PkaCompatibility:
    verdict: str
    delta: float | None
    acid: PkaValue | None
    conjugate_acid: PkaValue | None
    reason: str


@dataclass(frozen=True)
class EvidenceRecord:
    charge_valid: bool
    structurally_consistent: bool
    pka_compatible: PkaCompatibility
    experimentally_established: None


def assess_pka_compatible(
    *,
    already_charged: bool,
    proposed_acid_step_id: str,
    proposed_conjugate_acid_step_id: str,
    acid: PkaValue | None,
    conjugate_acid: PkaValue | None,
) -> PkaCompatibility:
    if already_charged:
        return PkaCompatibility(
            VERDICT_NOT_ASSESSED,
            None,
            None,
            None,
            "Already-charged input is not pKa-assessed; the state is in the drawing.",
        )
    if acid is None or conjugate_acid is None:
        return PkaCompatibility(
            VERDICT_MISSING,
            None,
            acid,
            conjugate_acid,
            "pKa was not assessed because a value for the proposed step is missing.",
        )
    if acid.step_id != proposed_acid_step_id or conjugate_acid.step_id != proposed_conjugate_acid_step_id:
        return PkaCompatibility(
            VERDICT_WRONG_STEP,
            None,
            acid,
            conjugate_acid,
            "pKa step identity does not match the proposed microspecies.",
        )
    if acid.medium != conjugate_acid.medium or acid.temperature_k != conjugate_acid.temperature_k:
        return PkaCompatibility(
            VERDICT_INCOMPARABLE,
            None,
            acid,
            conjugate_acid,
            "pKa values are not from comparable conditions.",
        )
    return PkaCompatibility(
        VERDICT_RECORDED,
        conjugate_acid.value - acid.value,
        acid,
        conjugate_acid,
        "ΔpKa = pKa(BH+) − pKa(HA) under the stated conditions; this is not a crystal.",
    )
```

`balance_two` must not be imported here. Tests must not import `openchem.chem.pka_providers`.

- [ ] **Step 4: Run `tests/test_salt_evidence.py -v`**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/domain/salt_evidence.py tests/test_salt_evidence.py
git commit -m "Record salt pKa as a named step under comparable conditions, not a proof."
```

---

### Task 3: Domain workflow 2 — two supplied ions

**Files:**
- Modify: `src/openchem/domain/salt_stoichiometry.py`
- Modify: `src/openchem/domain/salt_evidence.py` (optional helper `evidence_for_supplied_ions`)
- Test: `tests/test_salt_stoichiometry.py`, `tests/test_salt_evidence.py`

**Interfaces:**
- Consumes: `ModeASpecies`, `KIND_ION`, `balance_two`, `assess_pka_compatible`
- Produces:

```python
def compose_supplied_ions(
    cation: ModeASpecies,
    anion: ModeASpecies,
) -> ModeAComposition | ModeARefusal:
    ...
```

Two `KIND_ION` species, opposite signs, `balance_two`, **no** formula-unit conservation against neutrals (no transfer was modelled). Mixing a molecular neutral with a supplied ion remains `missing_proton_source` on `compose_mode_a` (already shipped). Do not add a neutralization path.

- [ ] **Step 1: Write the failing tests**

```python
from openchem.domain.salt_evidence import VERDICT_NOT_ASSESSED, assess_pka_compatible
from openchem.domain.salt_stoichiometry import (
    KIND_ION,
    KIND_MOLECULAR_NEUTRAL,
    ModeASpecies,
    compose_supplied_ions,
)


def test_sodium_and_acetate_as_given_ions_balance_one_to_one() -> None:
    sodium = ModeASpecies("[Na+]", 1, KIND_ION, (("Na", 1),))
    acetate = ModeASpecies("CC(=O)[O-]", -1, KIND_ION, (("C", 2), ("H", 3), ("O", 2)))
    result = compose_supplied_ions(sodium, acetate)
    assert result.cation_count == 1
    assert result.anion_count == 1
    assert result.charge_valid is True


def test_supplied_ions_do_not_assess_pka() -> None:
    result = assess_pka_compatible(
        already_charged=True,
        proposed_acid_step_id="x",
        proposed_conjugate_acid_step_id="y",
        acid=None,
        conjugate_acid=None,
    )
    assert result.verdict == VERDICT_NOT_ASSESSED


def test_a_neutral_passed_to_supplied_ions_is_refused() -> None:
    acetic = ModeASpecies("CC(=O)O", 0, KIND_MOLECULAR_NEUTRAL, (("C", 2), ("H", 4), ("O", 2)))
    sodium = ModeASpecies("[Na+]", 1, KIND_ION, (("Na", 1),))
    refused = compose_supplied_ions(sodium, acetic)
    assert refused.code == "missing_proton_source"
```

- [ ] **Step 2: Run the new tests**

Expected: FAIL with `ImportError` for `compose_supplied_ions`.

- [ ] **Step 3: Write minimal implementation**

```python
def compose_supplied_ions(
    cation: ModeASpecies,
    anion: ModeASpecies,
) -> ModeAComposition | ModeARefusal:
    if cation.kind != KIND_ION or anion.kind != KIND_ION:
        return ModeARefusal(
            code="missing_proton_source",
            reason=(
                "A molecular neutral plus a supplied ion does not provide "
                "the protons for a transfer; supply both ions as given."
            ),
        )
    balanced = balance_two(
        ChargedSpecies(cation.identity, cation.charge),
        ChargedSpecies(anion.identity, anion.charge),
    )
    if isinstance(balanced, BalanceRefusal):
        return ModeARefusal(code=balanced.code, reason=balanced.reason)
    return ModeAComposition(
        cation_count=balanced.cation_count,
        anion_count=balanced.anion_count,
        charge_valid=True,
    )
```

Do not call `formula_unit_conserved`. Do not call `assess_pka_compatible` from this function.

- [ ] **Step 4: Run the new tests plus `tests/test_salt_stoichiometry.py` and `tests/test_salt_evidence.py`**

Expected: PASS (including existing Mode A tests).

- [ ] **Step 5: Commit**

```bash
git add src/openchem/domain/salt_stoichiometry.py tests/test_salt_stoichiometry.py tests/test_salt_evidence.py
git commit -m "Compose two supplied ions as given, without inventing protons or a pKa."
```

---

### Task 4: Chem site transform (structure, not charge)

**Files:**
- Create: `src/openchem/chem/salt_ionization.py`
- Test: `tests/test_salt_ionization.py`

**Interfaces:**
- Consumes: `fragment_key`, `fragment_formal_charge` from `salt_components`; `choose_ionization` from domain
- Produces:

```python
@dataclass(frozen=True)
class SiteTransform:
    atom_index: int
    direction: str  # "protonate" | "deprotonate"


def apply_site_transform(mol: Chem.Mol, transform: SiteTransform) -> Chem.Mol | IdentityRefusal:
    ...


def ionize_at_sites(mol: Chem.Mol, transforms: Sequence[SiteTransform]) -> str | IdentityRefusal | IonizationRefusal:
    """Apply the named sites, then choose_ionization on the single result identity."""
```

`protonate`: `SetNumExplicitHs(n+1)` and `SetFormalCharge(z+1)` on that atom, then sanitize.
`deprotonate`: Hs must be ≥1 (explicit or implicit via `GetTotalNumHs`); then explicit Hs become `total-1`, charge `z-1`.

- [ ] **Step 1: Write the failing tests**

```python
from rdkit import Chem

from openchem.chem.salt_components import fragment_formal_charge, fragment_key
from openchem.chem.salt_ionization import SiteTransform, apply_site_transform


def _acetic() -> Chem.Mol:
    return Chem.MolFromSmiles("CC(=O)O")


def test_deprotonating_acetic_acid_updates_hydrogen_and_charge() -> None:
    mol = _acetic()
    oxygen = next(
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if atom.GetSymbol() == "O" and atom.GetTotalNumHs() == 1
    )
    result = apply_site_transform(mol, SiteTransform(oxygen, "deprotonate"))
    assert fragment_formal_charge(result) == -1
    assert fragment_key(result) == "CC(=O)[O-]"
    # parent unchanged
    assert fragment_formal_charge(mol) == 0


def test_protonating_pyridine_updates_hydrogen_and_charge() -> None:
    mol = Chem.MolFromSmiles("c1ccncc1")
    nitrogen = next(atom.GetIdx() for atom in mol.GetAtoms() if atom.GetSymbol() == "N")
    result = apply_site_transform(mol, SiteTransform(nitrogen, "protonate"))
    assert fragment_formal_charge(result) == 1
    assert "[nH+]" in fragment_key(result) or "c1cc[nH+]cc1" == fragment_key(result)


def test_a_bad_atom_index_is_refused() -> None:
    mol = _acetic()
    refused = apply_site_transform(mol, SiteTransform(99, "deprotonate"))
    assert refused.code == "invalid_site"
```

If pyridine's canonical SMILES in this RDKit pin is not `c1cc[nH+]cc1`, assert equality to `fragment_key` of `Chem.MolFromSmiles("c1cc[nH+]cc1")` instead of a literal.

- [ ] **Step 2: Run to verify FAIL** (`ModuleNotFoundError` for `salt_ionization`).

- [ ] **Step 3: Write minimal implementation**

Copy the molecule. Do not mutate the input. `REACHED_BY` pointing at `tests/test_salt_ionization.py`. Direction must be exactly `protonate` or `deprotonate`; anything else `invalid_site`.

```python
"""Fully specified ionization states for salt composition. No pKa sidecar."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rdkit import Chem

from openchem.chem.salt_components import IdentityRefusal, fragment_key
from openchem.domain.salt_stoichiometry import IonizationRefusal, choose_ionization

REACHED_BY = (
    "tooling: consumed by tests/test_salt_ionization.py; ionization is not "
    "on the window yet"
)


@dataclass(frozen=True)
class SiteTransform:
    atom_index: int
    direction: str


def apply_site_transform(mol: Chem.Mol, transform: SiteTransform) -> Chem.Mol | IdentityRefusal:
    if transform.direction not in {"protonate", "deprotonate"}:
        return IdentityRefusal(code="invalid_site", reason="direction must be protonate or deprotonate.")
    if transform.atom_index < 0 or transform.atom_index >= mol.GetNumAtoms():
        return IdentityRefusal(code="invalid_site", reason="atom index is not in the parent.")
    copy = Chem.Mol(mol)
    atom = copy.GetAtomWithIdx(transform.atom_index)
    if transform.direction == "protonate":
        atom.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
        atom.SetFormalCharge(atom.GetFormalCharge() + 1)
        atom.SetNoImplicit(True)
    else:
        total = atom.GetTotalNumHs()
        if total < 1:
            return IdentityRefusal(code="invalid_site", reason="that atom has no hydrogen to remove.")
        atom.SetNumExplicitHs(total - 1)
        atom.SetFormalCharge(atom.GetFormalCharge() - 1)
        atom.SetNoImplicit(True)
    try:
        Chem.SanitizeMol(copy)
    except (ValueError, RuntimeError):
        return IdentityRefusal(code="unsanitizable", reason="the ionized structure could not be sanitized.")
    return copy


def ionize_at_sites(
    mol: Chem.Mol, transforms: Sequence[SiteTransform]
) -> str | IdentityRefusal | IonizationRefusal:
    current: Chem.Mol | IdentityRefusal = mol
    for transform in transforms:
        if isinstance(current, IdentityRefusal):
            return current
        current = apply_site_transform(current, transform)
    if isinstance(current, IdentityRefusal):
        return current
    key = fragment_key(current)
    if isinstance(key, IdentityRefusal):
        return key
    return choose_ionization([key])
```

Do not import `pka_providers` or `pka_species_ladder`.

- [ ] **Step 4: Run `tests/test_salt_ionization.py -v`**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/chem/salt_ionization.py tests/test_salt_ionization.py
git commit -m "Ionize a named atom by moving both its hydrogens and its formal charge."
```

---

### Task 5: Chem net-charge enumeration without auto-pick

**Files:**
- Modify: `src/openchem/chem/salt_ionization.py`
- Test: `tests/test_salt_ionization.py`

**Interfaces:**
- Consumes: `apply_site_transform`, `choose_ionization`
- Produces:

```python
def structures_at_net_charge(mol: Chem.Mol, target_charge: int) -> tuple[str, ...]:
    """Distinct fragment_key values reachable by protonate/deprotonate of heavy atoms that match target_charge."""
```

v1 enumeration: for each heavy atom, try `protonate` once and `deprotonate` once (single-site). Collect identities whose `fragment_formal_charge` equals `target_charge`. Do not rank. Then `choose_ionization` on that tuple.

Also:

```python
def select_by_net_charge(mol: Chem.Mol, target_charge: int) -> str | IonizationRefusal | IdentityRefusal:
    return choose_ionization(structures_at_net_charge(mol, target_charge))
```

- [ ] **Step 1: Write the failing tests**

```python
from openchem.chem.salt_ionization import select_by_net_charge, structures_at_net_charge
from openchem.domain.salt_stoichiometry import IonizationRefusal


def test_acetic_acid_at_minus_one_is_acetate() -> None:
    mol = Chem.MolFromSmiles("CC(=O)O")
    chosen = select_by_net_charge(mol, -1)
    assert chosen == fragment_key(Chem.MolFromSmiles("CC(=O)[O-]"))


def test_acetic_acid_at_plus_one_is_net_charge_only() -> None:
    mol = Chem.MolFromSmiles("CC(=O)O")
    refused = select_by_net_charge(mol, 1)
    assert isinstance(refused, IonizationRefusal)
    assert refused.code == "net_charge_only"


def test_two_inequivalent_sites_at_the_same_charge_are_not_picked() -> None:
    # 4-aminophenol: O-H and aniline N are different graphs at -1 vs +1;
    # at charge 0 the parent is already unique. Use 3-aminophenol / 4-aminophenol
    # is not the pair. Use 4-hydroxybenzoic acid: carboxylate vs phenolate at -1.
    mol = Chem.MolFromSmiles("O=C(O)c1ccc(O)cc1")
    keys = structures_at_net_charge(mol, -1)
    assert len(set(keys)) >= 2
    refused = select_by_net_charge(mol, -1)
    assert isinstance(refused, IonizationRefusal)
    assert refused.code == "ambiguous_microspecies"
```

If 4-hydroxybenzoic acid yields only one SMILES in this RDKit pin (tautomer merge — **forbidden by design** if it happens), the test must fail: identity is graph, not formula. Do not call `CanonicalRankAtoms` tautomer canonicalization. If the two deprotonations collapse, pick another pair (e.g. `NCCCO` vs wait — use `OCCc1ccc(O)cc1` tyrosol: aliphatic alcohol vs phenol). Prefer `OCCc1ccc(O)cc1` if 4-hydroxybenzoic collapses.

- [ ] **Step 2: Run to verify FAIL** (`select_by_net_charge` missing).

- [ ] **Step 3: Implement** by looping heavy atoms, applying each direction, skipping `IdentityRefusal`, keeping keys whose charge matches. `structures_at_net_charge` returns a tuple of unique keys in atom-index then protonate-before-deprotonate order.

- [ ] **Step 4: Run `tests/test_salt_ionization.py -v`**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/chem/salt_ionization.py tests/test_salt_ionization.py
git commit -m "List ionization microspecies at a charge; never pick among several."
```

---

### Task 6: Cited ion catalog

**Files:**
- Create: `src/openchem/chem/data/ionic_species.json`
- Create: `src/openchem/chem/ionic_species.py`
- Modify: `docs/sources.toml` — add `used_by` path on a new `salt_ion_catalog` entry (**no DOI**). Do not claim CRC pKa numbers.
- Test: `tests/test_ionic_species.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class IonicSpeciesRow:
    ion_id: str
    name: str
    ion_smiles: str
    charge: int
    parent_smiles: str | None
    relationship: str
    source_key: str


def load_ionic_species() -> tuple[IonicSpeciesRow, ...]:
    ...


def row_by_id(ion_id: str) -> IonicSpeciesRow | None:
    ...
```

JSON shape:

```json
{
  "_source_key": "salt_ion_catalog",
  "ions": [
    {
      "id": "chloride",
      "name": "chloride",
      "ion_smiles": "[Cl-]",
      "charge": -1,
      "parent_smiles": "Cl",
      "relationship": "hydrohalide",
      "source_key": "salt_ion_catalog"
    }
  ]
}
```

v1 rows (exact ids): `chloride`, `bromide`, `iodide`, `hydrogen_sulfate`, `sulfate`, `dihydrogen_phosphate`, `hydrogen_phosphate`, `phosphate`, `acetate`, `nitrate`, `ammonium`, `pyridinium`.

SMILES (must round-trip through `fragment_key` after `MolFromSmiles`):

- chloride `[Cl-]` parent `Cl` relationship `hydrohalide`
- bromide `[Br-]` parent `Br` relationship `hydrohalide`
- iodide `[I-]` parent `I` relationship `hydrohalide`
- hydrogen_sulfate `OS(=O)(=O)[O-]` parent `OS(=O)(=O)O` relationship `first_dissociation`
- sulfate `[O-]S(=O)(=O)[O-]` parent `OS(=O)(=O)O` relationship `second_dissociation`
- dihydrogen_phosphate `OP(=O)(O)[O-]` parent `OP(=O)(O)O` relationship `first_dissociation`
- hydrogen_phosphate `OP(=O)([O-])[O-]` parent `OP(=O)(O)O` relationship `second_dissociation`
- phosphate `[O-]P(=O)([O-])[O-]` parent `OP(=O)(O)O` relationship `third_dissociation`
- acetate `CC(=O)[O-]` parent `CC(=O)O` relationship `first_dissociation`
- nitrate `[O-][N+](=O)[O-]` parent `O[N+](=O)[O-]` relationship `first_dissociation`
- ammonium `[NH4+]` parent `N` relationship `protonated_base`
- pyridinium `c1cc[nH+]cc1` parent `c1ccncc1` relationship `protonated_base`

If `fragment_key` of `MolFromSmiles(ion_smiles)` differs from the JSON string, **store the `fragment_key` form** so identity matches Mode B.

`salt_ion_catalog` in `docs/sources.toml`:

```toml
[[source]]
key = "salt_ion_catalog"
kind = "dataset"
citation = "OpenChem Studio v1 salt ion catalog: named common ions as canonical SMILES for composition, not a pharmaceutical list."
identifier_type = "none"
identifier = "salt_ion_catalog"
status = "shipped"
verification = "citation"
verified_date = 2026-11-11
used_by = ["src/openchem/chem/data/ionic_species.json"]
reason = """
STRUCTURES ONLY. Each row is a named ion's graph and its parent, so Mode A
workflow 2 and the catalog agree on identity. No pKa numbers. Not safety or
acceptability. Hydrogen sulfate and sulfate are different rows.
"""
```

If `identifier_type = "none"` is rejected by `tests/test_sources_are_current.py`, use the same `identifier_type` a similar internal dataset uses (search `kind = "dataset"`). Do not invent a DOI.

- [ ] **Step 1: Write failing tests** (file missing).

```python
from openchem.chem.ionic_species import load_ionic_species, row_by_id
from openchem.chem.salt_components import fragment_formal_charge, fragment_key
from rdkit import Chem


def test_hydrogen_sulfate_and_sulfate_are_different_rows() -> None:
    hso4 = row_by_id("hydrogen_sulfate")
    so4 = row_by_id("sulfate")
    assert hso4 is not None and so4 is not None
    assert hso4.ion_smiles != so4.ion_smiles
    assert hso4.charge == -1
    assert so4.charge == -2


def test_every_row_round_trips_to_its_charge_and_key() -> None:
    for row in load_ionic_species():
        mol = Chem.MolFromSmiles(row.ion_smiles)
        assert mol is not None, row.ion_id
        assert fragment_formal_charge(mol) == row.charge, row.ion_id
        assert fragment_key(mol) == row.ion_smiles, row.ion_id


def test_catalog_is_not_a_pharma_whitelist() -> None:
    ids = {row.ion_id for row in load_ionic_species()}
    assert "chloride" in ids
    # An unusual ion is simply absent, not forbidden.
    assert row_by_id("hexafluorophosphate") is None
```

- [ ] **Step 2: Run — FAIL import.**

- [ ] **Step 3: Add JSON, loader, sources.toml entry.** Loader reads `Path(__file__).resolve().parent / "data" / "ionic_species.json"`. Refuse a row whose `charge` disagrees with `fragment_formal_charge` at load time by raising `ValueError` naming `id` (fail closed).

`REACHED_BY` on the loader module.

- [ ] **Step 4: Run `tests/test_ionic_species.py` and `tests/test_sources_are_current.py` (or the tests that fail on an unregistered `used_by` path / DOI).**

If `test_sources_are_current` requires `SOURCES.md` regeneration, run `uv run --no-sync python tools/build_sources_doc.py` and include the generated file.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/chem/ionic_species.py src/openchem/chem/data/ionic_species.json docs/sources.toml docs/SOURCES.md tests/test_ionic_species.py
git commit -m "Catalog named salt ions as graphs, with sulfate and hydrogen sulfate kept apart."
```

---

### Task 7: Changelog, shards, architecture, design status

**Files:**
- Create: changelog fragment via `tools/changelog.py new salt-composition-slice-3`
- Modify: `docs/SALT_COMPOSITION_DESIGN.md` status line — slice 3 adds ionization, catalog, pKa evidence; Mode C/UI still not authorized
- Modify: `docs/ROADMAP.md` salt-composition bullet
- Modify: `CLAUDE.md` Key Files salt line — mention `salt_ionization.py`, `salt_evidence.py`, `ionic_species.py`
- Modify: `docs/ARCHITECTURE.md` — chem count 165 → 167; name `salt_ionization.py` and `ionic_species.py` beside `salt_mode_a.py`
- Modify: `docs/README.md` salt row if it still says slice 1–2 only
- Modify: `tools/suite-shard-pins.json` via `--pin-new` **without** `--splits=3`
- Modify: `src/openchem/domain/salt_stoichiometry.py` `REACHED_BY` to also name new tests if the reachability guard requires it

**Interfaces:** none

- [ ] **Step 1: Changelog fragment** titled `### Salt composition, slice 3 (library, no UI)` so it does not collide with slice 1/2 headings.

Body:

```markdown
### Salt composition, slice 3 (library, no UI)

- Fully specified ionization (site transforms; net charge alone refused;
  several microspecies at one charge listed, not picked), two supplied ions
  as given, a small cited ion catalog, and `pka_compatible` as named-step
  evidence that never feeds `balance_two`. Still no panel and not a crystal.
```

- [ ] **Step 2: Pin** `python tools/suite_shards.py --pin-new`

- [ ] **Step 3: Docs + architecture count.** Run:

`uv run --no-sync pytest tests/test_docs_are_current.py::test_the_architecture_module_count_is_live tests/test_docs_are_current.py::test_every_chem_module_is_named_in_the_package_map tests/test_layering.py tests/test_salt_stoichiometry.py tests/test_salt_evidence.py tests/test_salt_ionization.py tests/test_ionic_species.py tests/test_constant_docs.py::test_no_constant_has_fallen_out_of_documentation tests/test_changelog_fragments.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add changelog.d docs/SALT_COMPOSITION_DESIGN.md docs/ROADMAP.md docs/ARCHITECTURE.md docs/README.md CLAUDE.md tools/suite-shard-pins.json src/openchem/domain/salt_stoichiometry.py
git commit -m "Record slice 3 of salt composition in the changelog and the file map."
```

---
