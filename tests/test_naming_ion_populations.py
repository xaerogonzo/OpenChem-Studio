"""`tools/naming_ion_populations.py`: the ions it makes, and how it judges a name.

The tool is how naming rounds 46 to 49 found their defects (change ONE site of every census molecule into an ion, read each name back). These tests pin the two parts that can be
wrong without anything crashing: WHICH ions it builds (a silent zero or a double site would make a round believe a population was clean) and how it classifies a name.
The OPSIN read-back is not exercised here; `verdict` takes the read-back as an argument.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from rdkit import Chem

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import naming_ion_populations as pop  # noqa: E402


def _canon(smiles: str) -> str:
    return Chem.MolToSmiles(Chem.MolFromSmiles(smiles))


def _smiles(mode: str, *molecules: str) -> list[str]:
    rows = [{"label": f"m{i}", "smiles": s} for i, s in enumerate(molecules)]
    return [c.smiles for c in pop.generate(mode, rows)]


def test_a_sulfonamide_loses_its_proton():
    assert _smiles("anion", "CS(=O)(=O)NC") == [_canon("CS(=O)(=O)[N-]C")]


def test_a_carboxylic_acid_loses_its_proton():
    assert _smiles("anion", "CC(=O)O") == [_canon("CC(=O)[O-]")]


def test_a_pyridine_gains_a_proton_and_an_amine_gains_one_too():
    assert _smiles("cation", "c1ccncc1") == [_canon("c1cc[nH+]cc1")]
    assert _smiles("cation", "CCN") == [_canon("CC[NH3+]")]


def test_a_pyridine_gains_a_methyl_not_a_proton_in_the_quaternary_mode():
    assert _smiles("quaternary", "c1ccncc1") == [_canon("C[n+]1ccccc1")]


def test_a_molecule_with_two_sites_of_a_kind_makes_no_ion_of_that_kind():
    """Two acidic sulfonamides: which one is deprotonated is a choice, and the population is one change at a time."""
    assert _smiles("anion", "CS(=O)(=O)NCCNS(C)(=O)=O") == []


def test_a_charged_molecule_or_a_salt_is_not_a_parent():
    assert _smiles("anion", "CC(=O)[O-].[Na+]") == []
    assert _smiles("cation", "C[NH3+]") == []


def test_a_nitro_group_does_not_stop_a_molecule_being_a_parent():
    assert _smiles("anion", "O=[N+]([O-])c1ccc(O)cc1") == [_canon("O=[N+]([O-])c1ccc([O-])cc1")]


def test_the_limit_is_per_kind():
    rows = [{"label": f"m{i}", "smiles": "CC(=O)O"} for i in range(5)] + [{"label": "p", "smiles": "Oc1ccccc1"}]
    kinds = [c.kind for c in pop.generate("anion", rows, limit=2)]
    assert kinds.count("carboxylic") == 2 and kinds.count("phenol") == 1


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        pop.generate("radical", [])


@pytest.mark.parametrize(
    "mode,smiles,name,back,expected",
    [
        ("anion", "CC(=O)[O-]", "acetate", "CC(=O)O", "ok"),                                      # OPSIN reads the anion neutral: compared on neutral connectivity
        ("anion", "CS(=O)(=O)[N-]C", "N-methylmethanesulfonamidate", "CNS(C)(=O)=O", "ok"),
        ("anion", "O=C1CCC(=O)[N-]1", "pyrrolidine-2,5-dione", "O=C1CCC(=O)N1", "no_anion_word"),  # the charge is in no word: the defect round 46 found
        ("anion", "CC(=O)[O-]", "ethanamide", "CC(N)=O", "no_anion_word"),                          # `amide` is not an anion word
        ("anion", "CC(=O)[O-]", "propanoate", "CCC(=O)O", "wrong"),
        ("anion", "CC(=O)[O-]", "acetate", "", "unparsable"),
        ("cation", "c1cc[nH+]cc1", "pyridin-1-ium", "c1cc[nH+]cc1", "ok"),
        ("cation", "c1cc[nH+]cc1", "pyridine", "c1ccncc1", "no_cation_word"),
        ("cation", "CC[NH3+]", "ethan-1-aminium", "CC[NH3+]", "ok"),
        ("cation", "NC(=[NH+]O)C", "N'-hydroxyethanimidamidium", "ON=C(C)[NH3+]", "ok"),            # standard InChI normalises WHERE the proton sits: the same cation
        ("cation", "c1cc[nH+]cc1", "pyridin-1-ium", "c1ccncc1", "charge_changed"),                  # OPSIN returned the neutral compound
        ("cation", "c1cc[nH+]cc1", "pyrimidin-1-ium", "c1cnc[nH+]c1", "wrong"),
        ("quaternary", "C[n+]1ccccc1", "1-methylpyridin-1-ium", "C[n+]1ccccc1", "ok"),
    ],
)
def test_the_verdict(mode, smiles, name, back, expected):
    assert pop.verdict(mode, smiles, name, back) == expected


def test_a_refusal_and_an_error_name_are_their_own_classes():
    assert pop.verdict("anion", "x", None, None, "No name found that keeps the negative charge") == "refused"
    assert pop.verdict("cation", "c1cc[nH+]cc1", "1-{[NAMING ERROR: no plan]}x", "") == "naming_error"


def test_names_only_skips_the_read_back():
    assert pop.verdict("anion", "CC(=O)[O-]", "acetate", None) == "ok"


def test_the_summary_lists_the_kinds_and_the_failures():
    results = [
        {"kind": "carboxylic", "verdict": "ok", "smiles": "a", "name": "n", "refusal": None},
        {"kind": "imide", "verdict": "no_anion_word", "smiles": "O=C1CCC(=O)[N-]1", "name": "pyrrolidine-2,5-dione", "refusal": None},
    ]
    text = pop.summary(results)
    assert "2 ions" in text and "imide" in text and "no_anion_word" in text and "pyrrolidine-2,5-dione" in text


def test_the_names_only_run_works_on_a_small_sample_without_opsin():
    rows = [{"label": "a", "smiles": "CC(=O)O"}, {"label": "b", "smiles": "c1ccncc1"}]
    results = pop.run("anion", rows, limit=None, names_only=True)
    assert [r["verdict"] for r in results] == ["ok"] and results[0]["name"] == "acetate"


# Rounds 51 and 52: site patterns the first populations never tried. A molecule can match several kinds (an acethydrazide is a hydrazide AND an acyclic amide), so each test asks for one kind.
def _of_kind(mode: str, smiles: str, kind: str) -> list[str]:
    return [c.smiles for c in pop.generate(mode, [{"label": "m", "smiles": smiles}]) if c.kind == kind]


def test_a_lactam_nitrogen_loses_its_proton_but_an_open_amide_does_not_count_as_one():
    assert _of_kind("anion", "O=C1CCCN1", "lactam") == [_canon("O=C1CCC[N-]1")]
    assert _of_kind("anion", "CC(=O)NC", "lactam") == []


def test_a_hydrazide_nitrogen_loses_its_proton():
    assert _of_kind("anion", "CC(=O)NN", "hydrazide") == [_canon("CC(=O)[N-]N")]


def test_an_azole_nh_loses_its_proton():
    assert _of_kind("anion", "c1cc[nH]n1", "azole_nh") == [_canon("c1cc[n-]n1")]


def test_a_hydroxamic_acid_loses_the_proton_of_its_oxygen():
    assert _of_kind("anion", "CC(=O)NO", "hydroxamic") == [_canon("CC(=O)N[O-]")]


def test_an_amide_oxygen_is_protonated_and_methylated():
    assert _of_kind("cation", "CC(=O)N", "amide_o") == [_canon("CC(N)=[OH+]")]
    assert _of_kind("quaternary", "CC(=O)N", "amide_o") == [_canon("CC(N)=[O+]C")]


def test_a_ketone_oxygen_is_a_site_of_its_own_and_an_amide_oxygen_is_not_one_too():
    kinds = [(c.kind, c.smiles) for c in pop.generate("cation", [{"label": "k", "smiles": "CC(C)=O"}])]
    assert kinds == [("carbonyl_o", _canon("CC(C)=[OH+]"))]


def test_round_52_anion_sites():
    assert _of_kind("anion", "CC(=O)NC", "amide_acyclic") == [_canon("CC(=O)[N-]C")]
    assert _of_kind("anion", "CNC(N)=O", "urea") == [_canon("C[N-]C(N)=O")]
    assert _of_kind("anion", "CC(=S)NC", "thioamide") == [_canon("CC(=S)[N-]C")]
    assert _of_kind("anion", "CC=NO", "oxime") == [_canon("CC=N[O-]")]
    assert _of_kind("anion", "CP(=O)(O)C", "phosphonic") == [_canon("CP(=O)([O-])C")]
    assert _of_kind("anion", "CS(=O)O", "sulfinic") == [_canon("CS(=O)[O-]")]


def test_round_52_cation_sites():
    assert _of_kind("cation", "CC(N)=S", "thiocarbonyl_s") == [_canon("CC(N)=[SH+]")]
    assert _of_kind("cation", "CS(C)=O", "sulfoxide_o") == [_canon("CS(C)=[OH+]")]
    assert _of_kind("cation", "CP(C)C", "phosphine_p") == [_canon("C[PH+](C)C")]
    assert _of_kind("cation", "CC#N", "nitrile_n") == [_canon("CC#[NH+]")]
