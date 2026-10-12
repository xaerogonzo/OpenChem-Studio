"""A docked ligand's ions are its real ions, not the charges its drawing carries.

`pose_analysis._ligand_features` used to call every atom with a formal charge a cation or an anion, so a nitro
group -- a NEUTRAL group, drawn `[N+](=O)[O-]` -- fed a ligand cation into cation-pi and a ligand cation AND anion
into salt bridges. Measured on nitrobenzene before the fix, with an Asp carboxylate 3.2 A from the nitro nitrogen, a
Lys NZ 2.8 A from the nitro oxygen and a Phe ring 4.5 A over the nitro nitrogen: two salt bridges and a cation-pi,
for a molecule with no net charge anywhere. Every check here goes through `analyze_pose`, the function the docking
service calls, so it is the stored pose metadata that is asserted, not a helper.
"""
from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import interaction_analysis, pose_analysis
from openchem.chem.pose_analysis import analyze_pose, receptor_atoms_from_structure

_PHE_RING = [
    ("CG", -1.4, 0.0), ("CD1", -0.7, 1.2), ("CD2", -0.7, -1.2),
    ("CE1", 0.7, 1.2), ("CE2", 0.7, -1.2), ("CZ", 1.4, 0.0),
]


def _pdb(rows) -> str:
    """Column-exact PDB (atom name in columns 13-16, residue name in 18-20)."""
    lines = [
        f"ATOM  {index:5d}  {name:<3s} {residue:>3s} A{number:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {element:>2s}"
        for index, (name, residue, number, x, y, z, element) in enumerate(rows, 1)
    ]
    return "\n".join(lines) + "\nEND\n"


def _pose(smiles: str) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=3)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _receptor_around_charges(mol: Chem.Mol):
    """For EVERY charged ligand atom: a Lys NZ, an Asp carboxylate and a Phe ring close by.

    So whichever atoms the analysis reads as ions finds a partner of the opposite sign (a salt bridge) or a ring
    (cation-pi), and an atom wrongly read as an ion cannot hide for want of a neighbour.
    """
    conformer = mol.GetConformer()
    rows, number = [], 0
    for atom in mol.GetAtoms():
        if not atom.GetFormalCharge():
            continue
        p = conformer.GetAtomPosition(atom.GetIdx())
        number += 1
        rows.append(("NZ", "LYS", number, p.x + 2.8, p.y, p.z, "N"))
        number += 1
        rows += [("OD1", "ASP", number, p.x - 3.0, p.y, p.z, "O"),
                 ("OD2", "ASP", number, p.x - 3.0, p.y, p.z + 1.0, "O")]
        number += 1
        rows += [(name, "PHE", number, p.x + x, p.y + y, p.z + 4.5, "C") for name, x, y in _PHE_RING]
    assert rows, "the ligand must carry a formal charge or this tests nothing"
    return receptor_atoms_from_structure(_pdb(rows), "pdb")


def _analyse(smiles: str) -> dict:
    mol = _pose(smiles)
    return analyze_pose(Chem.MolToMolBlock(mol), _receptor_around_charges(mol))


@pytest.mark.parametrize(
    "smiles",
    [
        "c1ccccc1[N+](=O)[O-]",        # nitro
        "[O-][n+]1ccccc1",             # N-oxide
        "C[S+](C)[O-]",                # sulfoxide drawn with charges
        "CN=[N+]=[N-]",                # azide
        "C[N+](C)(C)[O-]",             # aliphatic N-oxide
        "O=[N+]([O-])c1ccc(cc1)[N+](=O)[O-]",  # two nitro groups
    ],
)
def test_a_charge_separated_neutral_group_is_neither_a_cation_nor_an_anion(smiles):
    found = _analyse(smiles)

    assert found["salt_bridges"] == [], "no net charge in the ligand, so nothing to bridge a receptor ion"
    # The other direction (a receptor Lys over the LIGAND's ring) is real and stays; the probe Lys sits near it.
    assert [e for e in found["cation_pi"] if e["cation"] == "ligand"] == [], (
        "a ligand cation over a receptor ring needs a ligand cation"
    )


def test_a_real_cation_and_a_real_anion_are_still_found():
    """The control that keeps the rule honest: an ammonium and a carboxylate, each a cluster of one."""
    cation = _analyse("c1ccccc1C[N+](C)(C)C")
    anion = _analyse("c1ccccc1C(=O)[O-]")

    assert {e["charge"] for e in cation["salt_bridges"]} == {"ligand +"}
    assert [e for e in cation["cation_pi"] if e["cation"] == "ligand"], "the ammonium sits over the Phe ring"
    assert {e["charge"] for e in anion["salt_bridges"]} == {"ligand -"}


def test_a_real_ion_beside_a_nitro_group_keeps_its_own_site_only():
    """4-nitrobenzoate: the carboxylate is an anion, the nitro group is nothing."""
    found = _analyse("[O-]C(=O)c1ccc(cc1)[N+](=O)[O-]")

    assert found["salt_bridges"], "the carboxylate is a real anion next to a Lys"
    assert {e["charge"] for e in found["salt_bridges"]} == {"ligand -"}, "and only that: no 'ligand +' from the nitro N"
    assert [e for e in found["cation_pi"] if e["cation"] == "ligand"] == []


def test_nitrate_keeps_the_sign_it_nets_to():
    """A cluster that does not cancel keeps the atoms of its net sign (nitrate nets -1): an anion, never a cation."""
    found = _analyse("O=[N+]([O-])[O-]")

    assert {e["charge"] for e in found["salt_bridges"]} == {"ligand -"}
    assert [e for e in found["cation_pi"] if e["cation"] == "ligand"] == []


def test_the_rule_holds_when_the_pose_does_not_sanitise():
    """`_ligand_features` parses without sanitising and goes on when sanitising fails. The bonds are still there, so
    the cluster rule must not depend on a sanitised molecule."""
    rw = Chem.RWMol(Chem.AddHs(Chem.MolFromSmiles("C[N+](=O)[O-]")))
    carbon = 0
    for _ in range(2):  # push the methyl carbon to five bonds: valence 5 cannot be sanitised
        hydrogen = rw.AddAtom(Chem.Atom(1))
        rw.AddBond(carbon, hydrogen, Chem.BondType.SINGLE)
    mol = rw.GetMol()
    with pytest.raises(Exception):
        Chem.SanitizeMol(Chem.Mol(mol))
    conformer = Chem.Conformer(mol.GetNumAtoms())
    # Any geometry will do: a nitro-N at the origin, everything else spread out so the molblock is valid.
    for index in range(mol.GetNumAtoms()):
        conformer.SetAtomPosition(index, (1.4 * index, 0.3 * (index % 2), 0.2 * (index % 3)))
    mol.AddConformer(conformer, assignId=True)

    found = analyze_pose(Chem.MolToMolBlock(mol), _receptor_around_charges(mol))

    assert found["salt_bridges"] == []
    assert [e for e in found["cation_pi"] if e["cation"] == "ligand"] == []


def test_the_two_analysers_share_one_rule():
    """Intramolecular and receptor-ligand analysis must not hold two copies of what counts as an ion."""
    assert interaction_analysis._formal_charge_sites is pose_analysis._formal_charge_sites
