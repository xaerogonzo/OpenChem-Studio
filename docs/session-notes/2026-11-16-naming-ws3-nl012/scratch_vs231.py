from rdkit import Chem
from rdkit.Chem import rdCIPLabeler

smi = "CC=[C@]=C1CC[C@H](CC1)CC"
Chem.SetUseLegacyStereoPerception(False)
mol = Chem.MolFromSmiles(smi)
print("legacy false parse", mol is not None)
if mol:
    print("smiles back", Chem.MolToSmiles(mol))
    Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
    try:
        rdCIPLabeler.AssignCIPLabels(mol)
    except Exception as e:
        print("cip", e)
    for a in mol.GetAtoms():
        print(
            a.GetIdx(),
            a.GetSymbol(),
            "chiral",
            a.GetChiralTag(),
            "stereo",
            getattr(a, "GetStereo", lambda: None)(),
            "props",
            {k: v for k, v in a.GetPropsAsDict().items() if "CIP" in k or "stereo" in k.lower() or "chiral" in k.lower()},
        )
    print("--- bonds ---")
    for b in mol.GetBonds():
        print(b.GetIdx(), b.GetBeginAtomIdx(), b.GetEndAtomIdx(), b.GetBondType(), b.GetStereo(), b.GetPropsAsDict())

print("--- stereo info ---")
try:
    from rdkit.Chem.rdchem import StereoType, StereoDescriptor
    print("StereoType", [x for x in dir(StereoType) if not x.startswith("_")])
except Exception as e:
    print(e)

try:
    infos = mol.GetStereoInfo() if mol else []
    print("GetStereoInfo", infos)
except Exception as e:
    print("GetStereoInfo", e)

print("FindMolChiralCenters", Chem.FindMolChiralCenters(mol, includeUnassigned=True) if mol else None)
print("legacy true")
Chem.SetUseLegacyStereoPerception(True)
mol2 = Chem.MolFromSmiles(smi)
print("parse", mol2 is not None, Chem.MolToSmiles(mol2) if mol2 else None)
if mol2:
    for a in mol2.GetAtoms():
        if a.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED:
            print("tagged", a.GetIdx(), a.GetChiralTag())
