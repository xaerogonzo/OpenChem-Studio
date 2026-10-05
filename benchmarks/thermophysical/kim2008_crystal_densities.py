"""Measured crystal densities of 41 energetic molecules, from Kim et al. 2008, Table 1 (kim2008 in
docs/research/literature.toml; DOI 10.1002/jcc.20943).

WHAT THIS IS: 41 X-ray crystal structures the paper selected from the Cambridge Structural Database
(CSD 5.24), each with its CSD refcode, the density that structure gives, the R factor, and the
TEMPERATURE of the diffraction experiment. They are measurements of one quantity -- a CRYSTAL density
at the stated temperature -- not loading densities and not theoretical maximum densities (see
docs/research/README.md, "The four density-type quantities").

WHAT THIS IS NOT, and the consequence for anyone comparing methods on it:

* **Not an independent holdout for anything trained on the CSD.** Every row is a CSD entry, so a method
  fitted to CSD data (Davis 2024 did train on the CSD) may have seen these molecules or close relatives.
  Whether a given method did is a question for that method's own paper, not assumed here: judge leakage
  per model with `tools/validation_rows.py`, which refuses to call an unenumerated fit population clean.
  Every row is `partition="selection"`, and none is an untouched holdout.
* **Not all at one temperature.** 38 are at 295 K and one each at 145, 153 and 200 K, so
  a prediction normalised to one temperature must be compared on the row's own `temperature_k`.
* **Not detonation data.** No detonation velocity, pressure or enthalpy of formation is here.

HOW IT WAS CHECKED, because the PDF is not read at run time and the first transcription of a table is the
likeliest to be wrong (`tests/test_kim2008_crystal_densities.py` holds the checks that can be repeated):

* The paper prints every density TWICE, as Table 1 and as the "Exp." column of Table 3. They agree for 40
  rows. The 41st, picric acid, does not (below).
* Table 3 also prints each prediction's deviation from "Exp."; all 41 rows' deviations are arithmetic on
  the Table 3 value (every predicted-minus-experimental difference agrees to within rounding), so the
  Table 3 column is internally consistent and independent of how Table 1 was read.
* Every SMILES was written by hand or built from the von Baeyer skeleton, and checked two ways: its element
  count equals the printed formula (one printed formula is wrong, see SIQKAE), and OPSIN's reading of the
  printed name (after repairing the print damage listed under each row's `note`) is the same molecule by
  InChIKey first block. All 41 agree; the cubanes and cages are the cases that mattered.

THE ONE DISAGREEMENT IN THE SOURCE: Table 1 prints picric acid at 1.655 g/cm3, the value of the TNT row
immediately above it. Table 3 prints 1.771 and every one of its seven deviations for that row is arithmetic on
1.771. This module uses 1.771 and keeps the Table 1 figure in `table1_printed_density`.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class KimRow:
    """One row of Kim 2008 Table 1, plus the structure this project assigns it."""

    refcode: str
    molecular_class: str
    #: Verbatim, including print damage (lost primes, a missing hydrogen count, a misspelling).
    printed_name: str
    printed_formula: str
    smiles: str
    #: The density this project uses.
    density_g_cm3: float
    #: What Table 1 prints for it. Differs from `density_g_cm3` for exactly one row.
    table1_printed_density: float
    #: The absolute temperature of the X-ray experiment (the parenthesis beside the R factor).
    temperature_k: int
    r_factor_percent: float
    note: str = ""


ROWS: tuple[KimRow, ...] = (
    KimRow(
        refcode='BEVQUO',
        molecular_class='Acyclic hydrocarbons',
        printed_name='2,5-dimethyl-2,5-dinitrohex-3-ene',
        printed_formula='C8H14N2O4',
        smiles='CC(C)(C=CC(C)(C)[N+](=O)[O-])[N+](=O)[O-]',
        density_g_cm3=1.269,
        table1_printed_density=1.269,
        temperature_k=295,
        r_factor_percent=4.13,
    ),
    KimRow(
        refcode='BECJEY01',
        molecular_class='Acyclic hydrocarbons',
        printed_name='2,3-dimethyl-2,3-dinitrobutane',
        printed_formula='C6H12N2O4',
        smiles='CC(C)([N+](=O)[O-])C(C)(C)[N+](=O)[O-]',
        density_g_cm3=1.352,
        table1_printed_density=1.352,
        temperature_k=295,
        r_factor_percent=3.1,
    ),
    KimRow(
        refcode='KOVGIL',
        molecular_class='Acyclic hydrocarbons',
        printed_name='1,1-bis(dimethylamino)-2,2-dinitroethylene',
        printed_formula='C6H12N4O4',
        smiles='CN(C)C(=C([N+](=O)[O-])[N+](=O)[O-])N(C)C',
        density_g_cm3=1.412,
        table1_printed_density=1.412,
        temperature_k=295,
        r_factor_percent=3.8,
    ),
    KimRow(
        refcode='JORBUN',
        molecular_class='Acyclic hydrocarbons',
        printed_name='2-methyl-2,3,3-trinitrobutane',
        printed_formula='C5H9N3O6',
        smiles='CC(C)([N+](=O)[O-])C(C)([N+](=O)[O-])[N+](=O)[O-]',
        density_g_cm3=1.553,
        table1_printed_density=1.553,
        temperature_k=295,
        r_factor_percent=3.2,
    ),
    KimRow(
        refcode='JUTGEK',
        molecular_class='Acyclic hydrocarbons',
        printed_name='1,2-dinitroethane',
        printed_formula='C2H4N2O4',
        smiles='O=[N+]([O-])CC[N+](=O)[O-]',
        density_g_cm3=1.62,
        table1_printed_density=1.62,
        temperature_k=295,
        r_factor_percent=3.3,
    ),
    KimRow(
        refcode='NTRGUA01',
        molecular_class='Acyclic hydrocarbons',
        printed_name='2-nitroguanidine',
        printed_formula='C1H4N4O2',
        smiles='N=C(N)N[N+](=O)[O-]',
        density_g_cm3=1.76,
        table1_printed_density=1.76,
        temperature_k=295,
        r_factor_percent=2.0,
    ),
    KimRow(
        refcode='SEDTUQ01',
        molecular_class='Acyclic hydrocarbons',
        printed_name='1,1-diamino-2,2-dinitroethylene (FOX-7)',
        printed_formula='C2H4N4O4',
        smiles='NC(N)=C([N+](=O)[O-])[N+](=O)[O-]',
        density_g_cm3=1.883,
        table1_printed_density=1.883,
        temperature_k=295,
        r_factor_percent=3.02,
    ),
    KimRow(
        refcode='DFTNBD',
        molecular_class='Acyclic hydrocarbons',
        printed_name='1,4-diﬂuoro-1,1,4,4-tetranitro-2,3-butanediol',
        printed_formula='C4H4N4O10F2',
        smiles='O=[N+]([O-])C(F)(C(O)C(O)C(F)([N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]',
        density_g_cm3=1.946,
        table1_printed_density=1.946,
        temperature_k=295,
        r_factor_percent=3.0,
    ),
    KimRow(
        refcode='QQQBRD02',
        molecular_class='Acyclic hydrocarbons',
        printed_name='hexanitroethane',
        printed_formula='C2N6O12',
        smiles='O=[N+]([O-])C([N+](=O)[O-])([N+](=O)[O-])C([N+](=O)[O-])([N+](=O)[O-])[N+](=O)[O-]',
        density_g_cm3=2.075,
        table1_printed_density=2.075,
        temperature_k=145,
        r_factor_percent=3.3,
    ),
    KimRow(
        refcode='NUKBOK',
        molecular_class='Benzenes derivatives',
        printed_name='5-nitro-1,1,3,3-tetramethylisoindoline',
        printed_formula='C12H16N2O2',
        smiles='CC1(C)NC(C)(C)c2cc([N+](=O)[O-])ccc21',
        density_g_cm3=1.247,
        table1_printed_density=1.247,
        temperature_k=295,
        r_factor_percent=4.9,
    ),
    KimRow(
        refcode='ACNTBP',
        molecular_class='Benzenes derivatives',
        printed_name='4-acetyl-20-nitrobiphenyl',
        printed_formula='C14H11NO3',
        smiles='CC(=O)c1ccc(-c2ccccc2[N+](=O)[O-])cc1',
        density_g_cm3=1.339,
        table1_printed_density=1.339,
        temperature_k=295,
        r_factor_percent=4.5,
        note="The printed name reads '20-nitro': 2'-nitro (the prime was lost in print).",
    ),
    KimRow(
        refcode='KOTSIV',
        molecular_class='Benzenes derivatives',
        printed_name='2-methoxy-4-nitroaniline',
        printed_formula='C7H8N2O3',
        smiles='COc1cc([N+](=O)[O-])ccc1N',
        density_g_cm3=1.454,
        table1_printed_density=1.454,
        temperature_k=295,
        r_factor_percent=3.62,
    ),
    KimRow(
        refcode='LACLAC',
        molecular_class='Benzenes derivatives',
        printed_name='alpah-3,5-dinitro-2-methylbenzamide',
        printed_formula='C8H7N3O5',
        smiles='Cc1c(C(N)=O)cc([N+](=O)[O-])cc1[N+](=O)[O-]',
        density_g_cm3=1.583,
        table1_printed_density=1.583,
        temperature_k=295,
        r_factor_percent=5.0,
        note="The printed name begins 'alpah-'; read as 3,5-dinitro-2-methylbenzamide.",
    ),
    KimRow(
        refcode='ZZZMUC01',
        molecular_class='Benzenes derivatives',
        printed_name='2,4,6-trinitrotuluene (TNT)',
        printed_formula='C7H5N3O6',
        smiles='Cc1c([N+](=O)[O-])cc([N+](=O)[O-])cc1[N+](=O)[O-]',
        density_g_cm3=1.655,
        table1_printed_density=1.655,
        temperature_k=295,
        r_factor_percent=5.7,
    ),
    KimRow(
        refcode='PICRAC',
        molecular_class='Benzenes derivatives',
        printed_name='picric acid',
        printed_formula='C6H3N3O7',
        smiles='O=[N+]([O-])c1cc([N+](=O)[O-])c(O)c([N+](=O)[O-])c1',
        density_g_cm3=1.771,
        table1_printed_density=1.655,
        temperature_k=295,
        r_factor_percent=5.1,
        note="Table 1 prints 1.655, the TNT row's value one line above. Table 3 prints 1.771, and all seven of its predicted-minus-experimental deviations are arithmetic on 1.771. This row uses 1.771.",
    ),
    KimRow(
        refcode='SIQKAE',
        molecular_class='Benzenes derivatives',
        printed_name='3,5-dichloro-2,4,6-trinitroaniline',
        printed_formula='C6N2Cl2N4O6',
        smiles='Nc1c([N+](=O)[O-])c(Cl)c([N+](=O)[O-])c(Cl)c1[N+](=O)[O-]',
        density_g_cm3=1.858,
        table1_printed_density=1.858,
        temperature_k=295,
        r_factor_percent=5.1,
        note='Table 1 prints the formula as C6N2Cl2N4O6 (the hydrogens are missing); the structure is C6H2Cl2N4O6.',
    ),
    KimRow(
        refcode='TATNBZ',
        molecular_class='Benzenes derivatives',
        printed_name='1,3,5-triamino-2,4,6-trinitrobenzene (TATB)',
        printed_formula='C6H6N6O6',
        smiles='Nc1c([N+](=O)[O-])c(N)c([N+](=O)[O-])c(N)c1[N+](=O)[O-]',
        density_g_cm3=1.937,
        table1_printed_density=1.937,
        temperature_k=295,
        r_factor_percent=5.6,
    ),
    KimRow(
        refcode='WILBAU',
        molecular_class='Aromatic heterocycles',
        printed_name='3,5-di-t-butyl-4-nitropyrazole',
        printed_formula='C11H19N3O2',
        smiles='CC(C)(C)c1n[nH]c(C(C)(C)C)c1[N+](=O)[O-]',
        density_g_cm3=1.214,
        table1_printed_density=1.214,
        temperature_k=295,
        r_factor_percent=4.9,
    ),
    KimRow(
        refcode='LETNAZ',
        molecular_class='Aromatic heterocycles',
        printed_name='3,5-dimethyl-4-nitropyrazole',
        printed_formula='C5H7N3O2',
        smiles='Cc1n[nH]c(C)c1[N+](=O)[O-]',
        density_g_cm3=1.33,
        table1_printed_density=1.33,
        temperature_k=295,
        r_factor_percent=5.3,
    ),
    KimRow(
        refcode='LEKHUE',
        molecular_class='Aromatic heterocycles',
        printed_name='2,5-dimethyl-4-nitroimidazole',
        printed_formula='C5H7N3O2',
        smiles='Cc1nc([N+](=O)[O-])c(C)[nH]1',
        density_g_cm3=1.44,
        table1_printed_density=1.44,
        temperature_k=295,
        r_factor_percent=3.49,
    ),
    KimRow(
        refcode='RIKNOO',
        molecular_class='Aromatic heterocycles',
        printed_name='3-nitropyrazole',
        printed_formula='C3H3N3O2',
        smiles='O=[N+]([O-])c1cc[nH]n1',
        density_g_cm3=1.579,
        table1_printed_density=1.579,
        temperature_k=295,
        r_factor_percent=3.8,
    ),
    KimRow(
        refcode='KOMHAV',
        molecular_class='Aromatic heterocycles',
        printed_name='4-nitroimidazole',
        printed_formula='C3H3N3O2',
        smiles='O=[N+]([O-])c1c[nH]cn1',
        density_g_cm3=1.66,
        table1_printed_density=1.66,
        temperature_k=295,
        r_factor_percent=4.8,
    ),
    KimRow(
        refcode='TEVHEH',
        molecular_class='Aromatic heterocycles',
        printed_name='2,4-dinitroimidazole (24-DNI)',
        printed_formula='C3H2N4O4',
        smiles='O=[N+]([O-])c1c[nH]c([N+](=O)[O-])n1',
        density_g_cm3=1.77,
        table1_printed_density=1.77,
        temperature_k=295,
        r_factor_percent=6.0,
    ),
    KimRow(
        refcode='JOWWIB',
        molecular_class='Aromatic heterocycles',
        printed_name='3-amino-5-nitro-1,2,4-triazole',
        printed_formula='C2H3N5O2',
        smiles='Nc1n[nH]c([N+](=O)[O-])n1',
        density_g_cm3=1.819,
        table1_printed_density=1.819,
        temperature_k=295,
        r_factor_percent=2.8,
    ),
    KimRow(
        refcode='TASJEC',
        molecular_class='Aromatic heterocycles',
        printed_name='1,1-diﬂuoroamino-3,30,4,40-tetranitro-5,50-bipyrazole',
        printed_formula='C6F4N10O8',
        smiles='O=[N+]([O-])c1nn(N(F)F)c(-c2c([N+](=O)[O-])c([N+](=O)[O-])nn2N(F)F)c1[N+](=O)[O-]',
        density_g_cm3=1.923,
        table1_printed_density=1.923,
        temperature_k=295,
        r_factor_percent=7.4,
        note="The printed name says 1,1-difluoroamino; the formula C6F4N10O8 needs two NF2 groups, so the structure is 1,1'-bis(difluoroamino)-3,3',4,4'-tetranitro-5,5'-bipyrazole (OPSIN reads that name to this structure).",
    ),
    KimRow(
        refcode='TOHWIW',
        molecular_class='Aliphatic heterocycles',
        printed_name='2,5-dimethyl-1-nitropyrrolidine',
        printed_formula='C6H12N2O2',
        smiles='CC1CCC(C)N1[N+](=O)[O-]',
        density_g_cm3=1.266,
        table1_printed_density=1.266,
        temperature_k=200,
        r_factor_percent=2.2,
    ),
    KimRow(
        refcode='LITRAH',
        molecular_class='Aliphatic heterocycles',
        printed_name='2,3,4-trimethyl-1,5-dinitro-3-azabicyclo(3.3.1)non-6-ene',
        printed_formula='C11H17N3O4',
        smiles='CC1N(C)C(C)C2([N+](=O)[O-])CC=CC1([N+](=O)[O-])C2',
        density_g_cm3=1.396,
        table1_printed_density=1.396,
        temperature_k=153,
        r_factor_percent=5.77,
    ),
    KimRow(
        refcode='HECVIU',
        molecular_class='Aliphatic heterocycles',
        printed_name='4-benzolyl-8-nitro-1,3,6-triazatricyclo(4.3.1.13,8)undecane',
        printed_formula='C15H18N4O3',
        smiles='O=C(c1ccccc1)C1CN2CN3CN1CC([N+](=O)[O-])(C2)C3',
        density_g_cm3=1.422,
        table1_printed_density=1.422,
        temperature_k=295,
        r_factor_percent=5.4,
    ),
    KimRow(
        refcode='BABBUB',
        molecular_class='Aliphatic heterocycles',
        printed_name='2-nitroimino-imidazolidine',
        printed_formula='C3H6N4O2',
        smiles='O=[N+]([O-])N=C1NCCN1',
        density_g_cm3=1.528,
        table1_printed_density=1.528,
        temperature_k=295,
        r_factor_percent=4.9,
    ),
    KimRow(
        refcode='ZZZTLC01',
        molecular_class='Aliphatic heterocycles',
        printed_name='1,4-dinitro-1,4-diazacyclohexane',
        printed_formula='C4H8N4O4',
        smiles='O=[N+]([O-])N1CCN([N+](=O)[O-])CC1',
        density_g_cm3=1.635,
        table1_printed_density=1.635,
        temperature_k=295,
        r_factor_percent=6.4,
    ),
    KimRow(
        refcode='KEMTIF',
        molecular_class='Aliphatic heterocycles',
        printed_name='2,4,8,10-tetranitro-2,4,8,10-tetra-azaspiro(5.5)undecane',
        printed_formula='C7H12N8O8',
        smiles='O=[N+]([O-])N1CN([N+](=O)[O-])CC2(C1)CN([N+](=O)[O-])CN([N+](=O)[O-])C2',
        density_g_cm3=1.738,
        table1_printed_density=1.738,
        temperature_k=295,
        r_factor_percent=4.9,
    ),
    KimRow(
        refcode='CTMTNA',
        molecular_class='Aliphatic heterocycles',
        printed_name='cyclotrimethylenetrinitramine (RDX)',
        printed_formula='C3H6N6O6',
        smiles='O=[N+]([O-])N1CN([N+](=O)[O-])CN([N+](=O)[O-])C1',
        density_g_cm3=1.806,
        table1_printed_density=1.806,
        temperature_k=295,
        r_factor_percent=2.1,
    ),
    KimRow(
        refcode='OCHTET04',
        molecular_class='Aliphatic heterocycles',
        printed_name='1,3,5,7-tetranitro-1,3,5,7-tetraazacyclooctane (HMX)',
        printed_formula='C4H8N8O8',
        smiles='O=[N+]([O-])N1CN([N+](=O)[O-])CN([N+](=O)[O-])CN([N+](=O)[O-])C1',
        density_g_cm3=1.903,
        table1_printed_density=1.903,
        temperature_k=295,
        r_factor_percent=6.5,
        note='Table 3 prints this refcode as OCTTET04; the density (1.903) is the same in both tables.',
    ),
    KimRow(
        refcode='PUBMUU02',
        molecular_class='Aliphatic heterocycles',
        printed_name='2,4,6,8,10,12-hexanitro-2,4,6,8,10,12-hexaazatetra-cyclo(5.5.0.05,9.03,11)dodecane (CL-20)',
        printed_formula='C6H6N12O12',
        smiles='O=[N+]([O-])N1C2C3N([N+](=O)[O-])C1C1N([N+](=O)[O-])C(C(N1[N+](=O)[O-])N3[N+](=O)[O-])N2[N+](=O)[O-]',
        density_g_cm3=2.044,
        table1_printed_density=2.044,
        temperature_k=295,
        r_factor_percent=3.63,
    ),
    KimRow(
        refcode='NTMCPO',
        molecular_class='Cyclic hydrocarbons',
        printed_name='2-nitro-3,5,5-trimethylcyclopentane',
        printed_formula='C8H13NO3',
        smiles='CC1CC(C)(C)C(=O)C1[N+](=O)[O-]',
        density_g_cm3=1.192,
        table1_printed_density=1.192,
        temperature_k=295,
        r_factor_percent=4.9,
        note='The printed name ends in -cyclopentane but the printed formula C8H13NO3 is a ketone: the structure is 2-nitro-3,5,5-trimethylcyclopentanone, which OPSIN reads from the corrected name.',
    ),
    KimRow(
        refcode='JIDBED',
        molecular_class='Cyclic hydrocarbons',
        printed_name='1,10-dinitrobicyclopentyl',
        printed_formula='C10H16N2O4',
        smiles='O=[N+]([O-])C1(C2([N+](=O)[O-])CCCC2)CCCC1',
        density_g_cm3=1.332,
        table1_printed_density=1.332,
        temperature_k=295,
        r_factor_percent=4.3,
        note="The printed name reads '1,10-': 1,1'- (the prime was lost in print).",
    ),
    KimRow(
        refcode='LINHUL',
        molecular_class='Cyclic hydrocarbons',
        printed_name='3,7-dinitronoradamantane',
        printed_formula='C9H12N2O4',
        smiles='O=[N+]([O-])C12CC3CC(C1)CC2([N+](=O)[O-])C3',
        density_g_cm3=1.448,
        table1_printed_density=1.448,
        temperature_k=295,
        r_factor_percent=4.8,
    ),
    KimRow(
        refcode='LINJAT',
        molecular_class='Cyclic hydrocarbons',
        printed_name='3,7,9-trinitronoradamantane',
        printed_formula='C9H11N3O6',
        smiles='O=[N+]([O-])C1C2CC3([N+](=O)[O-])CC1CC3([N+](=O)[O-])C2',
        density_g_cm3=1.583,
        table1_printed_density=1.583,
        temperature_k=295,
        r_factor_percent=3.2,
    ),
    KimRow(
        refcode='CEDZUG',
        molecular_class='Cyclic hydrocarbons',
        printed_name='1,4-dinitrocubane',
        printed_formula='C8H6N2O4',
        smiles='O=[N+]([O-])C12C3C4C1C1C2C3C41[N+](=O)[O-]',
        density_g_cm3=1.662,
        table1_printed_density=1.662,
        temperature_k=295,
        r_factor_percent=4.88,
    ),
    KimRow(
        refcode='JUVMIW',
        molecular_class='Cyclic hydrocarbons',
        printed_name='2,2,5,5-tetranitrobicyclo(2.2.1)heptane',
        printed_formula='C7H8N4O8',
        smiles='O=[N+]([O-])C1([N+](=O)[O-])CC2CC1CC2([N+](=O)[O-])[N+](=O)[O-]',
        density_g_cm3=1.708,
        table1_printed_density=1.708,
        temperature_k=295,
        r_factor_percent=3.9,
    ),
    KimRow(
        refcode='HASHEO',
        molecular_class='Cyclic hydrocarbons',
        printed_name='1,3,5,7-tetranitrocubane',
        printed_formula='C8H4N4O8',
        smiles='O=[N+]([O-])C12C3C4([N+](=O)[O-])C1C1([N+](=O)[O-])C2C3([N+](=O)[O-])C41',
        density_g_cm3=1.814,
        table1_printed_density=1.814,
        temperature_k=295,
        r_factor_percent=5.16,
    ),
)


def _load_validation_rows():
    path = ROOT / "tools" / "validation_rows.py"
    spec = importlib.util.spec_from_file_location("validation_rows", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass looks its module up here
    spec.loader.exec_module(module)
    return module


def validation_rows():
    """The 41 densities as `ValidationRow`s: property `crystal_density`, phase `crystal`, at the row's own
    temperature, all `selection` (see the module docstring for why none is a holdout)."""
    module = _load_validation_rows()
    return [
        module.ValidationRow(
            row_id=f"density_kim2008_{row.refcode.lower()}",
            smiles=row.smiles,
            property="crystal_density",
            value=row.density_g_cm3,
            units="g/cm3",
            source_id="kim2008",
            record_id=f"CSD {row.refcode}; Kim 2008 Table 1",
            partition="selection",
            temperature_k=float(row.temperature_k),
            phase="crystal",
            value_source="secondary",
            primary_reference=f"Cambridge Structural Database entry {row.refcode} (X-ray, {row.temperature_k} K, R = {row.r_factor_percent}%)",
            secondary_reference="Kim et al. 2008, J. Comput. Chem., Table 1 (density) and Table 3 (Exp. column)",
            note=row.note,
        )
        for row in ROWS
    ]
