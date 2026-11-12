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

