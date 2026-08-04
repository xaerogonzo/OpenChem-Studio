"""What is actually IN a structure file: chains, sequences, ligands, waters.

WHY THIS EXISTS. A deposited structure is very often not just the target.
GPCR structures in particular are routinely crystallised with a fusion
partner spliced into a loop (BRIL, T4 lysozyme) and a nanobody or Fab to
lock a conformation, and a nucleotide-free G protein is three more chains
again. All of it lands in one file. Until now the app imported that file
whole, showed no chain information anywhere in the UI (measured: zero
occurrences of "chain" under `ui/`), and handed the entire assembly to
Vina.

Measured on the bundled catalogue: 32 of 49 curated receptors are
multi-polymer. 3SN6 is the sharp case -- its largest chain is a T4
lysozyme FUSED to the receptor and its second largest is Gs-alpha, so
neither "the biggest chain" nor "chain A" finds the target. That is also
why `ChainSummary` carries the sequence: it is the only thing here that
lets a chain be identified, since the depositor's own naming lives in
mmCIF entity records this deliberately does not read (below).

DERIVED FROM ATOMS, NOT FROM mmCIF ENTITY RECORDS. `_entity` and
`_struct_asym` are richer -- they carry the depositor's own description,
which is how you would know a chain is "T4 lysozyme" rather than "162
residues" -- but they exist only in mmCIF, and half this app's structures
arrive as PDB. Classifying from the residues themselves works on both,
and reuses `pose_analysis`'s parser and its residue vocabulary rather
than starting a second, subtly different one. The cost is honest and
stated in the UI: chains are described by size and sequence, not named.

NOTHING HERE STRIPS ANYTHING. The summary is deliberately built with
water and cofactor stripping OFF, because its whole job is to report what
the file contains -- including the parts docking preparation would later
remove. A summary that quietly agreed with the preparation would be
unable to tell you what you were about to lose.
"""

from __future__ import annotations

from dataclasses import dataclass

from openchem.chem.pose_analysis import (
    STANDARD_RECEPTOR_RESIDUES,
    WATER_RESIDUE_NAMES,
    receptor_atoms_from_structure,
)

#: Three-letter to one-letter, for the 20 standard residues plus the
#: alternate-protonation names `STANDARD_RECEPTOR_RESIDUES` already
#: tolerates. Anything else in a polymer becomes "X" rather than being
#: dropped, so the sequence stays positionally aligned with the residues.
_ONE_LETTER = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    "HID": "H", "HIE": "H", "HIP": "H", "HSD": "H", "HSE": "H", "HSP": "H",
    "CYX": "C", "CYM": "C", "ASH": "D", "GLH": "E", "LYN": "K",
}

#: Below this many standard residues, a chain is not treated as a polymer.
#: A lone amino acid in its own chain is a LIGAND -- glycine and glutamate
#: are neurotransmitters, and several receptors in the bundled catalogue
#: are solved with one bound. Calling that a "1-residue protein chain"
#: would be both wrong and unhelpful.
MIN_POLYMER_RESIDUES = 2


@dataclass(frozen=True)
class ChainSummary:
    """One chain, classified by what its residues actually are.

    A chain is not one kind of thing: in PDB files the protein, its
    ordered waters and its bound ligands routinely share a chain id. So
    the counts are all reported side by side and `kind` names only the
    DOMINANT component, for sorting and for a one-line label.
    """

    chain_id: str
    polymer_residue_count: int
    sequence: str
    ligand_codes: tuple[str, ...]
    water_count: int
    atom_count: int

    @property
    def kind(self) -> str:
        if self.polymer_residue_count >= MIN_POLYMER_RESIDUES:
            return "polymer"
        if self.ligand_codes:
            return "ligand"
        if self.water_count:
            return "water"
        return "empty"

    def describe(self) -> str:
        """A one-line label, sized to a table cell."""
        if self.kind == "polymer":
            parts = [f"{self.polymer_residue_count} residues"]
            if self.ligand_codes:
                parts.append(f"+ {', '.join(self.ligand_codes)}")
            if self.water_count:
                parts.append(f"+ {self.water_count} waters")
            return " ".join(parts)
        if self.kind == "ligand":
            return ", ".join(self.ligand_codes)
        if self.kind == "water":
            return f"{self.water_count} waters"
        return "empty"


@dataclass(frozen=True)
class StructureSummary:
    """Every chain in a structure, largest polymer first.

    Ordered by polymer size rather than by chain id because the question
    a user is answering is "which of these is my target", and the target
    is very rarely the shortest chain.
    """

    chains: tuple[ChainSummary, ...]

    @property
    def polymer_chains(self) -> tuple[ChainSummary, ...]:
        return tuple(c for c in self.chains if c.kind == "polymer")

    @property
    def total_atoms(self) -> int:
        return sum(c.atom_count for c in self.chains)

    def ligand_codes(self) -> tuple[str, ...]:
        """Every distinct non-water heteroatom component, any chain."""
        seen: dict[str, None] = {}
        for chain in self.chains:
            for code in chain.ligand_codes:
                seen[code] = None
        return tuple(seen)

    def looks_like_a_complex(self) -> bool:
        """More than one polymer chain of real size.

        The signal that a user should look before docking: a fusion
        partner, a nanobody or a G protein all show up this way. Says
        nothing about WHICH chain is the target -- that needs the
        depositor's own annotation, which is not available from atoms.
        """
        return len(self.polymer_chains) > 1


def summarize_structure(
    structure_text: str, source_format: str
) -> StructureSummary:
    """Group a structure's atoms into chains and classify each one."""
    atoms = receptor_atoms_from_structure(
        structure_text,
        source_format,
        # See the module docstring: the summary reports the file, not
        # what preparation would leave of it.
        {"strip_waters": False, "strip_cofactors": False},
    )

    # Residue identity is (chain, name, number) -- the same key
    # `pose_analysis._residues` uses, and for the same reason: without the
    # chain, every subunit of a multimer collapses onto the first.
    by_chain: dict[str, dict[tuple[str, int], str]] = {}
    atom_counts: dict[str, int] = {}
    for atom in atoms:
        chain = atom.chain or "?"
        atom_counts[chain] = atom_counts.get(chain, 0) + 1
        residues = by_chain.setdefault(chain, {})
        residues[(atom.residue_name, atom.residue_number)] = atom.residue_name

    chains = []
    for chain_id, residues in by_chain.items():
        polymer, ligands, waters = [], {}, 0
        # Sorted by residue number so the sequence reads in order; the
        # atom stream is not guaranteed to.
        for (name, number) in sorted(residues, key=lambda key: key[1]):
            upper = name.strip().upper()
            if upper in WATER_RESIDUE_NAMES:
                waters += 1
            elif upper in STANDARD_RECEPTOR_RESIDUES:
                polymer.append(upper)
            else:
                ligands[upper] = None
        # Too few standard residues to be a polymer means they are not a
        # short protein, they are FREE AMINO ACIDS -- glycine and
        # glutamate are neurotransmitters, and several receptors in the
        # bundled catalogue are solved with one bound. Reclassify them
        # rather than leaving them below the threshold: an earlier version
        # left them counted as polymer, so a chain holding one glutamate
        # matched no branch at all and reported as "empty", losing the
        # very content this summary exists to show.
        if len(polymer) < MIN_POLYMER_RESIDUES:
            for name in polymer:
                ligands.setdefault(name, None)
            polymer = []

        chains.append(
            ChainSummary(
                chain_id=chain_id,
                polymer_residue_count=len(polymer),
                sequence="".join(_ONE_LETTER.get(name, "X") for name in polymer),
                ligand_codes=tuple(ligands),
                water_count=waters,
                atom_count=atom_counts[chain_id],
            )
        )

    # A short polymer chain still outranks a ligand-only one, so sort on
    # the kind first and the size second.
    order = {"polymer": 0, "ligand": 1, "water": 2, "empty": 3}
    chains.sort(key=lambda c: (order[c.kind], -c.polymer_residue_count, -c.atom_count))
    return StructureSummary(chains=tuple(chains))
