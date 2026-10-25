"""Naming round 84 (D-376 .. D-378): the defects a SCAN OF SPIRO JOINTS OF TWO CURATED RINGS finds.

The population is new: two curated rings (16 atoms or fewer, no charge) joined at one sp3 carbon of each (600 molecules), named and read back through OPSIN. 566 read back, 30 were a
NAMING ERROR, 3 unreadable and 1 wrong; after the fixes 593, 2, 4 and 1 (the rest in "What round 84 left open"). The earlier populations of this round (about 11,000 molecules of ring pairs
joined by 12 functional linkers, richer substituents and charged rings) were clean apart from OPSIN's stereo defaults.

* D-376 a spiro joint on a bridged, benzo-fused polycycle (25 atoms, 36 bridges) made the von Baeyer numbering search try every ordering of each run of equal-length bridges, billions of
  them: the call never returned (one molecule held an 800-molecule scan for 50 minutes). A system with more than 50,000 orderings has no von Baeyer numbering.
* D-377 a ring ketone on a pyridone-type component of a spiro system (`c(=O)cc[nH]`) was a NAMING ERROR: the partner was rebuilt from bare elements without the =O, and the ring could not be
  kekulized with its N-H. The component is the pyridine and the N-H is the added hydrogen of the suffix: `spiro[5,6,7,8-tetrahydroquinoline-6,1'-cyclopropane]-4(1H)-one` (without the `(1H)`
  OPSIN reads another tautomer).
* D-378 the same with no N-H to drop (a bridgehead nitrogen, a ring sulfur): the partner is built from the Kekule form, the carbon that held the =O is a CH2 of the component and the
  indicated hydrogen sits there: `spiro[6,7,8,9-tetrahydro-4H-pyrido[1,2-a]pyrimidine-8,1'-cyclohexane]-4-one`.
"""

from __future__ import annotations

import shutil
import time

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NAMED = [
    ("a spiro quinolin-4(1H)-one", "O=c1cc[nH]c2c1CC1(CC1)CC2", "spiro[5,6,7,8-tetrahydroquinoline-6,1'-cyclopropane]-4(1H)-one"),
    ("a spiro quinolin-2(1H)-one", "O=c1ccc2c([nH]1)CC1(CCCC1)CC2", "spiro[5,6,7,8-tetrahydroquinoline-7,1'-cyclopentane]-2(1H)-one"),
    ("a bridgehead nitrogen", "O=c1ccnc2n1CCC1(CCCCC1)C2", "spiro[6,7,8,9-tetrahydro-4H-pyrido[1,2-a]pyrimidine-8,1'-cyclohexane]-4-one"),
    ("...the ketone on the other side", "O=c1ccn2CCC3(CCCC3)Cc2n1", "spiro[6,7,8,9-tetrahydro-2H-pyrido[1,2-a]pyrimidine-8,1'-cyclopentane]-2-one"),
    ("a ring sulfur", "O=c1ccsc2c1CC1(CCCC1)CC2", "spiro[5,6,7,8-tetrahydro-4H-1-benzothiopyran-6,1'-cyclopentane]-4-one"),
]

KEPT = [
    ("a saturated ring ketone", "O=C1CC2(CCCCC2)Nc2ccccc12", "spiro[1,2,3,4-tetrahydroquinoline-2,1'-cyclohexane]-4-one"),
    ("a spiro pyridine with an -ol", "Oc1ccnc2c1CC1(CCCC1)CC2", "spiro[5,6,7,8-tetrahydroquinoline-6,1'-cyclopentane]-4-ol"),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[r[0] for r in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


def _key(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))


@needs_opsin
@pytest.mark.parametrize("label,smiles", [(r[0], r[1]) for r in ALL], ids=[r[0] for r in ALL])
def test_the_name_reads_back_to_the_same_molecule(label, smiles):
    from py2opsin import py2opsin

    name = name_smiles(smiles)
    back = py2opsin(name)
    assert back, name
    assert _key(back) == _key(smiles), (name, back)


def test_a_polycycle_with_dozens_of_bridges_is_named_in_seconds():
    """D-376: this molecule's ring system has 36 bridges, with runs of ten of one length; the call used to run for hours."""
    start = time.time()
    name_smiles("O=C1CC2(c3ccccc3N1)C1CNCC2c2cc3nccnc3cc21")
    assert time.time() - start < 60


def test_a_ring_system_past_the_ordering_cap_has_no_von_baeyer_numbering(monkeypatch):
    """The cap itself, on a small system (bicyclo[2.2.2]octane has three bridges of one length, six orderings), so it does not need the hang to be seen."""
    from openchem.vendor.iupac_namer.perception.atoms import AtomAnalysis
    from openchem.vendor.iupac_namer.perception.rings import RingAnalysis
    from openchem.vendor.iupac_namer.ring_naming import bridged

    mol = Chem.MolFromSmiles("C1CC2CCC1CC2")
    rs = RingAnalysis(mol, AtomAnalysis(mol)).ring_systems[0]
    assert bridged.compute_vb_numberings(rs, rs.bridge_sizes, mol)
    monkeypatch.setattr(bridged, "_MAX_BRIDGE_ORDERINGS", 1)
    assert bridged.compute_vb_numberings(rs, rs.bridge_sizes, mol) == ()
