"""The structural families of `PREREGISTRATION.md` section 5, as a function of a structure and nothing else.

Fixed BEFORE any energetic-materials label has been compared with any prediction. A family is read from the
neutral molecule alone (no label, no source, no method output), by the FIRST rule that applies, so that the strata a
result is reported in cannot be chosen after the result is seen. The cage flag is the one overlapping property: it is
reported beside the family, never instead of it.

This module reads no data and scores nothing. It exists so that the family of every compound is a property of its
structure that a test can hold, the way `benchmarks/mp_bp` fixed its own thirteen.
"""

from __future__ import annotations

from rdkit import Chem

#: (family, SMARTS). First match wins. Order encodes the preregistered precedence: a molecule that carries both an
#: N-nitro and a C-nitro group (tetryl, TNAZ) is a nitramine, because the N-NO2 bond is the one that decides its
#: thermal and enthalpy behaviour in the literature this benchmark reads.
FAMILY_RULES: tuple[tuple[str, str], ...] = (
    ("nitrate_ester", "[OX2][N+](=O)[O-]"),
    ("nitramine", "[#7;!$([N+](=O)[O-])][N+](=O)[O-]"),
    ("nitroaromatic", "[c][N+](=O)[O-]"),
    ("nitroaliphatic", "[#6;!c][N+](=O)[O-]"),
    ("azide", "[N-]=[N+]=[N]"),
    ("peroxide", "[OX2][OX2]"),
)

#: Families that need more than one atom pattern, or none.
N_RICH_HETEROCYCLE = "n_rich_heterocycle"
HALOGENATED = "halogenated"
OTHER_ORGANIC = "other_organic"
NOT_ORGANIC = "not_organic"

FAMILIES = tuple(name for name, _ in FAMILY_RULES) + (N_RICH_HETEROCYCLE, HALOGENATED, OTHER_ORGANIC, NOT_ORGANIC)

_COMPILED = tuple((name, Chem.MolFromSmarts(smarts)) for name, smarts in FAMILY_RULES)
_HALOGEN = Chem.MolFromSmarts("[F,Cl,Br,I]")
#: The elements an organic molecule of this benchmark may hold. A metal makes it organometallic or a metal salt,
#: which is a separate stratum outside the primary gate.
ORGANIC_ELEMENTS = frozenset({"H", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Br", "I"})


def _is_organic(mol: Chem.Mol) -> bool:
    """Contains carbon and nothing outside `ORGANIC_ELEMENTS`.

    NOT Phase A's rule (a carbon with at least one C-H or C-C bond): that rule drops NTO, nitroguanidine, 5-aminotetrazole
    and 3,6-diaminotetrazine, whose carbons bond only to nitrogen, oxygen and each other's ring partners. An energetic
    benchmark that inherited it would lose exactly the nitrogen-rich compounds it exists to describe.
    """
    symbols = {a.GetSymbol() for a in mol.GetAtoms()}
    return "C" in symbols and symbols <= ORGANIC_ELEMENTS


def _n_rich_ring(mol: Chem.Mol) -> bool:
    """A ring of the molecule holds two or more nitrogens (azoles, azines, furazans, tetrazines)."""
    for ring in mol.GetRingInfo().AtomRings():
        if sum(1 for i in ring if mol.GetAtomWithIdx(i).GetSymbol() == "N") >= 2:
            return True
    return False


def is_cage(mol: Chem.Mol) -> bool:
    """Some atom belongs to three or more rings (cubane, adamantane).

    Flat fused systems (naphthalene, anthracene) and simple bridged bicycles (norbornane) have no atom in more than two
    rings and are not cages. The flag marks the polycyclic skeletons whose crystal density the group-additivity
    literature treats as an exception; it uses RDKit's symmetrized smallest set of smallest rings.
    """
    ring_info = mol.GetRingInfo()
    return any(ring_info.NumAtomRings(i) >= 3 for i in range(mol.GetNumAtoms()))


def _read(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"cannot read {smiles!r} as a structure")
    return mol


def family(smiles: str) -> str:
    """The family of a neutral structure, by the first rule that applies. Raises ValueError for unreadable input."""
    mol = _read(smiles)
    if not _is_organic(mol):
        return NOT_ORGANIC
    for name, pattern in _COMPILED:
        if mol.HasSubstructMatch(pattern):
            return name
    if _n_rich_ring(mol):
        return N_RICH_HETEROCYCLE
    if mol.HasSubstructMatch(_HALOGEN):
        return HALOGENATED
    return OTHER_ORGANIC


def cage_flag(smiles: str) -> bool:
    return is_cage(_read(smiles))
