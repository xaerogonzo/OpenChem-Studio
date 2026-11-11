"""Shipped structure templates parse, render, and stay complete molecules."""

from __future__ import annotations

from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.chem.structure_templates import (
    PLACEMENT_GAP_ANGSTROM,
    SHIPPED_DIR,
    bounds_2d,
    load_shipped,
    molblock_for,
    place_to_the_right,
)
from openchem.domain.structure_template import (
    TemplateEntry,
    TemplateError,
    TemplateKind,
    TemplateOrigin,
)


def test_shipped_catalog_lives_beside_the_other_chem_data_tables():
    assert SHIPPED_DIR.is_dir()
    assert (SHIPPED_DIR / "rings.json").is_file()


def test_every_shipped_category_loads_with_unique_ids_and_complete_molecules():
    categories = load_shipped()
    ids = [c.id for c in categories]
    assert ids == ["rings", "amino_acids", "nucleobases", "sugars"]
    assert all(c.origin is TemplateOrigin.SHIPPED for c in categories)
    entry_ids = [e.id for c in categories for e in c.entries]
    assert len(entry_ids) == len(set(entry_ids))
    assert all(e.kind is TemplateKind.COMPLETE_MOLECULE for c in categories for e in c.entries)
    assert all(e.smiles and not e.molblock for c in categories for e in c.entries)


def test_every_shipped_entry_makes_a_2d_molblock_without_dummy_atoms():
    engine = ChemistryEngine()
    for category in load_shipped(engine):
        for entry in category.entries:
            molblock = molblock_for(entry, engine)
            mol = engine.mol_from_molblock(molblock)
            assert mol.GetNumConformers() == 1
            assert all(atom.GetAtomicNum() > 0 for atom in mol.GetAtoms())
            assert bounds_2d(molblock) is not None


def test_an_entry_with_both_smiles_and_molblock_is_refused():
    try:
        TemplateEntry(
            id="x",
            name="X",
            category_id="rings",
            smiles="C",
            molblock="\n\n\n  0  0  0  0  0  0            999 V2000\nM  END\n",
        )
    except TemplateError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("expected TemplateError")


def test_l_alanine_keeps_its_stereochemistry():
    engine = ChemistryEngine()
    [amino] = [c for c in load_shipped(engine) if c.id == "amino_acids"]
    [alanine] = [e for e in amino.entries if e.id == "amino_acids.l_alanine"]
    mol = engine.mol_from_molblock(molblock_for(alanine, engine))
    chiral = [a for a in mol.GetAtoms() if a.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED]
    assert len(chiral) == 1
    smiles = engine.molblock_to_smiles(molblock_for(alanine, engine))
    assert "@" in smiles


def test_the_two_glucopyranose_anomers_are_different_molecules():
    engine = ChemistryEngine()
    [sugars] = [c for c in load_shipped(engine) if c.id == "sugars"]
    alpha = next(e for e in sugars.entries if "alpha" in e.id)
    beta = next(e for e in sugars.entries if "beta" in e.id)
    assert engine.molblock_to_smiles(molblock_for(alpha, engine)) != engine.molblock_to_smiles(
        molblock_for(beta, engine)
    )


def test_place_to_the_right_does_not_overlap_or_move_the_canvas():
    engine = ChemistryEngine()
    [rings] = [c for c in load_shipped(engine) if c.id == "rings"]
    benzene = next(e for e in rings.entries if e.id == "rings.benzene")
    canvas = molblock_for(benzene, engine)
    fragment = molblock_for(next(e for e in rings.entries if e.id == "rings.pyridine"), engine)
    placed = place_to_the_right(canvas, fragment)
    canvas_box = bounds_2d(canvas)
    placed_box = bounds_2d(placed)
    original_box = bounds_2d(fragment)
    assert canvas_box is not None and placed_box is not None and original_box is not None
    assert placed_box[0] >= canvas_box[1] + PLACEMENT_GAP_ANGSTROM - 1e-6
    width = original_box[1] - original_box[0]
    assert abs((placed_box[1] - placed_box[0]) - width) < 1e-4
    assert bounds_2d(canvas) == canvas_box


def test_place_on_an_empty_canvas_leaves_the_template_coordinates():
    engine = ChemistryEngine()
    [rings] = [c for c in load_shipped(engine) if c.id == "rings"]
    benzene = molblock_for(next(e for e in rings.entries if e.id == "rings.benzene"), engine)
    assert place_to_the_right("", benzene) == benzene


def test_a_dummy_atom_fragment_is_refused():
    entry = TemplateEntry(
        id="bad.star",
        name="Methyl wildcard",
        category_id="user:x",
        smiles="*C",
    )
    try:
        molblock_for(entry)
    except TemplateError as exc:
        assert "dummy" in str(exc).casefold() or "wildcard" in str(exc).casefold()
    else:
        raise AssertionError("expected TemplateError")


def test_search_matches_name_and_tags():
    entry = TemplateEntry(
        id="rings.benzene",
        name="Benzene",
        category_id="rings",
        smiles="c1ccccc1",
        tags=("aromatic", "six-membered ring"),
        description="A six-carbon aromatic ring.",
    )
    assert entry.matches("benzene")
    assert entry.matches("AROMATIC")
    assert entry.matches("six-membered")
    assert not entry.matches("glucose")
