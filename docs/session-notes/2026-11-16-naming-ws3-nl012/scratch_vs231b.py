from rdkit import Chem
from rdkit.Chem import rdCIPLabeler

smi = "CC=[C@]=C1CC[C@H](CC1)CC"
Chem.SetUseLegacyStereoPerception(False)
mol = Chem.MolFromSmiles(smi)

print("BondStereo", [x for x in dir(Chem.BondStereo) if not x.startswith("_")])
print("ChiralType", [x for x in dir(Chem.ChiralType) if not x.startswith("_")])

try:
    from rdkit.Chem import rdmolops
    print("FindPotentialStereo", list(rdmolops.FindPotentialStereo(mol)))
except Exception as e:
    print("FindPotentialStereo rdmolops", e)

try:
    from rdkit.Chem.EnumerateStereoisomers import GetStereoisomerCount, StereoEnumerationOptions
    print("count", GetStereoisomerCount(mol))
except Exception as e:
    print("enum", e)

try:
    from rdkit.Chem import rdchem
    print("has FindPotentialStereo on Chem", hasattr(Chem, "FindPotentialStereo"))
    fps = Chem.FindPotentialStereo(mol)
    for s in fps:
        print("stereo", s, type(s), dir(s))
        print("  centeredOn", s.centeredOn, "type", s.type, "specified", s.specified, "descriptor", getattr(s, "descriptor", None))
except Exception as e:
    print("Chem.FindPotentialStereo", e)

print("cxsmiles", Chem.MolToCXSmiles(mol) if mol else None)
print("MolToMolBlock first lines:")
print("\n".join(Chem.MolToMolBlock(mol).splitlines()[:20]))

# try with explicit coords from a 3D embed
from rdkit.Chem import AllChem
m3 = Chem.AddHs(mol)
cids = AllChem.EmbedMolecule(m3, randomSeed=1)
print("embed", cids)
AllChem.UFFOptimizeMolecule(m3)
try:
    rdCIPLabeler.AssignCIPLabels(m3)
except Exception as e:
    print("3d cip", e)
for a in m3.GetAtoms():
    p = a.GetPropsAsDict().get("_CIPCode")
    if p:
        print("3d atom", a.GetIdx(), a.GetSymbol(), p)
for s in Chem.FindPotentialStereo(m3):
    print("3d stereo", s.centeredOn, s.type, s.specified, getattr(s, "descriptor", None))
