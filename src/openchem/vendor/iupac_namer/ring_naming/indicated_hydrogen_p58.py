"""Indicated hydrogen, 'added indicated hydrogen' and hydro prefixes, by P-58.2.

When a ring C=O (or C=S, C=Se, C=Te) of a mancude ring system is expressed
as a suffix, the name has to say where the hydrogen atoms went, and the
2013 recommendations give one procedure for it (P-58.2.2, P-58.2.3). This
module is that procedure, as a pure function of the structure. It knows
nothing about names: it returns which ring atoms carry INDICATED hydrogen,
which carry ADDED indicated hydrogen, and which are HYDRO positions, and the
caller renders them.

The procedure, with the book's own examples as the acceptance set
(`tests/vendor/iupac_namer/test_indicated_hydrogen_p58.py`):

1. The parent needs `h0` indicated hydrogens -- the atoms a maximum set of
   noncumulative double bonds leaves over (1 for indole and purine, 0 for
   pyridine and naphthalene).
2. P-58.2.3.1.1 / .1.2: when there are at least as many indicated hydrogens
   as groups, they go on the carbons that carry the groups
   (`1,2-dihydro-3H-indol-3-one`, `2H-1-benzopyran-2-one`), any extra at the
   lowest remaining position.
3. P-58.2.3.1.3: when there are fewer, one goes to the lowest position
   consistent with the double bonds, the others to group carbons.
4. P-58.2.2: groups the indicated hydrogens cannot accommodate get ADDED
   indicated hydrogen -- the fewest atoms that leave the rest of the ring
   system a Kekule structure (`pyridin-2(1H)-one`,
   `pyrimidine-4,6(1H,5H)-dione`). "This method is preferred over the use of
   nondetachable hydro prefixes".
5. What saturation is left is expressed by hydro prefixes, in pairs
   (`3,4-dihydronaphthalen-1(2H)-one`, `2,3-dihydronaphthalene-1,4-dione`).

Ties are broken by lowest locants in that order: indicated hydrogen, then
added (rule (4): "indicated hydrogen ... has seniority over 'added indicated
hydrogen' for lower locants"), then hydro.

Returns None whenever the structure is outside what this models (charged or
radical ring atoms, a ring atom that is neither pi-capable nor a divalent
chalcogen, an odd number of hydro positions), so the caller keeps the
engine's own answer rather than receiving a guess.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from typing import Iterable


@dataclass(frozen=True)
class HydrogenPlan:
    indicated: frozenset[int]
    added: frozenset[int]
    hydro: frozenset[int]


def _perfect_matching_exists(atoms: frozenset[int], adjacency: dict[int, frozenset[int]]) -> bool:
    """Exact perfect-matching test by backtracking on the lowest free atom.

    Ring systems here are tens of atoms at most, and the graphs are not
    bipartite (five-membered rings), so a bipartite algorithm would be wrong
    and a general blossom implementation is more machinery than the size
    warrants. Memoised on the remaining set.
    """

    @lru_cache(maxsize=None)
    def solve(remaining: frozenset[int]) -> bool:
        if not remaining:
            return True
        if len(remaining) % 2:
            return False
        first = min(remaining)
        for partner in adjacency[first]:
            if partner in remaining:
                if solve(remaining - {first, partner}):
                    return True
        return False

    return solve(atoms)


def _max_matching_size(atoms: frozenset[int], adjacency: dict[int, frozenset[int]]) -> int:
    """Size of a maximum matching, by removing the fewest atoms that leave a perfect one."""
    atom_list = sorted(atoms)
    for removed in range(len(atom_list) + 1):
        if (len(atom_list) - removed) % 2:
            continue
        for drop in combinations(atom_list, removed):
            if _perfect_matching_exists(atoms - frozenset(drop), adjacency):
                return (len(atom_list) - removed) // 2
    return 0


def plan_hydrogens(
    mol,
    ring_atoms: Iterable[int],
    group_carbons: Iterable[int],
    locant_of: dict[int, object],
) -> HydrogenPlan | None:
    """Indicated / added / hydro atoms for ring-C=X suffixes, per P-58.2.

    `mol` is the whole molecule; `ring_atoms` the parent ring system;
    `group_carbons` the ring carbons whose exocyclic double bond is expressed
    as a suffix; `locant_of` maps ring atoms to their locants in the chosen
    numbering (anything with a sensible ordering, e.g. the engine's Locant).
    """
    from rdkit import Chem

    ring = frozenset(ring_atoms)
    groups = frozenset(group_carbons)
    if not groups or not groups <= ring or any(a not in locant_of for a in ring):
        return None

    kek = Chem.Mol(mol)
    try:
        Chem.Kekulize(kek, clearAromaticFlags=True)
    except Exception:  # noqa: BLE001
        return None

    pi_capable: set[int] = set()
    for idx in ring:
        atom = kek.GetAtomWithIdx(idx)
        if atom.GetFormalCharge() != 0 or atom.GetNumRadicalElectrons():
            return None
        symbol = atom.GetSymbol()
        ring_degree = sum(1 for nb in atom.GetNeighbors() if nb.GetIdx() in ring)
        if symbol in ("O", "S", "Se", "Te") and ring_degree == 2:
            continue  # divalent chalcogen: never in a ring double bond
        if symbol == "N" and ring_degree == 3:
            continue  # neutral bridgehead N: three sigma bonds, no double bond
            # left to take part in -- as the chalcogen above. Treating it as
            # pi-capable invented "4aH" in pyrido[1,2-a]pyrimidin-4-one.
        if symbol in ("C", "N") and ring_degree <= 3:
            pi_capable.add(idx)
            continue
        return None
    pi = frozenset(pi_capable)
    if not groups <= pi:
        return None

    adjacency = {
        idx: frozenset(
            nb.GetIdx() for nb in kek.GetAtomWithIdx(idx).GetNeighbors() if nb.GetIdx() in pi
        )
        for idx in pi
    }

    # Saturated positions in the actual structure: pi-capable ring atoms in
    # no ring double bond, excluding the group carbons (their double bond is
    # exocyclic and is what the suffix expresses).
    def in_ring_double_bond(idx: int) -> bool:
        for bond in kek.GetAtomWithIdx(idx).GetBonds():
            other = bond.GetOtherAtomIdx(idx)
            if other in ring and bond.GetBondType() == Chem.BondType.DOUBLE:
                return True
        return False

    for carbon in groups:
        if in_ring_double_bond(carbon):
            return None  # a "group carbon" that is also in a ring double bond is not C=X
    saturated = frozenset(idx for idx in pi - groups if not in_ring_double_bond(idx))

    h0 = len(pi) - 2 * _max_matching_size(pi, adjacency)

    def key(atoms: Iterable[int]) -> tuple:
        return tuple(sorted(locant_of[a] for a in atoms))

    best: tuple | None = None
    best_plan: HydrogenPlan | None = None
    host_pool = sorted(saturated | groups, key=lambda a: locant_of[a])
    enough_indicated = len(groups) <= h0
    for indicated in combinations(host_pool, h0):
        indicated_set = frozenset(indicated)
        if enough_indicated and not groups <= indicated_set:
            continue  # P-58.2.3.1.1: enough indicated H must sit on the groups
        # The indicated hydrogens must describe a real mancude parent: with
        # them removed, the rest must carry a full set of double bonds.
        if not _perfect_matching_exists(pi - indicated_set, adjacency):
            continue
        remaining = pi - groups - indicated_set
        free = sorted(saturated - indicated_set, key=lambda a: locant_of[a])
        for n_added in range(len(free) + 1):
            found = False
            for added in combinations(free, n_added):
                added_set = frozenset(added)
                hydro = saturated - indicated_set - added_set
                if len(hydro) % 2:
                    continue
                if not _perfect_matching_exists(remaining - added_set, adjacency):
                    continue
                if not _perfect_matching_exists(remaining - added_set - hydro, adjacency):
                    continue
                # P-58.2.3.1.1: indicated hydrogen sits on the groups, so the
                # question is only how few ADDED hydrogens remain.
                # P-58.2.3.1.3 (1): with fewer indicated hydrogens than groups,
                # the indicated hydrogen goes FIRST to the lowest position the
                # mancude parent allows, and the groups are accommodated after
                # -- "3,3a-dihydro-1H-indene-1,4(2H)-dione", not the
                # added-hydrogen-free "2H" form.
                if enough_indicated:
                    rank = (n_added, key(indicated_set), key(added_set), key(hydro))
                else:
                    rank = (key(indicated_set), n_added, key(added_set), key(hydro))
                if best is None or rank < best:
                    best = rank
                    best_plan = HydrogenPlan(indicated_set, added_set, frozenset(hydro))
                found = True
            if found:
                break  # the fewest added hydrogens for this indicated set
    return best_plan


# ---------------------------------------------------------------------------
# Applying a plan to a parent the engine has already named
# ---------------------------------------------------------------------------

_RING_CX_SUFFIXES = frozenset({"one", "thione", "selone", "tellurone"})

# "<locants>-<n>hydro" then "<locants with H>-", in front of the ring name.
# The engine bakes both into NamedParent.name/.stem, so they are read back
# off the text; a parent whose text does not match is left alone.
_HYDRO_IH = re.compile(
    r"^(?:(?P<hloc>\d+[a-z]?(?:,\d+[a-z]?)*)-(?P<mult>di|tetra|hexa|octa|deca|dodeca|tetradeca|hexadeca|octadeca)hydro-?)?"
    r"(?:(?P<ih>\d+[a-z]?H(?:,\d+[a-z]?H)*)-)?"
    r"(?P<base>[a-z\[\d].*)$"
)
# Only a MANCUDE ring name can carry indicated / added hydrogen. "systematic"
# covers both aromatic fusion names and cycloalkanes, so the method alone
# cannot decide it; a von Baeyer, spiro, cyclo- or "-ene" name, and benzene
# (whose quinones are "cyclohexa-2,5-diene-1,4-dione", pdf p. 558), is refused
# on its text.
_MANCUDE_METHODS = frozenset({"retained", "hantzsch_widman", "systematic", "fused_hetero_hydro"})
_NOT_MANCUDE_BASE = re.compile(
    # benzene; a von Baeyer or spiro bracket ("bicyclo[", "spiro["); a bare
    # cycloalkane ("cyclohexane"); a locanted "-ene" ending. NOT a bare
    # "cyclo": "cyclopenta[a]phenanthrene" is a fusion name, and refusing it
    # kept every steroid ketone out (found by timing the planner on them).
    r"^benzene$|cyclo\[|spiro\[|^cyclo[a-z]+ane$|-\d+(?:,\d+)*-[a-z]*en(?:e|$)|ane$"
)
_HYDRO_MULT = {2: "di", 4: "tetra", 6: "hexa", 8: "octa", 10: "deca", 12: "dodeca",
               14: "tetradeca", 16: "hexadeca", 18: "octadeca"}


def _split_hydrogen_prefix(text: str) -> tuple[str, list[str]] | None:
    """(ring name without its hydro / indicated-H block, the old locants)."""
    m = _HYDRO_IH.match(text)
    if m is None or "hydro" in m.group("base"):
        return None  # a hydro block this pattern did not consume
    old: list[str] = []
    if m.group("hloc"):
        old += m.group("hloc").split(",")
        if _HYDRO_MULT.get(len(old)) != m.group("mult"):
            return None
    if m.group("ih"):
        old += [s[:-1] for s in m.group("ih").split(",")]
    return m.group("base"), old


def _hydrogen_prefix(indicated: list[str], hydro: list[str], base: str) -> str:
    text = ""
    if hydro:
        text = f"{','.join(hydro)}-{_HYDRO_MULT[len(hydro)]}hydro"
    if indicated:
        text += ("-" if text else "") + ",".join(f"{loc}H" for loc in indicated) + "-"
    elif text and (base[0].isdigit() or base[0] == "["):
        text += "-"
    return text


def _resolve(mol, named_parent, numbering, suffix_groups):
    """The P-58.2 plan for a named parent, or None where this module declines.

    Declines when:
    - any suffix is not a ring C=X on the parent;
    - the parent's text does not parse as [hydro][indicated H]ring, or is not
      a mancude ring name;
    - no ring double bond survives, where the saturated name is the PIN
      ("piperidin-2-one", "imidazolidine-2,4-dione", pdf pp. 556, 566) and a
      tetrahydro-mancude rewrite would be the wrong direction;
    - the old description names an atom the plan cannot account for, which
      would mean the text and the structure are not about the same atoms;
    - the plan puts a hydrogen on an atom the numbering gives no locant.
    """
    if not suffix_groups or getattr(named_parent, "precomposed_retained_no_suffix", False):
        return None
    if named_parent.candidate.ring_system is None:
        return None
    ring = frozenset(named_parent.candidate.atom_indices)
    if any(sg.base_form not in _RING_CX_SUFFIXES for sg in suffix_groups):
        return None
    groups = []
    for sg in suffix_groups:
        if sg.fg.anchor not in ring:
            return None
        groups.append(sg.fg.anchor)

    name_split = _split_hydrogen_prefix(named_parent.name or "")
    stem_split = _split_hydrogen_prefix(named_parent.stem or "")
    if name_split is None or stem_split is None or name_split[1] != stem_split[1]:
        return None
    base_name, old = name_split
    if named_parent.naming_method not in _MANCUDE_METHODS or _NOT_MANCUDE_BASE.search(base_name):
        return None
    if base_name in _hydro_ring_names():
        return None  # "isoindoline" is 2,3-dihydroisoindole, not a mancude parent
    if not _ring_double_bond_atoms(mol, ring):
        return None

    # Fusion atoms can be missing from `atom_to_locant` (round 2's indole
    # 3a/7a gap). They only need to sort; a plan that puts a hydrogen on one
    # is declined below, since its locant could not be written.
    from openchem.vendor.iupac_namer.types import Locant

    locant_of = {}
    unnamed = set()
    for a in ring:
        loc = numbering.atom_to_locant.get(a)
        if loc is None:
            loc = Locant.numeric(10**6 + a)
            unnamed.add(a)
        locant_of[a] = loc

    plan = plan_hydrogens(mol, ring, groups, locant_of)
    if plan is None or (plan.indicated | plan.added | plan.hydro) & unnamed:
        return None
    described = plan.indicated | plan.added | plan.hydro | frozenset(groups)
    by_label = {str(locant_of[a]): a for a in ring}
    old_atoms = {by_label.get(label) for label in old} | set(named_parent.added_indicated_h_atoms or ())
    if None in old_atoms or not old_atoms <= described:
        return None
    if plan.hydro and len(plan.hydro) not in _HYDRO_MULT:
        return None
    return plan, locant_of, base_name, stem_split[0]


def added_hydrogen_tier(mol, named_parent, numbering, suffix_groups) -> tuple[int, ...]:
    """The added-hydrogen locants of a plan, as numbers, for the preference key.

    P-31.1.4.2.4 (pdf p. 76) ranks "'added indicated hydrogen' (consistent
    with the structure of the compound...)" after the principal group and
    before hydro prefixes, so it decides between numberings that tie on the
    suffix: pyrimidine-4,6(1H,5H)-dione, not (3H,5H). A fusion letter sorts
    after its number (3 < 3a < 4). Empty when this module declines.
    """
    if mol is None:
        return ()
    resolved = _resolve(mol, named_parent, numbering, suffix_groups)
    if resolved is None:
        return ()
    plan, locant_of, _, _ = resolved
    values = []
    for a in plan.added:
        loc = locant_of[a]
        suffix = loc.suffix
        if not loc.is_numeric or (suffix and not (len(suffix) == 1 and suffix.islower())):
            return ()
        values.append(loc._numeric_value * 100 + (ord(suffix) - 96 if suffix else 0))
    return tuple(values)


def apply_to_parent(mol, named_parent, numbering, suffix_groups):
    """Re-describe the hydrogens of a ring parent carrying ring C=X suffixes.

    Returns ``(named_parent, suffix_groups)`` rewritten by P-58.2, or None to
    keep the engine's own description (see `_resolve` for when). The
    numbering is the engine's; only the hydro prefixes, the indicated
    hydrogen and the added hydrogen change, so the structure the name
    denotes cannot move -- only how it is said.
    """
    resolved = _resolve(mol, named_parent, numbering, suffix_groups)
    if resolved is None:
        return None
    plan, locant_of, base_name, base_stem = resolved

    def labels(atoms):
        return [str(loc) for loc in sorted(locant_of[a] for a in atoms)]

    indicated, hydro = labels(plan.indicated), labels(plan.hydro)
    new_parent = dataclasses.replace(
        named_parent,
        name=_hydrogen_prefix(indicated, hydro, base_name) + base_name,
        stem=_hydrogen_prefix(indicated, hydro, base_stem) + base_stem,
        added_indicated_h_atoms=None,
    )
    # The rendered "(1H,5H)" block pairs added hydrogens with suffix locants
    # in suffix order, so the whole sorted block rides on the lowest suffix.
    added = tuple(sorted(locant_of[a] for a in plan.added))
    first = min(range(len(suffix_groups)), key=lambda i: min(suffix_groups[i].locants))
    new_groups = tuple(
        dataclasses.replace(sg, added_indicated_h=added if i == first else ())
        for i, sg in enumerate(suffix_groups)
    )
    return new_parent, new_groups


def _ring_double_bond_atoms(mol, ring: frozenset[int]) -> frozenset[int]:
    from rdkit import Chem

    kek = Chem.Mol(mol)
    try:
        Chem.Kekulize(kek, clearAromaticFlags=True)
    except Exception:  # noqa: BLE001
        return frozenset()
    atoms = set()
    for bond in kek.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if a in ring and b in ring and bond.GetBondType() == Chem.BondType.DOUBLE:
            atoms |= {a, b}
    return frozenset(atoms)


@lru_cache(maxsize=1)
def _hydro_ring_names() -> frozenset[str]:
    """Ring-table names that denote a HYDRO ring, derived from their keys.

    "isoindoline", "indoline", "chroman" name partly saturated rings; putting
    indicated or added hydrogen on one produced "1H-isoindoline-1,3(2H)-dione".
    A name is hydro when its key has more pi-capable ring atoms outside every
    double bond than the mancude ring's own indicated hydrogens (indole: one,
    and h0 is one; isoindoline: three against one). Derived rather than
    listed, so a new table entry is classified the moment it is added.
    """
    from rdkit import Chem

    from openchem.vendor.iupac_namer import data_loader

    names = set()
    for smi, rec in data_loader._RING_CURATED_SMILES.items():
        mol = Chem.MolFromSmiles(smi)
        if mol is None or not mol.GetRingInfo().NumRings():
            continue
        kek = Chem.Mol(mol)
        try:
            Chem.Kekulize(kek, clearAromaticFlags=True)
        except Exception:  # noqa: BLE001
            continue
        ring = {a.GetIdx() for a in kek.GetAtoms() if a.IsInRing()}
        pi = set()
        for idx in ring:
            atom = kek.GetAtomWithIdx(idx)
            degree = sum(1 for nb in atom.GetNeighbors() if nb.GetIdx() in ring)
            if atom.GetFormalCharge() or atom.GetSymbol() not in ("C", "N"):
                continue
            if atom.GetSymbol() == "N" and degree == 3:
                continue
            pi.add(idx)
        adjacency = {
            i: frozenset(nb.GetIdx() for nb in kek.GetAtomWithIdx(i).GetNeighbors() if nb.GetIdx() in pi)
            for i in pi
        }
        unsaturated = set()
        for bond in kek.GetBonds():
            if bond.GetBondType() == Chem.BondType.DOUBLE:
                unsaturated |= {bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()}
        saturated = len(pi - unsaturated)
        h0 = len(pi) - 2 * _max_matching_size(frozenset(pi), adjacency)
        if saturated > h0:
            names.add(rec["name"])
    return frozenset(names)
