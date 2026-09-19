"""
Multiplicative nomenclature, P-15.3 and P-51.3 (naming round 5, N4).

"Multiplicative nomenclature is preferred to substitutive nomenclature for
generating preferred IUPAC names to express multiple occurrences of
identical parent structures, other than alkanes when (1) the linking bonds
... are identical and (2) the multiplicative groups, other than the central
multiplicative group, are symmetrically substituted; and (3) the locants of
all substituent groups on the identical parent structures, including suffix
groups, are identical" (P-51.3.1, pdf p. 436). The engine had a
`MultiplicativePlan` type that nothing constructed, so every such PIN came
out substitutive: "phenoxybenzene" for 1,1'-oxydibenzene, "methane-1,1-
diphosphonic acid" for methylenebis(phosphonic acid).

THE DECOMPOSITION IS READ OFF THE MOLECULE'S SYMMETRY, NOT OFF A NAME. A set
of bonds whose ends fall in the same two symmetry classes is cut; if that
leaves one linker component touching every cut bond and n identical units
each hanging by one of them, it is a candidate. Symmetry is what makes the
three conditions hold: an automorphism that carries one unit onto another
carries its substituents, its suffixes and its linking bond with it.

WHICH CANDIDATE, AND WHETHER AT ALL:

* the units must carry the senior parent. Either the engine's own
  substitutive parent lies inside a unit, or the unit is a functional parent
  compound whose anchor is the attachment atom (phosphonic acid) or which is
  named whole (guanidine) -- see `_FUNCTIONAL_PARENT_UNITS`;
* the linker may hold no suffix-eligible group as senior as the units' own
  (P-15.3.3.2.2: "bis(phenyldiazenyl)methanone (PIN) [not
  1,1'-carbonylbis(2-phenyldiazene)]", and the amine N of diphenylamine
  keeps "N-phenylaniline");
* units are not acyclic hydrocarbons (P-15.3.4.2);
* more units first (P-15.3.3.2.1), then the larger unit -- the senior parent
  is the whole chain or ring, so HO-CH2CH2-O-CH2CH2-OH multiplies ethanol,
  not methanol.

OUTSIDE THE BUILT CLASS the construction declines and the substitutive name
stands; `explain` says why. Declined: stereo, charge, isotopes, radicals,
more than one component, a double-bonded linkage, a substituted or branched
linker, an unsymmetrical central group (P-15.3.3.1's propane-1,2-diyl),
units with two or more nitrogenous characteristic groups (P-15.3.2.2.2),
and an acyclic chain with four or more heteroatoms, where skeletal
replacement is the PIN (P-51.4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rdkit import Chem

# Functional parent compounds (P-15.3.1.1 (d)) that are named whole rather
# than as a substituted parent hydride, so the engine's own parent is not
# inside them: the phosphonic acid of "methylenebis(phosphonic acid)" is
# expressed on methane by the substitutive path. Each is the name
# `name_smiles` gives the bare unit.
_FUNCTIONAL_PARENT_UNITS = frozenset({
    "phosphonic acid", "phosphinic acid", "arsonic acid", "arsinic acid",
    "stibonic acid", "boronic acid", "guanidine",
})

# A unit whose "di" name is another compound takes "bis" (P-15.3.2.3):
# "(benzene-1,3,5-triyl)tris(silane) (not ...trisilane)", and
# "[azanediylbis(methylene)]bis(phosphonic acid) (PIN)" (pdf pp. 105, 107).
_BIS_UNITS = frozenset({
    "silane", "germane", "stannane", "plumbane", "borane", "phosphane",
    "arsane", "stibane", "bismuthane", "disilane",
    "phosphonic acid", "phosphinic acid", "arsonic acid", "arsinic acid",
    "stibonic acid", "boronic acid",
})

# Nitrogen-locant levels a unit's own name already uses, so the next unit's
# primes start after them (P-15.3.2.2.1: "N',N'''-methylenediacetohydrazide
# (PIN)", pdf p. 106 -- acetohydrazide has N and N').
_N_LEVELS_BY_ENDING = (
    ("hydrazide", 2),
    ("guanidine", 3),
    ("imidamide", 2),
)

_ALKANE = {1: "methane", 2: "ethane", 3: "propane", 4: "butane", 5: "pentane",
           6: "hexane", 7: "heptane", 8: "octane", 9: "nonane", 10: "decane",
           11: "undecane", 12: "dodecane", 13: "tridecane", 14: "tetradecane",
           15: "pentadecane", 16: "hexadecane", 17: "heptadecane", 18: "octadecane",
           19: "nonadecane", 20: "icosane"}

_MULTIPLIER = {2: ("di", "bis"), 3: ("tri", "tris"), 4: ("tetra", "tetrakis")}

# Simple one-atom (or one-group) linking components (P-15.3.1.2.1.1). Keyed
# by (element, heavy-atom decoration) of the component's single skeletal
# atom; "=O" counts terminal double-bonded oxygens.
_SIMPLE_DIVALENT = {
    ("O", 0): "oxy",
    ("S", 0): "sulfanediyl",
    ("S", 1): "sulfinyl",
    ("S", 2): "sulfonyl",
    ("Se", 0): "selanediyl",
    ("N", 0): "azanediyl",
    ("C", 0): "methylene",
    ("C", 1): "carbonyl",
    ("Si", 0): "silanediyl",
    ("P", 0): "phosphanediyl",
}
_SIMPLE_POLYVALENT = {
    ("N", 3): "nitrilo",
    ("P", 3): "phosphanetriyl",
    ("C", 3): "methanetriyl",
    ("C", 4): "methanetetrayl",
}


@dataclass(frozen=True)
class Decomposition:
    linker: frozenset[int]
    units: tuple[frozenset[int], ...]
    unit_attach: tuple[int, ...]      # atom of each unit bonded to the linker
    linker_attach: tuple[int, ...]    # atom of the linker bonded to each unit


class Declined(Exception):
    """The construction does not apply, or is outside the built class."""


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def try_name(mol, whole_tree) -> str | None:
    """The multiplicative PIN for *mol*, or None where it does not apply."""
    try:
        return _build(mol, whole_tree)
    except Declined:
        return None


def explain(mol, whole_tree) -> str:
    """Why the construction applied or declined -- for tests and diagnosis."""
    try:
        return "built: " + _build(mol, whole_tree)
    except Declined as exc:
        return f"declined: {exc}"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def _build(mol, whole_tree) -> str:
    _check_input(mol)
    candidates = _decompositions(mol)
    if not candidates:
        raise Declined("no set of identical units")
    fgs = _suffix_fgs(mol)
    reasons = []
    built = []
    for dec in candidates:
        try:
            built.append((dec, _name_decomposition(mol, dec, whole_tree, fgs)))
        except Declined as exc:
            reasons.append(str(exc))
    if not built:
        raise Declined("; ".join(sorted(set(reasons))))
    # P-15.3.3.2.1: most units; then the larger unit (the senior parent is
    # the whole chain or ring).
    built.sort(key=lambda item: (-len(item[0].units), -len(item[0].units[0]), item[1]))
    return built[0][1]


def _check_input(mol) -> None:
    if len(Chem.GetMolFrags(mol)) != 1:
        raise Declined("more than one component")
    for atom in mol.GetAtoms():
        if atom.GetFormalCharge() or atom.GetNumRadicalElectrons() or atom.GetIsotope():
            raise Declined("charge, radical or isotope")
        if atom.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED:
            raise Declined("stereo")
    for bond in mol.GetBonds():
        if bond.GetStereo() != Chem.BondStereo.STEREONONE:
            raise Declined("stereo")


def _decompositions(mol) -> list[Decomposition]:
    """Every symmetric cut into one linker and n >= 2 identical units."""
    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
    classes: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for bond in mol.GetBonds():
        if bond.GetBondType() != Chem.BondType.SINGLE or bond.IsInRing():
            continue
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        # Each orientation: (linker end, unit end).
        classes.setdefault((ranks[a], ranks[b]), []).append((a, b))
        classes.setdefault((ranks[b], ranks[a]), []).append((b, a))
    found: list[Decomposition] = []
    seen: set[tuple] = set()
    for (rank_link, rank_unit), pairs in classes.items():
        if rank_link == rank_unit or len(pairs) < 2:
            continue
        dec = _cut(mol, pairs)
        if dec is None:
            continue
        key = (dec.linker, dec.units)
        if key not in seen:
            seen.add(key)
            found.append(dec)
    return found


def _cut(mol, pairs) -> Decomposition | None:
    cut = {frozenset(p) for p in pairs}
    n = mol.GetNumAtoms()
    comp = [-1] * n
    comps: list[set[int]] = []
    for start in range(n):
        if comp[start] >= 0:
            continue
        stack, members = [start], set()
        comp[start] = len(comps)
        while stack:
            i = stack.pop()
            members.add(i)
            for nb in mol.GetAtomWithIdx(i).GetNeighbors():
                j = nb.GetIdx()
                if comp[j] < 0 and frozenset((i, j)) not in cut:
                    comp[j] = len(comps)
                    stack.append(j)
        comps.append(members)
    linker_ids = {comp[a] for a, _ in pairs}
    if len(linker_ids) != 1:
        return None
    link_id = linker_ids.pop()
    unit_ids = [comp[b] for _, b in pairs]
    if link_id in unit_ids or len(set(unit_ids)) != len(unit_ids):
        return None
    if len(comps) != len(pairs) + 1:
        return None
    units = [frozenset(comps[u]) for u in unit_ids]
    order = sorted(range(len(pairs)), key=lambda k: min(units[k]))
    dec = Decomposition(
        linker=frozenset(comps[link_id]),
        units=tuple(units[k] for k in order),
        unit_attach=tuple(pairs[k][1] for k in order),
        linker_attach=tuple(pairs[k][0] for k in order),
    )
    smiles = {_unit_smiles(mol, u, att) for u, att in zip(dec.units, dec.unit_attach)}
    return dec if len(smiles) == 1 else None


def _unit_smiles(mol, atoms, attach, marker: str | None = None) -> str:
    """The unit alone, with *marker* ("[*]", "azido", "methyl") at the attachment."""
    return Chem.MolToSmiles(_build_unit(mol, atoms, attach, marker)[0])


def _marked_unit(mol, atoms, attach, marker: str):
    return _build_unit(mol, atoms, attach, marker)


def _build_unit(mol, atoms, attach, marker: str | None):
    """(unit molecule, the marker's atom indices in it). Built atom by atom,
    never through a SMILES round trip, so the marker's indices are known."""
    rw = Chem.RWMol()
    index = {}
    for i in sorted(atoms):
        atom = mol.GetAtomWithIdx(i)
        new = Chem.Atom(atom.GetAtomicNum())
        new.SetFormalCharge(atom.GetFormalCharge())
        new.SetIsAromatic(atom.GetIsAromatic())
        new.SetNoImplicit(False)
        index[i] = rw.AddAtom(new)
    for bond in mol.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if a in index and b in index:
            rw.AddBond(index[a], index[b], bond.GetBondType())
    head = index[attach]
    first = rw.GetNumAtoms()
    if marker == "azido":
        n1 = rw.AddAtom(Chem.Atom(7))
        n2 = rw.AddAtom(Chem.Atom(7))
        n3 = rw.AddAtom(Chem.Atom(7))
        rw.GetAtomWithIdx(n2).SetFormalCharge(1)
        rw.GetAtomWithIdx(n3).SetFormalCharge(-1)
        rw.AddBond(head, n1, Chem.BondType.SINGLE)
        rw.AddBond(n1, n2, Chem.BondType.DOUBLE)
        rw.AddBond(n2, n3, Chem.BondType.DOUBLE)
    elif marker == "methyl":
        c = rw.AddAtom(Chem.Atom(6))
        rw.AddBond(head, c, Chem.BondType.SINGLE)
    elif marker == "ethyl":
        c1 = rw.AddAtom(Chem.Atom(6))
        c2 = rw.AddAtom(Chem.Atom(6))
        rw.AddBond(head, c1, Chem.BondType.SINGLE)
        rw.AddBond(c1, c2, Chem.BondType.SINGLE)
    elif marker in ("chloro", "bromo"):
        x = rw.AddAtom(Chem.Atom(17 if marker == "chloro" else 35))
        rw.AddBond(head, x, Chem.BondType.SINGLE)
    elif marker == "[*]":
        d = rw.AddAtom(Chem.Atom(0))
        rw.AddBond(head, d, Chem.BondType.SINGLE)
    out = rw.GetMol()
    for atom in out.GetAtoms():
        atom.SetNoImplicit(False)
        atom.SetNumExplicitHs(0)
    Chem.SanitizeMol(out)
    return out, frozenset(range(first, out.GetNumAtoms()))


def _suffix_fgs(mol):
    from openchem.vendor.iupac_namer.perception import Perception

    try:
        return [fg for fg in Perception(mol).fgs.detected_fgs
                if getattr(fg, "suffix_eligible", False)]
    except Exception as exc:  # noqa: BLE001 - perception failure is a decline
        raise Declined(f"perception failed: {exc}") from exc


def _fg_atoms(fg) -> frozenset[int]:
    context = frozenset(getattr(fg, "context_atoms", ()) or ())
    return frozenset(fg.atoms) - context


def _seniority(fg) -> int:
    return int(fg.get_property("seniority", 9999))


def _name_decomposition(mol, dec: Decomposition, whole_tree, fgs) -> str:
    from openchem.vendor.iupac_namer.types import SubstitutiveTree

    # Every atom owned exactly once: by the linker or by one unit.
    owned = [dec.linker, *dec.units]
    if sum(len(s) for s in owned) != mol.GetNumAtoms() or len(frozenset().union(*owned)) != mol.GetNumAtoms():
        raise Declined("the parts do not partition the molecule")

    # A group belongs where its anchor is: an amine's SMARTS reaches into the
    # CH2 beside it, which is how N1,N1'-methylenedi(benzene-1,4-diamine)
    # first read its own amines as the linker's.
    all_units = frozenset().union(*dec.units)
    unit_fgs = [fg for fg in fgs if fg.anchor in all_units]
    link_fgs = [fg for fg in fgs if fg.anchor in dec.linker]
    best_unit = min((_seniority(fg) for fg in unit_fgs), default=None)
    best_link = min((_seniority(fg) for fg in link_fgs), default=None)
    if _linker_has_carbonyl(mol, dec.linker):
        # A C=O in the linker is a ketone for P-41, perceived or not:
        # "bis(phenyldiazenyl)methanone (PIN) [not 1,1'-carbonylbis(2-
        # phenyldiazene) ... ketone is senior to 'diazene']" (pdf p. 110).
        # The engine does not perceive that C=O between two N as a ketone.
        best_link = min(best_link if best_link is not None else _KETONE, _KETONE)
    if best_link is not None and (best_unit is None or best_link <= best_unit):
        raise Declined("the linker holds a group as senior as the units' (P-15.3.3.2.2)")
    if best_unit is not None:
        per_unit = [sum(1 for fg in unit_fgs if fg.anchor in u and _seniority(fg) == best_unit)
                    for u in dec.units]
        if len(set(per_unit)) != 1 or per_unit[0] == 0:
            raise Declined("the principal groups are not shared equally")

    unit_name, locant, bare_name, substituted = _unit_name(mol, dec)
    functional_parent = bare_name in _FUNCTIONAL_PARENT_UNITS
    whole_parent = None
    if isinstance(whole_tree, SubstitutiveTree):
        whole_parent = frozenset(whole_tree.named_parent.candidate.atom_indices)
    if not functional_parent:
        if whole_parent is None or not any(whole_parent <= u for u in dec.units):
            raise Declined("the units do not carry the senior parent")
        if best_unit is None and _is_acyclic_hydrocarbon_parent(mol, whole_parent):
            raise Declined("acyclic hydrocarbons are not identical units (P-15.3.4.2)")
    if _heterogeneous_chain(mol, dec):
        raise Declined("unit and linker form a heterogeneous parent hydride (P-21.2.3)")
    if _skeletal_replacement_applies(mol, dec):
        raise Declined("four or more heteroatoms in one chain: skeletal replacement (P-51.4)")

    linker = _linker_name(mol, dec)
    n = len(dec.units)
    return _assemble(linker, unit_name, locant, n, bare_name, substituted)


_KETONE = 1600  # functional_groups.json's ketone seniority


def _heterogeneous_chain(mol, dec) -> bool:
    """Si-O-Si, Si-NH-Si, B-O-B ...: the units' attachment atoms and a
    one-atom chalcogen or NH linker are a heterogeneous parent hydride
    (disiloxane, disilazane; P-21.2.3.1), not two identical units. Measured:
    hexamethyldisiloxane came out "oxybis[tri(methyl)silane]"."""
    if len(dec.linker) != 1:
        return False
    link = mol.GetAtomWithIdx(next(iter(dec.linker)))
    heads = {mol.GetAtomWithIdx(a).GetSymbol() for a in dec.unit_attach}
    return (link.GetSymbol() in ("O", "S", "Se", "Te", "N")
            and len(heads) == 1
            and heads.pop() in ("Si", "Ge", "Sn", "Pb", "B", "Al", "Ga", "P", "As", "Sb"))


def _linker_has_carbonyl(mol, linker) -> bool:
    for i in linker:
        atom = mol.GetAtomWithIdx(i)
        if atom.GetSymbol() != "C":
            continue
        for nb in atom.GetNeighbors():
            if (nb.GetIdx() in linker and nb.GetSymbol() == "O" and nb.GetDegree() == 1
                    and mol.GetBondBetweenAtoms(i, nb.GetIdx()).GetBondType()
                    == Chem.BondType.DOUBLE):
                return True
    return False


def _is_acyclic_hydrocarbon_parent(mol, parent_atoms) -> bool:
    if not parent_atoms:
        return False
    return all(
        mol.GetAtomWithIdx(i).GetSymbol() == "C" and not mol.GetAtomWithIdx(i).IsInRing()
        for i in parent_atoms
    )


def _skeletal_replacement_applies(mol, dec) -> bool:
    """P-51.4: an acyclic chain with four or more heteroatoms is named by
    skeletal replacement, not multiplied: "3,6,9,12-tetraoxatetradecane-
    1,14-dioic acid (PIN)" over the multiplicative name (pdf p. 437). Counted
    on the acyclic atoms of linker plus units when the units are acyclic."""
    unit_rings = any(mol.GetAtomWithIdx(i).IsInRing() for u in dec.units for i in u)
    if unit_rings:
        return False
    hetero = sum(
        1 for i in dec.linker
        if mol.GetAtomWithIdx(i).GetSymbol() not in ("C", "H")
        and mol.GetAtomWithIdx(i).GetDegree() >= 2
    )
    return hetero >= 4


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

def _unit_name(mol, dec: Decomposition) -> tuple[str, str, str, bool]:
    """(unit name, attachment locant or "", the bare unit's own name,
    whether the unit carries substituents of its own).

    The unit is named carrying a marker where the linker was, so the
    engine's own numbering gives the linker the lowest locant the unit
    allows ("the locants of the point of substitution by the linking
    multiplicative substituent groups ... are as low as possible",
    P-15.3.1, pdf p. 103). Azido marks a carbon: it sorts first, so an
    alphanumerical tie also goes to the linker. A heteroatom takes an
    alkyl or chloro instead, since an azide on N or P is read as something
    else; there the locant is fixed by the atom, not by a tie.
    """
    from openchem.vendor.iupac_namer.engine import name_smiles

    atoms, attach = dec.units[0], dec.unit_attach[0]
    bare_name = name_smiles(_unit_smiles(mol, atoms, attach))
    if "NAMING ERROR" in bare_name:
        raise Declined("the unit cannot be named")
    if mol.GetAtomWithIdx(attach).GetSymbol() == "C":
        markers = ("azido",)
    else:
        # A marker the unit already carries merges with it ("N,N-dimethyl"),
        # so the first one it does not.
        markers = ("methyl", "ethyl", "chloro", "bromo")
    reasons = []
    for marker in markers:
        try:
            return _unit_name_with(mol, atoms, attach, marker, bare_name)
        except Declined as exc:
            reasons.append(str(exc))
    raise Declined("; ".join(reasons))


def _unit_name_with(mol, atoms, attach, marker, bare_name):
    import dataclasses

    from openchem.vendor.iupac_namer.assembly import assemble
    from openchem.vendor.iupac_namer.engine import name as _engine_name
    from openchem.vendor.iupac_namer.strategy import active_strategy
    from openchem.vendor.iupac_namer.types import SubstitutiveTree

    marked, marker_atoms = _marked_unit(mol, atoms, attach, marker)
    tree = _engine_name(marked, active_strategy())
    if isinstance(tree, SubstitutiveTree):
        marker_entry = _marker_entry(tree, marker_atoms)
        if marker_entry is not None:
            rest = [p for p in tree.prefixes if p is not marker_entry]
            locant = ",".join(str(x) for x in marker_entry.locants)
            # The unit is cut out of the MARKED name, not reassembled
            # without the marker: reassembly re-runs locant omission for
            # the now-lone suffix and gives "ethanol", where the multiplied
            # unit keeps its locants, "2,2'-oxydi(ethan-1-ol) (PIN)" and
            # "1,1'-oxybis(4-bromobenzene) (PIN)" (pdf pp. 104, 107).
            unit_name = _cut_marker(assemble(tree), locant, marker)
            if _is_mononuclear(tree):
                # No numbering to keep, and the bare name has none of the
                # marker's side effects ("ethyltri(methyl)silane").
                locant = ""
                unit_name = bare_name
            if not rest:
                bare_tree = dataclasses.replace(tree, prefixes=())
                if assemble(bare_tree) != bare_name:
                    raise Declined("the marked unit's parent is not the unit's own")
            return unit_name, locant, bare_name, bool(rest)
    # A functional parent named whole: read the marker off the string, and
    # accept it only if what is left is the bare unit's own name.
    text = assemble(tree)
    match = re.match(rf"^(?:([^\s-]+)-)?{marker}(.+)$", text)
    if match is None or match.group(2) != bare_name:
        raise Declined(f"the marker could not be read off {text!r}")
    locant = match.group(1) or ""
    if locant.isdigit() and locant == "1":
        locant = ""
    return bare_name, locant, bare_name, False


def _cut_marker(text: str, locant: str, marker: str) -> str:
    """Remove the one "<locant>-<marker>" prefix from an assembled name,
    with the hyphen that joined it to its neighbour."""
    loc = re.escape(locant) + "-" if locant else ""
    pattern = re.compile(rf"(^|-)(?:{loc})?{marker}(-?)")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise Declined(f"the marker is not one prefix of {text!r}")
    m = matches[0]
    lead, trail = m.group(1), m.group(2)
    join = "-" if (lead and trail) else ""
    out = text[:m.start()] + join + text[m.end():]
    if not out or out[0] in "-,":
        raise Declined(f"cutting the marker left {out!r}")
    return out


def _marker_entry(tree, marker_atoms):
    """The prefix entry the marker became: its atoms are the marker's."""
    for entry in tree.prefixes:
        if entry.claimed_atoms and frozenset(entry.claimed_atoms) == marker_atoms:
            return entry
    return None


def _is_mononuclear(tree) -> bool:
    """P-15.3.1.3 (a): 'the locant 1 is omitted when alone in the name of a
    mononuclear parent hydride'."""
    candidate = tree.named_parent.candidate
    return len(candidate.atom_indices) == 1 and candidate.ring_system is None


# ---------------------------------------------------------------------------
# Linker
# ---------------------------------------------------------------------------

def _linker_name(mol, dec: Decomposition) -> str:
    """The multiplicative substituent group. Its terminal =O atoms belong to
    their carbonyl or sulfonyl component; everything else is skeleton, and
    any skeleton atom off the path between units (a substituent on the
    linker, P-15.3.1.2.1.2) is outside the built class."""
    linker = dec.linker
    n = len(dec.units)
    oxo_atoms = {
        nb.GetIdx()
        for i in linker
        for nb in mol.GetAtomWithIdx(i).GetNeighbors()
        if nb.GetIdx() in linker and nb.GetSymbol() == "O" and nb.GetDegree() == 1
        and mol.GetBondBetweenAtoms(i, nb.GetIdx()).GetBondType() == Chem.BondType.DOUBLE
    }
    skeleton = linker - oxo_atoms
    for i in skeleton:
        atom = mol.GetAtomWithIdx(i)
        if atom.IsInRing() and not _in_benzene(mol, i, skeleton):
            raise Declined("a ring other than benzene in the linker")
    if n == 2:
        return _divalent_linker(mol, dec, skeleton)
    return _polyvalent_linker(mol, dec, skeleton)


def _in_benzene(mol, idx, skeleton) -> bool:
    ring_info = mol.GetRingInfo()
    for ring in ring_info.AtomRings():
        if idx in ring and len(ring) == 6 and all(
                mol.GetAtomWithIdx(r).GetSymbol() == "C" and mol.GetAtomWithIdx(r).GetIsAromatic()
                for r in ring) and set(ring) <= skeleton:
            return True
    return False


def _components_along(mol, path, skeleton) -> list[tuple[str, tuple]]:
    """Split a linker path into linking components, in path order.

    Each is (kind, data): ("chain", (n_carbons,)), ("ring", (ortho/meta/para
    offset,)), or ("simple", (name,)).
    """
    out: list[tuple[str, tuple]] = []
    i = 0
    rings = [set(r) for r in mol.GetRingInfo().AtomRings()]
    while i < len(path):
        idx = path[i]
        atom = mol.GetAtomWithIdx(idx)
        if atom.GetIsAromatic():
            ring = next(r for r in rings if idx in r)
            j = i
            while j + 1 < len(path) and path[j + 1] in ring:
                j += 1
            entry, leave = path[i], path[j]
            distance = _ring_distance(mol, ring, entry, leave)
            if distance == 0:
                raise Declined("a ring joined at one atom")
            out.append(("ring", (distance,)))
            i = j + 1
            continue
        oxo = sum(
            1 for nb in atom.GetNeighbors()
            if nb.GetSymbol() == "O" and nb.GetDegree() == 1
            and mol.GetBondBetweenAtoms(idx, nb.GetIdx()).GetBondType() == Chem.BondType.DOUBLE
        )
        side = [nb.GetIdx() for nb in atom.GetNeighbors()
                if nb.GetIdx() in skeleton and nb.GetIdx() not in path]
        if side:
            raise Declined("a substituted linker")
        if atom.GetSymbol() == "C" and oxo == 0:
            j = i
            while (j + 1 < len(path) and mol.GetAtomWithIdx(path[j + 1]).GetSymbol() == "C"
                   and not mol.GetAtomWithIdx(path[j + 1]).GetIsAromatic()
                   and not any(nb.GetSymbol() == "O" and nb.GetDegree() == 1
                               for nb in mol.GetAtomWithIdx(path[j + 1]).GetNeighbors())):
                bond = mol.GetBondBetweenAtoms(path[j], path[j + 1])
                if bond.GetBondType() != Chem.BondType.SINGLE:
                    raise Declined("an unsaturated linker")
                j += 1
            out.append(("chain", (j - i + 1,)))
            i = j + 1
            continue
        key = (atom.GetSymbol(), oxo)
        if atom.GetSymbol() in ("O", "S") and i + 1 < len(path) and \
                mol.GetAtomWithIdx(path[i + 1]).GetSymbol() == atom.GetSymbol():
            out.append(("simple", ("peroxy" if atom.GetSymbol() == "O" else "disulfanediyl",)))
            i += 2
            continue
        name = _SIMPLE_DIVALENT.get(key)
        if name is None:
            raise Declined(f"no linking-group name for {key}")
        out.append(("simple", (name,)))
        i += 1
    return out


def _ring_distance(mol, ring, a, b) -> int:
    from collections import deque

    seen, queue = {a: 0}, deque([a])
    while queue:
        x = queue.popleft()
        for nb in mol.GetAtomWithIdx(x).GetNeighbors():
            y = nb.GetIdx()
            if y in ring and y not in seen:
                seen[y] = seen[x] + 1
                queue.append(y)
    return seen.get(b, 0)


def _component_name(kind, data, central: bool) -> str:
    """P-15.3.1.2.2.4: a component in a branch is numbered from the end
    nearest the multiplied unit, which is cited LAST ('oxybis(ethane-2,1-
    diyl)', 'peroxydi(4,1-phenylene)'); a central one ascends."""
    if kind == "simple":
        return data[0]
    if kind == "chain":
        m = data[0]
        if m == 1:
            return "methylene"
        stem = _ALKANE.get(m)
        if stem is None:
            raise Declined("a chain too long for the table")
        return f"{stem}-1,{m}-diyl" if central else f"{stem}-{m},1-diyl"
    if kind == "ring":
        k = data[0] + 1
        return f"1,{k}-phenylene" if central else f"{k},1-phenylene"
    raise Declined(kind)


def _divalent_linker(mol, dec, skeleton) -> str:
    a, b = dec.linker_attach
    path = Chem.GetShortestPath(mol, a, b) if a != b else (a,)
    path = list(path)
    if set(path) != skeleton:
        # Only a benzene may carry atoms off the path.
        off = skeleton - set(path)
        if not all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in off):
            raise Declined("a branched or substituted linker")
    comps = _components_along(mol, path, skeleton)
    if comps != comps[::-1]:
        raise Declined("an unsymmetrical linker (P-15.3.3.1 is not built)")
    if len(comps) % 2 == 0:
        raise Declined("no central linking group")
    mid = len(comps) // 2
    centre = _component_name(*comps[mid], central=True)
    if mid == 0:
        return centre
    branch = [_component_name(*c, central=False) for c in reversed(comps[:mid])]
    return centre + _multiplied_branch(branch, 2)


def _multiplied_branch(branch: list[str], n: int) -> str:
    """The branch after the central group. One simple group with locants
    takes "di": "[oxydi(tetradecane-14,1-diyl)]bis(silane) (PIN) [for 'di'
    before 'tetradecane-14,1-diyl' see P-16.3.4 (c)]" and "peroxydi(4,1-
    phenylene)"; one without locants takes "bis", as "methylenebis(oxy)"
    and "oxybis(methylene)" (dioxy could be read as peroxy); a concatenated
    branch takes "bis", "oxybis(ethane-2,1-diyloxy)" (pdf pp. 100-107)."""
    di, bis = _MULTIPLIER[n]
    text = "".join(branch)
    if len(branch) == 1 and re.search(r"\d", text):
        return f"{di}({text})"
    return f"{bis}({text})"


def _polyvalent_linker(mol, dec, skeleton) -> str:
    n = len(dec.units)
    # A single central atom with every branch identical.
    centres = [i for i in skeleton
               if sum(1 for nb in mol.GetAtomWithIdx(i).GetNeighbors() if nb.GetIdx() in skeleton)
               + sum(1 for a in dec.linker_attach if a == i) == n]
    if len(centres) != 1:
        raise Declined("no single central atom")
    c = centres[0]
    atom = mol.GetAtomWithIdx(c)
    name = _SIMPLE_POLYVALENT.get((atom.GetSymbol(), n))
    if name is None or atom.GetIsAromatic():
        raise Declined("no name for the central group")
    branches = []
    for a in dec.linker_attach:
        if a == c:
            branches.append(())
            continue
        path = list(Chem.GetShortestPath(mol, c, a))[1:]
        branches.append(tuple(_components_along(mol, path, skeleton)))
    if len(set(branches)) != 1:
        raise Declined("unequal branches")
    if not branches[0]:
        return name
    branch = [_component_name(*comp, central=False) for comp in branches[0]]
    return name + _multiplied_branch(branch, n)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _enclose(text: str) -> str:
    if "{" in text:
        raise Declined("nesting beyond braces")
    if "[" in text:
        return "{" + text + "}"
    if "(" in text:
        return "[" + text + "]"
    return "(" + text + ")"


def _n_levels(unit_name: str) -> int:
    for ending, levels in _N_LEVELS_BY_ENDING:
        if unit_name.endswith(ending):
            return levels
    return 1


def _primed(locant: str, k: int, n_levels: int) -> str:
    if not locant:
        return ""
    if locant.startswith("N"):
        return locant + "'" * (k * n_levels)
    return locant + "'" * k


def _assemble(linker: str, unit_name: str, locant: str, n: int, bare_name: str,
              substituted: bool) -> str:
    """P-15.3.1.3 (a)-(d) and P-15.3.2.1/.3/.4: locants, the linking group,
    then "di" before an unsubstituted unit -- enclosed when it carries
    locants, "di(ethan-1-ol)" -- or "bis" and enclosing marks before a
    substituted one, "bis(4-bromobenzene)", and before a unit whose "di"
    name is another compound, "bis(silane)"."""
    di, bis = _MULTIPLIER[n]
    levels = _n_levels(bare_name)
    locants = ",".join(_primed(locant, k, levels) for k in range(n)) if locant else ""
    needs_locant_enclosure = bool(re.search(r"\d", linker)) or "(" in linker
    link = _enclose(linker) if needs_locant_enclosure else linker
    has_locants = bool(re.search(r"\d", unit_name))
    if substituted or unit_name in _BIS_UNITS:
        unit = bis + _enclose(unit_name)
    elif has_locants:
        unit = di + _enclose(unit_name)
    else:
        unit = di + unit_name
    return f"{locants}-{link}{unit}" if locants else f"{link}{unit}"
