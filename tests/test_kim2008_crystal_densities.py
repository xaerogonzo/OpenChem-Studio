"""Kim 2008 Table 1: the 41 measured crystal densities and the checks that can be repeated without the PDF.

The module's docstring says how the table was read and checked. What survives here is what needs no PDF and
no Java: the SECOND PRINTED COPY of every density (Table 3's "Exp." column, transcribed separately below)
must equal the first, the structures must carry the formulas the paper prints, and each row must be a
legitimate common-set row. The one known disagreement in the source (picric acid) and the one known wrong
printed formula (SIQKAE) are asserted as EXACT sets, so a new exception cannot be added quietly and a
repaired one cannot linger.
"""

from __future__ import annotations

import collections
import importlib.util
import re
import sys
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem.rdMolDescriptors import CalcMolFormula

ROOT = Path(__file__).resolve().parent.parent

#: Table 3's "Exp." column, as printed (picric acid 1.771; HMX's refcode is OCTTET04 there, OCHTET04 in Table 1).
TABLE_3_EXP = {
    'BEVQUO': 1.269,
    'BECJEY01': 1.352,
    'KOVGIL': 1.412,
    'JORBUN': 1.553,
    'JUTGEK': 1.62,
    'NTRGUA01': 1.76,
    'SEDTUQ01': 1.883,
    'DFTNBD': 1.946,
    'QQQBRD02': 2.075,
    'NUKBOK': 1.247,
    'ACNTBP': 1.339,
    'KOTSIV': 1.454,
    'LACLAC': 1.583,
    'ZZZMUC01': 1.655,
    'PICRAC': 1.771,
    'SIQKAE': 1.858,
    'TATNBZ': 1.937,
    'WILBAU': 1.214,
    'LETNAZ': 1.33,
    'LEKHUE': 1.44,
    'RIKNOO': 1.579,
    'KOMHAV': 1.66,
    'TEVHEH': 1.77,
    'JOWWIB': 1.819,
    'TASJEC': 1.923,
    'TOHWIW': 1.266,
    'LITRAH': 1.396,
    'HECVIU': 1.422,
    'BABBUB': 1.528,
    'ZZZTLC01': 1.635,
    'KEMTIF': 1.738,
    'CTMTNA': 1.806,
    'OCHTET04': 1.903,
    'PUBMUU02': 2.044,
    'NTMCPO': 1.192,
    'JIDBED': 1.332,
    'LINHUL': 1.448,
    'LINJAT': 1.583,
    'CEDZUG': 1.662,
    'JUVMIW': 1.708,
    'HASHEO': 1.814,
}


def _load(name: str):
    path = ROOT / "benchmarks" / "thermophysical" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def kim():
    return _load("kim2008_crystal_densities")


def _counts(formula: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for element, n in re.findall(r"([A-Z][a-z]?)(\d*)", formula):
        out[element] = out.get(element, 0) + int(n or 1)
    return out


def test_there_are_41_rows_of_41_different_molecules(kim):
    assert len(kim.ROWS) == 41
    assert len({row.refcode for row in kim.ROWS}) == 41
    blocks = {Chem.MolToInchiKey(Chem.MolFromSmiles(row.smiles)).split("-")[0] for row in kim.ROWS}
    assert len(blocks) == 41, "two rows are the same molecule"


def test_the_two_printed_copies_of_every_density_agree_except_picric_acid(kim):
    assert len(TABLE_3_EXP) == 41, "the second copy must cover every row, or this proves nothing"
    differing = {
        row.refcode for row in kim.ROWS if row.table1_printed_density != TABLE_3_EXP[row.refcode]
    }
    assert differing == {"PICRAC"}
    for row in kim.ROWS:
        assert row.density_g_cm3 == TABLE_3_EXP[row.refcode], row.refcode
    picric = next(row for row in kim.ROWS if row.refcode == "PICRAC")
    assert picric.table1_printed_density == 1.655 and picric.density_g_cm3 == 1.771
    assert picric.note, "the one corrected value must say why"


def test_each_structure_has_the_formula_the_paper_prints_except_the_one_misprint(kim):
    wrong = {
        row.refcode
        for row in kim.ROWS
        if _counts(CalcMolFormula(Chem.MolFromSmiles(row.smiles))) != _counts(row.printed_formula)
    }
    assert wrong == {"SIQKAE"}
    siqkae = next(row for row in kim.ROWS if row.refcode == "SIQKAE")
    assert CalcMolFormula(Chem.MolFromSmiles(siqkae.smiles)) == "C6H2Cl2N4O6" and siqkae.note


def test_every_density_is_a_plausible_crystal_density_and_carries_its_temperature(kim):
    for row in kim.ROWS:
        assert 1.1 < row.density_g_cm3 < 2.2, row.refcode
        assert 100 <= row.temperature_k <= 300, row.refcode
    assert collections.Counter(row.temperature_k for row in kim.ROWS) == {295: 38, 145: 1, 153: 1, 200: 1}


def test_the_known_explosives_are_the_molecules_they_are_named_for(kim):
    by_code = {row.refcode: row for row in kim.ROWS}
    known = {
        "CTMTNA": "O=[N+]([O-])N1CN([N+](=O)[O-])CN([N+](=O)[O-])C1",  # RDX
        "ZZZMUC01": "Cc1c([N+](=O)[O-])cc([N+](=O)[O-])cc1[N+](=O)[O-]",  # TNT
        "NTRGUA01": "NC(=N)N[N+](=O)[O-]",  # nitroguanidine
    }
    for code, smiles in known.items():
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(by_code[code].smiles)) == Chem.MolToInchiKey(
            Chem.MolFromSmiles(smiles)
        ), code
    # RDX and HMX are also in the energetics fixtures, at the same crystal-density order of magnitude.
    assert by_code["CTMTNA"].density_g_cm3 == pytest.approx(1.806)
    assert by_code["OCHTET04"].density_g_cm3 == pytest.approx(1.903)


def test_every_row_enters_the_common_evaluation_set_as_a_selection_row(kim):
    rows = kim.validation_rows()
    assert len(rows) == 41
    spec = importlib.util.spec_from_file_location("validation_rows", ROOT / "tools" / "validation_rows.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    for row in rows:
        assert row.partition == "selection" and row.phase == "crystal" and row.property == "crystal_density"
        assert row.temperature_k is not None
        assert module.admit_to_common_set(row) is None
