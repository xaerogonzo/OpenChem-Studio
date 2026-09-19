"""General fusion nomenclature (P-25.3), naming round 5 N3.

Names an ortho- or ortho- and peri-fused ring system that has no retained
name, by the book's construction: find the named components the system is
made of, choose the parent component by P-25.3.2.4, name every other
component as a first-order attached prefix with its fusion descriptor, and
number the whole system by its preferred drawing (`fusion_orientation`).

**THE SUPPORTED CLASS**, stated rather than implied: one parent component and
first-order attached components only (identical ones multiplied, "difuro",
"dibenzo"), every ring of three to eight members. Anything else raises
`fusion_orientation.Unsupported` with the reason -- a second-order component,
a multiparent system, a component this vocabulary does not have -- and the
caller keeps its older route. A partial fusion name is never emitted.

**WHAT THE VOCABULARY IS.** Components are matched on the SKELETON (elements
and ring bonds; bond orders and hydrogens ignored, since every component is
the mancude form):

* monocycles: benzene, the cycloalka prefixes, [n]annulenes as parents,
  the retained heteromonocycles of Table 2.2, and Hantzsch-Widman names built
  from `hw_tables.json` (the azoles take their HW names in brackets,
  P-25.3.2.1.2: "[1,3]oxazole", never "oxazole");
* benzo-heterocycles (P-25.2.2.4, "4H-3,1-benzoxazine", "[1]benzofuro"),
  formed only from an isolated benzene (P-25.3.5.4) and never where the
  heterocycle carries two benzenes, which are "dibenzo" (P-25.3.5,
  "6H-dibenzo[b,d]pyran, not 6H-benzo[c][1]benzopyran");
* the retained polycycles of Tables 2.7 and 2.8, numbered by the fusion rules
  except the book's traditional numberings (anthracene, phenanthrene,
  acridine, carbazole, xanthene and its chalcogen analogues, purine).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from functools import lru_cache

from openchem.vendor.iupac_namer.ring_naming import fusion_orientation as fo
from openchem.vendor.iupac_namer.ring_naming.fusion_orientation import Unsupported
from openchem.vendor.iupac_namer.types import Locant

# --- seniority orders -------------------------------------------------------

#: P-25.3.2.4 (a): a component containing a heteroatom earlier in this list.
PARENT_HETERO_ORDER = (
    "N", "F", "Cl", "Br", "I", "O", "S", "Se", "Te", "P", "As", "Sb", "Bi",
    "Si", "Ge", "Sn", "Pb", "B", "Al", "Ga", "In", "Tl",
)
#: P-25.3.2.4 (f), (i) and the HW citation order of 'a' prefixes (Table 2.4).
REPLACEMENT_ORDER = (
    "F", "Cl", "Br", "I", "O", "S", "Se", "Te", "N", "P", "As", "Sb", "Bi",
    "Si", "Ge", "Sn", "Pb", "B", "Al", "Ga", "In", "Tl",
)

#: The only contracted attached-component prefixes kept for PINs
#: (P-25.3.2.2.3); every other prefix changes a final 'e' to 'o' or adds 'o'.
RETAINED_PREFIX = {
    "anthracene": "anthra", "naphthalene": "naphtho", "benzene": "benzo",
    "phenanthrene": "phenanthro", "furan": "furo", "imidazole": "imidazo",
    "pyridine": "pyrido", "pyrimidine": "pyrimido", "thiophene": "thieno",
}

#: Table 2.2 names used as components, keyed by (ring size, heteroatoms in
#: HW numbering order). Numbering is the HW one: see `_hw_numberings`.
RETAINED_MONOCYCLES = {
    (5, ("N",)): "pyrrole", (5, ("O",)): "furan", (5, ("S",)): "thiophene",
    (5, ("Se",)): "selenophene", (5, ("Te",)): "tellurophene",
    (5, ("N", "N"), (1, 3)): "imidazole", (5, ("N", "N"), (1, 2)): "pyrazole",
    (6, ("N",)): "pyridine", (6, ("O",)): "pyran", (6, ("S",)): "thiopyran",
    (6, ("Se",)): "selenopyran", (6, ("Te",)): "telluropyran",
    (6, ("N", "N"), (1, 4)): "pyrazine", (6, ("N", "N"), (1, 3)): "pyrimidine",
    (6, ("N", "N"), (1, 2)): "pyridazine",
}

_HW_PREFIX = {
    "O": "oxa", "S": "thia", "Se": "selena", "Te": "tellura", "N": "aza",
    "P": "phospha", "As": "arsa", "Sb": "stiba", "Bi": "bisma", "Si": "sila",
    "Ge": "germa", "Sn": "stanna", "Pb": "plumba", "B": "bora",
}
_SIX_GROUP_A = {"O", "S", "Se", "Te", "Bi"}
_SIX_GROUP_B = {"N", "Si", "Ge", "Sn", "Pb"}
_MULT = {1: "", 2: "di", 3: "tri", 4: "tetra", 5: "penta"}
_CARBO_PREFIX = {3: "cyclopropa", 4: "cyclobuta", 5: "cyclopenta", 7: "cyclohepta",
                 8: "cycloocta"}


# --- retained polycyclic components (Tables 2.7, 2.8) --------------------------

#: name -> skeleton SMILES. Atom-map numbers index `_TRADITIONAL` labels
#: where the book keeps a traditional numbering; otherwise the numbering is
#: computed by the fusion rules on the skeleton.
POLYCYCLES: dict[str, str] = {
    "naphthalene": "C1CCC2CCCCC2C1",
    "azulene": "C1CCC2CCCC2CC1",
    "indene": "C1CC2CCCCC2C1",
    "pentalene": "C1CC2CCCC2C1",
    "heptalene": "C1CCCC2CCCCCC2CC1",
    "biphenylene": "C1CCC2C(C1)C1CCCCC12",
    "as-indacene": "C1CC2CCC3CCCC3C2C1",
    "s-indacene": "C1CC2CC3CCCC3CC2C1",
    "acenaphthylene": "C1CC2CCCC3CCC(C1)C23",
    "fluorene": "C1CCC2C(C1)CC1CCCCC12",
    "phenalene": "C1CC2CCCC3CCCC(C1)C23",
    "fluoranthene": "C1CC2CCCC3C4CCCCC4C(C1)C23",
    "triphenylene": "C1CCC2C(C1)C1CCCCC1C1CCCCC21",
    "pyrene": "C1CC2CCC3CCCC4CCC(C1)C2C34",
    "chrysene": "C1CCC2C(C1)CCC1C3CCCCC3CCC21",
    "tetracene": "C1CCC2CC3CC4CCCCC4CC3CC2C1",
    "tetraphene": "C1CCC2CC3C(CCC4CCCCC43)CC2C1",
    "picene": "C1CCC2C(C1)CCC1C2CCC2C3CCCCC3CCC21",
    "pentacene": "C1CCC2CC3CC4CC5CCCCC5CC4CC3CC2C1",
    "perylene": "C1CC2CCCC3C4CCCC5CCCC(C(C1)C23)C54",
    "indole": "C1CCC2NCCC2C1",
    "isoindole": "C1CCC2CNCC2C1",
    "indolizine": "C1CCN2CCCC2C1",
    "indazole": "C1CCC2NNCC2C1",
    "quinolizine": "C1CCN2CCCCC2C1",
    "quinoline": "C1CCC2NCCCC2C1",
    "isoquinoline": "C1CCC2CNCCC2C1",
    "phthalazine": "C1CCC2CNNCC2C1",
    "quinoxaline": "C1CCC2NCCNC2C1",
    "quinazoline": "C1CCC2NCNCC2C1",
    "cinnoline": "C1CCC2NNCCC2C1",
    "pteridine": "C1CNC2NCNCC2N1",
    "phenanthridine": "C1CCC2C(C1)CNC1CCCCC21",
    "perimidine": "C1CC2CCCC3NCNC(C1)C23",
    "phenazine": "C1CCC2NC3CCCCC3NC2C1",
    "phenoxazine": "C1CCC2OC3CCCCC3NC2C1",
    "phenothiazine": "C1CCC2SC3CCCCC3NC2C1",
    "phenoxathiine": "C1CCC2OC3CCCCC3SC2C1",
    "thianthrene": "C1CCC2SC3CCCCC3SC2C1",
    "oxanthrene": "C1CCC2OC3CCCCC3OC2C1",
    "aceanthrylene": "C1CC2CC3CCCCC3C3CCC(C1)C23",
    "acephenanthrylene": "C1CCC2C(C1)CC1CCC3CCCC2C31",
    # Table 2.8: the As and P analogues keep the parent's numbering
    "arsindole": "C1CCC2[As]CCC2C1", "phosphindole": "C1CCC2PCCC2C1",
    "isoarsindole": "C1CCC2C[As]CC2C1", "isophosphindole": "C1CCC2CPCC2C1",
    "arsindolizine": "C1CC[As]2CCCC2C1", "phosphindolizine": "C1CCP2CCCC2C1",
    "arsinoline": "C1CCC2[As]CCCC2C1", "phosphinoline": "C1CCC2PCCCC2C1",
    "isoarsinoline": "C1CCC2C[As]CCC2C1", "isophosphinoline": "C1CCC2CPCCC2C1",
    "arsinolizine": "C1CC[As]2CCCCC2C1", "phosphinolizine": "C1CCP2CCCCC2C1",
    "arsanthridine": "C1CCC2C(C1)C[As]C1CCCCC21",
    "phosphanthridine": "C1CCC2C(C1)CPC1CCCCC21",
    # traditional numberings (P-25.3.3): labels by atom-map number
    "anthracene": "[C:1]1[C:2][C:3][C:4][C:5]2[C:6][C:7]3[C:8][C:9][C:10][C:11][C:12]3[C:13][C:14]12",
    "phenanthrene": "[C:1]1[C:2][C:3][C:4][C:5]2[C:6]3[C:7][C:8][C:9][C:10][C:11]3[C:12][C:13][C:14]12",
    "acridine": "[C:1]1[C:2][C:3][C:4][C:5]2[N:6][C:7]3[C:8][C:9][C:10][C:11][C:12]3[C:13][C:14]12",
    "carbazole": "[C:1]1[C:2][C:3][C:4][C:5]2[C:6]3[C:7][C:8][C:9][C:10][C:11]3[N:12][C:13]12",
    "xanthene": "[C:1]1[C:2][C:3][C:4][C:5]2[O:6][C:7]3[C:8][C:9][C:10][C:11][C:12]3[C:13][C:14]12",
    "thioxanthene": "[C:1]1[C:2][C:3][C:4][C:5]2[S:6][C:7]3[C:8][C:9][C:10][C:11][C:12]3[C:13][C:14]12",
    "selenoxanthene": "[C:1]1[C:2][C:3][C:4][C:5]2[Se:6][C:7]3[C:8][C:9][C:10][C:11][C:12]3[C:13][C:14]12",
    "telluroxanthene": "[C:1]1[C:2][C:3][C:4][C:5]2[Te:6][C:7]3[C:8][C:9][C:10][C:11][C:12]3[C:13][C:14]12",
    "purine": "[N:1]1[C:2][N:3][C:4]2[C:5]([C:6]1)[N:7][C:8][N:9]2",
    "acridarsine": "[C:1]1[C:2][C:3][C:4][C:5]2[As:6][C:7]3[C:8][C:9][C:10][C:11][C:12]3[C:13][C:14]12",
    "acridophosphine": "[C:1]1[C:2][C:3][C:4][C:5]2[P:6][C:7]3[C:8][C:9][C:10][C:11][C:12]3[C:13][C:14]12",
}

_ANTHRACENE_LABELS = ("1", "2", "3", "4", "4a", "10", "10a", "5", "6", "7", "8", "8a", "9", "9a")
_TRADITIONAL: dict[str, tuple[str, ...]] = {
    "anthracene": _ANTHRACENE_LABELS,
    "phenanthrene": ("1", "2", "3", "4", "4a", "4b", "5", "6", "7", "8", "8a", "9", "10", "10a"),
    "acridine": _ANTHRACENE_LABELS,
    "carbazole": ("1", "2", "3", "4", "4a", "4b", "5", "6", "7", "8", "8a", "9", "9a"),
    "xanthene": _ANTHRACENE_LABELS,
    "thioxanthene": _ANTHRACENE_LABELS,
    "selenoxanthene": _ANTHRACENE_LABELS,
    "telluroxanthene": _ANTHRACENE_LABELS,
    "purine": ("1", "2", "3", "4", "5", "6", "7", "8", "9"),
    "acridarsine": _ANTHRACENE_LABELS,
    "acridophosphine": _ANTHRACENE_LABELS,
}
#: A retained polycycle whose name cites heteroatom locants inside a fusion
#: name (Table 2.8: "1,8-naphthyridine" -> "[1,8]naphthyridine").
_LOCANT_NAMED_POLYCYCLES: dict[str, str] = {}


# --- component occurrences ----------------------------------------------------


@dataclass(frozen=True)
class Component:
    """One named component as it occurs in the system being named."""

    name: str            # "pyridine", "[1,3]oxazole", "1-benzofuran", "benzene"
    prefix: str          # "pyrido", "[1,3]oxazolo", "[1]benzofuro", "benzo"
    rings: frozenset[int]    # indices into the system's rings
    atoms: frozenset[int]
    #: every valid numbering of the component: molecule atom -> locant label
    numberings: tuple[tuple[tuple[int, str], ...], ...]
    kind: str            # "carbocycle", "annulene", "heteromono", "benzo", "polycycle"
    ring_sizes: tuple[int, ...]
    hetero: tuple[str, ...]   # heteroatom elements, sorted
    horizontal_row: int = 1
    #: (atom, element) for every atom, so seniority can read locants by element
    elements: tuple[tuple[int, str], ...] = ()
    #: the name as a PARENT inside a fusion name ("[2,1]benzothiazole")
    parent_name: str = ""

    @property
    def monocyclic_hydrocarbon(self) -> bool:
        return self.kind in ("carbocycle", "annulene") or self.name == "benzene"

    def label_maps(self) -> list[dict[int, str]]:
        return [dict(n) for n in self.numberings]


def _locant_key(label: str) -> tuple[int, str]:
    digits = "".join(ch for ch in label if ch.isdigit() and label.index(ch) < len(label))
    i = 0
    while i < len(label) and label[i].isdigit():
        i += 1
    return (int(label[:i]) if i else 0, label[i:])


def _elements(mol, atoms) -> tuple[tuple[int, str], ...]:
    return tuple(sorted((a, mol.GetAtomWithIdx(a).GetSymbol()) for a in atoms))


def _hetero_elements(mol, atoms) -> tuple[str, ...]:
    return tuple(sorted(mol.GetAtomWithIdx(a).GetSymbol() for a in atoms
                        if mol.GetAtomWithIdx(a).GetSymbol() != "C"))


# --- monocycles ---------------------------------------------------------------


def _cycle(ring: tuple[int, ...]) -> list[int]:
    return list(ring)


def _hw_numberings(mol, ring: tuple[int, ...]) -> list[dict[int, int]]:
    """P-31.1.4.2.4 / P-22.2.2.1: locant 1 on a most-senior heteroatom, then
    lowest locants to the heteroatoms as a set, then in seniority order.
    Returns every numbering that ties (they are symmetry-equivalent)."""
    n = len(ring)
    el = {a: mol.GetAtomWithIdx(a).GetSymbol() for a in ring}
    hetero = [a for a in ring if el[a] != "C"]
    if not hetero:
        # carbocycle: every start and direction is equivalent
        out = []
        for start in range(n):
            for step in (1, -1):
                out.append({ring[(start + step * i) % n]: i + 1 for i in range(n)})
        return out
    senior = min(REPLACEMENT_ORDER.index(el[a]) for a in hetero)
    candidates = []
    for start in range(n):
        if el[ring[start]] == "C" or REPLACEMENT_ORDER.index(el[ring[start]]) != senior:
            continue
        for step in (1, -1):
            num = {ring[(start + step * i) % n]: i + 1 for i in range(n)}
            key = (
                sorted(num[a] for a in hetero),
                [num[a] for e in REPLACEMENT_ORDER for a in sorted(hetero, key=lambda x: num[x]) if el[a] == e],
            )
            candidates.append((key, num))
    best = min(k for k, _n in candidates)
    return [num for k, num in candidates if k == best]


def _hw_name(mol, ring: tuple[int, ...], numbering: dict[int, int]) -> str | None:
    """Hantzsch-Widman (or Table 2.2) name of the mancude monocycle, with the
    heteroatom locants a fusion name keeps in brackets."""
    n = len(ring)
    el = {a: mol.GetAtomWithIdx(a).GetSymbol() for a in ring}
    hetero = sorted((a for a in ring if el[a] != "C"), key=lambda a: numbering[a])
    elements = tuple(el[a] for a in hetero)
    locs = tuple(numbering[a] for a in hetero)
    by_order = sorted(hetero, key=lambda a: (REPLACEMENT_ORDER.index(el[a]), numbering[a]))
    if (n, tuple(sorted(elements))) in RETAINED_MONOCYCLES:
        return RETAINED_MONOCYCLES[(n, tuple(sorted(elements)))]
    if (n, tuple(sorted(elements)), locs) in RETAINED_MONOCYCLES:
        return RETAINED_MONOCYCLES[(n, tuple(sorted(elements)), locs)]
    if any(e not in _HW_PREFIX for e in elements) or n > 10 or n < 3:
        return None
    # prefixes in citation order, multiplied, with 'a' elided before a vowel
    groups: list[tuple[str, int]] = []
    for a in by_order:
        if groups and groups[-1][0] == el[a]:
            groups[-1] = (el[a], groups[-1][1] + 1)
        else:
            groups.append((el[a], 1))
    has_n = "N" in elements
    if n == 6:
        last = {e for e in elements}
        if last - _SIX_GROUP_A - _SIX_GROUP_B:
            stem = "inine"
        else:
            stem = "ine"
    else:
        stem = {3: "irine" if has_n else "irene", 4: "ete", 5: "ole", 7: "epine",
                8: "ocine", 9: "onine", 10: "ecine"}[n]
    text = ""
    for i, (e, count) in enumerate(groups):
        piece = _MULT[count] + _HW_PREFIX[e]
        text += piece
    # elide the final 'a' of each prefix before a vowel
    parts = []
    for i, (e, count) in enumerate(groups):
        parts.append(_MULT[count] + _HW_PREFIX[e])
    if len(groups) == 1 and groups[0][1] >= 3:
        # "tetrazole", "triazole": the multiplier's vowel meets the prefix's
        parts = [parts[0].replace("aaza", "aza").replace("aoxa", "oxa")]
    joined = ""
    for i, piece in enumerate(parts):
        nxt = parts[i + 1] if i + 1 < len(parts) else stem
        if piece.endswith("a") and nxt[0] in "aeiou":
            piece = piece[:-1]
        joined += piece
    name = joined + stem
    only_arrangement = len(set(elements)) == 1 and len(hetero) == n - 1
    if (len(hetero) > 1 or n > 10) and not only_arrangement:
        loc_text = ",".join(str(numbering[a]) for a in by_order)
        name = f"[{loc_text}]{name}"
    return name


def _attach_prefix(name: str) -> str:
    base = name
    if base in RETAINED_PREFIX:
        return RETAINED_PREFIX[base]
    return base[:-1] + "o" if base.endswith("e") else base + "o"


# --- polycycle numberings -----------------------------------------------------


@lru_cache(maxsize=None)
def _polycycle_template(name: str):
    """(skeleton mol, [atom -> label map, ...], horizontal-row count)."""
    from rdkit import Chem

    smi = POLYCYCLES[name]
    mol = Chem.MolFromSmiles(smi, sanitize=False)
    mol.UpdatePropertyCache(strict=False)
    Chem.FastFindRings(mol)
    if name in _TRADITIONAL:
        labels = _TRADITIONAL[name]
        base = {a.GetIdx(): labels[a.GetAtomMapNum() - 1] for a in mol.GetAtoms()}
        maps = _automorphic_images(mol, base)
    else:
        rings = [tuple(r) for r in _ring_cycles(mol)]
        options = fo.preferred_numberings(mol, rings)
        maps = []
        for option in options:
            base = {a: loc.label for a, loc in option.atom_to_locant.items()}
            maps.extend(_automorphic_images(mol, base))
    rings = [tuple(r) for r in _ring_cycles(mol)]
    system = fo.prepare(mol, rings)
    best = fo.preferred_drawings(system)
    row = fo.orientation_key(best[0])[0]
    for a in mol.GetAtoms():
        a.SetAtomMapNum(0)
    unique = {tuple(sorted(m.items())): m for m in maps}
    return mol, list(unique.values()), row


def _ring_cycles(mol):
    from rdkit import Chem

    # The SSSR, not FastFindRings: the latter also returns envelope rings
    # (naphthalene's 10-membered perimeter), which are not components.
    return tuple(tuple(r) for r in Chem.GetSymmSSSR(mol))


def _automorphic_images(mol, base: dict[int, str]) -> list[dict[int, str]]:
    """Every numbering equivalent to *base* by an element-preserving
    automorphism of the skeleton."""
    query = _skeleton_query(mol)
    out = []
    for match in mol.GetSubstructMatches(query, uniquify=False, maxMatches=5000,
                                          useChirality=False):
        out.append({match[i]: base[i] for i in base})
    return out or [base]


def _skeleton_query(mol):
    """A query matching the same skeleton: elements fixed, any bond."""
    from rdkit import Chem

    rw = Chem.RWMol()
    for atom in mol.GetAtoms():
        q = Chem.AtomFromSmarts(f"[#{atom.GetAtomicNum()}]")
        rw.AddAtom(q)
    for bond in mol.GetBonds():
        rw.AddBond(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx(), Chem.BondType.UNSPECIFIED)
        qb = rw.GetBondBetweenAtoms(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
    query = rw.GetMol()
    return Chem.MolFromSmarts(Chem.MolToSmarts(query).replace("-", "~").replace("=", "~"))


# --- finding components in the system ------------------------------------------


@dataclass
class _System:
    mol: object
    rings: list[tuple[int, ...]]
    ring_sets: list[frozenset[int]]
    atoms: frozenset[int]
    ring_bonds: set[frozenset[int]] = field(default_factory=set)

    def rings_of(self, atoms: frozenset[int]) -> frozenset[int] | None:
        """The ring indices whose union is exactly *atoms*, or None."""
        chosen = frozenset(i for i, r in enumerate(self.ring_sets) if r <= atoms)
        union = frozenset().union(*(self.ring_sets[i] for i in chosen)) if chosen else frozenset()
        return chosen if union == atoms else None


def _system_skeleton(system: _System):
    """The ring skeleton of the system as its own mol, with an index map."""
    from rdkit import Chem

    rw = Chem.RWMol()
    index = {}
    for a in sorted(system.atoms):
        atom = system.mol.GetAtomWithIdx(a)
        index[a] = rw.AddAtom(Chem.Atom(atom.GetAtomicNum()))
    for bond in system.mol.GetBonds():
        u, v = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if frozenset((u, v)) in system.ring_bonds:
            rw.AddBond(index[u], index[v], Chem.BondType.SINGLE)
    skel = rw.GetMol()
    skel.UpdatePropertyCache(strict=False)
    Chem.FastFindRings(skel)
    back = {v: k for k, v in index.items()}
    return skel, back


def _find_polycycles(system: _System) -> list[Component]:
    skel, back = _system_skeleton(system)
    found: dict[tuple[str, frozenset[int]], Component] = {}
    for name in POLYCYCLES:
        template, maps, row = _polycycle_template(name)
        if template.GetNumAtoms() > len(system.atoms):
            continue
        query = _skeleton_query(template)
        for match in skel.GetSubstructMatches(query, uniquify=False, maxMatches=2000):
            atoms = frozenset(back[i] for i in match)
            rings = system.rings_of(atoms)
            if rings is None or len(rings) != len(_ring_cycles(template)):
                continue
            # the component's bonds must be exactly the system's bonds among them
            inner = sum(1 for b in system.ring_bonds if b <= atoms)
            if inner != template.GetNumBonds():
                continue
            key = (name, rings)
            images = [tuple(sorted((back[match[t]], lab) for t, lab in m.items())) for m in maps]
            comp = found.get(key)
            numberings = tuple(sorted(set(images) | set(comp.numberings if comp else ())))
            found[key] = Component(
                name=name, prefix=_attach_prefix(name), rings=rings, atoms=atoms,
                numberings=numberings, kind="polycycle",
                ring_sizes=tuple(sorted((len(system.rings[i]) for i in rings), reverse=True)),
                hetero=_hetero_elements(system.mol, atoms), horizontal_row=row,
                elements=_elements(system.mol, atoms), parent_name=name,
            )
    return list(found.values())


def _monocycle(system: _System, i: int) -> Component | None:
    mol = system.mol
    ring = system.rings[i]
    atoms = frozenset(ring)
    hetero = _hetero_elements(mol, atoms)
    size = len(ring)
    maps = _hw_numberings(mol, ring)
    if not hetero:
        if size == 6:
            name, prefix, kind = "benzene", "benzo", "carbocycle"
        elif size in _CARBO_PREFIX:
            name = f"[{size}]annulene" if size >= 7 else f"cyclo{size}"
            prefix, kind = _CARBO_PREFIX[size], ("annulene" if size >= 7 else "carbocycle")
        else:
            return None
    else:
        name = _hw_name(mol, ring, maps[0])
        if name is None:
            return None
        prefix, kind = _attach_prefix(name), "heteromono"
    numberings = tuple(sorted({tuple(sorted((a, str(m[a])) for a in ring)) for m in maps}))
    if kind == "carbocycle" and size != 6:
        parent_name = ""  # cyclopenta etc. are prefixes only; never a parent
    else:
        parent_name = name
    return Component(name=name, prefix=prefix, rings=frozenset({i}), atoms=atoms,
                     numberings=numberings, kind=kind, ring_sizes=(size,), hetero=hetero,
                     elements=_elements(mol, atoms), parent_name=parent_name)


def _benzo_heterocycles(system: _System, monos: list[Component],
                        polys: list[Component]) -> list[Component]:
    """P-25.2.2.4: an isolated benzene ortho-fused to a heteromonocycle of
    five or more members, as one component -- never where the benzene is part
    of a retained polycycle, and never on a heterocycle carrying two
    benzenes (they are "dibenzo", P-25.3.5)."""
    from rdkit import Chem

    in_poly = set()
    for p in polys:
        in_poly |= p.rings
    benzenes = [m for m in monos if m.name == "benzene" and not (m.rings & in_poly)]
    out = []
    for het in monos:
        if het.kind != "heteromono" or het.ring_sizes[0] < 5:
            continue
        fused_benz = [b for b in benzenes if len(b.atoms & het.atoms) == 2]
        if len(fused_benz) != 1:
            continue
        b = fused_benz[0]
        atoms = b.atoms | het.atoms
        # the bicycle's own numbering by the fusion rules; locant 1 then falls
        # on a heterocycle atom next to a fusion atom (P-25.2.2.4)
        rings = [system.rings[next(iter(b.rings))], system.rings[next(iter(het.rings))]]
        try:
            options = fo.preferred_numberings(system.mol, rings)
        except Unsupported:
            continue
        maps = [{a: loc.label for a, loc in o.atom_to_locant.items()} for o in options]
        el = {a: system.mol.GetAtomWithIdx(a).GetSymbol() for a in atoms}
        hetero_atoms = [a for a in atoms if el[a] != "C"]
        m0 = maps[0]
        by_order = sorted(hetero_atoms, key=lambda a: (REPLACEMENT_ORDER.index(el[a]), _locant_key(m0[a])))
        locs = ",".join(m0[a] for a in by_order)
        stem = het.name.split("]", 1)[-1]  # drop the monocycle's own locants
        body = "benz" + stem if stem[0] in "aeiou" else "benzo" + stem
        name = f"{locs}-{body}"
        # the contracted prefixes survive inside a benzo name: "[1]benzofuro"
        tail = RETAINED_PREFIX.get(stem, _attach_prefix(stem))
        prefix = f"[{locs}]" + ("benz" + tail if tail[0] in "aeiou" else "benzo" + tail)
        out.append(Component(
            name=name, prefix=prefix, rings=b.rings | het.rings, atoms=atoms,
            numberings=tuple(sorted({tuple(sorted(m.items())) for m in maps})),
            kind="benzo", ring_sizes=tuple(sorted((6, het.ring_sizes[0]), reverse=True)),
            hetero=_hetero_elements(system.mol, atoms), horizontal_row=2,
            elements=_elements(system.mol, atoms), parent_name=f"[{locs}]{body}",
        ))
    return out


# --- seniority (P-25.3.2.4) ---------------------------------------------------


def seniority_key(c: Component) -> tuple:
    """Smaller is MORE senior. (a)-(j) of P-25.3.2.4."""
    def first_hetero(elements):
        ranks = [PARENT_HETERO_ORDER.index(e) for e in elements if e in PARENT_HETERO_ORDER]
        return min(ranks) if ranks else len(PARENT_HETERO_ORDER)

    n_rings = len(c.rings)
    sizes = tuple(-s for s in c.ring_sizes)
    variety = len(set(c.hetero))
    senior_counts = tuple(-c.hetero.count(e) for e in REPLACEMENT_ORDER)
    element = dict(c.elements)
    m = c.label_maps()
    hetero_locs = min(
        tuple(sorted(_locant_key(lab) for a, lab in mp.items()
                     if element.get(a, "C") != "C")) for mp in m
    ) if m else ()
    # (i) heteroatom locants element by element in the 'a'-prefix order;
    # (j) peripheral fusion carbon locants
    by_element = min(
        tuple(_locant_key(mp[a]) for e in REPLACEMENT_ORDER
              for a in sorted((x for x in mp if element.get(x) == e), key=lambda x: _locant_key(mp[x])))
        for mp in m
    ) if m else ()
    fusion_c = min(
        tuple(sorted(_locant_key(lab) for a, lab in mp.items()
                     if element.get(a, "C") == "C" and any(ch.isalpha() for ch in lab)))
        for mp in m
    ) if m else ()
    return (
        first_hetero(c.hetero), -n_rings, sizes, -len(c.hetero), -variety,
        senior_counts, -c.horizontal_row, hetero_locs, by_element, fusion_c,
    )


# --- descriptors ----------------------------------------------------------------


def _periphery_order(comp: Component, label_map: dict[int, str], ring_sets) -> list[int]:
    """The component's peripheral atoms in the order of its own locants. An
    atom in three of the component's rings is interior to it (pyrene's two
    central carbons) and carries no lettered side."""
    rings = [ring_sets[i] for i in comp.rings]
    return [a for a, _lab in sorted(label_map.items(), key=lambda kv: _locant_key(kv[1]))
            if sum(1 for r in rings if a in r) < 3]


def _sides(order: list[int]) -> list[tuple[int, int]]:
    return [(order[i], order[(i + 1) % len(order)]) for i in range(len(order))]


def _letter(i: int) -> str:
    return chr(ord("a") + i)


def fusion_descriptor(parent: Component, parent_map: dict[int, str],
                      attached: Component, attached_map: dict[int, str],
                      ring_sets, bonds: set[frozenset[int]]) -> tuple[tuple[int, ...], str, str] | None:
    """(letter indices, letters, attached locants) for one attached component
    under one parent numbering and one attached numbering. Letters follow the
    parent's peripheral sides a = 1-2, b = 2-3 ...; the attached locants are
    those of the shared atoms, cited in the parent's lettering direction."""
    order = _periphery_order(parent, parent_map, ring_sets)
    sides = _sides(order)
    shared = parent.atoms & attached.atoms
    fused = [i for i, (u, v) in enumerate(sides)
             if u in shared and v in shared and frozenset((u, v)) in bonds]
    if not fused:
        return None
    # consecutive sides (peri fusion) -- the path runs from the first side's
    # first atom to the last side's second atom in lettering direction
    fused.sort()
    if len(fused) > 1 and fused != list(range(fused[0], fused[0] + len(fused))):
        # wrapped around the end of the lettering (e.g. sides j and a)
        n = len(sides)
        rotated = sorted(fused, key=lambda i: (i - fused[-1] - 1) % n)
        fused = rotated
    path = [sides[fused[0]][0]] + [sides[i][1] for i in fused]
    # P-25.3.1.3: for ortho- and peri-fusion "only locants of the nonfused
    # atoms of the attached component are indicated" -- its own fusion atoms
    # inside the path drop out (naphtho[2,1,8-def], not [2,1,8a,8-def]); an
    # endpoint stays (naphtho[1,8a-b]azirine)
    keep = [a for i, a in enumerate(path)
            if i in (0, len(path) - 1) or not any(ch.isalpha() for ch in attached_map[a])]
    locs = ",".join(attached_map[a] for a in keep)
    letters = "".join(_letter(i) for i in sorted(fused))
    return tuple(sorted(fused)), letters, locs


# --- the constructor ------------------------------------------------------------


@dataclass(frozen=True)
class FusionName:
    text: str                     # "cyclohepta[b]quinoline" (no indicated H)
    numberings: tuple             # fusion_orientation Numbering options


def name_fusion(mol, ring_atom_tuples) -> FusionName:
    """The fusion name of the mancude system, and its numberings."""
    from rdkit import Chem  # noqa: F401

    rings = [tuple(r) for r in ring_atom_tuples]
    ring_sets = [frozenset(r) for r in rings]
    atoms = frozenset().union(*ring_sets)
    ring_bonds = set()
    for r in rings:
        for i in range(len(r)):
            ring_bonds.add(frozenset((r[i], r[(i + 1) % len(r)])))
    system = _System(mol=mol, rings=rings, ring_sets=ring_sets, atoms=atoms, ring_bonds=ring_bonds)
    if sum(1 for r in rings if len(r) >= 5) < 2:
        raise Unsupported("P-52.2.4.1: fewer than two rings of five or more members")

    numberings = fo.preferred_numberings(mol, rings)

    monos = [c for i in range(len(rings)) if (c := _monocycle(system, i)) is not None]
    polys = _find_polycycles(system)
    benzos = _benzo_heterocycles(system, monos, polys)
    components = monos + polys + benzos

    # a two-ring benzene + heteromonocycle IS its benzo name (P-25.2.2.4)
    if len(rings) == 2:
        whole = [c for c in benzos if len(c.rings) == 2]
        if whole:
            return FusionName(text=whole[0].name, numberings=tuple(numberings))

    by_senior = sorted((c for c in components if c.parent_name), key=seniority_key)
    if not by_senior:
        raise Unsupported("no component here can be the parent")
    top = seniority_key(by_senior[0])
    parents = [c for c in by_senior if seniority_key(c) == top]
    parent_types = {p.name for p in parents}
    if len(parent_types) != 1:
        raise Unsupported(f"no single most senior parent component: {sorted(parent_types)}")
    for p, q in itertools.combinations(parents, 2):
        if not (p.rings & q.rings) and not _shares_bond(p, q, system):
            # two occurrences joined through another component: P-25.3.4.1.3
            raise Unsupported("the parent component occurs twice (a multiparent system)",
                              code=Unsupported.NEEDS_UNBUILT_CONSTRUCTION)
    # P-25.3.5.3: a multiparent name beats a benzo-heterocycle -- look past
    # the benzo units for a repeated senior component, too
    plain = sorted((c for c in monos + polys if c.parent_name), key=seniority_key)
    if plain:
        top_plain = [c for c in plain if seniority_key(c) == seniority_key(plain[0])]
        for p, q in itertools.combinations(top_plain, 2):
            if not (p.rings & q.rings) and not _shares_bond(p, q, system):
                raise Unsupported("the senior component occurs twice (a multiparent system)",
                              code=Unsupported.NEEDS_UNBUILT_CONSTRUCTION)

    best = None
    for parent in parents:
        rest = frozenset(range(len(rings))) - parent.rings
        for partition in _partitions(rest, components, parent, system):
            key, text = _score_and_name(parent, partition, system)
            if key is None:
                continue
            if best is None or key < best[0]:
                best = (key, text)
    if best is None:
        raise Unsupported(
            "the rings outside the parent component need a second-order or "
            "unnamed attached component",
            code=Unsupported.NEEDS_UNBUILT_CONSTRUCTION,
        )
    return FusionName(text=best[1], numberings=tuple(numberings))


def _partitions(rest: frozenset[int], components, parent: Component, system: _System):
    """Every way to cover *rest* with components, each fused to the parent
    by a shared bond and none fused to another (first-order only)."""
    usable = [c for c in components
              if c.rings <= rest and _shares_bond(c, parent, system)]

    def rec(remaining, chosen):
        if not remaining:
            yield list(chosen)
            return
        first = min(remaining)
        for c in usable:
            if first not in c.rings or not c.rings <= remaining:
                continue
            if any(_shares_bond(c, o, system) for o in chosen):
                continue
            chosen.append(c)
            yield from rec(remaining - c.rings, chosen)
            chosen.pop()

    yield from rec(rest, [])


def _shares_bond(a: Component, b: Component, system: _System) -> bool:
    shared = a.atoms & b.atoms
    return any(bond <= shared for bond in system.ring_bonds)


def _score_and_name(parent: Component, attached: list[Component], system: _System):
    """The P-25.3.4.2.1/2 key of one decomposition and its name text.

    Key (smaller better): more first-order components (c); more identical
    ones (d); senior attached components first (f / P-25.3.4.2.2 (a)); then
    the lowest letters as a set (b); then in citation order (c); then the
    lowest attached locants."""
    mol = system.mol
    groups: dict[str, list[Component]] = {}
    for c in attached:
        groups.setdefault(c.name, []).append(c)
    identical = sum(len(g) for g in groups.values() if len(g) > 1)
    seniority = tuple(sorted(seniority_key(c) for c in attached))

    best = None
    for pmap in parent.label_maps():
        described = []
        for c in attached:
            options = []
            for amap in c.label_maps():
                d = fusion_descriptor(parent, pmap, c, amap, system.ring_sets, system.ring_bonds)
                if d is None:
                    continue
                idx, letters, locs = d
                loc_key = tuple(_locant_key(x) for x in locs.split(","))
                options.append((idx, loc_key, letters, locs))
            if not options:
                break
            options.sort()
            described.append((c, options[0]))
        else:
            letters_set = tuple(sorted(i for _c, (idx, *_r) in described for i in idx))
            text = _assemble(parent, described)
            citation = tuple(idx for _c, (idx, *_r) in sorted(described, key=lambda d: _cite_key(d[0])))
            loc_keys = tuple(lk for _c, (_i, lk, *_r) in sorted(described, key=lambda d: _cite_key(d[0])))
            key = (letters_set, citation, loc_keys)
            if best is None or key < best[0]:
                best = (key, text)
    if best is None:
        return None, None
    return (-len(attached), -identical, seniority, best[0]), best[1]


def _cite_key(c: Component) -> tuple[str, str]:
    """Alphabetical order of prefixes, ignoring locant brackets and italic
    designators (P-25.3.4.2.3.1, the indacene note), then the locants."""
    text = c.prefix
    while text.startswith("["):
        text = text.split("]", 1)[1]
    for italic in ("as-", "s-"):
        if text.startswith(italic):
            text = text[len(italic):]
    return (text, c.prefix)


def _assemble(parent: Component, described) -> str:
    """Prefixes in alphabetical order, identical ones multiplied, then the
    parent name. Numerical locants of a monocyclic hydrocarbon attached
    component are omitted (P-25.3.8.1), and the letters too when the parent is
    also a monocyclic hydrocarbon."""
    groups: dict[str, list] = {}
    for c, option in described:
        groups.setdefault(c.prefix, []).append((c, option))
    pieces = []
    for prefix in sorted(groups, key=lambda p: _cite_key(groups[p][0][0])):
        members = sorted(groups[prefix], key=lambda m: m[1][0])
        c0 = members[0][0]
        mult = _MULT[len(members)] if len(members) > 1 else ""
        if c0.monocyclic_hydrocarbon:
            if parent.monocyclic_hydrocarbon:
                desc = ""
            else:
                desc = "[" + ",".join(opt[2] for _c, opt in members) + "]"
        else:
            parts = []
            for k, (_c, opt) in enumerate(members):
                primes = "'" * k
                locs = ",".join(x + primes for x in opt[3].split(","))
                parts.append(f"{locs}-{opt[2]}")
            desc = "[" + ":".join(parts) + "]"
        body = prefix
        if mult and body.startswith("["):
            # "2H,9H-bis([1,3]benzodioxolo)[4,5,6-cd:5',6'-f]indole"
            mult = {"di": "bis", "tri": "tris", "tetra": "tetrakis"}[mult]
            body = f"({body})"
        piece = f"{mult}{body}{desc}"
        if pieces and (piece.startswith("as-") or piece.startswith("s-")):
            piece = "-" + piece
        pieces.append(piece)
    return "".join(pieces) + parent.parent_name


# --- the engine's entry point -------------------------------------------------


def _ordered_rings(ring_system, mol) -> list[tuple[int, ...]]:
    """The system's rings as atom cycles in ring order (RDKit's own), since
    `RingSystem.rings` holds unordered sets."""
    wanted = {frozenset(r) for r in ring_system.rings}
    cycles = [tuple(r) for r in mol.GetRingInfo().AtomRings() if frozenset(r) in wanted]
    if len({frozenset(c) for c in cycles}) != len(wanted):
        raise Unsupported("the ring system's rings are not all simple ring cycles")
    return cycles


def name_fusion_parents(ring_system, candidate, mol) -> list:
    """NamedParents for the system by general fusion, one per numbering that
    survives P-25.3.3, each carrying its hydro and indicated-hydrogen block
    (P-31.1.4.2.4, planned by `indicated_hydrogen_p58.plan_hydrogens` on
    the actual structure). Raises `Unsupported` outside the class."""
    import dataclasses  # noqa: F401

    from openchem.vendor.iupac_namer.ring_naming.indicated_hydrogen_p58 import (
        _HYDRO_MULT, _hydrogen_prefix, _pi_capable, plan_hydrogens,
    )
    from openchem.vendor.iupac_namer.types import NamedParent

    for idx in ring_system.atom_indices:
        atom = mol.GetAtomWithIdx(idx)
        if atom.GetFormalCharge() or atom.GetNumRadicalElectrons() or atom.GetIsotope():
            raise Unsupported("a charged, radical or labelled ring atom")
    cycles = _ordered_rings(ring_system, mol)
    fusion = name_fusion(mol, cycles)
    whole_retained = "[" not in fusion.text and fusion.text in POLYCYCLES
    if whole_retained and fusion.text in _TRADITIONAL:
        # The ring table carries the traditional numbering the book keeps
        # for these (anthracene, acridine, purine ...); this module computes
        # the fusion-rule numbering, which is not theirs.
        raise Unsupported("the whole system is a retained parent with a traditional numbering")
    ring = frozenset(ring_system.atom_indices)
    planned = []
    for numbering in fusion.numberings:
        locant_of = numbering.atom_to_locant
        plan = plan_hydrogens(mol, ring, (), locant_of)
        if plan is None or plan.added:
            raise Unsupported("the ring hydrogens cannot be described (P-58.2)")
        planned.append((numbering, plan))
    exocyclic = any(
        bond.GetBondTypeAsDouble() >= 2.0
        and (bond.GetBeginAtomIdx() in ring) != (bond.GetEndAtomIdx() in ring)
        for idx in ring for bond in mol.GetAtomWithIdx(idx).GetBonds()
    )
    if not exocyclic and len(planned) > 1:
        # P-31.1.4.2.4: among ring numberings the system allows, indicated
        # hydrogen takes the lowest locants BEFORE principal characteristic
        # groups -- "1H-cyclopenta[8]annulene", never "3H-". A ring C=X is
        # left to the P-58.2 suffix route, which places the hydrogens itself.
        def ih_key(item):
            numbering, plan = item
            return tuple(sorted(numbering.atom_to_locant[a] for a in plan.indicated))
        low = min(ih_key(item) for item in planned)
        planned = [item for item in planned if ih_key(item) == low]
    # One NamedParent per distinct NAME, carrying every numbering that gives
    # it: `name_ring_system` keeps one parent per name, so two mirror
    # numberings emitted separately lost one to the atom order, and
    # "2-chloro...thiepin-10-ol" vs "8-chloro...-11-ol" was decided by how the
    # SMILES was written (the permutation test caught it). Carried together,
    # the substitutive plans choose between them by P-31.1.4.
    by_name: dict[str, list] = {}
    for numbering, plan in planned:
        locant_of = numbering.atom_to_locant
        if plan.hydro and len(plan.hydro) not in _HYDRO_MULT:
            raise Unsupported("an odd number of hydro positions")
        labels = lambda atoms: [str(loc) for loc in sorted(locant_of[a] for a in atoms)]  # noqa: E731
        complete = not (_pi_capable(mol, ring) - plan.indicated - plan.hydro)
        block = _hydrogen_prefix(labels(plan.indicated), labels(plan.hydro), fusion.text,
                                 complete=complete)
        by_name.setdefault(block + fusion.text, []).append(numbering)
    return [
        NamedParent(
            candidate=candidate,
            name=name,
            stem=name[:-1] if name.endswith("e") else name,
            alkyl_stem=None,
            # A whole retained polycycle is its retained name ("4H-quinolizine");
            # a constructed one is a fusion name.
            naming_method="retained" if whole_retained else "fusion",
            indicated_hydrogen=None,
            numbering_options=tuple(numberings),
            source="fusion_general",
        )
        for name, numberings in by_name.items()
    ]
