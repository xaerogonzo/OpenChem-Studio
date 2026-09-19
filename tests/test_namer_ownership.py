"""Atom ownership on the semantic tree (naming round 5, N2).

Every heavy atom named at a substitutive level is owned by exactly one node of
the tree built for it -- parent, suffix group or prefix -- and that is checked
on the TREE (`ownership.py`), not on the plan and never on the emitted string.

The plan-level check the engine already had asks only whether the union of the
plan's claims covers the molecule. Round 4 dropped atoms twice past it, both
caught only by an OPSIN round trip after the fact:

* a claimed prefix that never became a tree node ("pentanoic acid" for an
  oxime acid);
* an Si-OH suffix class that owned the Si under the form "ol", so
  trimethylsilanol came out "hydroxymethane".

The tests below re-inject both, plus a doubly owned atom and a spectator owned
by the wrong tree, and run the tuning populations in strict mode. heldout_v3
is never named here (tests/test_naming_heldout_lock.py).
"""

from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import engine, name_smiles, ownership
from openchem.vendor.iupac_namer.strategy import default_strategy

BENCH = Path(__file__).resolve().parent.parent / "benchmarks" / "naming"


@pytest.fixture
def strict(monkeypatch):
    monkeypatch.setenv("OPENCHEM_NAMER_OWNERSHIP", "strict")


def _tree(smiles: str):
    return engine.name(Chem.MolFromSmiles(smiles), default_strategy())


# --- the wiring: through name_smiles, the path every caller takes -------------


def _drop_prefixes_claiming(atom: int):
    """Round 4's first drop, re-injected: an assignment whose execution
    appends nothing, so its atoms reach no node."""
    original = ownership.ClaimingPrefixList.append

    def append(self, entry):
        if atom in self.claim:
            return
        original(self, entry)

    return append


def test_a_prefix_that_never_becomes_a_node_is_caught_in_strict_mode(strict, monkeypatch):
    """Glycolic acid's hydroxy is the only prefix; dropping it would name
    the molecule "acetic acid", which parses and is a different molecule."""
    monkeypatch.setattr(ownership.ClaimingPrefixList, "append", _drop_prefixes_claiming(0))
    with pytest.raises(ownership.OwnershipError, match="owned by no node"):
        name_smiles("OCC(=O)O")


def test_in_production_the_dropped_name_is_never_emitted(monkeypatch):
    """`enforce` (the default) fails the plan closed instead of raising, so the
    plan loop moves on. Whatever comes out, it is not the name missing the O."""
    monkeypatch.delenv("OPENCHEM_NAMER_OWNERSHIP", raising=False)
    monkeypatch.setattr(ownership.ClaimingPrefixList, "append", _drop_prefixes_claiming(0))
    assert name_smiles("OCC(=O)O") != "acetic acid"


def test_the_unmutated_molecule_names_as_before(strict):
    assert name_smiles("OCC(=O)O") == "hydroxyacetic acid"


# --- mutations of REAL engine trees ------------------------------------------


def test_every_prefix_is_stamped_with_the_atoms_it_names():
    tree = _tree("OCC(=O)O")
    assert [sorted(p.claimed_atoms) for p in tree.prefixes] == [[0]]
    assert ownership.check_substitutive_level(Chem.MolFromSmiles("OCC(=O)O"), tree) is None


def test_an_atom_owned_twice_is_caught():
    tree = _tree("OCC(=O)O")
    doubled = dataclasses.replace(tree, prefixes=tree.prefixes + tree.prefixes)
    violation = ownership.check_substitutive_level(Chem.MolFromSmiles("OCC(=O)O"), doubled)
    assert violation is not None and violation.owned_twice == ((0, ("prefix[0]", "prefix[1]")),)


def test_a_suffix_cannot_own_an_element_its_form_does_not_name():
    """Round 4's second drop, as a tree. 2-methylpropan-2-ol's real tree has
    the same indices as the silanol; moving the central atom from the parent
    into the "ol" suffix is exactly the abandoned Si-OH suffix class, which
    named trimethylsilanol "hydroxymethane". Every atom is still owned once,
    so only the element rule can see it."""
    carbinol = _tree("CC(C)(C)O")
    assert carbinol.named_parent.name == "propane"
    silanol = Chem.MolFromSmiles("C[Si](C)(C)O")
    parent = carbinol.named_parent
    candidate = dataclasses.replace(
        parent.candidate, atom_indices=frozenset(parent.candidate.atom_indices) - {1}
    )
    group = carbinol.suffix_groups[0]
    mutated = dataclasses.replace(
        carbinol,
        named_parent=dataclasses.replace(parent, candidate=candidate),
        suffix_groups=(dataclasses.replace(
            group, fg=dataclasses.replace(group.fg, atoms=frozenset(group.fg.atoms) | {1}),
        ),),
    )
    violation = ownership.check_substitutive_level(silanol, mutated)
    assert violation is not None
    assert not violation.unowned and not violation.owned_twice
    assert violation.inexpressible == ((1, "suffix[0] 'ol'"),)


def test_a_spectator_left_unnamed_at_a_substitutive_level_is_caught():
    """A salt's ions each reach the executor as their own fragment
    (`_name_salt`). If the whole drawing ever reached a substitutive level,
    the counter-ion would be owned by nothing -- and that is reported, never
    passed as an allowed exclusion."""
    salt = Chem.MolFromSmiles("CCC(=O)[O-].[Na+]")
    propanoate = _tree("CCC(=O)O")  # same first five indices; acetic acid is a retained leaf
    violation = ownership.check_substitutive_level(salt, propanoate)
    assert violation is not None and violation.unowned == (5,)


def test_a_spectator_owned_by_the_parent_is_caught():
    salt = Chem.MolFromSmiles("CCC(=O)[O-].[Na+]")
    propanoate = _tree("CCC(=O)O")
    parent = propanoate.named_parent
    grabbed = dataclasses.replace(
        propanoate,
        named_parent=dataclasses.replace(parent, candidate=dataclasses.replace(
            parent.candidate, atom_indices=frozenset(parent.candidate.atom_indices) | {5},
        )),
    )
    violation = ownership.check_substitutive_level(salt, grabbed)
    assert violation is not None and violation.outside_component
    assert not violation.unowned


def test_record_mode_keeps_the_tree_and_collects_the_diagnostic(monkeypatch):
    monkeypatch.setenv("OPENCHEM_NAMER_OWNERSHIP", "record")
    tree = _tree("OCC(=O)O")
    doubled = dataclasses.replace(tree, prefixes=tree.prefixes + tree.prefixes)
    before = len(ownership.RECORDED)
    kept = ownership.enforce(Chem.MolFromSmiles("OCC(=O)O"), doubled, lambda m: None)
    assert kept is doubled
    assert "owned by prefix[0] and prefix[1]" in ownership.RECORDED[before]


# --- the populations the round tunes on --------------------------------------


def _tuning_rows():
    rows = []
    for filename in ("corpus.json", "heldout.json", "heldout2.json"):
        rows += json.loads((BENCH / filename).read_text(encoding="utf-8"))
    return rows


def test_every_tuning_row_holds_the_invariant_in_strict_mode(strict):
    """Measured before the check was enforced (record mode, 2026-09-19): 30
    double-owned levels in 22 molecules, every one a suffix SMARTS counting
    its neighbours -- fixed by reading the pattern's context atoms, not by
    loosening the check. 0 after, and no name changed."""
    logging.disable(logging.WARNING)
    try:
        failures = []
        for row in _tuning_rows():
            try:
                name_smiles(row["smiles"])
            except ownership.OwnershipError as exc:
                failures.append(f"{row['label']}: {exc}")
            except Exception:  # noqa: BLE001 - other failures are not this test's
                pass
    finally:
        logging.disable(logging.NOTSET)
    assert not failures, failures
