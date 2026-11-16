"""A nitroxide nitrogen is not a basic, hydrogen-bond-accepting or ligand-donating amine (OS4 of docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md).

The oracle is measured chemistry: the pKa of the protonated radical is -5.5 +/- 1 (Malatesta and Ingold 1973) and -5.8 +/- 0.3 (Sen and Golubev) for TEMPO and -6.2 for
4-hydroxy-TEMPO, in concentrated sulfuric acid, with protonation on OXYGEN (Voinov et al. 2024; `docs/sources.toml`). Before this change TEMPO's nitrogen was counted as a
basic centre (LogD 0.96 against Crippen LogP 2.38 at pH 7.4), an H-bond acceptor and a ligand donor. Every control that SHOULD still be an amine must not move.
"""

from __future__ import annotations

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import Crippen

from openchem.chem.descriptor_providers import compute_logd
from openchem.chem.hbond_sites import find_sites
from openchem.chem.logd import classify_ionizable_centres
from openchem.chem.steric import NoDonorError, find_donor

RDLogger.DisableLog("rdApp.*")
TEMPO = "CC1(C)CCCC(C)(C)N1[O]"
TEMPOL = "CC1(C)CC(O)CC(C)(C)N1[O]"
AMINO_TEMPO = "CC1(C)CC(N)CC(C)(C)N1[O]"
TEMPOH = "CC1(C)CCCC(C)(C)N1O"
TMP = "CC1(C)CCCC(C)(C)N1"


def mol(smiles: str) -> Chem.Mol:
    return Chem.MolFromSmiles(smiles)


@pytest.mark.parametrize("smiles", [TEMPO, TEMPOL, "CCN([O])CC"])
def test_a_nitroxide_has_no_basic_centre(smiles):
    assert classify_ionizable_centres(mol(smiles)) == (0, 0)


def test_the_amine_that_is_there_still_counts_beside_a_nitroxide():
    assert classify_ionizable_centres(mol(AMINO_TEMPO)) == (0, 1)


@pytest.mark.parametrize("smiles", [TMP, TEMPOH, "CCNCC", "CCN(CC)CC"])
def test_real_amines_and_the_hydroxylamine_are_still_basic(smiles):
    """TEMPOH (N-OH, the oxygen has two connections) is a base of pKa about 7 to 8, so it stays counted."""
    assert classify_ionizable_centres(mol(smiles)) == (0, 1)


def test_tempo_logd_at_ph_7_4_is_its_logp():
    """Nothing ionises, so LogD is LogP. Measured before: 0.96 against 2.38."""
    molecule = Chem.AddHs(mol(TEMPO))
    result = compute_logd(molecule, "u", {})
    values = {f.label: f.value for f in result.facts if f.value is not None}
    logd = next(v for k, v in values.items() if k.startswith("LogD at pH"))
    assert logd == pytest.approx(Crippen.MolLogP(mol(TEMPO)), abs=0.01)


def test_the_nitroxide_nitrogen_is_not_a_hydrogen_bond_acceptor_but_an_amine_still_is():
    tempo = mol(TEMPO)
    nitrogen = next(a.GetIdx() for a in tempo.GetAtoms() if a.GetSymbol() == "N")
    assert nitrogen not in find_sites(tempo)
    amino = mol(AMINO_TEMPO)
    nitrogens = [a.GetIdx() for a in amino.GetAtoms() if a.GetSymbol() == "N"]
    acceptors = [i for i in nitrogens if i in find_sites(amino) and find_sites(amino)[i].acceptor]
    assert len(acceptors) == 1  # the amine, not the nitroxide
    tmp = mol(TMP)
    assert next(a.GetIdx() for a in tmp.GetAtoms() if a.GetSymbol() == "N") in find_sites(tmp)


def test_a_nitroxide_nitrogen_is_not_a_ligand_donor():
    with pytest.raises(NoDonorError):
        find_donor(mol(TEMPO))
    amino = mol(AMINO_TEMPO)
    donor = find_donor(amino)
    assert amino.GetAtomWithIdx(donor).GetTotalNumHs() == 2  # the NH2, not the nitroxide nitrogen
    tmp = mol(TMP)
    assert tmp.GetAtomWithIdx(find_donor(tmp)).GetSymbol() == "N"


def test_a_nitroso_nitrogen_is_still_a_donor():
    """N=O is a double bond: only an N-oxyl (single bond to a one-connection oxygen) is excluded."""
    assert mol("CN=O").GetAtomWithIdx(find_donor(mol("CN=O"))).GetSymbol() == "N"
