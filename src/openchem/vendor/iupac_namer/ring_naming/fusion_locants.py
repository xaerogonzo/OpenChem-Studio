"""Fusion-atom locants for ring-table entries that ship without them.

Many ring-table entries give numerals for the ring atoms that can carry a
substituent and nothing for the fusion carbons (isoquinoline has no 4a/8a,
carbazole no 4a/4b/8a/9a). The hydro route matches a ring onto its table
entry and needs a locant for every saturated atom, so a SATURATED form of such
a ring found no orientation at all and fell to a von Baeyer name:
"3-azabicyclo[4.4.0]decan-8-ol" for decahydroisoquinolin-6-ol,
"2-azatricyclo[7.4.0.0^{3,8}]tridecane" for perhydrocarbazole (naming round
4, A7; round 2 had recorded the indole 3a/7a case of the same gap).

P-25.3.3.1.3 numbers a fusion carbon from the position before it: walking the
periphery in numbering order, an unnumbered atom takes the preceding numeral
plus the next letter (4, 4a, 5; and anthracene's 4, 4a, 10, 10a, 5, whose
special numbering the walk follows because it reads the numerals the entry
already has). Interior atoms continue the letters of the highest numeral
(pyrene's 10b, 10c).

Measured 2026-09-18 against the 186 entries that already have complete
locants: the walk reproduces 161, declines 10 (the entry letters a fusion
heteroatom, or numbers a fusion carbon), and differs on 15. Of those 15 the entry is the one in error
wherever it could be checked by adjacency -- isochromenylium and its S/Se/Te
analogues, 1,5-naphthyridine and 2,1,3-benzoxadiazole label as "4a" (or
"3a") an atom bonded to 8 and 1; both dibenz[b,f]azepines put "10a" between
9 and 10; 1,4-dihydronaphthalene's numerals are mirrored in the benzo ring --
and the rest are special numberings. This module never
overwrites a locant an entry has; it only fills gaps, and only for carbons,
since a fusion HETEROatom takes a numeral of its own (indolizine's N4).
"""

from __future__ import annotations

from collections import deque

_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _periphery_cycle(mol, ring: set[int]) -> list[int] | None:
    """Ring atoms on the periphery, in cycle order: the bonds in exactly one
    SSSR ring. None where that is not one simple cycle (bridged systems)."""
    count: dict[int, int] = {}
    for bond_ring in mol.GetRingInfo().BondRings():
        for b in bond_ring:
            count[b] = count.get(b, 0) + 1
    adj: dict[int, list[int]] = {}
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if i in ring and j in ring and count.get(bond.GetIdx(), 0) == 1:
            adj.setdefault(i, []).append(j)
            adj.setdefault(j, []).append(i)
    if not adj or any(len(v) != 2 for v in adj.values()):
        return None
    start = min(adj)
    cycle, prev, cur = [start], None, start
    while True:
        nxt = adj[cur][0] if adj[cur][0] != prev else adj[cur][1]
        if nxt == start:
            break
        cycle.append(nxt)
        prev, cur = cur, nxt
    return cycle if len(cycle) == len(adj) else None


def derive_fusion_locants(mol, atom_locants: dict) -> dict | None:
    """``atom_locants`` with every missing ring carbon filled in, or None
    where the walk is not well defined (no locant 1, a bridged periphery, a
    missing heteroatom, interior atoms it cannot order)."""
    ring = {a.GetIdx() for a in mol.GetAtoms() if a.IsInRing()}
    loc = dict(atom_locants)
    missing = ring - set(loc)
    if not missing:
        return loc
    if any(mol.GetAtomWithIdx(a).GetAtomicNum() != 6 for a in missing):
        return None
    # Only FUSION atoms are lettered. An entry missing an ordinary position's
    # numeral is incomplete in a way the walk cannot repair; lettering it
    # anyway produced "decahydroisoquinolin-4c-ol".
    ring_info = mol.GetRingInfo()
    if any(ring_info.NumAtomRings(a) < 2 for a in missing):
        return None
    # A fusion CARBON that already has a numeral means a special numbering
    # (cyclopenta[a]phenanthrene's steroid-style 5, 10, 13), where the gaps
    # are not letters at all; "4a" there was invented. Decline.
    if any(
        str(v).isdigit()
        and ring_info.NumAtomRings(a) >= 2
        and mol.GetAtomWithIdx(a).GetAtomicNum() == 6
        for a, v in loc.items()
    ):
        return None
    numeric = {int(str(v)): a for a, v in loc.items() if str(v).isdigit()}
    if 1 not in numeric:
        return None
    cycle = _periphery_cycle(mol, ring)
    if cycle is None or numeric[1] not in cycle:
        return None
    k = cycle.index(numeric[1])
    forward = cycle[k:] + cycle[:k]
    backward = [forward[0]] + forward[1:][::-1]

    def first_numeral(order):
        for a in order[1:]:
            if str(loc.get(a, "")).isdigit():
                return int(str(loc[a]))
        return 10**9

    order = forward if first_numeral(forward) < first_numeral(backward) else backward
    last_num: int | None = None
    used = 0
    for a in order:
        value = loc.get(a)
        if value is not None:
            text = str(value)
            last_num = int("".join(ch for ch in text if ch.isdigit()))
            used = 0 if text.isdigit() else _LETTERS.index(text[-1]) + 1
            continue
        if last_num is None:
            return None
        loc[a] = f"{last_num}{_LETTERS[used]}"
        used += 1

    pending = ring - set(loc)
    if pending:
        top = max(numeric)
        taken = [
            str(v)[len(str(top)):] for v in loc.values()
            if str(v).startswith(str(top)) and str(v)[len(str(top)):].isalpha()
        ]
        nxt = max((_LETTERS.index(t) for t in taken), default=-1) + 1
        seed_label = f"{top}{_LETTERS[nxt - 1]}" if nxt else str(top)
        seeds = [a for a in ring if str(loc.get(a, "")) == seed_label]
        if not seeds:
            return None
        adjacency = {
            a: sorted(n.GetIdx() for n in mol.GetAtomWithIdx(a).GetNeighbors() if n.GetIdx() in ring)
            for a in ring
        }
        seen, queue, inner = {seeds[0]}, deque([seeds[0]]), []
        while queue:
            x = queue.popleft()
            for y in adjacency[x]:
                if y not in seen:
                    seen.add(y)
                    queue.append(y)
                    if y in pending:
                        inner.append(y)
        if len(inner) != len(pending):
            return None
        for i, a in enumerate(inner):
            loc[a] = f"{top}{_LETTERS[nxt + i]}"
    return loc
