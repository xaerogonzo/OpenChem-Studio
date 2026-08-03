"""One environment code per environment, however the record was drawn.

34.3% of nmrshiftdb2's records carry explicit hydrogens and the rest do
not, and `hose_code` walks every bond -- so before `heavy_atom_view` the
index held two incompatible code vocabularies and a molecule drawn in
this application could only match one of them. These pin the three parts
of the fix that are silent when wrong: that coding is unaffected by how
hydrogens were drawn, that a proton's own index still reaches its heavy
atom, and that results come back in the CALLER's numbering.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.hose_codes import hose_codes
from openchem.chem.nmr_database import (
    INDEX_FORMAT,
    build_index,
    connect,
    heavy_atom_view,
    iter_assigned_spectra,
    predict_spectrum,
    stale_format,
)

from tests.test_nmr_database import _write_sdf


# --- The view itself ------------------------------------------------------


def test_heavy_atoms_keep_their_order_so_the_mapping_is_a_shift():
    """`RemoveAllHs` renumbers, and the whole mapping rests on it keeping
    the surviving atoms in order. Verified by symbol rather than assumed
    -- if RDKit ever reordered, every measurement would land on the wrong
    atom and nothing else here would notice."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)Nc1ccccc1O"))

    heavy, mapping = heavy_atom_view(mol)

    for original, new in mapping.items():
        source = mol.GetAtomWithIdx(original)
        if source.GetAtomicNum() == 1:
            continue
        assert heavy.GetAtomWithIdx(new).GetSymbol() == source.GetSymbol()
    assert heavy.GetNumAtoms() == mol.GetNumHeavyAtoms()


def test_a_protons_own_index_maps_to_the_heavy_atom_it_sits_on():
    """444 of the held-out split's 1H assignments point at an explicit
    hydrogen rather than its parent. Dropping them would discard real
    measurements; the parent is where the other 6,987 already are."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CO"))
    carbon = 0

    _, mapping = heavy_atom_view(mol)

    protons = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1]
    on_carbon = [
        p for p in protons if mol.GetAtomWithIdx(p).GetNeighbors()[0].GetIdx() == carbon
    ]
    assert on_carbon, "expected explicit hydrogens on the methyl"
    for proton in on_carbon:
        assert mapping[proton] == mapping[carbon]


def test_a_hydrogen_with_no_heavy_neighbour_is_left_unmapped():
    """H2 has no parent to file a shift against, and guessing one would
    attach a real measurement to an unrelated atom."""
    mol = Chem.MolFromSmiles("[H][H]")

    _, mapping = heavy_atom_view(mol)

    assert mapping == {}


def test_a_molecule_without_explicit_hydrogens_is_returned_unchanged():
    """The common case, and it should not pay for a copy."""
    mol = Chem.MolFromSmiles("CCO")

    heavy, mapping = heavy_atom_view(mol)

    assert heavy is mol
    assert mapping == {0: 0, 1: 1, 2: 2}


# --- The point of it ------------------------------------------------------


@pytest.mark.parametrize("smiles", ["Cc1ccccc1", "CC(=O)Nc1ccccc1O", "C1CCCCC1"])
def test_codes_do_not_depend_on_how_hydrogens_were_drawn(smiles):
    """The whole bug in one assertion. These two molecules are the same
    molecule; before this they produced different codes and therefore
    matched different halves of the index."""
    plain = Chem.MolFromSmiles(smiles)
    explicit = Chem.AddHs(Chem.MolFromSmiles(smiles))

    plain_view, plain_map = heavy_atom_view(plain)
    explicit_view, explicit_map = heavy_atom_view(explicit)

    for index in range(plain.GetNumAtoms()):
        assert hose_codes(plain_view, plain_map[index], 4) == hose_codes(
            explicit_view, explicit_map[index], 4
        )


def test_the_same_record_indexes_identically_with_or_without_hydrogens(tmp_path):
    """Two spellings of one measurement must reach one environment, not
    two. Written as SDF records because that is how the discrepancy got
    into the database in the first place."""
    plain = _write_sdf(tmp_path / "plain.sd", [("CCO", {"Spectrum 13C 0": "18.4;0.0;0|"})])

    block = Chem.MolToMolBlock(Chem.AddHs(Chem.MolFromSmiles("CCO")))
    (tmp_path / "explicit.sd").write_text(
        f"{block}\n> <Spectrum 13C 0>\n18.4;0.0;0|\n\n$$$$\n", encoding="utf-8"
    )

    codes = []
    for path in (plain, tmp_path / "explicit.sd"):
        (_, mol, _, assignments), = list(iter_assigned_spectra(path))
        codes.append(hose_codes(mol, assignments[0][0], 4))
        assert assignments[0][1] == pytest.approx(18.4)

    assert codes[0] == codes[1]


def test_predicting_from_a_molecule_with_explicit_hydrogens_agrees_with_one_without(tmp_path):
    """Measured on the real index before the fix: toluene's methyl read
    8.89 ppm from `Chem.AddHs(...)` against 21.4 in the literature, and
    21.52 from the same molecule without explicit hydrogens. Same index,
    same molecule, two answers, no error either way."""
    sdf = _write_sdf(
        tmp_path / "toluene.sd",
        [("Cc1ccccc1", {"Spectrum 13C 0": f"{21.4 + n / 10};0.0;0|"}) for n in range(4)],
    )
    database = tmp_path / "index.sqlite"
    build_index(sdf, database, max_spheres=4)

    plain = predict_spectrum(
        Chem.MolFromSmiles("Cc1ccccc1"), "u", database_path=database, max_spheres=4
    )
    explicit = predict_spectrum(
        Chem.AddHs(Chem.MolFromSmiles("Cc1ccccc1")), "u", database_path=database, max_spheres=4
    )

    assert plain.values[0] == pytest.approx(explicit.values[0])
    assert plain.values[0] == pytest.approx(21.55, abs=0.01)


def test_predictions_come_back_in_the_callers_numbering(tmp_path):
    """The correlation plot and the spectrum widget key shifts back to the
    molecule they passed in. Returning heavy-view indices would put every
    label on the wrong atom of a molecule that has explicit hydrogens."""
    sdf = _write_sdf(
        tmp_path / "ethanol.sd",
        [("CCO", {"Spectrum 13C 0": f"{18.0 + n / 10};0.0;0|{57.6 + n / 10};0.0;1|"}) for n in range(4)],
    )
    database = tmp_path / "index.sqlite"
    build_index(sdf, database, max_spheres=4)

    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    result = predict_spectrum(mol, "u", database_path=database, max_spheres=4)

    assert set(result.values) == {0, 1}
    for index in result.values:
        assert mol.GetAtomWithIdx(index).GetSymbol() == "C"


# --- Telling the user their index predates this ---------------------------


def test_a_freshly_built_index_is_not_stale(tmp_path):
    sdf = _write_sdf(
        tmp_path / "toy.sd",
        [("CCO", {"Spectrum 13C 0": f"{18.0 + n / 10};0.0;0|"}) for n in range(4)],
    )
    database = tmp_path / "index.sqlite"
    build_index(sdf, database, max_spheres=4)

    assert not stale_format(database)


def test_an_index_without_the_format_key_is_stale(tmp_path):
    """Format 1 never wrote the key, so absent and "1" are the same thing
    -- and an index that reports nothing must not be assumed current."""
    sdf = _write_sdf(
        tmp_path / "toy.sd",
        [("CCO", {"Spectrum 13C 0": f"{18.0 + n / 10};0.0;0|"}) for n in range(4)],
    )
    database = tmp_path / "index.sqlite"
    build_index(sdf, database, max_spheres=4)
    connection = connect(database)
    connection.execute("DELETE FROM metadata WHERE key = 'format'")
    connection.commit()
    connection.close()

    assert stale_format(database)


def test_a_stale_index_is_reported_rather_than_refused(tmp_path):
    """It still answers correctly for the environments it can reach, so
    the cost of not rebuilding is accuracy, not correctness."""
    from openchem.services import nmr_database_setup

    sdf = _write_sdf(
        tmp_path / "toy.sd",
        [("CCO", {"Spectrum 13C 0": f"{18.0 + n / 10};0.0;0|"}) for n in range(4)],
    )
    database = tmp_path / "index.sqlite"
    build_index(sdf, database, max_spheres=4)
    connection = connect(database)
    connection.execute("UPDATE metadata SET value = '1' WHERE key = 'format'")
    connection.commit()
    connection.close()

    assert stale_format(database)
    assert predict_spectrum(
        Chem.MolFromSmiles("CCO"), "u", database_path=database, max_spheres=4
    ).values


def test_a_missing_index_is_not_called_stale(tmp_path):
    """"Not built" and "built by an older version" need different advice."""
    assert not stale_format(tmp_path / "absent.sqlite")


def test_the_format_number_is_recorded_in_the_index(tmp_path):
    from openchem.chem.nmr_database import database_summary

    sdf = _write_sdf(
        tmp_path / "toy.sd",
        [("CCO", {"Spectrum 13C 0": f"{18.0 + n / 10};0.0;0|"}) for n in range(4)],
    )
    database = tmp_path / "index.sqlite"
    build_index(sdf, database, max_spheres=4)

    connection = connect(database)
    try:
        assert database_summary(connection)["format"] == str(INDEX_FORMAT)
    finally:
        connection.close()
