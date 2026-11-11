# Salt composition slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a domain-only two-ion charge balancer and a Mode B analyzer that classifies a drawing without silently correcting stoichiometry.

**Architecture:** `balance_two` lives in `domain/` (integers only, no RDKit, no `lattice_energy`). Mode B lives in `chem/`: graph-sensitive fragment identity, drawn counts, `drawn_total_charge`, and a diagnostic call to `balance_two` that never rewrites the input. Contract: [`docs/SALT_COMPOSITION_DESIGN.md`](../../SALT_COMPOSITION_DESIGN.md).

**Tech Stack:** Python 3.11+, stdlib `math.gcd`, RDKit only in `chem/` and tests, pytest, `uv run --no-sync pytest`.

## Global Constraints

- Work on `cursor/salt-composition-design` (this worktree), not `claude/nl005-close-validator`.
- No UI, no calculator registry, no pKa, no Mode A generation, no Mode C, no ionic-species JSON, no CIF/COD, no ion-pair 3D, no hydrates as first-class, no `balance_many`, no NaOH neutralization.
- Domain must not import `rdkit`, `openbabel`, `PySide6`, or `openchem.chem.lattice_energy`.
- `charge_valid` for Mode B is `drawn_total_charge == 0`. `balance_two`'s ratio is a separate diagnostic.
- Identity is isomeric canonical SMILES after sanitization, atom maps stripped; formula+charge is not identity.
- Neutral disconnected fragments are unclassified extras, not coformers/hydrates.
- Changelog is a fragment (`tools/changelog.py new`), not an edit of `CHANGELOG.md`.
- New test files: `uv run --no-sync python tools/suite_shards.py --pin-new --splits=3`.
- Tests that would pass if identity were formula+charge must use two different constitutions with the same formula.

---

### Task 1: Domain `balance_two` for the 1:1 case

**Files:**
- Create: `src/openchem/domain/salt_stoichiometry.py`
- Test: `tests/test_salt_stoichiometry.py`

**Interfaces:**
- Consumes: nothing
- Produces: `ChargedSpecies(identity: str, charge: int)`, `TwoIonBalance(cation_count: int, anion_count: int)`, `BalanceRefusal(code: str, reason: str)`, `balance_two(cation: ChargedSpecies, anion: ChargedSpecies) -> TwoIonBalance | BalanceRefusal`

- [ ] **Step 1: Write the failing test**

```python
"""Two-ion charge balance: integers only, no chemistry toolkit.

Contract: docs/SALT_COMPOSITION_DESIGN.md. The solver never sees a molecule.
"""

from openchem.domain.salt_stoichiometry import (
    BalanceRefusal,
    ChargedSpecies,
    TwoIonBalance,
    balance_two,
)


def test_plus_one_and_minus_one_is_one_to_one() -> None:
    result = balance_two(
        ChargedSpecies(identity="cation", charge=1),
        ChargedSpecies(identity="anion", charge=-1),
    )
    assert result == TwoIonBalance(cation_count=1, anion_count=1)
    assert not isinstance(result, BalanceRefusal)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_salt_stoichiometry.py::test_plus_one_and_minus_one_is_one_to_one -v`

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `openchem.domain.salt_stoichiometry`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Smallest charge-neutral integers for exactly two ions.

No RDKit. No lattice-energy import. Identity is opaque: the solver uses
charges only. Drawn multiplicities are a later layer's problem.

    n_C = |z-| / gcd(|z+|, |z-|)
    n_A = |z+| / gcd(|z+|, |z-|)
"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd


@dataclass(frozen=True)
class ChargedSpecies:
    """One ion, as the stoichiometry layer is allowed to see it."""

    identity: str
    charge: int


@dataclass(frozen=True)
class TwoIonBalance:
    cation_count: int
    anion_count: int


@dataclass(frozen=True)
class BalanceRefusal:
    code: str
    reason: str


def balance_two(
    cation: ChargedSpecies, anion: ChargedSpecies
) -> TwoIonBalance | BalanceRefusal:
    if cation.charge <= 0 or anion.charge >= 0:
        return BalanceRefusal(
            code="not_opposite_signs",
            reason=(
                "A binary salt needs one positive charge and one negative "
                f"charge; got {cation.charge:+d} and {anion.charge:+d}."
            ),
        )
    common = gcd(cation.charge, -anion.charge)
    return TwoIonBalance(
        cation_count=(-anion.charge) // common,
        anion_count=cation.charge // common,
    )
```

- [ ] **Step 4: Run the test and make sure it passes**

Run: `uv run --no-sync pytest tests/test_salt_stoichiometry.py::test_plus_one_and_minus_one_is_one_to_one -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/openchem/domain/salt_stoichiometry.py tests/test_salt_stoichiometry.py
git commit -m "Add a domain two-ion balancer so charge math has no chemistry in it."
```

---

### Task 2: Remaining two-ion ratios and refusals

**Files:**
- Modify: `src/openchem/domain/salt_stoichiometry.py`
- Test: `tests/test_salt_stoichiometry.py`

**Interfaces:**
- Consumes: `balance_two` from Task 1
- Produces: same signatures; refusal codes `not_opposite_signs` (covers zero charge and same sign)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_salt_stoichiometry.py`)

```python
import pytest


@pytest.mark.parametrize(
    ("z_plus", "z_minus", "n_c", "n_a"),
    [
        (1, -2, 2, 1),
        (2, -1, 1, 2),
        (2, -2, 1, 1),
        (3, -2, 2, 3),
        (4, -2, 1, 2),
        (6, -9, 3, 2),
    ],
)
def test_the_reduced_ratio_follows_the_gcd(
    z_plus: int, z_minus: int, n_c: int, n_a: int
) -> None:
    result = balance_two(
        ChargedSpecies("c", z_plus),
        ChargedSpecies("a", z_minus),
    )
    assert result == TwoIonBalance(cation_count=n_c, anion_count=n_a)
    assert n_c * z_plus + n_a * z_minus == 0


def test_identity_is_ignored_by_the_counts() -> None:
    a = balance_two(ChargedSpecies("NH4+", 1), ChargedSpecies("Cl-", -1))
    b = balance_two(ChargedSpecies("Na+", 1), ChargedSpecies("acetate", -1))
    assert a == b == TwoIonBalance(cation_count=1, anion_count=1)


def test_a_zero_charge_is_refused() -> None:
    result = balance_two(ChargedSpecies("c", 0), ChargedSpecies("a", -1))
    assert isinstance(result, BalanceRefusal)
    assert result.code == "not_opposite_signs"


def test_same_sign_charges_are_refused() -> None:
    result = balance_two(ChargedSpecies("c", 1), ChargedSpecies("a", 1))
    assert isinstance(result, BalanceRefusal)
    assert result.code == "not_opposite_signs"


def test_roles_swapped_are_refused() -> None:
    """The cation argument must actually be positive."""
    result = balance_two(ChargedSpecies("c", -1), ChargedSpecies("a", 1))
    assert isinstance(result, BalanceRefusal)


def test_successful_counts_are_positive() -> None:
    result = balance_two(ChargedSpecies("c", 3), ChargedSpecies("a", -2))
    assert isinstance(result, TwoIonBalance)
    assert result.cation_count > 0 and result.anion_count > 0
```

- [ ] **Step 2: Run tests to verify they fail or already pass**

Run: `uv run --no-sync pytest tests/test_salt_stoichiometry.py -v`

Expected: the GCD cases PASS on the Task 1 implementation; keep them. If any FAIL, they must FAIL on assertion, not import.

- [ ] **Step 3: Adjust implementation only if a case fails**

Task 1's `gcd` formula already covers the table. Do not import `lattice_energy`. Do not add `balance_many`.

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `uv run --no-sync pytest tests/test_salt_stoichiometry.py -v`

Expected: all PASS

- [ ] **Step 5: Guard that the domain module does not import lattice energy**

Append:

```python
from pathlib import Path


def test_the_domain_module_does_not_import_lattice_energy() -> None:
    text = Path("src/openchem/domain/salt_stoichiometry.py").read_text(
        encoding="utf-8"
    )
    assert "lattice_energy" not in text
    assert "rdkit" not in text.lower()
```

Run: `uv run --no-sync pytest tests/test_salt_stoichiometry.py::test_the_domain_module_does_not_import_lattice_energy -v`

Expected: PASS. Also: `uv run --no-sync pytest tests/test_layering.py::test_the_domain_layer_imports_neither_a_toolkit_nor_a_gui -v` PASS.

- [ ] **Step 6: Commit**

```bash
git add src/openchem/domain/salt_stoichiometry.py tests/test_salt_stoichiometry.py
git commit -m "Cover the two-ion GCD table and refuse same-sign or zero charges."
```

---

### Task 3: Graph-sensitive fragment identity

**Files:**
- Create: `src/openchem/chem/salt_components.py`
- Test: `tests/test_salt_components.py`

**Interfaces:**
- Consumes: RDKit `Mol` (a single connected fragment)
- Produces: `fragment_identity(mol) -> str`, `fragment_formal_charge(mol) -> int`, `IdentityRefusal(code: str, reason: str)` if sanitization fails — use a result type:

`def fragment_key(mol: Chem.Mol) -> str | IdentityRefusal`

- [ ] **Step 1: Write the failing tests**

```python
"""Mode B pieces: identity is the graph, not the formula.

Contract: docs/SALT_COMPOSITION_DESIGN.md.
"""

from rdkit import Chem

from openchem.chem.salt_components import fragment_key


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None
    return mol


def test_butanoate_and_methylpropanoate_do_not_share_an_identity() -> None:
    a = fragment_key(_mol("CCCC(=O)[O-]"))
    b = fragment_key(_mol("CC(C)C(=O)[O-]"))
    assert isinstance(a, str) and isinstance(b, str)
    assert a != b
    formula_a = Chem.rdMolDescriptors.CalcMolFormula(_mol("CCCC(=O)[O-]"))
    formula_b = Chem.rdMolDescriptors.CalcMolFormula(_mol("CC(C)C(=O)[O-]"))
    assert formula_a.split("-")[0] == formula_b.split("-")[0]


def test_atom_maps_are_stripped_from_the_key() -> None:
    mapped = _mol("[Na+:1]")
    plain = _mol("[Na+]")
    assert fragment_key(mapped) == fragment_key(plain)


def test_enantiomeric_carboxylates_keep_distinct_keys() -> None:
    r = fragment_key(_mol("C[C@H](O)C(=O)[O-]"))
    s = fragment_key(_mol("C[C@@H](O)C(=O)[O-]"))
    assert r != s


def test_sodium_oxide_is_not_sulfate() -> None:
    oxide = fragment_key(_mol("[O-2]"))
    sulfate = fragment_key(_mol("S(=O)(=O)([O-])[O-]"))
    assert oxide != sulfate
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_salt_components.py::test_butanoate_and_methylpropanoate_do_not_share_an_identity -v`

Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

```python
"""Fragments of a drawing, identified by graph, for salt Mode B.

Does not call chem.substance._components: that key is (formula, charge).
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem


@dataclass(frozen=True)
class IdentityRefusal:
    code: str
    reason: str


def fragment_formal_charge(mol: Chem.Mol) -> int:
    return sum(atom.GetFormalCharge() for atom in mol.GetAtoms())


def fragment_key(mol: Chem.Mol) -> str | IdentityRefusal:
    copy = Chem.Mol(mol)
    for atom in copy.GetAtoms():
        atom.SetAtomMapNum(0)
    try:
        Chem.SanitizeMol(copy)
    except (ValueError, RuntimeError):
        return IdentityRefusal(
            code="unsanitizable",
            reason="The fragment could not be sanitized, so it has no identity key.",
        )
    smiles = Chem.MolToSmiles(copy, isomericSmiles=True)
    charge = fragment_formal_charge(copy)
    parsed = Chem.MolFromSmiles(smiles)
    if parsed is None:
        return IdentityRefusal(
            code="unsanitizable",
            reason="The canonical SMILES of the fragment could not be read back.",
        )
    if fragment_formal_charge(parsed) != charge:
        return IdentityRefusal(
            code="charge_mismatch",
            reason=(
                f"The graph key {smiles!r} has charge "
                f"{fragment_formal_charge(parsed):+d}, not {charge:+d}."
            ),
        )
    return smiles
```

Do **not** run tautomer canonicalization or `CanonicalRankAtoms` beyond `MolToSmiles`.

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `uv run --no-sync pytest tests/test_salt_components.py -v`

Expected: PASS. If enantiomers collapse, the implementation dropped `isomericSmiles=True` — restore it.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/chem/salt_components.py tests/test_salt_components.py
git commit -m "Key salt fragments by isomeric SMILES so formula twins stay distinct."
```

---

### Task 4: Mode B `analyze_drawing` — balanced binary and no silent correction

**Files:**
- Modify: `src/openchem/chem/salt_components.py`
- Test: `tests/test_salt_components.py`

**Interfaces:**
- Consumes: `fragment_key`, `fragment_formal_charge`, `balance_two`, `ChargedSpecies`, `TwoIonBalance`
- Produces:

```python
@dataclass(frozen=True)
class SaltComponent:
    identity: str
    charge: int
    drawn_count: int
    formula: str

@dataclass(frozen=True)
class ModeBResult:
    code: str
    # "charge_neutral" | "unbalanced" | "unsupported_multicomponent"
    # | "ambiguous_pairing" | "not_a_salt" | "zwitterion" | "identity_refused"
    reason: str
    ions: tuple[SaltComponent, ...]
    extras: tuple[SaltComponent, ...]
    drawn_total_charge: int
    charge_valid: bool
    theoretical: TwoIonBalance | None

def analyze_drawing(mol: Chem.Mol) -> ModeBResult
```

- [ ] **Step 1: Write the failing tests** (append)

```python
from openchem.chem.salt_components import analyze_drawing
from openchem.domain.salt_stoichiometry import TwoIonBalance


def test_two_chlorides_and_calcium_is_charge_neutral() -> None:
    mol = _mol("[Ca+2].[Cl-].[Cl-]")
    result = analyze_drawing(mol)
    assert result.code == "charge_neutral"
    assert result.charge_valid is True
    assert result.drawn_total_charge == 0
    assert result.theoretical == TwoIonBalance(cation_count=1, anion_count=2)
    calcium = next(c for c in result.ions if c.charge > 0)
    chloride = next(c for c in result.ions if c.charge < 0)
    assert calcium.drawn_count == 1 and chloride.drawn_count == 2


def test_one_chloride_and_calcium_is_not_silently_corrected() -> None:
    mol = _mol("[Ca+2].[Cl-]")
    result = analyze_drawing(mol)
    assert result.code == "unbalanced"
    assert result.charge_valid is False
    assert result.drawn_total_charge == 1
    assert result.theoretical == TwoIonBalance(cation_count=1, anion_count=2)
    chloride = next(c for c in result.ions if c.charge < 0)
    assert chloride.drawn_count == 1


def test_one_sodium_and_sulfate_is_unbalanced() -> None:
    mol = _mol("[Na+].S(=O)(=O)([O-])[O-]")
    result = analyze_drawing(mol)
    assert result.code == "unbalanced"
    assert result.charge_valid is False
    assert result.theoretical == TwoIonBalance(cation_count=2, anion_count=1)


def test_two_sodium_and_sulfate_is_charge_neutral() -> None:
    mol = _mol("[Na+].[Na+].S(=O)(=O)([O-])[O-]")
    result = analyze_drawing(mol)
    assert result.code == "charge_neutral"
    assert result.charge_valid is True
    sodium = next(c for c in result.ions if c.charge > 0)
    assert sodium.drawn_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest tests/test_salt_components.py::test_one_chloride_and_calcium_is_not_silently_corrected -v`

Expected: FAIL with `analyze_drawing` not defined

- [ ] **Step 3: Write `analyze_drawing`**

Implementation rules (must appear in the module docstring as well):

1. Split with `Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)`.
2. Key each fragment with `fragment_key`. On `IdentityRefusal`, return `code="identity_refused"` and that reason.
3. `charge == 0` fragments go to `extras` (formula via `rdMolDescriptors.CalcMolFormula` after sanitize of a copy). Do not label them coformer/hydrate.
4. Nonzero-charge fragments group by `identity` (not formula). `drawn_count` is the group size.
5. Distinct ionic identities: if `>= 2` cations and `>= 2` anions → `ambiguous_pairing`, `theoretical=None`, do not call `balance_two`.
6. Else if distinct ionic identities `> 2` → `unsupported_multicomponent`, `theoretical=None`.
7. Else if distinct ionic identities `== 0`: if one fragment and that fragment has both a positive and a negative atom charge → `zwitterion`; else `not_a_salt`.
8. Else if exactly one cation identity and one anion identity: `drawn_total_charge = sum(c.drawn_count * c.charge for c in ions)`. Call `balance_two` for `theoretical`. If `drawn_total_charge == 0` then `code="charge_neutral"` and `charge_valid=True`; else `code="unbalanced"` and `charge_valid=False`. **Never change `drawn_count`.**
9. One ionic identity only (e.g. only `[Na+]`) → `unbalanced` (or `not_a_salt` if you treat a lone ion as not a salt pair: **use `unbalanced`** when any ion is present without a counter-ion of opposite sign; `theoretical=None`).

```python
from collections import defaultdict

from rdkit.Chem import rdMolDescriptors

from openchem.domain.salt_stoichiometry import (
    ChargedSpecies,
    TwoIonBalance,
    balance_two,
)


@dataclass(frozen=True)
class SaltComponent:
    identity: str
    charge: int
    drawn_count: int
    formula: str


@dataclass(frozen=True)
class ModeBResult:
    code: str
    reason: str
    ions: tuple[SaltComponent, ...]
    extras: tuple[SaltComponent, ...]
    drawn_total_charge: int
    charge_valid: bool
    theoretical: TwoIonBalance | None


def _formula(mol: Chem.Mol) -> str:
    copy = Chem.Mol(mol)
    try:
        Chem.SanitizeMol(copy)
    except (ValueError, RuntimeError):
        return ""
    return rdMolDescriptors.CalcMolFormula(copy)


def analyze_drawing(mol: Chem.Mol) -> ModeBResult:
    if mol is None or mol.GetNumAtoms() == 0:
        return ModeBResult(
            code="not_a_salt",
            reason="empty structure",
            ions=(),
            extras=(),
            drawn_total_charge=0,
            charge_valid=False,
            theoretical=None,
        )
    frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
    extras_acc: dict[str, SaltComponent] = {}
    ion_acc: dict[str, SaltComponent] = {}
    for frag in frags:
        key = fragment_key(frag)
        if isinstance(key, IdentityRefusal):
            return ModeBResult(
                code="identity_refused",
                reason=key.reason,
                ions=(),
                extras=(),
                drawn_total_charge=0,
                charge_valid=False,
                theoretical=None,
            )
        charge = fragment_formal_charge(frag)
        formula = _formula(frag)
        bucket = extras_acc if charge == 0 else ion_acc
        existing = bucket.get(key)
        if existing is None:
            bucket[key] = SaltComponent(key, charge, 1, formula)
        else:
            bucket[key] = SaltComponent(key, charge, existing.drawn_count + 1, formula)
    ions = tuple(ion_acc.values())
    extras = tuple(extras_acc.values())
    drawn_total = sum(c.drawn_count * c.charge for c in ions)
    cations = [c for c in ions if c.charge > 0]
    anions = [c for c in ions if c.charge < 0]

    def _result(code: str, reason: str, theoretical: TwoIonBalance | None, valid: bool) -> ModeBResult:
        return ModeBResult(code, reason, ions, extras, drawn_total, valid, theoretical)

    if len(cations) >= 2 and len(anions) >= 2:
        return _result(
            "ambiguous_pairing",
            "Several cation and anion species; the drawing does not say which pair.",
            None,
            False,
        )
    if len(ions) > 2:
        return _result(
            "unsupported_multicomponent",
            "More than two distinct ionic species; v1 does not balance those.",
            None,
            False,
        )
    if len(cations) == 1 and len(anions) == 1:
        theoretical = balance_two(
            ChargedSpecies(cations[0].identity, cations[0].charge),
            ChargedSpecies(anions[0].identity, anions[0].charge),
        )
        ratio = theoretical if isinstance(theoretical, TwoIonBalance) else None
        if drawn_total == 0:
            return _result(
                "charge_neutral",
                "Drawn charges cancel. The theoretical ratio is a separate fact.",
                ratio,
                True,
            )
        return _result(
            "unbalanced",
            "Drawn charges do not cancel. The theoretical ratio is diagnostic only.",
            ratio,
            False,
        )
    if ions:
        return _result(
            "unbalanced",
            "No opposite-charge partner in the drawing.",
            None,
            False,
        )
    if len(frags) == 1:
        signs = {atom.GetFormalCharge() for atom in mol.GetAtoms() if atom.GetFormalCharge()}
        if 1 in {1 if s > 0 else -1 for s in signs} and -1 in {1 if s > 0 else -1 for s in signs}:
            return _result(
                "zwitterion",
                "One connected molecule with internal charges, not a salt pair.",
                None,
                False,
            )
    return _result(
        "not_a_salt",
        "No charged components.",
        None,
        False,
    )
```

Fix the zwitterion sign set in implementation: use `any(c > 0)` and `any(c < 0)` on atom formal charges. Do not ship the `{1 if s > 0}` draft if a cleaner check exists:

```python
atom_charges = [atom.GetFormalCharge() for atom in mol.GetAtoms()]
if any(c > 0 for c in atom_charges) and any(c < 0 for c in atom_charges):
    ...
```

- [ ] **Step 4: Run the four tests**

Run: `uv run --no-sync pytest tests/test_salt_components.py::test_two_chlorides_and_calcium_is_charge_neutral tests/test_salt_components.py::test_one_chloride_and_calcium_is_not_silently_corrected tests/test_salt_components.py::test_one_sodium_and_sulfate_is_unbalanced tests/test_salt_components.py::test_two_sodium_and_sulfate_is_charge_neutral -v`

Expected: PASS. The unbalanced calcium test must still have `drawn_count == 1` for chloride.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/chem/salt_components.py tests/test_salt_components.py
git commit -m "Analyze drawn salts without rewriting an unbalanced ratio as CaCl2."
```

---

### Task 5: Mode B classification refusals and extras

**Files:**
- Modify: `src/openchem/chem/salt_components.py` only if a test fails
- Test: `tests/test_salt_components.py`

**Interfaces:**
- Consumes: `analyze_drawing` from Task 4
- Produces: unchanged `ModeBResult.code` vocabulary

- [ ] **Step 1: Write the failing tests**

```python
def test_two_cations_and_one_anion_is_unsupported() -> None:
    mol = _mol("[Na+].[K+].[Cl-]")
    result = analyze_drawing(mol)
    assert result.code == "unsupported_multicomponent"
    assert result.theoretical is None
    assert result.charge_valid is False


def test_one_cation_and_two_anions_is_unsupported() -> None:
    mol = _mol("[Na+].[Cl-].[Br-]")
    result = analyze_drawing(mol)
    assert result.code == "unsupported_multicomponent"
    assert result.theoretical is None


def test_nacl_and_kbr_is_ambiguous() -> None:
    mol = _mol("[Na+].[Cl-].[K+].[Br-]")
    result = analyze_drawing(mol)
    assert result.code == "ambiguous_pairing"
    assert result.theoretical is None


def test_ethanol_and_benzene_is_not_a_salt() -> None:
    mol = _mol("CCO.c1ccccc1")
    result = analyze_drawing(mol)
    assert result.code == "not_a_salt"
    assert result.ions == ()
    assert len(result.extras) == 2
    assert "coformer" not in result.reason.lower()
    assert "hydrate" not in result.reason.lower()
    assert "solvate" not in result.reason.lower()


def test_a_neutral_extra_beside_nacl_is_unclassified() -> None:
    mol = _mol("[Na+].[Cl-].CCO")
    result = analyze_drawing(mol)
    assert result.code == "charge_neutral"
    assert len(result.extras) == 1
    assert "coformer" not in result.reason.lower()


def test_glycine_zwitterion_is_one_molecule() -> None:
    mol = _mol("C(C(=O)[O-])[NH3+]")
    result = analyze_drawing(mol)
    assert result.code == "zwitterion"
    assert result.ions == ()
    assert result.theoretical is None


def test_drawn_counts_survive_when_the_ratio_reduces() -> None:
    mol = _mol("[Ca+2].[Ca+2].[Cl-].[Cl-].[Cl-].[Cl-]")
    result = analyze_drawing(mol)
    assert result.code == "charge_neutral"
    calcium = next(c for c in result.ions if c.charge > 0)
    chloride = next(c for c in result.ions if c.charge < 0)
    assert calcium.drawn_count == 2
    assert chloride.drawn_count == 4
    assert result.theoretical == TwoIonBalance(cation_count=1, anion_count=2)
```

- [ ] **Step 2: Run tests**

Run: `uv run --no-sync pytest tests/test_salt_components.py -v`

Expected: FAIL on unsupported/ambiguous/zwitterion until Task 4's branches exist; then PASS.

- [ ] **Step 3: Implement missing branches** so `[Na+].[K+].[Cl-]` is `unsupported_multicomponent` (len(ions)==3, not 2+2) and `[Na+].[Cl-].[K+].[Br-]` is `ambiguous_pairing`. Check **ambiguous first**.

- [ ] **Step 4: Run the full Mode B file**

Run: `uv run --no-sync pytest tests/test_salt_components.py tests/test_salt_stoichiometry.py -v`

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/openchem/chem/salt_components.py tests/test_salt_components.py
git commit -m "Refuse multicomponent and ambiguous drawings instead of inventing a pair."
```

---

### Task 6: Changelog, shards, and index

**Files:**
- Create: `changelog.d/YYYYMMDDHHMM-salt-composition-slice-1-<hex>.md` via the tool
- Modify: `docs/SALT_COMPOSITION_DESIGN.md` status line only (slice 1 in progress, still no UI)
- Modify: `CLAUDE.md` Key Files — one line for the two new modules
- Modify: `tests/` shard pin file (whatever `tools/suite_shards.py --pin-new` edits)

**Interfaces:** none

- [ ] **Step 1: Create the fragment**

Run: `uv run --no-sync python tools/changelog.py new salt-composition-slice-1`

Edit the printed file to:

```markdown
### Salt composition (library, no UI)

- Two-ion charge balance as a domain function, and Mode B analysis of a
  disconnected drawing: drawn counts, a diagnostic theoretical ratio, and
  refusals for unbalanced, unsupported, and ambiguous inputs. Not a claim
  that a salt exists. No panel and no calculator row.
```

Run: `uv run --no-sync python tools/changelog.py check`

Expected: exit 0

- [ ] **Step 2: Pin new tests**

Run: `uv run --no-sync python tools/suite_shards.py --pin-new --splits=3`

Expected: the two new test files appear in the pin map. Commit that file with the tests if it changed.

- [ ] **Step 3: One-liner in `CLAUDE.md` Key Files**

Add after the `formulation.py` mention is not required; add:

`- src/openchem/domain/salt_stoichiometry.py / chem/salt_components.py -- two-ion charge balance and Mode B drawing analysis (docs/SALT_COMPOSITION_DESIGN.md); no UI`

Keep it one line.

- [ ] **Step 4: Design note status**

Change the first paragraph status to: architecture contract accepted for slice 1; `balance_two` and Mode B are the first code; Mode A/C/UI still not authorized by this slice.

- [ ] **Step 5: Run the docs citation guard if CLAUDE/design cite the new `.py` files**

`docs/SALT_COMPOSITION_DESIGN.md` currently avoids citing unbuilt `.py` paths. After the files exist, you **may** cite them in backticks. If you add `src/openchem/domain/salt_stoichiometry.py` to a guarded doc, stage the source files first (`git add`) so `git ls-files` sees them.

Run: `uv run --no-sync pytest tests/test_docs_are_current.py::test_every_file_a_doc_cites_still_exists tests/test_layering.py -q --tb=line`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add changelog.d docs/SALT_COMPOSITION_DESIGN.md CLAUDE.md
git add tests/  # only the shard pin if changed
git commit -m "Record slice 1 of salt composition in the changelog and the file map."
```

---

## Later slices (not this plan)

- Slice 2: Mode A molecular `B + HA` with multiplicity-weighted conservation; refuse NaOH neutralization; refuse neutral + supplied ion without a proton source.
- Slice 3: fully specified ionization states; polyprotic/polybasic pKa as evidence only.
- Slice 4: Mode C enumeration with generated/returned/omitted.
- Slice 5: UI beside the pKa view.

## Spec coverage (slice 1)

| Contract item | Task |
|---|---|
| Domain `balance_two`, no RDKit, no lattice_energy | 1–2 |
| GCD table +1/−1 … +3/−2 | 2 |
| Identity ≠ formula | 3 |
| Atom maps / stereo | 3 |
| No silent CaCl2 correction | 4 |
| Na2SO4 drawn vs 1:1 | 4 |
| >2 ionic species / ambiguous | 5 |
| Neutral extras unclassified | 5 |
| Zwitterion | 5 |
| Drawn counts vs reduced ratio | 5 |
| Mode A / pKa / Mode C / UI / NaOH / hydrates / CIF | deferred |

## Execution

Plan saved to `docs/superpowers/plans/2026-11-10-salt-composition-slice-1.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks
2. **Inline Execution** — execute tasks in this session with checkpoints

Which approach?
