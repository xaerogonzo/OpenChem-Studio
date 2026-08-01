"""Builds the naming benchmark corpus. Run once; the result is committed.

Ground truth comes from PubChem, which is the same source the app already
treats as authoritative -- so "exact match" means "agrees with what we
would have shown anyway", not agreement with some third standard.

The categories are chosen to probe where a naming engine breaks rather
than to flatter it: each one is a different way to be hard. Silicon,
boron and phosphorus are in here because a model trained mostly on
drug-like carbon chemistry has no reason to handle them, and a naming
tool that quietly invents a plausible-looking name for a silane is worse
than one that admits it cannot.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from rdkit import Chem

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from openchem.chem import naming_providers as n  # noqa: E402

CORPUS: dict[str, list[tuple[str, str]]] = {
    "simple_aliphatic": [
        ("methanol", "CO"), ("ethanol", "CCO"), ("propan-2-ol", "CC(C)O"),
        ("acetic acid", "CC(=O)O"), ("acetone", "CC(C)=O"), ("butanal", "CCCC=O"),
        ("diethyl ether", "CCOCC"), ("butyl propanoate", "CCCCOC(=O)CC"),
        ("triethylamine", "CCN(CC)CC"), ("acetonitrile", "CC#N"),
        ("urea", "NC(N)=O"), ("glycerol", "OCC(O)CO"),
    ],
    "aromatic": [
        ("benzene", "c1ccccc1"), ("toluene", "Cc1ccccc1"), ("phenol", "Oc1ccccc1"),
        ("aniline", "Nc1ccccc1"), ("benzoic acid", "OC(=O)c1ccccc1"),
        ("styrene", "C=Cc1ccccc1"), ("nitrobenzene", "O=[N+]([O-])c1ccccc1"),
        ("p-xylene", "Cc1ccc(C)cc1"), ("benzaldehyde", "O=Cc1ccccc1"),
        ("mesitylene", "Cc1cc(C)cc(C)c1"),
    ],
    "heterocycle": [
        ("pyridine", "c1ccncc1"), ("pyrrole", "c1cc[nH]c1"), ("furan", "c1ccoc1"),
        ("thiophene", "c1ccsc1"), ("imidazole", "c1cnc[nH]1"), ("pyrimidine", "c1cncnc1"),
        ("piperidine", "C1CCNCC1"), ("morpholine", "C1COCCN1"),
        ("oxazole", "c1cocn1"), ("1,2,3-triazole", "c1cn[nH]n1"),
        ("tetrahydrofuran", "C1CCOC1"), ("piperazine", "C1CNCCN1"),
    ],
    "fused_polycyclic": [
        ("naphthalene", "c1ccc2ccccc2c1"), ("anthracene", "c1ccc2cc3ccccc3cc2c1"),
        ("quinoline", "c1ccc2ncccc2c1"), ("indole", "c1ccc2[nH]ccc2c1"),
        ("purine", "c1nc2[nH]cnc2cn1"), ("carbazole", "c1ccc2c(c1)[nH]c1ccccc12"),
        ("phenanthrene", "c1ccc2c(c1)ccc1ccccc12"), ("benzofuran", "c1ccc2occc2c1"),
        ("acridine", "c1ccc2nc3ccccc3cc2c1"), ("indazole", "c1ccc2[nH]ncc2c1"),
    ],
    "bridged_bicyclic": [
        ("norbornane", "C1CC2CCC1C2"), ("bicyclo[2.2.2]octane", "C1CC2CCC1CC2"),
        ("adamantane", "C1C2CC3CC1CC(C2)C3"), ("camphor (flat)", "CC1(C)C2CCC1(C)C(=O)C2"),
        ("quinuclidine", "C1CN2CCC1CC2"), ("cubane", "C12C3C4C1C1C4C3C12"),
    ],
    "charged_zwitterion": [
        ("acetate", "CC(=O)[O-]"), ("ammonium", "[NH4+]"),
        ("tetramethylammonium", "C[N+](C)(C)C"), ("glycine zwitterion", "[NH3+]CC(=O)[O-]"),
        ("betaine", "C[N+](C)(C)CC(=O)[O-]"), ("methanesulfonate", "CS(=O)(=O)[O-]"),
        ("pyridinium", "c1cc[nH+]cc1"), ("diazomethane", "[CH2-][N+]#N"),
    ],
    "isotopic": [
        ("deuterated methanol", "[2H]CO"), ("deuterated water", "[2H]O[2H]"),
        ("N-15 ammonia", "[15NH3]"), ("carbon-13 methane", "[13CH4]"),
    ],
    "stereochemistry": [
        ("(R)-naproxen", "COc1ccc2cc([C@@H](C)C(=O)O)ccc2c1"),
        ("(S)-naproxen", "COc1ccc2cc([C@H](C)C(=O)O)ccc2c1"),
        ("(S)-ibuprofen", "CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O"),
        ("L-alanine", "C[C@@H](N)C(=O)O"), ("D-alanine", "C[C@H](N)C(=O)O"),
        ("(E)-but-2-ene", "C/C=C/C"), ("(Z)-but-2-ene", "C/C=C" + chr(92) + "C"),
        ("(S)-nicotine", "CN1CCC[C@H]1c1cccnc1"),
        ("L-lactic acid", "C[C@H](O)C(=O)O"),
        ("(1R,2S)-ephedrine", "CN[C@@H](C)[C@H](O)c1ccccc1"),
        ("(2R,3R)-tartaric acid", "O[C@@H]([C@H](O)C(=O)O)C(=O)O"),
        ("trans-decalin", "C1CCC[C@@H]2CCCC[C@@H]12"),
    ],
    "organosilicon": [
        ("tetramethylsilane", "C[Si](C)(C)C"), ("trimethylsilanol", "C[Si](C)(C)O"),
        ("phenyltrimethylsilane", "C[Si](C)(C)c1ccccc1"),
        ("hexamethyldisiloxane", "C[Si](C)(C)O[Si](C)(C)C"),
        ("triethoxysilane", "CCO[SiH](OCC)OCC"),
    ],
    "organoboron": [
        ("boric acid", "OB(O)O"), ("phenylboronic acid", "OB(O)c1ccccc1"),
        ("trimethylborane", "CB(C)C"), ("pinacol phenylboronate", "CC1(C)OB(OC1(C)C)c1ccccc1"),
        ("borohydride anion", "[BH4-]"),
    ],
    "sulfur_rich": [
        ("dimethyl sulfoxide", "CS(C)=O"), ("dimethyl sulfone", "CS(C)(=O)=O"),
        ("thiophenol", "Sc1ccccc1"), ("methanethiol", "CS"),
        ("benzenesulfonamide", "NS(=O)(=O)c1ccccc1"),
        ("carbon disulfide", "S=C=S"), ("thiourea", "NC(N)=S"),
        ("dimethyl disulfide", "CSSC"), ("sulfanilamide", "Nc1ccc(cc1)S(N)(=O)=O"),
    ],
    "phosphorus": [
        ("trimethyl phosphate", "COP(=O)(OC)OC"),
        ("triphenylphosphine", "c1ccc(cc1)P(c1ccccc1)c1ccccc1"),
        ("phosphoric acid", "OP(=O)(O)O"), ("trimethylphosphine", "CP(C)C"),
        ("dimethyl methylphosphonate", "COP(C)(=O)OC"),
        ("triphenylphosphine oxide", "O=P(c1ccccc1)(c1ccccc1)c1ccccc1"),
    ],
    "halogenated": [
        ("chloroform", "ClC(Cl)Cl"), ("carbon tetrachloride", "ClC(Cl)(Cl)Cl"),
        ("chlorobenzene", "Clc1ccccc1"), ("trifluoromethylbenzene", "FC(F)(F)c1ccccc1"),
        ("iodomethane", "CI"), ("1,2-dibromoethane", "BrCCBr"),
    ],
    "medicinal_scaffold": [
        ("aspirin", "CC(=O)Oc1ccccc1C(=O)O"), ("paracetamol", "CC(=O)Nc1ccc(O)cc1"),
        ("caffeine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C"),
        ("ibuprofen (flat)", "CC(C)Cc1ccc(cc1)C(C)C(=O)O"),
        ("diazepam", "CN1c2ccc(Cl)cc2C(=NCC1=O)c1ccccc1"),
        ("nicotine (flat)", "CN1CCCC1c1cccnc1"),
        ("salicylic acid", "OC(=O)c1ccccc1O"),
        ("metformin", "CN(C)C(=N)N=C(N)N"),
        ("phenobarbital", "CCC1(c2ccccc2)C(=O)NC(=O)NC1=O"),
        ("sulfamethoxazole", "Cc1cc(NS(=O)(=O)c2ccc(N)cc2)no1"),
        ("warfarin (flat)", "CC(=O)CC(c1ccccc1)c1c(O)c2ccccc2oc1=O"),
        ("chloroquine (flat)", "CCN(CC)CCCC(C)Nc1ccnc2cc(Cl)ccc12"),
        ("indomethacin", "COc1ccc2c(c1)c(CC(=O)O)c(C)n2C(=O)c1ccc(Cl)cc1"),
        ("atenolol", "CC(C)NCC(O)COc1ccc(CC(N)=O)cc1"),
        ("omeprazole (flat)", "COc1ccc2[nH]c(S(=O)Cc3ncc(C)c(OC)c3C)nc2c1"),
    ],
    "novel_unregistered": [
        ("novel pyrazolone", "CC1=NN(C(=O)C1CCNC(=O)c1cccc(OC(F)(F)F)c1)c1ccc(Br)cc1"),
        ("novel triazole sulfonamide",
         "O=C(NCCn1cc(-c2ccc(C(F)(F)F)cc2)nn1)C1CCN(S(=O)(=O)c2ccccc2)CC1"),
        ("novel spiro amide", "O=C(NC1CCC2(CC1)OCCO2)c1ccc(N2CCOCC2)nc1"),
        ("novel biaryl urea", "O=C(Nc1ccc(-c2ccncc2)cc1)Nc1cccc(C(F)(F)F)c1"),
    ],
    # Charged species. Added after a defect hunt found that the engine was
    # SILENTLY NEUTRALIZING whole families of these -- the benzyl cation named
    # as "methylbenzene" (toluene), the phthaloyl dication as
    # "1,2-bis(oxomethyl)benzene" (phthalaldehyde). Twenty-six such cases were
    # fixed, and none of them were measurable here, because the one
    # charged_zwitterion category above contains no carbocation, no carbanion
    # and no polyacylium. The benchmark could not see the single largest
    # correctness problem the engine had.
    #
    # Deliberately includes species that still FAIL (phenyl anion,
    # guanidinium, azide). A benchmark that only contains what the engine
    # already handles measures nothing.
    "carbocation": [
        ("methylium", "[CH3+]"), ("ethan-1-ylium", "[CH2+]C"),
        ("propan-2-ylium", "C[CH+]C"), ("tert-butyl cation", "C[C+](C)C"),
        ("cyclohexan-1-ylium", "[CH+]1CCCCC1"),
        ("benzyl cation", "[CH2+]c1ccccc1"),
        ("allyl cation", "[CH2+]C=C"), ("vinyl cation", "[CH+]=C"),
        ("phenylium", "[C+]1=CC=CC=C1"), ("tropylium", "[CH+]1C=CC=CC=C1"),
        ("acetylium", "[C+](C)=O"), ("benzoylium", "O=[C+]c1ccccc1"),
    ],
    "carbanion": [
        ("methanide", "[CH3-]"), ("ethan-1-ide", "[CH2-]C"),
        ("propan-2-ide", "C[CH-]C"), ("benzyl anion", "[CH2-]c1ccccc1"),
        ("allyl anion", "[CH2-]C=C"), ("acetylide", "[C-]#C"),
        ("cyclopentadienide", "[cH-]1cccc1"),
        ("phenyl anion", "c1ccc[c-]c1"),
    ],
    "onium_ion": [
        ("methylammonium", "C[NH3+]"), ("trimethylsulfonium", "C[S+](C)C"),
        ("tetramethylphosphonium", "C[P+](C)(C)C"),
        ("N-methylpyridinium", "C[n+]1ccccc1"),
        ("pyrylium", "[O+]1=CC=CC=C1"), ("thiopyrylium", "[S+]1=CC=CC=C1"),
        ("guanidinium", "[NH2+]=C(N)N"),
        ("diphenyliodonium", "c1ccccc1[I+]c1ccccc1"),
        ("benzenediazonium", "c1ccc(cc1)[N+]#N"),
    ],
    "polycharged": [
        ("propane-1,3-diylium", "[CH2+]C[CH2+]"),
        ("methanediylium", "[CH2+2]"),
        ("propane-1,3-diide", "[CH2-]C[CH2-]"),
        ("ethylenediammonium", "[NH3+]CC[NH3+]"),
        ("malonate", "[O-]C(=O)CC(=O)[O-]"),
        ("phthalate", "[O-]C(=O)c1ccccc1C(=O)[O-]"),
        ("oxalylium", "O=[C+][C+]=O"),
        ("propanedioylium", "O=[C+]C[C+]=O"),
        ("benzene-1,2-dicarbonylium", "O=[C+]c1ccccc1[C+]=O"),
        ("benzene-1,3,5-tricarbonylium", "O=[C+]c1cc([C+]=O)cc([C+]=O)c1"),
        ("azide", "[N-]=[N+]=[N-]"),
        ("tetrafluoroborate", "[B-](F)(F)(F)F"),
    ],
}


def _trusted_pubchem_name(mol: Chem.Mol) -> str | None:
    """PubChem's name for this structure, but only if it denotes it.

    PubChem resolves a structure it does not hold to the nearest thing it
    does, and for charged species that is routinely the NEUTRAL PARENT:
    it answers "methylbenzene" for the benzyl cation and "propane" for the
    isopropyl cation. Storing those as ground truth would enshrine, as the
    benchmark's own reference, exactly the neutralisation bug this corpus
    was extended to detect.

    So the name is kept only when parsing it back with OPSIN yields the
    structure it was fetched for. Otherwise the row gets None, which costs
    nothing but the ability to score EXACT -- `classify` uses this field
    only to upgrade EQUIVALENT to EXACT, never to fail a row.

    The guard also rejects ground truth that silently drops information:
    PubChem answers "azane" for 15-N ammonia and "carbane" for 13-C
    methane, both of which discard the isotope label.
    """
    try:
        name = n.pubchem_name_for_structure(mol).name
    except n.NamingError:
        return None
    if not name:
        return None
    try:
        parsed = n.opsin_structure_for_name(name)
    except Exception:
        return None
    back = Chem.MolFromSmiles(parsed.smiles)
    if back is None:
        return None
    if Chem.MolToSmiles(back) != Chem.MolToSmiles(mol):
        print(f"      (dropped ground truth {name!r}: denotes a different structure)")
        return None
    return name


def main() -> None:
    """Build the corpus, or with --append add only rows that are missing.

    Appending matters because a full rebuild re-queries PubChem for all
    124 existing rows, and PubChem's answers drift. Re-fetching them to
    add new molecules would silently move the baseline the whole benchmark
    is measured against, which is the one thing this file must not do.
    """
    append = "--append" in sys.argv
    out = Path(__file__).with_name("corpus.json")
    existing: list[dict] = []
    if append and out.exists():
        existing = json.loads(out.read_text(encoding="utf-8"))
    # Deduplicate on canonical SMILES, not on (category, label). The corpus
    # is a set of MOLECULES, and the same molecule added twice under two
    # labels would be scored twice. Labels are not a reliable key: the
    # committed corpus and this file already disagree about several stereo
    # names -- CC(C)Cc1ccc([C@@H](C)C(=O)O)cc1 is "(R)-ibuprofen" there and
    # "(S)-ibuprofen" here -- so keying on them silently duplicated six rows.
    seen = {r["smiles"] for r in existing}

    rows = list(existing)
    added = 0
    for category, entries in CORPUS.items():
        for label, smiles in entries:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                print(f"  SKIP (bad SMILES) {label}: {smiles}")
                continue
            if Chem.MolToSmiles(mol) in seen:
                continue
            kekule_smiles = None
            try:
                copy = Chem.Mol(mol)
                Chem.Kekulize(copy, clearAromaticFlags=True)
                kekule_smiles = Chem.MolToSmiles(copy, kekuleSmiles=True)
            except Exception:
                pass
            truth = _trusted_pubchem_name(mol)
            rows.append({
                "label": label,
                "category": category,
                "smiles": Chem.MolToSmiles(mol),
                "kekule_smiles": kekule_smiles,
                "has_stereo": _has_stereo(mol),
                "pubchem_name": truth,
            })
            added += 1
            print(f"  {'ok ' if truth else '-- '} {category:20} {label}")
            time.sleep(0.25)  # NCBI asks for no more than 5 requests/second

    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    named = sum(1 for r in rows if r["pubchem_name"])
    stereo = sum(1 for r in rows if r["has_stereo"])
    print(f"\n{len(rows)} molecules ({added} added) | {named} with a trusted "
          f"PubChem name | {stereo} carrying stereochemistry")
    print(f"-> {out}")


def _has_stereo(mol: Chem.Mol) -> bool:
    """Any defined stereochemistry, tetrahedral or double-bond."""
    if Chem.FindMolChiralCenters(mol, includeUnassigned=False):
        return True
    return any(b.GetStereo() != Chem.BondStereo.STEREONONE for b in mol.GetBonds())


if __name__ == "__main__":
    main()
