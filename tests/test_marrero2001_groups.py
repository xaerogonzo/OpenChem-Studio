"""The Marrero-Gani (2001) first-order fragmenter (`benchmarks/thermophysical/marrero2001_groups.py`), held to
the paper's own printed values and rules, not to its own output:

* every one of the 182 groups' sample compound (Table 6, "Example (n)") must produce that group n times;
* Appendix B's six worked examples must give the printed groups, the printed sums and the printed Tb / Tm;
* the paper's text examples of its golden rule and its two exceptions (p. 186) must come out as printed;
* the counts must not depend on how the SMILES is written (a seeded random atom order, as in
  `tests/test_energetics_groups.py`), and the ten-group counter in `energetics_groups.py` must agree on
  everything it handles;
* what the groups cannot describe must be REFUSED naming the atoms, and a tie must be refused as ambiguous.
"""

from __future__ import annotations

import importlib.util
import math
import re
import sys
from pathlib import Path

import pytest

from tests.naming_spellings import random_spellings

ROOT = Path(__file__).resolve().parents[1]
THERMO = ROOT / "benchmarks" / "thermophysical"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, THERMO / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mg():
    return _load("marrero2001_groups")


@pytest.fixture(scope="module")
def table():
    return _load("marrero2001_table")


@pytest.fixture(scope="module")
def eg():
    return _load("energetics_groups")


# --------------------------------------------------------------------------------------------------------
# The sample compound of every Table 6 group (the paper's "Example" column), as a SMILES.
# --------------------------------------------------------------------------------------------------------
SAMPLES: dict[int, str] = {
    1: "C" * 40, 2: "C" * 40, 3: "CC(C)CCC", 4: "CCC(C)(C)C", 5: "C=CCCCC", 6: "CC=CCCC",
    7: "C=C(C)CC", 8: "CC=C(C)C", 9: "CC(C)=C(C)C", 10: "C=C=CC", 11: "C=C=C(C)C", 12: "CC=C=CC",
    13: "C#CCCC", 14: "CCC#CCCCCCC", 15: "c1ccccc1", 16: "c1ccc2ccccc2c1", 17: "c1ccc2c(c1)CCC2",
    18: "O=C(c1ccccc1)c1ccccc1", 19: "c1ccncc1", 20: "Cc1ccccc1", 21: "CCc1ccccc1",
    22: "CC(C)c1ccccc1", 23: "CC(C)(C)c1ccccc1", 24: "C=Cc1ccccc1", 25: "CC=Cc1ccccc1",
    26: "C=C(C)c1ccccc1", 27: "C#Cc1ccccc1", 28: "CC#Cc1ccccc1", 29: "OCCCCO", 30: "Oc1ccccc1",
    31: "OC(=O)CCCC(=O)O", 32: "OC(=O)c1ccccc1", 33: "CCC(C)=O", 34: "CCC(=O)CC",
    35: "CC(C)C(=O)C(C)C", 36: "CC(C)(C)C(=O)C(C)(C)C", 37: "CC(=O)c1ccccc1", 38: "CCCCCC=O",
    39: "O=Cc1ccccc1", 40: "CCCCOC(C)=O", 41: "CCCC(=O)OC", 42: "CCOC(=O)C(C)C",
    43: "CCOC(=O)C(C)(C)C", 44: "CCCOC=O", 45: "COC(=O)c1ccccc1", 46: "O=COc1ccccc1",
    47: "CC(=O)Oc1ccccc1", 48: "C=CC(=O)OCC", 49: "CCCCOC", 50: "CCCCOCCCC", 51: "CCC(C)OC(C)CC",
    52: "CC(C)(C)OC(C)(C)C", 53: "COc1ccccc1", 54: "CCN", 55: "CCC(C)N", 56: "CC(C)(C)N",
    57: "CNC", 58: "CCCNCCC", 59: "CC(C)NC(C)C", 60: "CCN(C)CC", 61: "CCN(CC)CC",
    62: "Nc1ccccc1", 63: "CNc1ccccc1", 64: "CN(C)c1ccccc1", 65: "NC1CCC1", 66: "CC=NN=CC",
    67: "CC(C)=NN=C(C)C", 68: "CCC#N", 69: "CC(C)C#N", 70: "CC(C)(C)C#N", 71: "N#Cc1ccccc1",
    72: "C=CC#N", 73: "CCN=C=O", 74: "CC(C)N=C=O", 75: "CC(C)(C)N=C=O", 76: "O=C=Nc1ccccc1",
    77: "CCC[N+](=O)[O-]", 78: "CC(C)[N+](=O)[O-]", 79: "CC(C)(C)[N+](=O)[O-]",
    80: "O=[N+]([O-])c1ccccc1", 81: "O=[N+]([O-])C1CCCCC1", 82: "CCCCON=O",
    83: "CCCCO[N+](=O)[O-]", 84: "CCN(CC)C=O", 85: "CCNC=O", 86: "CCCC(N)=O", 87: "CNC(C)=O",
    88: "CCNC(C)=O", 89: "CN(C)C(C)=O", 90: "CCN(C)C(C)=O", 91: "CCN(CC)C(C)=O",
    92: "CC(=O)NC(C)=O", 93: "CC(=O)N(C)C(C)=O", 94: "NC(=O)c1ccccc1", 95: "O=CNc1ccccc1",
    96: "CN(C=O)c1ccccc1", 97: "CNC(=O)c1ccccc1", 98: "CC(=O)Nc1ccccc1C", 99: "CC(=O)N(C)c1ccccc1",
    100: "CNC(=O)NC", 101: "CNC(N)=O", 102: "CN(C)C(N)=O", 103: "CNC(=O)N(C)C",
    104: "CN(C)C(=O)N(C)C", 105: "NC(=O)Nc1ccccc1", 106: "O=C(Nc1ccccc1)Nc1ccccc1",
    107: "CC(=O)NCl", 108: "CCCCCl", 109: "CC(C)Cl", 110: "CC(C)(C)Cl", 111: "CC(Cl)Cl",
    112: "CC(C)(Cl)Cl", 113: "CC(Cl)(Cl)Cl", 114: "CCCCF", 115: "CCC(C)F", 116: "CC(C)(C)F",
    117: "CC(F)F", 118: "FC(F)(F)C(F)(F)C(F)(F)C(F)(F)C(F)(F)C(F)(F)F", 119: "FC(F)(F)C(F)(F)F",
    120: "ClC(Cl)(F)C(Cl)(Cl)F", 121: "FC(F)(F)C(F)Cl", 122: "FC(F)(Cl)C(F)(F)Cl",
    123: "Clc1ccccc1", 124: "Fc1c(F)c(F)c(F)c(F)c1F", 125: "Ic1ccccc1", 126: "Brc1ccccc1",
    127: "CCI", 128: "CCBr", 129: "FCc1ccccc1", 130: "CCOC(=O)CCl", 131: "CCC=NO",
    132: "CCC(=NO)CC", 133: "ON=Cc1ccccc1", 134: "CCOCCO", 135: "CCOC(C)CO", 136: "COCC(C)O",
    137: "CC(C)(C)OO", 138: "CCS", 139: "CC(C)S", 140: "CC(C)(C)S", 141: "Sc1ccccc1",
    142: "SC1CCCCC1", 143: "CSC", 144: "CCSCC", 145: "CC(C)SC(C)C", 146: "CC(C)(C)SC(C)(C)C",
    147: "CSc1ccccc1", 148: "CS(C)=O", 149: "CS(C)(=O)=O", 150: "COS(=O)OC", 151: "COS(C)(=O)=O",
    152: "COS(=O)(=O)OC", 153: "CS(=O)c1ccccc1", 154: "O=S(=O)(c1ccccc1)c1ccccc1", 155: "CPC",
    156: "CP(C)C", 157: "CCOP(OCC)OCC", 158: "COP(=O)OC", 159: "COP(C)(=O)OC",
    160: "CCOP(=O)(O)OCC", 161: "COP(=O)(OC)OC", 162: "O=P(Oc1ccccc1)(Oc1ccccc1)Oc1ccccc1",
    163: "c1ccc(P(c2ccccc2)c2ccccc2)cc1", 164: "CCOC(=O)OCC", 165: "CCC1CO1", 166: "CC1(C)CO1",
    167: "CC1OC1(C)C", 168: "C1CCCC1", 169: "CC1CCCC1", 170: "CC1(C)CCCCC1", 171: "C1=CCC1",
    172: "CC1=CCCC1", 173: "CC1=C(C)CCC1", 174: "C=C1CCCCC1", 175: "C1CCNC1", 176: "CN1CCCC1",
    177: "c1c[nH]cn1", 178: "Cc1ncc[nH]1", 179: "C1CCOCC1", 180: "O=C1CCC1", 181: "Cc1cccs1",
    182: "O=S1(=O)CCCC1",
}

#: samples the paper names loosely: what was taken, so a reader can disagree. The group, not the
#: compound, is what the test needs, so each is a compound that has the group's atoms.
EXAMPLE_ASSUMPTIONS = {
    107: "'N-chloroacetamide' read as CH3C(=O)NHCl: the group needs an amide N-H whose other substituent "
         "is not a carbon, and ClCH2CONH2 would be CONH2 + CH2Cl",
    151: "'Dimethyl sulfonate' read as methyl methanesulfonate, CH3SO2OCH3 (dimethyl sulfate is group 152)",
    159: "'Trimethylphosphonate' read as dimethyl methylphosphonate, CH3P(=O)(OCH3)2",
    167: "'Trimethyl oxirane' has one ring hydrogen but its symbol C2O has none: both are taken as C2O",
    175: "'Cyclopentimine' read as pyrrolidine (the group is a ring N-H)",
    182: "'Cyclobutadiene sulfone' is not a stable compound; sulfolane has the group's atoms",
}


def _printed_count(example: str) -> int:
    """The paper's own occurrence count: the number in brackets after the compound's name (1 if absent)."""
    m = re.search(r"\((\d+)\)\s*$", example)
    return int(m.group(1)) if m else 1


def test_every_group_has_a_sample_and_a_definition(mg, table):
    assert sorted(SAMPLES) == list(range(1, 183))
    assert sorted(mg._SMARTS) == list(range(1, 183))
    assert [r[0] for r in table.FIRST_ORDER] == list(range(1, 183))
    mg._patterns()  # every SMARTS compiles


@pytest.mark.parametrize("gid", range(1, 183))
def test_sample_compound_gives_the_group_its_printed_number_of_times(mg, table, gid):
    row = table.FIRST_ORDER[gid - 1]
    frag = mg.fragment(SAMPLES[gid])
    assert frag.counts.get(gid, 0) == _printed_count(row[2]), (
        f"group {gid} {row[1]!r} sample {row[2]!r}: got {frag.symbols()}"
    )


@pytest.mark.parametrize("gid", range(1, 183))
def test_every_atom_is_in_exactly_one_group(mg, gid):
    from rdkit import Chem

    smiles = SAMPLES[gid]
    frag = mg.fragment(smiles)
    atoms = [a for _gid, group in frag.assignment for a in group]
    assert sorted(atoms) == list(range(Chem.MolFromSmiles(smiles).GetNumAtoms()))
    assert {g: sum(1 for x, _ in frag.assignment if x == g) for g in frag.counts} == frag.counts


@pytest.mark.parametrize("gid", range(1, 183))
def test_counts_do_not_depend_on_how_the_smiles_is_written(mg, gid):
    expected = mg.fragment(SAMPLES[gid]).counts
    for seed, variant in enumerate(random_spellings(SAMPLES[gid], 6, 20261025 + gid)):
        assert mg.fragment(variant).counts == expected, f"seed {seed}: {variant!r}"


# --------------------------------------------------------------------------------------------------------
# Appendix B: the six worked examples, group for group, and the printed estimates
# --------------------------------------------------------------------------------------------------------
# (name, smiles, property, printed groups by group id, printed sum, printed first-order estimate in K)
APPENDIX_B = [
    ("Example 1, N-phenyl-1,4-benzenediamine", "Nc1ccc(Nc2ccccc2)cc1", "Tb",
     {62: 1, 63: 1, 18: 1, 15: 9}, 15.8281, 614.62),
    ("Example 2, pyrene", "c1cc2ccc3cccc4ccc(c1)c2c34", "Tb", {16: 6, 15: 10}, 18.7593, 652.43),
    ("Example 3, 4-aminobutanol", "NCCCCO", "Tb", {29: 1, 54: 1, 2: 3}, 7.508, 448.64),
    ("Example 4, dicoumarol", "OC1=C(Cc2c(O)c3ccccc3oc2=O)C(=O)Oc2ccccc12", "Tm",
     {29: 2, 17: 4, 15: 8, 173: 2, 180: 2, 179: 2, 2: 1}, 25.1421, 475.46),
    ("Example 5, flutemazepan", "CN1C(=O)C(O)N=C(c2ccccc2F)c2cc(Cl)ccc12", "Tm",
     {29: 1, 123: 1, 124: 1, 1: 1, 18: 1, 17: 2, 15: 7, 169: 1, 180: 1, 176: 1, 178: 1}, 24.0959, 469.19),
    ("Example 6, 1,9-nonanediol", "OCCCCCCCCCO", "Tm", {29: 2, 2: 9}, 7.8411, 303.66),
]


@pytest.mark.parametrize("name,smiles,prop,groups,total,printed", APPENDIX_B, ids=[a[0] for a in APPENDIX_B])
def test_appendix_b_example_group_for_group_and_to_the_printed_estimate(mg, name, smiles, prop, groups, total, printed):
    frag = mg.fragment(smiles)
    assert frag.counts == groups, name
    assert mg.first_order_sum(prop, frag.counts) == pytest.approx(total, abs=1e-3), name
    # Examples 5 and 6 print the wrong universal constant in the formula's text (ln(25.1421) for 24.0959;
    # Tb0 = 222.543 for a melting point) but the number printed after it is Tm0 * ln(sum): that is what is held.
    assert mg.estimate_first_order(prop, frag.counts) == pytest.approx(printed, abs=0.02), name


# --------------------------------------------------------------------------------------------------------
# The paper's own rules, with the paper's own examples (p. 186)
# --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "smiles,expected",
    [
        # golden rule: heavier group wins; "(1) CH3CO, (3) CH3, (1) C", not "(1) CCO, (4) CH3"
        ("CC(C)(C)C(C)=O", {"CH3CO": 1, "CH3": 3, "C": 1}),
        # exception 1: aC-R. "(1) aC-CO, (5) aCH, (1) CH3" not "(1) CH3CO, (1) aC, (5) aCH"
        ("CC(=O)c1ccccc1", {"aC-CO": 1, "aCH": 5, "CH3": 1}),
        # "(10) aCH, (1) aC-CH2, (1) aC-O" for benzyl phenyl ether, not "(10) aCH, (2) aC, (1) CH2O"
        ("c1ccc(COc2ccccc2)cc1", {"aCH": 10, "aC-CH2": 1, "aC-O": 1}),
        # exception 2: ureas. "(1) NHCONH, (2) CH3" not "(1) CONHCH3, (1) CH3"
        ("CNC(=O)NC", {"NHCONH": 1, "CH3": 2}),
        # criterion 5: "trimethylurea should be (1) NHCON, (3) CH3"
        ("CNC(=O)N(C)C", {"NHCON": 1, "CH3": 3}),
    ],
)
def test_the_papers_own_rule_examples(mg, smiles, expected):
    assert mg.count_groups(smiles) == expected


def test_a_substituent_atom_is_claimed_once_so_the_second_aryl_is_plain_aC(mg):
    """Appendix B, Example 1 prints one aC-NH and one plain aC for the nitrogen between two rings."""
    assert mg.count_groups("c1ccc(Nc2ccccc2)cc1") == {"aCH": 10, "aC-NH": 1, "aC except as above": 1}
    assert mg.count_groups("c1ccccc1Oc1ccccc1") == {"aCH": 10, "aC-O": 1, "aC except as above": 1}


def test_a_ring_that_rdkit_calls_aromatic_but_the_paper_does_not(mg):
    """Dicoumarol's pyranone, furan and thiophene are ring groups in the paper's own examples."""
    furan = mg.count_groups("c1ccoc1")
    assert furan == {"O (cyclic)": 1, "CH=CH (cyclic)": 2}
    assert mg.count_groups("c1ccsc1") == {"S (cyclic)": 1, "CH=CH (cyclic)": 2}
    assert mg.count_groups("c1ccncc1") == {"aN in aromatic ring": 1, "aCH": 5}


def test_a_six_ring_with_a_carbonyl_out_of_it_is_not_aromatic(mg):
    """2-Pyridone is aromatic to RDKit; with its ring C=O out of the ring it is the lactam groups here."""
    assert mg.count_groups("O=c1cccc[nH]1") == {"CO (cyclic)": 1, "NH (cyclic)": 1, "CH=CH (cyclic)": 2}


def test_the_duplicated_symbol_is_keyed_by_group_id(mg):
    """The paper prints `aC-NCO` for group 76 (isocyanate) and 99 (tertiary anilide)."""
    assert mg.count_groups("O=C=Nc1ccccc1") == {"aC-NCO": 1, "aCH": 5}
    assert mg.count_groups("CC(=O)N(C)c1ccccc1") == {"aC-NCO [99]": 1, "CH3": 2, "aCH": 5}
    assert mg.fragment("CC(=O)N(C)c1ccccc1").counts[99] == 1


# --------------------------------------------------------------------------------------------------------
# Representation invariance over molecules built from several groups at once
# --------------------------------------------------------------------------------------------------------
PANEL = [
    "CC(C)(C)C(C)=O", "CC(=O)c1ccccc1", "c1ccc(COc2ccccc2)cc1", "CNC(=O)NC", "CNC(=O)N(C)C",
    "OC1=C(Cc2c(O)c3ccccc3oc2=O)C(=O)Oc2ccccc12", "CN1C(=O)C(O)N=C(c2ccccc2F)c2cc(Cl)ccc12",
    "c1cc2ccc3cccc4ccc(c1)c2c34", "CCOC(=O)CCl", "COCC(C)O", "CC(=O)Nc1ccccc1C", "CN(C)c1ccc(cc1)C(=O)C",
    "O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]", "Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
    "C(C(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-])O[N+](=O)[O-]",
    "OC(=O)c1ccc(cc1)C(=O)OC", "CC1(C)CC(=O)CC(C)(C)C1", "c1ccc2[nH]ccc2c1", "O=C1c2ccccc2C(=O)c2ccccc12",
    "CC(C)Cc1ccc(cc1)C(C)C(=O)O", "COc1ccc(cc1)C=CC(=O)OC", "NC(=O)NC(=O)NC", "CCN(CC)CCOC(=O)c1ccccc1",
    "ClC(Cl)(Cl)C(Cl)(Cl)Cl", "FC(F)(F)c1ccccc1", "CS(=O)(=O)c1ccc(C)cc1", "Oc1ccc(O)cc1", "Nc1ccc(N)cc1",
    "O=C(c1ccccc1)Nc1ccccc1",  # a refusal (ambiguous): it must be the same refusal from every spelling
]


@pytest.mark.parametrize("smiles", PANEL)
def test_counts_are_invariant_on_multi_group_molecules(mg, smiles):
    try:
        expected = mg.fragment(smiles).counts
    except mg.GroupingRefusal as refusal:
        # a refusal must itself not depend on the spelling
        for variant in random_spellings(smiles, 8, 20261025):
            with pytest.raises(mg.GroupingRefusal) as other:
                mg.fragment(variant)
            assert other.value.reason == refusal.reason
        return
    for seed, variant in enumerate(random_spellings(smiles, 12, 20261025)):
        assert mg.fragment(variant).counts == expected, f"seed {seed}: {variant!r}"


# --------------------------------------------------------------------------------------------------------
# Agreement with the ten-group counter on everything it handles
# --------------------------------------------------------------------------------------------------------
def _old_corpus(eg):
    compare = _load("compare_energetics")
    smiles = [spec["smiles"] for spec in compare.MOLECULES.values() if spec["groups"] is not None]
    smiles += [
        "O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]",
        "Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
        "CN(c1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
        "C(C(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-])O[N+](=O)[O-]",
        "O=[N+]([O-])N1CN([N+](=O)[O-])C1",
        "Nc1c(N)c([N+](=O)[O-])c(N)c([N+](=O)[O-])c1[N+](=O)[O-]",
        "C(C(CO[N+](=O)[O-])O[N+](=O)[O-])O[N+](=O)[O-]",
    ]
    return smiles


#: more molecules from the ten groups' own territory (nitro, nitrate, aromatic substituents, ring N, alkanes)
_MORE_OLD_TERRITORY = [
    "Cc1ccccc1", "Nc1ccccc1", "O=[N+]([O-])c1ccccc1", "O=[N+]([O-])c1cccc([N+](=O)[O-])c1", "C[N+](=O)[O-]",
    "NC1CCC1", "CN1CCCC1", "CCCCCC", "CC(C)(C)C", "CCCCO[N+](=O)[O-]", "Cc1ccc(cc1)[N+](=O)[O-]",
    "Nc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]", "O=[N+]([O-])C1CCCCC1", "CCC(C)(C)C", "C1CCCCC1",
    "CCN(C)c1ccccc1", "O=[N+]([O-])N1CCCC1", "Cc1cc(C)cc(C)c1", "CC(C)(C)CO[N+](=O)[O-]",
]


def test_agrees_with_the_ten_group_counter_on_everything_it_handles(mg, eg):
    """Every molecule the ten-group counter can describe (the published hand decompositions of
    `compare_energetics.py` and the molecules above), the general fragmenter describes identically."""
    handled = 0
    for smiles in _old_corpus(eg) + _MORE_OLD_TERRITORY:
        try:
            old = eg.count_groups(smiles)
        except ValueError:
            continue
        handled += 1
        assert mg.count_groups(smiles) == old, smiles
    assert handled >= 20, handled


def test_ten_group_counter_refusals_are_refusals_here_too(mg, eg):
    for smiles in ("NC(=N)N[N+](=O)[O-]", "[NH4+].[O-][N+](=O)[O-]"):
        with pytest.raises(ValueError):
            eg.count_groups(smiles)
        with pytest.raises(mg.GroupingRefusal):
            mg.fragment(smiles)


# --------------------------------------------------------------------------------------------------------
# Refusals: the atoms named, never a partial sum
# --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "smiles,reason,element",
    [
        ("C=O", "uncovered", "C"),                       # formaldehyde: no group for H2C=O
        ("O", "uncovered", "O"),                         # water
        ("C1CO1", "uncovered", "O"),                     # ethylene oxide: an oxirane none of the epoxide groups fits
        ("CN(C)C=O", "uncovered", "C"),                  # DMF: HCON(CH2)2 needs CH2, not CH3
        ("C[Si](C)(C)C", "uncovered", "Si"),             # an element Table 6 has no group for
        ("CC(=O)Cl", "uncovered", "C"),                  # an acyl chloride has no group
        ("NC(=N)N[N+](=O)[O-]", "uncovered", "C"),       # nitroguanidine: the guanidine core
    ],
)
def test_refusal_names_the_atoms_no_group_claimed(mg, smiles, reason, element):
    with pytest.raises(mg.GroupingRefusal) as exc:
        mg.fragment(smiles)
    assert exc.value.reason == reason
    assert element in {el for _i, el, _nb in exc.value.uncovered}, exc.value.uncovered
    assert isinstance(exc.value, ValueError)


def test_a_salt_a_charge_and_a_bad_string_are_refused_for_their_own_reasons(mg):
    for smiles, reason in (("[NH4+].[O-][N+](=O)[O-]", "not_one_molecule"), ("C[N+](C)(C)C", "charged"),
                           ("not a smiles", "invalid")):
        with pytest.raises(mg.GroupingRefusal) as exc:
            mg.fragment(smiles)
        assert exc.value.reason == reason


def test_no_partial_cover_when_every_atom_has_a_group_but_they_do_not_tile(mg):
    """Atoms can each fit a group while no disjoint cover exists; that is a refusal naming the leftovers,
    not a sum over the groups that did fit."""
    with pytest.raises(mg.GroupingRefusal) as exc:
        mg.fragment("C=C1CCCC1=CC")  # an ethylidene on a ring carbon: no group for a chain-to-ring C=C
    assert exc.value.uncovered


def test_two_equally_good_splittings_are_refused_as_ambiguous(mg):
    """Benzanilide: aC-CONH + aC and aC-NHCO + aC weigh the same and the paper does not rank them."""
    with pytest.raises(mg.GroupingRefusal) as exc:
        mg.fragment("O=C(c1ccccc1)Nc1ccccc1")
    assert exc.value.reason == "ambiguous"
    assert len(exc.value.alternatives) == 2
    named = {frozenset(SYMBOL for SYMBOL in [mg.SYMBOL[g] for g in alt] if SYMBOL.startswith("aC-")) for alt in exc.value.alternatives}
    assert named == {frozenset({"aC-CONH"}), frozenset({"aC-NHCO"})}


# --------------------------------------------------------------------------------------------------------
# From groups to numbers
# --------------------------------------------------------------------------------------------------------
def test_estimates_equal_the_transcribed_tables_own_estimate(mg, table):
    for smiles in ("NCCCCO", "OCCCCCCCCCO", "Nc1ccc(Nc2ccccc2)cc1", "CC(C)(C)C(C)=O", "c1ccc(COc2ccccc2)cc1"):
        counts = mg.fragment(smiles).counts
        symbols = {mg.SYMBOL[g]: n for g, n in counts.items()}
        for prop in ("Tm", "Tb"):
            assert mg.estimate_first_order(prop, counts) == pytest.approx(table.estimate(prop, symbols))


def test_a_starred_contribution_raises_instead_of_counting_as_zero(mg, table):
    # group 28 (aC-C#C) has no Tm contribution in the paper ("*****")
    counts = mg.fragment("CC#Cc1ccccc1").counts
    with pytest.raises(mg.NoContribution):
        mg.estimate_first_order("Tm", counts)
    assert mg.estimate_first_order("Tb", counts) > 0


def test_estimate_smiles_refuses_where_it_cannot_describe(mg):
    with pytest.raises(mg.GroupingRefusal):
        mg.estimate_smiles("Tm", "C=O")
    assert math.isfinite(mg.estimate_smiles("Tb", "NCCCCO"))
