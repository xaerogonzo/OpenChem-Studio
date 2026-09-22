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
