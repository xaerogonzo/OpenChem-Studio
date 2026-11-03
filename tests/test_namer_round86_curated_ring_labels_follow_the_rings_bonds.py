"""Naming round 86 (D-380): the curated ring table's labels follow the ring's bonds.

Rounds 82 and 85 each found a curated entry whose `atom_locants` were wrong or incomplete (the benzodithiete's four missing atoms; the methano-bridged azepinoquinoxaline's 11 of 16, with its two
nitrogens swapped), and neither could be seen by chlorine-probing the entry: a probe on a symmetric pair gives the same molecule either way. The rule that does see it is structural, and needs no
OPSIN: in a ring numbering, two consecutive locants (`n` and `n+1`, or `n` and `na`) are bonded atoms, or are joined through one atom between them (the fusion atom `3a`, which an entry may leave unlabelled).

Naming round 87 read the exceptions against the book (pages in the comments below; two systems and corrin are not drawn in it) and probed every pair of labelled positions of 303 neutral entries against OPSIN (`tools/naming_ring_table_vs_opsin.py`: 8,585 pairs, no disagreement).

The limit: this finds a label placed away from where it belongs, not a swap of two atoms that both touch the same labelled atom (round 85's N1 and N4 both touch a carbon the entry labels). A stricter
rule, that the joining atom be unlabelled, flags the steroid skeleton's 10 and 11 (they meet through the labelled C9), which is the book's numbering, so it is not used; the swapped pair is
covered by `test_namer_round85_*` for that entry.

Of the 371 entries, 3,104 consecutive pairs were checked; the audit found one more mislabel (the tetracenetrione had its C1 and C3 carbonyls swapped against its C12a: D-380, which no name showed,
since the two carbonyls are symmetric) and 17 pairs that are the book's own numbering and not a mislabel, listed below with the reason. Any other pair fails this test.
"""

from __future__ import annotations

import re

from rdkit import Chem, RDLogger

from openchem.vendor.iupac_namer.data_loader import _RING_CURATED_SMILES

RDLogger.DisableLog("rdApp.*")

#: entry name -> the consecutive pairs whose atoms are neither bonded nor joined by one atom, because that is how the system is numbered.
#: Naming round 87 read each against the IUPAC 2013 recommendations (BlueBookV2.pdf, the PDF's own page numbers):
CONVENTIONS = {
    # p. 197, Table 2.7 (11): "anthracene (special numbering)": 1-4, 4a, 10, 10a, 5-8, 8a, 9, 9a
    "anthracene": {("4a", "5")},
    # p. 202, Table 2.8 (4): "acridine (special numbering)": 4a, N10, 10a, 5; p. 204 (22): xanthene, thioxanthene, selenoxanthene, telluroxanthene "special numbering": 4a, 10, 10a, 5
    "acridine": {("4a", "5")},
    "xanthene": {("4a", "5")},
    "thioxanthene": {("4a", "5")},
    "9H-xanthen-9-one": {("4a", "5")},
    "9H-thioxanthen-9-one": {("4a", "5")},
    # p. 196, Table 2.7 (5): perylene's interior atoms are 3a1 and 6b1; the table uses the CAS-style letters 12c and 12d (the declared deviation KD-constructor-interior)
    "perylene": {("12c", "12d")},
    # p. 970, P-101.3.1: the morphinan numbering is an established pattern (aromatic 1-4, junctions 11 and 12, C13, then 5-8, 14, 9, 10, 15, 16, N17): C4 meets C12, C5 is on C13
    "morphinan": {("4", "5")},
    # p. 172, Table 2.6: adamantane's C9 bridges C1 and C5 and C10 bridges C3 and C7, so they are not bonded
    "adamantane": {("9", "10")},
    # NOT PRINTED in the book (p. 967 only lists corrin among the fundamental parent structures; its reference list cites the 1973 IUBMB corrinoid recommendations); kept as the table has it, agreeing with OPSIN's pair probes
    "corrin": {("21", "22"), ("22", "23"), ("23", "24")},
    # p. 253, P-25.4.3.4.1: "Bridge atoms are numbered continuing from the highest locant of the fused ring system"
    "1,2,3,4,5,6-hexahydro-2,6-methano-3-benzazocine": {("10a", "11")},
    "7,8,9,10-tetrahydro-6H-6,10-methanoazepino[4,5-g]quinoxaline": {("11a", "12")},
    "1,4,5,6,7,8,9,10-octahydro-2H-3,7-methano[1]azacycloundecino[5,4-b]indole": {("14b", "15")},
    "2,3,4,5,6,7,8,9-octahydro-1H-2,6-methanoazecino[5,4-b]indole": {("9a", "10"), ("13b", "14")},
    "5,6,6a,7,8,9,10,12,13-nonahydro-6,9-methanopyrido[1',2':1,2]azepino[4,5-b]indole": {("13", "14")},
    # NOT PRINTED in the book (the numbering of these two large systems is a fusion-nomenclature result, not a drawn example); they agree with OPSIN's pair probes
    "1,12-dihydro-14H-pyrano[3',4':6,7]indolizino[1,2-b]quinoline-3,14(4H)-dione": {("5", "6")},
    "3a,4,5,5a,6,11,12,13-octahydro-1H-indolizino[8,1-cd]carbazole": {("10", "11")},
}


def _key(label) -> tuple[int, str] | None:
    m = re.match(r"^(\d+)([a-z]*)$", str(label))
    return (int(m.group(1)), m.group(2)) if m else None


def _unbonded_consecutive_pairs(smiles: str, atom_locants: dict) -> set[tuple[str, str]]:
    mol = Chem.MolFromSmiles(smiles)
    keys = {}
    for atom, label in atom_locants.items():
        k = _key(label)
        if k is not None and atom < mol.GetNumAtoms():
            keys[k] = atom
    ordered = sorted(keys)
    out = set()
    for k in ordered:
        later = [x for x in ordered if x > k]
        if not later:
            continue
        nx = later[0]
        consecutive = (nx[0] == k[0] and nx[1] != "") or (nx[0] == k[0] + 1 and nx[1] == "")
        if not consecutive:
            continue
        a1, a2 = keys[k], keys[nx]
        if mol.GetBondBetweenAtoms(a1, a2) is not None:
            continue
        shared = {n.GetIdx() for n in mol.GetAtomWithIdx(a1).GetNeighbors()} & {n.GetIdx() for n in mol.GetAtomWithIdx(a2).GetNeighbors()}
        if not shared:
            out.add((f"{k[0]}{k[1]}", f"{nx[0]}{nx[1]}"))
    return out


def test_consecutive_locants_are_bonded_or_joined_by_one_atom():
    wrong = {}
    for smiles, entry in _RING_CURATED_SMILES.items():
        labels = entry.get("atom_locants")
        if not labels or Chem.MolFromSmiles(smiles) is None:
            continue
        found = _unbonded_consecutive_pairs(smiles, labels) - CONVENTIONS.get(entry["name"], set())
        if found:
            wrong[entry["name"]] = sorted(found)
    assert not wrong, wrong


def test_the_conventions_are_all_still_needed():
    """An exception that is no longer one hides the next mislabel behind it."""
    stale = {}
    for smiles, entry in _RING_CURATED_SMILES.items():
        allowed = CONVENTIONS.get(entry["name"])
        labels = entry.get("atom_locants")
        if not allowed or not labels:
            continue
        gone = allowed - _unbonded_consecutive_pairs(smiles, labels)
        if gone:
            stale[entry["name"]] = sorted(gone)
    assert not stale, stale


def test_the_tetracenetrione_has_c1_beside_c12a():
    smiles = "O=C1CC(=O)C2C=C3C(=O)c4ccccc4CC3CC2C1"
    labels = _RING_CURATED_SMILES[smiles]["atom_locants"]
    by_label = {str(v): k for k, v in labels.items()}
    mol = Chem.MolFromSmiles(smiles)
    for a, b in (("12a", "1"), ("1", "2"), ("2", "3"), ("3", "4"), ("4", "4a")):
        assert mol.GetBondBetweenAtoms(by_label[a], by_label[b]) is not None, (a, b)
