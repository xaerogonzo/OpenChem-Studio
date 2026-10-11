"""The hydrogen-bond site table: which atoms are donors and which are acceptors, optionally at a pH.

`H-Bond Donors` and `H-Bond Acceptors` in Properties are counts, and `H-Bond Donors/Acceptors vs pH` is a
curve of counts. None of them says WHICH atoms. This lists them, and with the major microspecies at a pH
it says which atoms change role when the molecule ionises (a carboxylic acid's hydroxyl is a donor as
drawn and not at pH 7.4; its carboxylate oxygens are acceptors).

**ONE DEFINITION, THE COUNT'S.** The counts are RDKit's `CalcNumHBD` and `CalcNumHBA`, which give a
number and no atoms. The same two definitions are written out below as SMARTS patterns, and
`tests/test_hbond_sites.py` holds them to RDKit's count over a corpus (in the drawing's form and with
explicit hydrogens), so the table and the count cannot put two definitions of "donor" on one screen. The
donor pattern is RDKit's own `Lipinski.HDonorSmarts`; the acceptor pattern is its `HAcceptorSmarts` with
one change the corpus forced: an aromatic nitrogen is an acceptor only when it has two connections
(pyridine-type), not three (pyrrole-type, and every N-methyl of caffeine). The module-level pattern counts
all of those, 6 for caffeine against RDKit's own 3.

**ATOMS, NOT HYDROGENS, AND NOT STRENGTH.** The definitions are conventions about which atoms CAN take part:
an NH2 is one donor atom, as it is in the count; an amide nitrogen is a donor and not an acceptor; nothing
here says how strong a bond would be or whether geometry allows it (`Interaction Analysis` finds
intramolecular contacts in a conformer).
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem

from openchem.chem.calculator_options import DEFAULT_PH
from openchem.chem.components import drawing_label
from openchem.domain.common import Provenance
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis

#: RDKit's donor definition (`Lipinski.HDonorSmarts`): an N with a hydrogen and valence three, an N+ with
#: valence four and a hydrogen, an O or S with one hydrogen and no charge, an aromatic nH.
_DONOR = Chem.MolFromSmarts(
    "[$([N;!H0;v3]),$([N;!H0;+;v4]),$([O,S;H1;+0]),$([n;H1;+0])]"
)

#: RDKit's acceptor definition (`Lipinski.HAcceptorSmarts`) with the aromatic nitrogen restricted to two
#: connections (see the module docstring for why): a hydroxyl or thiol on a carbon that is not itself
#: double-bonded to O, N, P or S; a two-valent O or S with no hydrogen; an oxyanion; a three-valent N that
#: is not conjugated to such a double bond; a pyridine-type n; an aromatic o or s.
_ACCEPTOR = Chem.MolFromSmarts(
    "[$([O,S;H1;v2]-[!$(*=[O,N,P,S])]),$([O,S;H0;v2]),$([O,S;-]),"
    "$([N;v3;!$(N-*=!@[O,N,P,S])]),$([nX2,o,s;+0])]"
)

#: The role of an atom that gives a hydrogen to a bond.
DONOR = "donor"
#: The role of an atom that takes one.
ACCEPTOR = "acceptor"
#: The role of an atom that can do both (an alcohol oxygen, a primary amine).
BOTH = "donor and acceptor"


@dataclass(frozen=True)
class Site:
    """One atom that can take part in a hydrogen bond."""

    atom: int
    donor: bool
    acceptor: bool
    #: Hydrogens on the atom, which is what a donor atom offers (an NH2 is one donor atom with two).
    hydrogens: int

    @property
    def role(self) -> str:
        return BOTH if self.donor and self.acceptor else (DONOR if self.donor else ACCEPTOR)


#: The atom property that carries an atom's own index through the removal of explicit hydrogens.
_INDEX = "_oc_hbond_index"


def find_sites(mol: Chem.Mol) -> dict[int, Site]:
    """Every donor and acceptor atom of `mol`, by atom index.

    Matched on a copy WITHOUT explicit hydrogens, the form the counts are taken on. It matters: the
    acceptor pattern asks that a hydroxyl be bonded to something that is not double-bonded to O, N, P
    or S, and an explicit hydrogen is exactly such a neighbour, so an acid's OH would read as an
    acceptor on a conformer and not on the drawing (measured: acetic acid 2 acceptors against RDKit's
    1). The indices are carried back through an atom property, so the answer is in `mol`'s own numbering
    whichever form it was handed.
    """
    marked = Chem.Mol(mol)
    for atom in marked.GetAtoms():
        atom.SetIntProp(_INDEX, atom.GetIdx())
    bare = Chem.RemoveHs(marked, sanitize=False)
    bare.UpdatePropertyCache(strict=False)
    Chem.FastFindRings(bare)

    def originals(pattern) -> set[int]:
        return {bare.GetAtomWithIdx(match[0]).GetIntProp(_INDEX) for match in bare.GetSubstructMatches(pattern)}

    donors, acceptors = originals(_DONOR), originals(_ACCEPTOR)
    return {
        index: Site(
            atom=index,
            donor=index in donors,
            acceptor=index in acceptors,
            hydrogens=mol.GetAtomWithIdx(index).GetTotalNumHs(includeNeighbors=True),
        )
        for index in sorted(donors | acceptors)
    }


def counts(sites: dict[int, Site]) -> tuple[int, int]:
    """`(donors, acceptors)`: atoms, not hydrogens."""
    return (
        sum(1 for site in sites.values() if site.donor),
        sum(1 for site in sites.values() if site.acceptor),
    )


def sites_at_ph(mol: Chem.Mol, ph: float) -> dict[int, Site]:
    """The sites of the major microspecies at `ph`, keyed by the DRAWING's atom indices.

    The microspecies is built from the drawing and its atoms are not numbered like it, so the heavy-atom
    correspondence `pka_providers` already establishes is what carries each role back to the atom it is
    about. Raises `InvalidStructureError` where that cannot be established (rather than guessing: a role on
    the wrong atom is the defect this exists to prevent).
    """
    from openchem.chem.pka_providers import dominant_microspecies, heavy_correspondence

    species = dominant_microspecies(mol, ph).mol
    heavy, match = heavy_correspondence(mol, species)
    there = find_sites(species)
    carried: dict[int, Site] = {}
    for position, drawing_atom in enumerate(heavy):
        site = there.get(match[position])
        if site is not None:
            carried[drawing_atom] = Site(
                atom=drawing_atom, donor=site.donor, acceptor=site.acceptor, hydrogens=site.hydrogens
            )
    return carried


def _describe(site: Site | None) -> str:
    """`donor (2 H) and acceptor`, or `none` for an atom that is neither."""
    if site is None:
        return "none"
    parts = []
    if site.donor:
        parts.append(f"donor ({site.hydrogens} H)")
    if site.acceptor:
        parts.append("acceptor")
    return " and ".join(parts)


def compute_hbond_sites(mol: Chem.Mol, molecule_uuid: str, parameters: dict | None = None) -> ReportResult:
    """The "topology" category's hydrogen-bond site table: the counts, then one row per atom."""
    parameters = parameters or {}
    drawn = find_sites(mol)
    drawn_donors, drawn_acceptors = counts(drawn)
    ph: float | None = None
    at_ph: dict[int, Site] | None = None
    unavailable = ""
    if parameters.get("major_microspecies"):
        try:
            ph = min(14.0, max(0.0, float(parameters.get("pH", DEFAULT_PH))))
        except (TypeError, ValueError):
            ph = DEFAULT_PH
        try:
            at_ph = sites_at_ph(mol, ph)
        except Exception as exc:  # noqa: BLE001 - the drawn table is still an answer; say the pH half is not
            unavailable = str(exc) or type(exc).__name__

    definition = (
        "RDKit's donor and acceptor definitions, the ones behind the H-Bond Donors and H-Bond Acceptors "
        "properties: they count ATOMS (an NH2 is one donor), and say which atoms CAN take part, not how "
        "strongly or in what geometry."
    )
    facts = [
        Fact(
            category=FactCategory.TOPOLOGY, label="Donors", value=float(drawn_donors),
            display_value=str(drawn_donors), source="RDKit", basis=Basis.DETERMINISTIC,
            limitations=(definition,),
        ),
        Fact(
            category=FactCategory.TOPOLOGY, label="Acceptors", value=float(drawn_acceptors),
            display_value=str(drawn_acceptors), source="RDKit", basis=Basis.DETERMINISTIC,
            limitations=(definition,),
        ),
    ]
    microspecies_note = (
        "The major microspecies at this pH from Dimorphite-DL, which gives ionisation states only (no "
        "tautomers); each atom is carried back to the drawing through the heavy-atom correspondence."
    )
    if at_ph is not None:
        donors_ph, acceptors_ph = counts(at_ph)
        facts.append(
            Fact(
                category=FactCategory.TOPOLOGY, label=f"Donors at pH {ph:g}", value=float(donors_ph),
                display_value=str(donors_ph), source="Dimorphite-DL", basis=Basis.HEURISTIC,
                limitations=(definition, microspecies_note),
            )
        )
        facts.append(
            Fact(
                category=FactCategory.TOPOLOGY, label=f"Acceptors at pH {ph:g}", value=float(acceptors_ph),
                display_value=str(acceptors_ph), source="Dimorphite-DL", basis=Basis.HEURISTIC,
                limitations=(definition, microspecies_note),
            )
        )
    elif ph is not None:
        facts.append(
            Fact(
                category=FactCategory.TOPOLOGY, label=f"At pH {ph:g}", value=None,
                display_value=f"not available: {unavailable}", source="Dimorphite-DL",
                basis=Basis.HEURISTIC,
                limitations=("The structure at this pH could not be built or matched to the drawing, so the "
                             "table below is the drawn structure's only.",),
            )
        )

    rows = sorted(set(drawn) | set(at_ph or {}))
    for atom_index in rows:
        before, after = drawn.get(atom_index), (at_ph or {}).get(atom_index)
        if at_ph is None:
            shown = _describe(before)
        else:
            same = _describe(before) == _describe(after)
            shown = (
                f"{_describe(before)} (unchanged at pH {ph:g})" if same
                else f"{_describe(after)} at pH {ph:g} (as drawn: {_describe(before)})"
            )
        facts.append(
            Fact(
                category=FactCategory.TOPOLOGY,
                label=drawing_label(mol.GetAtomWithIdx(atom_index)),
                value=None,
                display_value=shown,
                source="RDKit",
                basis=Basis.DETERMINISTIC if at_ph is None else Basis.HEURISTIC,
                limitations=(definition,)
                + (
                    ("An amide nitrogen is a donor and not an acceptor: its lone pair is delocalised "
                     "into the carbonyl.",)
                    if (before or after) and mol.GetAtomWithIdx(atom_index).GetSymbol() == "N"
                    else ()
                ),
            )
        )
    recorded = {"definition": "rdkit-hbd-hba", "major_microspecies": at_ph is not None}
    if ph is not None:
        recorded["pH"] = ph
    return ReportResult(
        molecule_uuid=molecule_uuid,
        report_id="hbond_sites",
        name="Hydrogen-Bond Sites",
        category="topology",
        facts=tuple(facts),
        provenance=Provenance(created_by="core", method="rdkit", parameters=recorded),
    )
