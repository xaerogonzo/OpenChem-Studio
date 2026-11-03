"""The structural families of the Phase B (energetic materials) preregistration, held to well-known public structures.

`benchmarks/energetics_props/epb_families.py` is read from the structure alone and fixed before any label is
compared with any prediction. The fixtures are textbook structures written by hand; what is held is the PRECEDENCE
(a molecule with both an N-nitro and a C-nitro group is a nitramine, a nitro-substituted azole is a nitroaromatic and
not an N-rich heterocycle) and the cage flag, the two places a first-match table silently goes wrong.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fam = _load("epb_families", ROOT / "benchmarks" / "energetics_props" / "epb_families.py")

NO2 = "[N+](=O)[O-]"

#: name -> (SMILES, family, cage)
FIXTURES = {
    "TNT": (f"Cc1c({NO2})cc({NO2})cc1{NO2}", "nitroaromatic", False),
    "TATB": (f"Nc1c(N)c({NO2})c(N)c({NO2})c1{NO2}", "nitroaromatic", False),
    "DNAN": (f"COc1ccc({NO2})cc1{NO2}", "nitroaromatic", False),
    "RDX": ("O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]", "nitramine", False),
    "HMX": ("O=[N+]([O-])N1CN(CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]", "nitramine", False),
    "tetryl": (f"CN({NO2})c1c({NO2})cc({NO2})cc1{NO2}", "nitramine", False),
    "TNAZ": ("O=[N+]([O-])N1CC([N+](=O)[O-])([N+](=O)[O-])C1", "nitramine", False),
    "nitroguanidine": (f"NC(N)=N{NO2}", "nitramine", False),
    "PETN": (f"C(C(CO{NO2})(CO{NO2})CO{NO2})O{NO2}", "nitrate_ester", False),
    "nitroglycerin": (f"C(C(CO{NO2})O{NO2})O{NO2}", "nitrate_ester", False),
    "FOX-7": (f"NC(N)=C({NO2}){NO2}", "nitroaliphatic", False),
    "nitromethane": (f"C{NO2}", "nitroaliphatic", False),
    "NTO": (f"O=c1[nH]nc({NO2})[nH]1", "nitroaromatic", False),
    "ethyl azide": ("CCN=[N+]=[N-]", "azide", False),
    "TATP": ("CC1(C)OOC(C)(C)OOC(C)(C)OO1", "peroxide", False),
    "5-aminotetrazole": ("Nc1nnn[nH]1", "n_rich_heterocycle", False),
    "3,6-diamino-tetrazine": ("Nc1nnc(N)nn1", "n_rich_heterocycle", False),
    "1,2-dichloroethane": ("ClCCCl", "halogenated", False),
    "acetone": ("CC(C)=O", "other_organic", False),
    "cubane": ("C12C3C4C1C5C2C3C45", "other_organic", True),
    "adamantane": ("C1C2CC3CC1CC(C2)C3", "other_organic", True),
    "naphthalene": ("c1ccc2ccccc2c1", "other_organic", False),
    "anthracene": ("c1ccc2cc3ccccc3cc2c1", "other_organic", False),
    "norbornane": ("C1CC2CCC1C2", "other_organic", False),
    "water": ("O", "not_organic", False),
    "ammonium nitrate": ("[NH4+].[O-][N+](=O)[O-]", "not_organic", False),
    "lead azide": ("[N-]=[N+]=[N-].[N-]=[N+]=[N-].[Pb+2]", "not_organic", False),
}


def test_organic_is_not_phase_a_rule():
    # these four have no C-H and no C-C bond: Phase A's "organic" rule would have dropped every one of them
    for smiles in (FIXTURES["NTO"][0], FIXTURES["nitroguanidine"][0], FIXTURES["5-aminotetrazole"][0],
                   FIXTURES["3,6-diamino-tetrazine"][0]):
        assert fam.family(smiles) != "not_organic"


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_family_and_cage_of_a_known_structure(name):
    smiles, expected, cage = FIXTURES[name]
    assert fam.family(smiles) == expected
    assert fam.cage_flag(smiles) is cage


def test_every_family_is_exercised_by_a_fixture():
    # a family no fixture reaches is a rule nothing holds
    assert {f for _, f, _ in FIXTURES.values()} == set(fam.FAMILIES)


def test_precedence_is_the_preregistered_one():
    # N-nitro beats C-nitro; nitrate ester beats everything; a nitro azole is a nitroaromatic, not N-rich
    assert [name for name, _ in fam.FAMILY_RULES][:4] == ["nitrate_ester", "nitramine", "nitroaromatic", "nitroaliphatic"]
    assert fam.family("O=[N+]([O-])c1nnn[nH]1") == "nitroaromatic"
    assert fam.family("O=[N+]([O-])n1nnc(Cl)n1") == "nitramine"


def test_unreadable_structure_is_an_error_not_a_family():
    with pytest.raises(ValueError):
        fam.family("not a smiles ((")
    with pytest.raises(ValueError):
        fam.cage_flag("not a smiles ((")
