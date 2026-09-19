"""Atom ownership on the semantic tree (naming round 5, N2).

**THE INVARIANT.** Every heavy atom of the molecule named at a level is owned
by EXACTLY ONE node of the tree built for that level: the parent hydride, one
suffix group, or one prefix. Checked on the tree the executor is about to
return -- never by parsing the emitted string -- and at every recursion depth,
because every substituent is named by the same executor.

**WHY THE PLAN-LEVEL CHECK WAS NOT ENOUGH.** `SubstitutivePath.execute` has
long had a "no silent atom drop" check, but it asks only whether the UNION of
the plan's claims covers the molecule. Two things escape that:

* a claim that never becomes a tree node. Round 4 measured it twice: an FG
  with no prefix form that was not the principal group was claimed by a
  prefix assignment, produced no `PrefixEntry`, and "pentanoic acid" was
  emitted for an oxime acid; and an Si-OH suffix class claimed the Si, whose
  suffix could not express it, so trimethylsilanol came out "hydroxymethane".
  Both were caught only by an OPSIN round trip, after the fact.
* an atom claimed twice, which a union cannot see at all.

So the tree carries its own provenance: `PrefixEntry.claimed_atoms` is
stamped from the plan assignment that produced the entry
(`ClaimingPrefixList`), and the check reads the tree.

**WHAT A NODE OWNS.**

* parent: `named_parent.candidate.atom_indices`;
* a suffix group: its FG atoms that are neither parent atoms (a
  chain-terminal "-oic acid" carbon is a parent atom; its oxygens are the
  suffix's) nor pattern CONTEXT. A suffix SMARTS matches its neighbours as
  plain ``[#6]`` -- the R of an amine, the N-R of an amide, both R of a
  ketone -- and those atoms belong to whatever names them; first measured,
  every one of the 30 double-owned levels on the tuning corpora was this;
* a prefix: `claimed_atoms`.

Hydrogens are never owned; indicated and added hydrogen are descriptors.

**MODES** (`OPENCHEM_NAMER_OWNERSHIP`, read per call so a test can switch it):

* ``enforce`` (default): a violating tree is replaced by an `ErrorTree`
  carrying the diagnostic, so the plan loop tries the next plan and no name
  missing an atom is ever emitted -- "unsupported is not success";
* ``strict``: raise `OwnershipError` (the test suite runs this way);
* ``record``: keep the tree, append the diagnostic to `RECORDED` (for
  measuring a corpus before the check is enforced).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any

#: Diagnostics collected in ``record`` mode, oldest first.
RECORDED: list[str] = []

_MODE_VARIABLE = "OPENCHEM_NAMER_OWNERSHIP"


class OwnershipError(AssertionError):
    """A tree left a heavy atom unowned or owned it twice."""


def mode() -> str:
    value = os.environ.get(_MODE_VARIABLE, "enforce").strip().lower()
    return value if value in {"enforce", "strict", "record"} else "enforce"


class ClaimingPrefixList(list):
    """The executor's prefix list, which stamps each new entry with the atoms
    of the prefix assignment being executed.

    Every `PrefixEntry` in `SubstitutivePath.execute` is appended inside the
    loop over `plan.prefix_assignments` (19 sites when this was written), so
    setting `claim` once per iteration gives every entry its provenance
    without touching any of them -- and gives a future 20th site provenance
    too. An entry that already names its atoms keeps them.
    """

    def __init__(self) -> None:
        super().__init__()
        self.claim: frozenset[int] = frozenset()

    def append(self, entry: Any) -> None:  # noqa: D102
        if not getattr(entry, "claimed_atoms", None):
            entry = replace(entry, claimed_atoms=self.claim)
        super().append(entry)


@dataclass(frozen=True)
class Violation:
    """What was wrong, in terms a reader can check on the structure."""

    unowned: tuple[int, ...]
    owned_twice: tuple[tuple[int, tuple[str, ...]], ...]
    inexpressible: tuple[tuple[int, str], ...] = ()
    outside_component: tuple[tuple[int, str], ...] = ()

    def describe(self, parent_name: str) -> str:
        parts = []
        if self.unowned:
            parts.append(f"heavy atoms {list(self.unowned)} owned by no node")
        for atom, owners in self.owned_twice:
            parts.append(f"atom {atom} owned by {' and '.join(owners)}")
        for atom, owner in self.inexpressible:
            parts.append(f"atom {atom} owned by {owner}, whose form cannot express its element")
        for atom, owner in self.outside_component:
            parts.append(f"atom {atom} owned by {owner} but not connected to the parent")
        return f"atom ownership under parent {parent_name!r}: " + "; ".join(parts)


def substitutive_owners(tree: Any) -> list[tuple[str, frozenset[int]]]:
    """``(owner label, atoms)`` for every node of one substitutive level."""
    parent = frozenset(tree.named_parent.candidate.atom_indices)
    owners: list[tuple[str, frozenset[int]]] = [("parent", parent)]
    for i, group in enumerate(tree.suffix_groups):
        context = frozenset(group.fg.get_property("context_atoms") or ())
        owners.append(
            (f"suffix[{i}] {group.base_form!r}", frozenset(group.fg.atoms) - parent - context)
        )
    for i, entry in enumerate(tree.prefixes):
        owners.append((f"prefix[{i}]", frozenset(getattr(entry, "claimed_atoms", ()) or ())))
    return owners


#: What a suffix form must say for it to own an atom of that element. N and O
#: are expressed by the generic suffix words themselves (-amine, -ol, -one,
#: -amide, -nitrile, ...); every other element is named in the form, or the
#: suffix cannot be what expresses it. This is round 4's second drop: an
#: Si-OH suffix class owned the Si under the base form "ol", and the name was
#: "hydroxymethane" for trimethylsilanol.
ELEMENT_STEMS: dict[int, tuple[str, ...]] = {
    5: ("bor",), 6: ("carb",), 9: ("fluor",), 14: ("sil",), 15: ("phosph",),
    16: ("thi", "sulf"), 17: ("chlor",), 32: ("germ",), 33: ("ars",),
    34: ("sel",), 35: ("brom",), 50: ("stann",), 51: ("stib",), 52: ("tel",),
    53: ("iod",), 82: ("plumb",),
}
_ALWAYS_EXPRESSED = frozenset({7, 8})


def _inexpressible(mol: Any, tree: Any) -> tuple[tuple[int, str], ...]:
    """Atoms a suffix owns whose element its form does not name."""
    bad = []
    for label, atoms in substitutive_owners(tree):
        if not label.startswith("suffix["):
            continue
        form = label.split(" ", 1)[1].strip("'\"").lower()
        for atom in atoms:
            z = mol.GetAtomWithIdx(atom).GetAtomicNum()
            if z in _ALWAYS_EXPRESSED:
                continue
            if not any(stem in form for stem in ELEMENT_STEMS.get(z, ())):
                bad.append((atom, label))
    return tuple(sorted(bad))


def check_substitutive_level(mol: Any, tree: Any) -> Violation | None:
    """The invariant for one level; None when it holds."""
    heavy = frozenset(a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() != 1)
    seen: dict[int, list[str]] = {}
    for label, atoms in substitutive_owners(tree):
        for atom in atoms:
            seen.setdefault(atom, []).append(label)
    unowned = tuple(sorted(heavy - seen.keys()))
    twice = tuple(
        (atom, tuple(labels)) for atom, labels in sorted(seen.items()) if len(labels) > 1
    )
    silent = _inexpressible(mol, tree)
    stray = _outside_parent_component(mol, tree)
    if not unowned and not twice and not silent and not stray:
        return None
    return Violation(unowned=unowned, owned_twice=twice, inexpressible=silent,
                     outside_component=stray)


def _outside_parent_component(mol: Any, tree: Any) -> tuple[tuple[int, str], ...]:
    """Owned atoms that are not connected to the parent.

    The engine names ONE connected component per substitutive level: a salt's
    ions each reach this executor as their own fragment (`_name_salt`), which
    is where a spectator is legitimately left to another tree. So at this
    level an atom of a second component is never an allowed exclusion -- if
    it is owned at all, a spectator was claimed by the wrong tree."""
    from rdkit import Chem

    component: dict[int, int] = {}
    for k, atoms in enumerate(Chem.GetMolFrags(mol, asMols=False, sanitizeFrags=False)):
        for atom in atoms:
            component[atom] = k
    parent = tree.named_parent.candidate.atom_indices
    home = {component.get(a) for a in parent}
    if len(home) != 1:
        return tuple((a, "parent") for a in sorted(parent))
    (home_k,) = home
    return tuple(
        (atom, label)
        for label, atoms in substitutive_owners(tree)
        for atom in sorted(atoms)
        if component.get(atom) != home_k
    )


def enforce(mol: Any, tree: Any, make_error: Any) -> Any:
    """Apply the current mode to *tree*. *make_error(message)* builds the
    ErrorTree the executor would return for a failed plan."""
    violation = check_substitutive_level(mol, tree)
    if violation is None:
        return tree
    message = violation.describe(tree.named_parent.name)
    current = mode()
    if current == "strict":
        raise OwnershipError(message)
    if current == "record":
        try:
            from rdkit import Chem

            smiles = Chem.MolToSmiles(mol)
        except Exception:  # noqa: BLE001 - a diagnostic must not fail the name
            smiles = "?"
        RECORDED.append(f"{smiles}\t{message}")
        return tree
    return make_error(message)
