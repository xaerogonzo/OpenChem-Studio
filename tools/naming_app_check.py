"""The release-candidate DRIVEN CHECK of the naming path, asserting semantics and not "a name is present" (naming round 8).

    python tools/naming_app_check.py            # needs a JRE (JAVA_HOME and `java` on PATH) for the round-trip half

Every row goes through the application's OWN provider, `naming_providers.compute_iupac_name` (the calculator behind the Properties panel's IUPAC Name) and
`derived_name_for_structure`, and is asserted on:

  * the EXACT name (equality, never a substring),
  * the source tag and kind ('Nomenclature engine', 'derived') as the report line prints them,
  * the round-trip verdict (`MATCH`, or `TAUTOMER` where a tautomer is the point), so a withheld or errored name is a FAILURE,
  * the structure's charge and component count, so a name for the wrong ionisation state cannot pass on its string alone.

The expected names are the ones each class's rule produces. `basis` says how each was settled: PRINTED (the Blue Book prints it, with the page),
DERIVED (a printed rule applied), or ENGINE-ADJUDICATED (the engine's name after a reading of the rule; not printed). A row that fails is a change in
the app's behaviour to be read, not a name to be updated blindly. Round 7 ran 15 such rows; round 8 runs the same salts plus the classes it built.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

#: (label, SMILES, exact name, basis, expected round-trip verdict, expected net charge, expected components)
ROWS = [
    # -- the salts and ions round 7 and 8 exist for --------------------------------------------------------------------------------------------------
    ("choline salicylate", "C[N+](C)(C)CCO.[O-]C(=O)c1ccccc1O", "2-hydroxy-N,N,N-trimethylethan-1-aminium 2-hydroxybenzoate", "DERIVED (P-73.1.2, P-65.6.2)", "MATCH", 0, 2),
    ("sodium lactate", "[Na+].CC(O)C(=O)[O-]", "sodium 2-hydroxypropanoate", "DERIVED (P-65.6.2.2)", "MATCH", 0, 2),
    ("glycine", "NCC(=O)O", "glycine", "PRINTED (retained, p. 1047)", "MATCH", 0, 1),
    ("lysinium: the side-chain ammonium", "[NH3+]CCCCC(N)C(=O)O", "5-amino-5-carboxypentan-1-aminium", "DERIVED (P-73.1.2)", "MATCH", 1, 1),
    ("citrate trianion", "[O-]C(=O)CC(O)(CC([O-])=O)C([O-])=O", "2-hydroxypropane-1,2,3-tricarboxylate", "DERIVED from p. 578", "MATCH", -3, 1),
    ("trisodium citrate", "[Na+].[Na+].[Na+].[O-]C(=O)CC(O)(CC([O-])=O)C([O-])=O", "trisodium 2-hydroxypropane-1,2,3-tricarboxylate", "DERIVED (P-65.6.2.2)", "MATCH", 0, 4),
    ("metformin as PubChem draws it", "CN(C)C(=N)N=C(N)N", "N1,N1-dimethylimidodicarbonimidic diamide", "PRINTED shape (P-66.4.1.2, p. 677)", "TAUTOMER", 0, 1),
    ("imidazolium chloride", "c1c[nH]c[nH+]1.[Cl-]", "1H-imidazol-3-ium chloride", "PRINTED (p. 818)", "MATCH", 0, 2),
    # -- classes the limitations pass built -------------------------------------------------------------------------------------------------------------
    ("disodium 4-sulfonatobenzoate", "[Na+].[Na+].[O-]C(=O)c1ccc(cc1)S(=O)(=O)[O-]", "disodium 4-sulfonatobenzoate", "DERIVED (p. 619, P-72.7 e)", "MATCH", 0, 3),
    ("salicylate dianion", "[O-]C(=O)c1ccccc1[O-]", "2-oxidobenzoate", "DERIVED from p. 815", "MATCH", -2, 1),
    ("dimethyl carbonate", "COC(=O)OC", "dimethyl carbonate", "DERIVED (p. 620)", "MATCH", 0, 1),
    ("acrylamide", "C=CC(N)=O", "prop-2-enamide", "PRINTED (p. 646)", "MATCH", 0, 1),
    ("Weinreb amide", "CON(C)C(C)=O", "N-methoxy-N-methylacetamide", "DERIVED (P-66.1)", "MATCH", 0, 1),
    ("amyl nitrite", "CCCCCON=O", "pentyl nitrite", "PRINTED (p. 710)", "MATCH", 0, 1),
    ("biacetyl", "CC(=O)C(=O)C", "butane-2,3-dione", "PRINTED (p. 559)", "MATCH", 0, 1),
    ("a phosphonium beside an amide", "C[P+](C)(C)CC(N)=O", "(2-amino-2-oxoethyl)tri(methyl)phosphanium", "DERIVED (Table 4.1)", "MATCH", 1, 1),
    ("a piperidine amide on a benzoic acid", "OC(=O)c1ccc(cc1)C(=O)N1CCCCC1", "4-(piperidine-1-carbonyl)benzoic acid", "DERIVED (p. 667)", "MATCH", 0, 1),
    ("carbonyldiimidazole", "O=C(n1ccnc1)n1ccnc1", "bis(1H-imidazol-1-yl)methanone", "DERIVED (P-64.3.2)", "MATCH", 0, 1),
    # -- naming round 9's admissions ledger (D-130 to D-138; D-133 not driven here -- its fix IS a NamingError, --
    # -- an honest refusal this table's loop always treats as a failure, not a row shape it can represent) -----
    ("DCC (carbodiimide)", "C(=NC1CCCCC1)=NC1CCCCC1", "{[(cyclohexylimino)methylidene]amino}cyclohexane", "DERIVED (D-130: wrong molecule fixed, PIN open)", "MATCH", 0, 1),
    ("carbamimidoyl-locant", "CCN=C(N)C1(C(=N)N(C)C)CCCCC1", "N'-ethyl-N'',N''-dimethylcyclohexane-1,1-dicarboximidamide", "DERIVED (D-131)", "MATCH", 0, 1),
    ("naphthalene-ring-drop", "O=C(O)Cc1cc2ccccc2cc1CC(=O)O", "[3-(carboxymethyl)naphthalen-2-yl]acetic acid", "DERIVED (D-132, no PIN claimed)", "MATCH", 0, 1),
    ("phosphine-oxide-trihydrazide", "CN(N)P(=O)(N(C)N)N(C)N", "1-methyl-1-[bis(1-methylhydrazinyl)(oxo)phosphanyl]hydrazine", "DERIVED (D-134, no PIN claimed)", "MATCH", 0, 1),
    ("glycylalanine", "NCC(=O)N[C@@H](C)C(=O)O", "glycylalanine", "PRINTED (D-135, P-103.3.2, pdf p. 1048)", "MATCH", 0, 1),
    ("ethynediide", "[C-]#[C-]", "ethynediide", "DERIVED (D-136, no PIN claimed)", "MATCH", -2, 1),
    ("phosphide-anion", "C1C[PH-]2CCC1CC2", "1-phosphabicyclo[2.2.2]octan-1-uide", "DERIVED (D-137, P-73)", "MATCH", -1, 1),
    ("imine-anion", "CCCC=[N-]", "butan-1-iminide", "DERIVED (D-138, no PIN claimed)", "MATCH", -1, 1),
    # -- naming round 10: all 4 of round 9's deferred items (item 3, charge-polycarbocation, not driven here --
    # -- like D-133 its fix IS a raised refusal, not a name this table's row shape can represent) -------------
    ("methylene blue (phenothiazine locant)", "CN(C)c1ccc2nc3ccc(=[N+](C)C)cc-3sc2c1.[Cl-]", "[7-(dimethylamino)phenothiazin-3-ylidene]di(methyl)azanium chloride", "DERIVED (D-139)", "MATCH", 0, 2),
    ("phenoxazine dye analogue (converse of D-139)", "CN(C)c1ccc2nc3ccc(=[N+](C)C)cc-3oc2c1.[Cl-]", "[7-(dimethylamino)phenoxazin-3-ylidene]di(methyl)azanium chloride", "DERIVED (D-140)", "MATCH", 0, 2),
    ("fluorescein (spiro-xanthene locant)", "O=C1OC2(c3ccc(O)cc3Oc3cc(O)ccc32)c2ccccc21", "3',6'-dihydroxyspiro[1,3-dihydro-2-benzofuran-1,9'-xanthene]-3-one", "DERIVED (D-141)", "MATCH", 0, 1),
    ("carbamimidate (oxime-swap bracketing)", "COC(=N)NN", "(hydrazinyl)(methoxy)methanimine", "DERIVED (D-142)", "MATCH", 0, 1),
    # -- naming round 11: 2 fixes (a re-verification/re-diagnosis round; no other item was fixed) -------------
    ("ketone-parent enclosure (two distinct ring substituents)", "O=C(c1ccccc1)N1CCOCC1", "(morpholin-4-yl)(phenyl)methanone", "DERIVED (D-143, P-16.5.1.3.1)", "MATCH", 0, 1),
    ("carbamimidoyl N'/N,N split (both nitrogens substituted)", "CCN=C(N(C)C)c1ccc(C(=O)O)cc1", "4-(N'-ethyl-N,N-dimethylcarbamimidoyl)benzoic acid", "PRINTED (D-091v, p. 676)", "MATCH", 0, 1),
    # -- naming round 12: a charged acid group INSIDE a substituent (D-144), and its converse ------------------
    ("sulfonate inside a substituent", "[O-]C(=O)c1ccc(CS(=O)(=O)[O-])cc1", "4-(sulfonatomethyl)benzoate", "DERIVED (D-144a, P-65.6.2.3.1)", "MATCH", -2, 1),
    ("carboxylate inside a substituent, beside a neutral acid", "O=C([O-])Cc1ccc(C(=O)[O-])c(C(=O)O)c1", "2-carboxy-4-(carboxylatomethyl)benzoate", "DERIVED (D-144b, P-65.6.2.3.1)", "MATCH", -2, 1),
    ("round 8's recorded repro", "O=C([O-])Cc1ccc(C(=O)[O-])cc1C(=O)O", "3-carboxy-4-(carboxylatomethyl)benzoate", "DERIVED (D-144c, P-65.6.2.3.1)", "MATCH", -2, 1),
    ("homogeneous classifier route (converse of D-144)", "O=C([O-])Cc1ccc(C(=O)[O-])cc1", "4-(carboxylatomethyl)benzoate", "DERIVED (classifier route, unchanged)", "MATCH", -2, 1),
    # -- naming round 13: a wrong ring locant (D-145..D-148) and a demoted ketone's aryl carbon (D-149, D-150), with their boundaries -----------
    # Every "withheld before" row below was a NamingError in the application (the read-back mismatch or the embedded error); each now arrives
    # verified. Shown and verified does not mean the preferred name: the basis column says which rows are derived and which are unadjudicated.
    ("1,3,4-thiadiazole substituent, senior heteroatom at 1", "Cc1nnc(NC(C)=O)s1", "N-(5-methyl-1,3,4-thiadiazol-2-yl)acetamide", "DERIVED (D-145, Hantzsch-Widman)", "MATCH", 0, 1),
    ("1,3,4-oxadiazole substituent on a carbon chain", "Cc1nnc(CO)o1", "(5-methyl-1,3,4-oxadiazol-2-yl)methanol", "DERIVED (D-145)", "MATCH", 0, 1),
    ("benzodioxine benzo carbon", "CC(=O)Nc1ccc2c(c1)OCCO2", "N-(2,3-dihydro-1,4-benzodioxin-6-yl)acetamide", "DERIVED (D-146a, atom_locants)", "MATCH", 0, 1),
    ("benzodioxine next to the ring fusion", "CC(=O)Nc1cccc2c1OCCO2", "N-(2,3-dihydro-1,4-benzodioxin-5-yl)acetamide", "DERIVED (D-146b)", "MATCH", 0, 1),
    ("azepane carbon (not its nitrogen)", "CC(=O)NC1CCCCCN1", "N-(azepan-2-yl)acetamide", "DERIVED (D-147a)", "MATCH", 0, 1),
    ("1,2,3-oxadiazole, no longer called 1,2,5", "c1cnno1", "1,2,3-oxadiazole", "DERIVED (D-148a, data key corrected)", "MATCH", 0, 1),
    ("phenacyloxy group on a senior parent", "OC(=O)c1ccc(OCC(=O)c2ccccc2)cc1", "4-(2-oxo-2-phenylethoxy)benzoic acid", "DERIVED (D-149a, ownership)", "MATCH", 0, 1),
    ("coumarin carrying the phenacyloxy group (a census structure)", "Cc1cc(=O)oc2cc(OCC(=O)c3ccc(F)cc3)ccc12", "7-[2-(4-fluorophenyl)-2-oxoethoxy]-4-methyl-2H-1-benzopyran-2-one", "DERIVED (D-149b)", "MATCH", 0, 1),
    ("aryl ketone beside an acid: the acid is the parent", "OC(=O)CCC(=O)c1ccccc1", "4-oxo-4-phenylbutanoic acid", "DERIVED (D-150a, the silent half)", "MATCH", 0, 1),
    ("aryl ketone beside an amide: the amide is the parent", "NC(=O)CCC(=O)c1ccccc1", "4-oxo-4-phenylbutanamide", "DERIVED (D-150b)", "MATCH", 0, 1),
    # boundaries: each must be UNCHANGED by the fixes above
    ("table-backed ring (converse of D-146)", "CC(=O)Nc1ccc2OCOc2c1", "N-(2H-1,3-benzodioxol-5-yl)acetamide", "DERIVED (table-backed, unchanged)", "MATCH", 0, 1),
    ("1,2,4-oxadiazole (converse of D-145)", "Cc1noc(NC(C)=O)n1", "N-(3-methyl-1,2,4-oxadiazol-5-yl)acetamide", "DERIVED (unchanged)", "MATCH", 0, 1),
    ("azepane nitrogen keeps -1-yl (converse of D-147)", "O=C(C)N1CCCCCC1", "1-(azepan-1-yl)ethan-1-one", "DERIVED (unchanged)", "MATCH", 0, 1),
    ("methyl ketone as a substituent (converse of D-149)", "OC(=O)c1ccc(OCC(C)=O)cc1", "4-(2-oxopropoxy)benzoic acid", "DERIVED (unchanged)", "MATCH", 0, 1),
    # -- naming round 14: a ring-nitrogen sulfonamide, ring cations, stereo on retained substituents and spiro parents, derived fused-ring tables ------------
    # Every "withheld before" row was a NamingError in the application (a wrong-structure read-back or an embedded error), or was shown with a name that
    # read back as the right connectivity and the wrong stereo or charge. Shown and verified is not the preferred name: the basis column says which rows
    # are derived (P-65.3.2.3 for the sulfonyl prefix, P-73.1 for the -ium) and which are only the engine's reading.
    ("ester of an acid with a ring-nitrogen sulfonamide (D-151)", "CCOC(=O)c1ccc(S(=O)(=O)N2CCCCC2)cc1", "ethyl 4-(piperidine-1-sulfonyl)benzoate", "DERIVED (D-151, P-65.3.2.3)", "MATCH", 0, 1),
    ("the acid itself (D-151b)", "OC(=O)c1ccc(S(=O)(=O)N2CCOCC2)cc1", "4-(morpholine-4-sulfonyl)benzoic acid", "DERIVED (D-151c)", "MATCH", 0, 1),
    ("sulfamoyl with two different N-substituents (D-152)", "CN(C1CCCCC1)S(=O)(=O)c1ccc(C(=O)Nc2ccccc2)cc1", "4-(N-cyclohexyl-N-methylsulfamoyl)-N-phenylbenzamide", "DERIVED (D-152)", "MATCH", 0, 1),
    ("a fused cation that is not a retained ring (D-154)", "c1c[nH+]c2sccn12", "imidazo[2,1-b][1,3]thiazol-7-ium", "DERIVED (D-154, P-73.1)", "MATCH", 1, 1),
    ("a cation drawn on the bridgehead nitrogen (D-155)", "Cc1c[n+]2cccc(C)c2[nH]1", "2,8-dimethylimidazo[1,2-a]pyridin-1-ium", "DERIVED (D-155: one cation, its [nH+] drawing; the app says so with a tautomer note)", "TAUTOMER", 1, 1),
    ("a quaternary bridgehead cation with a substituent (D-156)", "CC(=O)OCC1CCC[N+]2(C)CCCCC12", "1-[(acetyloxy)methyl]-5-methylquinolizidin-5-ium", "DERIVED (D-156)", "MATCH", 1, 1),
    ("a ring cation inside an acyl prefix (D-157)", "C[NH+](C)CCNC(=O)c1ccc[nH+]c1", "N,N-dimethyl-2-{[(oxo)(pyridinium-3-yl)methyl]amino}ethan-1-aminium", "ENGINE-ADJUDICATED (D-157: structure and charge right, preferred spelling not derived)", "MATCH", 2, 1),
    ("stereo on a retained ring substituent (D-158)", "CC(=O)NC[C@@H]1CCCO1", "N-{[(2S)-oxolan-2-yl]methyl}acetamide", "DERIVED (D-158)", "MATCH", 0, 1),
    ("stereo on a spiro parent (D-159)", "C1CCC2(CC1)OC[C@@H](CN1CCOCC1)O2", "4-{[(3R)-1,4-dioxaspiro[4.5]decan-3-yl]methyl}morpholine", "DERIVED (D-159)", "MATCH", 0, 1),
    ("a derived fused-ring table (D-160)", "CC(=O)Nc1ccc2cc3cc4cc5cc6cc7ccccc7cc6cc5cc4cc3cc2c1", "N-(heptacen-2-yl)acetamide", "DERIVED (D-160, P-25.3.3 numbering)", "MATCH", 0, 1),
    ("octahydroindole position 6 (D-161)", "CC(=O)NC1CCC2CCNC2C1", "N-(octahydro-1H-indol-6-yl)acetamide", "DERIVED (D-161, indole numbering)", "MATCH", 0, 1),
    ("tropolone (D-153)", "COc1cccc(O)c(=O)c1", "2-hydroxy-6-methoxycyclohepta-2,4,6-trien-1-one", "DERIVED (D-153)", "MATCH", 0, 1),
    # boundaries: each must be UNCHANGED by the round's changes
    ("a tetrahydroisoquinolinium (converse of D-154)", "C[NH+]1CCc2ccccc2C1", "2-methyl-1,2,3,4-tetrahydroisoquinolin-2-ium", "DERIVED (unchanged)", "MATCH", 1, 1),
    ("a ring that IS the parent (converse of D-151)", "O=S(=O)(N1CCCCC1)c1ccccc1", "1-(benzenesulfonyl)piperidine", "DERIVED (unchanged)", "MATCH", 0, 1),
    ("unspecified stereo keeps the retained leaf (converse of D-158)", "CC(=O)NCC1CCCO1", "N-[(oxolan-2-yl)methyl]acetamide", "DERIVED (unchanged)", "MATCH", 0, 1),
    ("benzene is still benzene (converse of D-153)", "c1ccccc1", "benzene", "PRINTED (unchanged)", "MATCH", 0, 1),
]


def main() -> int:
    from rdkit import Chem, RDLogger

    from openchem.chem import naming_providers as providers

    RDLogger.DisableLog("rdApp.*")
    if not providers.opsin_available():
        print("OPSIN is not available (no JRE on PATH?): the round-trip half cannot run.")
        return 2
    failures: list[str] = []
    for label, smiles, expected, basis, verdict, charge, components in ROWS:
        mol = Chem.MolFromSmiles(smiles)
        problems: list[str] = []
        if Chem.GetFormalCharge(mol) != charge or len(Chem.GetMolFrags(mol)) != components:
            problems.append(f"the structure is not what the row says (charge {Chem.GetFormalCharge(mol)}, {len(Chem.GetMolFrags(mol))} components)")
        try:
            derived = providers.derived_name_for_structure(mol)
        except providers.NamingError as exc:
            failures.append(f"{label}: WITHHELD or errored: {exc}")
            print(f"FAIL  {label}: {exc}")
            continue
        if derived.name != expected:
            problems.append(f"name {derived.name!r}, expected {expected!r}")
        if (derived.source, derived.kind) != ("Nomenclature engine", providers.DERIVED):
            problems.append(f"source/kind {derived.source!r}/{derived.kind!r}")
        got = providers.verify_name_round_trip(derived.name, mol).name
        if got != verdict:
            problems.append(f"round trip {got}, expected {verdict}")
        if verdict == "MATCH" and derived.note:
            problems.append(f"an unexpected note on a matching name: {derived.note!r}")
        report = providers.compute_iupac_name(mol, str(uuid.uuid4()), {"use_pubchem": False})
        shown = " ".join(str(x) for x in getattr(report, "matched", None) or getattr(report, "matches", None) or [report])
        if f"{expected}  [Nomenclature engine, derived]" not in shown:
            problems.append("the report line does not carry the exact name with its source tag")
        status = "FAIL" if problems else "ok  "
        print(f"{status}  {label}: {derived.name}   [{basis}]")
        for problem in problems:
            print(f"        {problem}")
        failures.extend(f"{label}: {p}" for p in problems)
    print(f"\n{len(ROWS) - len({f.split(':')[0] for f in failures})}/{len(ROWS)} rows pass")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
