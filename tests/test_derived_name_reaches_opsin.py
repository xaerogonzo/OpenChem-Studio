"""The engine's own OPSIN checks must be able to find Java when the app runs it.

`derived_name_for_structure` calls the vendored engine, which confirms stereo on a
bridged parent by parsing its own candidate name with OPSIN and DROPS the stereo when
that fails. py2opsin shells out to a bare `java`; the app's managed runtime is on
neither PATH nor JAVA_HOME, so before naming round 24 every such check failed in the
app and every bridged stereocentre was dropped (camphor came back as
`1,7,7-trimethylbicyclo[2.2.1]heptan-2-one`). The engine's benchmarks ran with Java
on PATH, so they never showed it.
"""
import pytest
from rdkit import Chem

from openchem.chem.naming_providers import derived_name_for_structure, opsin_available

pytestmark = pytest.mark.skipif(not opsin_available(), reason="needs the managed JRE and py2opsin")


@pytest.mark.parametrize(
    "smiles,expected",
    [
        ("CC1(C)[C@@H]2CC[C@@]1(C)C(=O)C2", "(1R,4R)-1,7,7-trimethylbicyclo[2.2.1]heptan-2-one"),
        # a tropane: stereo on an azabicyclo[3.2.1] parent (cocaine). A morphinan is NOT used here any more:
        # since D-180 it is named on the retained parent, so it no longer reaches the von Baeyer stereo check.
        ("COC(=O)[C@H]1[C@@H]2CC[C@H](C[C@@H]1OC(=O)c1ccccc1)N2C",
         "(1R,3S,4S,5S)-4-(methoxycarbonyl)-8-methyl-8-azabicyclo[3.2.1]octan-3-yl benzoate"),
    ],
)
def test_bridged_stereo_survives_the_engines_own_opsin_check(smiles, expected):
    result = derived_name_for_structure(Chem.MolFromSmiles(smiles))
    assert result.name == expected
    assert not result.note  # round-trips with stereo, so no "does not express stereochemistry"
