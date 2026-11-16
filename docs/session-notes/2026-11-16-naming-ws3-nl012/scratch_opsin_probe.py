from py2opsin import py2opsin
from rdkit import Chem
from rdkit.Chem import inchi

CASES = [
    (
        "bzd",
        "O=C1Nc2ccccc2C=NC12CNc1c(nc[nH]c1=O)N2",
        [
            "spiro[5,6,7,8-tetrahydropteridine-7,3'-2,3-dihydro-1H-1,4-benzodiazepine]-2',4(3H)-dione",
            "spiro[5,6,7,8-tetrahydropteridine-7,3'-2,3-dihydro-1H-1,4-benzodiazepine]-2',4(1H,3H)-dione",
            "spiro[5,6,7,8-tetrahydropteridine-7,3'-2,3-dihydro-1H-1,4-benzodiazepine]-2',4(1H)-dione",
        ],
    ),
    (
        "imidazo",
        "NC1Nc2c(nc[nH]c2=O)N(O)C12C(=O)NC1=Nc3ccccc3CN12",
        [
            "6-amino-8-hydroxyspiro[5,6,7,8-tetrahydropteridine-7,3'-1,2,3,5-tetrahydroimidazo[2,1-b]quinazoline]-2',4(3H)-dione",
            "6-amino-8-hydroxyspiro[5,6,7,8-tetrahydropteridine-7,3'-1,2,3,5-tetrahydroimidazo[2,1-b]quinazoline]-2',4(1H,3H)-dione",
            "6-amino-8-hydroxyspiro[5,6,7,8-tetrahydropteridine-7,3'-1,2,3,5-tetrahydroimidazo[2,1-b]quinazoline]-2',4-dione",
        ],
    ),
]
for label, smi, variants in CASES:
    key = inchi.MolToInchiKey(Chem.MolFromSmiles(smi))
    print("===", label, key)
    for v in variants:
        back = py2opsin(v)
        if not back:
            print("EMPTY", v)
            continue
        bk = inchi.MolToInchiKey(Chem.MolFromSmiles(back))
        print("OK" if bk == key else "WRONG", v)
        if bk != key:
            print("  got", bk)