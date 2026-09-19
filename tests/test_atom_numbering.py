"""The numbers drawn beside the atoms, and the three states they have.

Two numberings, two different claims -- see `chem/atom_numbering.py`. What
is pinned here is that "numbered nothing" and "could not be numbered" stay
apart: both draw an empty canvas, and collapsing them is what makes a
working calculator read as broken.
"""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.atom_numbering import (
    INDEX,
    LOCANTS,
    MODE_LABELS,
    OFF,
    labels_for_molblock,
    locant_provenance,
)

MPMI = "CN1CCC[C@@H]1Cc1c[nH]c2ccccc12"
CAFFEINE = "Cn1cnc2c1c(=O)n(C)c(=O)n2C"
CAMPHOR = "CC1(C)C2CCC1(C)C(=O)C2"
# D-036 demoted camphor's and caffeine's retained names, so both now number
# systematically. TOLUENE is the retained-name example (a PIN by P-22.1.3)
# and NAPHTHALENE the ring-table one.
TOLUENE = "Cc1ccccc1"
NAPHTHALENE = "c1ccc2ccccc2c1"


def _molblock(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


def test_off_draws_nothing_and_says_nothing():
    labels, status = labels_for_molblock(_molblock(MPMI), OFF)
    assert labels == {}
    assert status == ""


def test_the_drawing_numbers_are_every_atom_from_one():
    labels, status = labels_for_molblock(_molblock(MPMI), INDEX)
    assert len(labels) == 16
    assert labels[0] == "1" and labels[15] == "16"
    assert "drawing position" in status


def test_the_locants_are_the_engines_and_cover_only_what_it_names():
    """MPMI, "3-{[(2R)-1-methylpyrrolidin-2-yl]methyl}-1H-indole".

    The indole is the parent and takes the parent numbering, fusion carbons
    included (3a/7a, which the ring entry left out until round 4, A7). Since
    round 4 (A12) the pyrrolidine takes ITS numbering too, as its prefix
    cites it -- N1, attachment carbon 2 -- carried from the prefix subtree
    through the carve's atom map. The N-methyl and the CH2 linker are
    one-atom substituents whose "1" is cited nowhere, and stay bare."""
    labels, status = labels_for_molblock(_molblock(MPMI), LOCANTS)
    indole = {9: "1", 8: "2", 7: "3", 15: "3a", 14: "4", 13: "5", 12: "6", 11: "7", 10: "7a"}
    pyrrolidine = {1: "1", 5: "2", 4: "3", 3: "4", 2: "5"}
    assert labels == {**indole, **pyrrolidine}
    assert status.startswith("14 of 16 atoms numbered")
    assert "substituents' own numbering" in status
    notes = locant_provenance(_molblock(MPMI))
    assert notes[5] == "2 of (2R)-1-methylpyrrolidin-2-yl (the substituent's own numbering)"
    assert notes[7] == "3 in this structure's parent numbering"


def test_a_retained_name_numbers_nothing_and_explains_itself():
    """A retained name carries no derived numbering. Zero labels and a
    sentence saying why -- NOT a failure, and not silence.

    Camphor was the example until D-036 demoted it; toluene is a retained PIN
    (P-22.1.3) and will not move.
    """
    labels, status = labels_for_molblock(_molblock(TOLUENE), LOCANTS)
    assert labels == {}
    assert status.startswith("0 of")
    assert "retained name" in status
    assert "failed" not in status


def test_a_ring_skeletons_numbering_says_that_it_is_one():
    """Naphthalene gets its numbering from the ring table rather than from
    its own name, and the status line distinguishes the two sources -- they
    have different standing (`LocantSource`).

    Caffeine was the example until D-036: with the retained name gone it now
    derives its own numbering, which is the OTHER source and so no longer
    exercises this.
    """
    _labels, status = labels_for_molblock(_molblock(NAPHTHALENE), LOCANTS)
    assert "ring skeleton" in status


def test_an_unreadable_structure_is_a_failure_not_an_empty_numbering():
    labels, status = labels_for_molblock("not a molblock", LOCANTS)
    assert labels == {}
    assert "could not be read" in status


def test_a_failure_is_worded_differently_from_an_empty_numbering():
    """The distinction this module exists for, asserted as a distinction
    rather than twice as an absence."""
    _empty, empty_status = labels_for_molblock(_molblock(CAMPHOR), LOCANTS)
    _broken, broken_status = labels_for_molblock("not a molblock", LOCANTS)
    assert empty_status != broken_status
    assert "atoms numbered" in empty_status
    assert "atoms numbered" not in broken_status


def test_the_mode_labels_do_not_call_the_drawing_number_an_index():
    """It follows the molfile, so it is a position rather than a stable id,
    and the menu must not imply otherwise."""
    assert MODE_LABELS[INDEX] == "Drawing atom numbers"
    assert "index" not in MODE_LABELS[INDEX].lower()
    assert MODE_LABELS[LOCANTS] == "IUPAC locants"


def test_the_locants_are_keyed_the_way_the_inspector_reads_them():
    """The overlay and the Atom Inspector's Locant column must agree about
    which atom is C-3, so both read the same annotation keyed by the
    DRAWING's atom index."""
    from openchem.chem.structure_annotation import annotate

    molblock = _molblock(MPMI)
    labels, _status = labels_for_molblock(molblock, LOCANTS)
    annotation = annotate(Chem.MolFromMolBlock(molblock))
    assert labels == {
        locant.atom_index: locant.label for locant in annotation.locants
    }
