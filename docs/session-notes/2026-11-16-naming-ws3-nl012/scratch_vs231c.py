from rdkit import Chem

# Can we restore allene chirality?
smi = "CC=[C@]=C1CC[C@H](CC1)CC"
Chem.SetUseLegacyStereoPerception(False)
mol = Chem.MolFromSmiles(smi)
print("atom2 hybrid", mol.GetAtomWithIdx(2).GetHybridization(), "degree", mol.GetAtomWithIdx(2).GetDegree())
print("atom2 bonds", [(b.GetBondType(), b.GetOtherAtomIdx(2)) for b in mol.GetAtomWithIdx(2).GetBonds()])

a = mol.GetAtomWithIdx(2)
a.SetChiralTag(Chem.ChiralType.CHI_ALLENE)
print("after set CHI_ALLENE", a.GetChiralTag(), Chem.MolToSmiles(mol))
from rdkit.Chem import rdCIPLabeler
Chem.AssignStereochemistry(mol, cleanIt=False, force=True)
rdCIPLabeler.AssignCIPLabels(mol)
print("cip after CHI_ALLENE", {i: mol.GetAtomWithIdx(i).GetPropsAsDict().get("_CIPCode") for i in range(mol.GetNumAtoms()) if mol.GetAtomWithIdx(i).GetPropsAsDict().get("_CIPCode")})
for s in Chem.FindPotentialStereo(mol):
    print("pot", s.centeredOn, s.type, s.specified, s.descriptor, s.controllingAtoms)

# Try CHI_TETRAHEDRAL_CW on central carbon
mol2 = Chem.MolFromSmiles("CC=C=C1CCC(CC)CC1")
mol2.GetAtomWithIdx(2).SetChiralTag(Chem.ChiralType.CHI_TETRAHEDRAL_CW)
print("CW smiles", Chem.MolToSmiles(mol2), mol2.GetAtomWithIdx(2).GetChiralTag())
rdCIPLabeler.AssignCIPLabels(mol2)
print("cip CW", {i: mol2.GetAtomWithIdx(i).GetPropsAsDict().get("_CIPCode") for i in range(mol2.GetNumAtoms()) if mol2.GetAtomWithIdx(i).GetPropsAsDict().get("_CIPCode")})

# Parse CX
for extra in [
    "CC=[C@]=C1CCC(CC)CC1 |wU:2.1|",
    "C/C=C=C1CCC(CC)CC1",
    r"C/C=C=C1\CCC(CC)CC1",
    "C/C=C=C1CCC(CC)CC1 |c:1,2|",
]:
    m = Chem.MolFromSmiles(extra)
    print("try", extra, "->", Chem.MolToSmiles(m) if m else None, "chi2", m.GetAtomWithIdx(2).GetChiralTag() if m else None)
    if m:
        for s in Chem.FindPotentialStereo(m):
            if s.specified.name != "Unspecified":
                print("  specified", s.centeredOn, s.type, s.specified, s.descriptor)
