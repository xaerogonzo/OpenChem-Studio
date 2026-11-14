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
    assert ids == [
        "rings",
        "amino_acids",
        "nucleobases",
        "sugars",
        "cycloalkanes",
        "heterocycles",
        "solvents_reagents",
        "alkaloids",
        "flavonoids",
        "vitamins",
        "functional_groups",
        "polycycles",
        "peptide_building_blocks",
        "allotropes",
        "reactive_species",
    ]
    assert all(c.origin is TemplateOrigin.SHIPPED for c in categories)
    entry_ids = [e.id for c in categories for e in c.entries]
    assert len(entry_ids) == len(set(entry_ids))
    assert all(e.kind is TemplateKind.COMPLETE_MOLECULE for c in categories for e in c.entries)
    assert all(e.smiles and not e.molblock for c in categories for e in c.entries)


def test_first_promotion_ids_are_shipped_once_and_not_the_research_dump():
    from pathlib import Path

    research = Path("docs/STRUCTURE_TEMPLATE_CANDIDATES.json")
    assert research.is_file()
    assert not (SHIPPED_DIR / "STRUCTURE_TEMPLATE_CANDIDATES.json").exists()
    assert (SHIPPED_DIR / "cycloalkanes.json").is_file()
    assert (SHIPPED_DIR / "heterocycles.json").is_file()
    assert (SHIPPED_DIR / "solvents_reagents.json").is_file()

    by_category = {c.id: [e.id for e in c.entries] for c in load_shipped()}
    assert by_category["cycloalkanes"] == [
        "cycloalkanes.cyclopropane",
        "cycloalkanes.cyclobutane",
        "cycloalkanes.methylcyclopentane",
        "cycloalkanes.methylcyclohexane",
        "cycloalkanes.cycloheptane",
        "cycloalkanes.cyclooctane",
        "cycloalkanes.cyclononane",
        "cycloalkanes.cyclodecane",
        "cycloalkanes.cycloundecane",
        "cycloalkanes.cyclododecane",
    ]
    assert "cycloalkanes.cyclopentane" not in by_category["cycloalkanes"]
    assert "cycloalkanes.cyclohexane" not in by_category["cycloalkanes"]
    assert "rings.cyclopentane" in by_category["rings"]
    assert "rings.cyclohexane" in by_category["rings"]
    for stem in (
        "pyrimidine",
        "imidazole",
        "morpholine",
        "piperidine",
        "quinoline",
        "hypoxanthine",
    ):
        assert f"heterocycles.{stem}" in by_category["heterocycles"]
    assert "heterocycles.pyridine" not in by_category["heterocycles"]
    assert "heterocycles.caffeine" not in by_category["heterocycles"]
    assert "heterocycles.morphine" not in by_category["heterocycles"]
    for stem in ("water", "ethanol", "acetone", "tetrahydrofuran", "1_4_dioxane"):
        assert f"solvents_reagents.{stem}" in by_category["solvents_reagents"]
    assert "sugars.alpha_d_galactopyranose" in by_category["sugars"]
    assert "sugars.beta_d_mannopyranose" in by_category["sugars"]
    assert "sugars.alpha_d_ribofuranose" in by_category["sugars"]
    assert "nucleobases.adenosine" in by_category["nucleobases"]
    assert "nucleobases.thymidine" in by_category["nucleobases"]
    assert "amino_acids.l_ornithine" in by_category["amino_acids"]
    assert "amino_acids.l_selenocysteine" in by_category["amino_acids"]
    assert "alkaloids.mescaline" in by_category["alkaloids"]
    assert "alkaloids.hordenine" in by_category["alkaloids"]
    assert "alkaloids.caffeine" in by_category["alkaloids"]
    assert "alkaloids.morphine" not in by_category["alkaloids"]
    assert "flavonoids.flavone" in by_category["flavonoids"]
    assert "vitamins.ascorbic_acid" in by_category["vitamins"]
    assert "functional_groups.phenol" in by_category["functional_groups"]
    assert "polycycles.adamantane" in by_category["polycycles"]
    assert "peptide_building_blocks.fmoc_glycine" in by_category["peptide_building_blocks"]
    assert "allotropes.singlet_oxygen" in by_category["allotropes"]
    assert "allotropes.triplet_oxygen" in by_category["allotropes"]
    assert "allotropes.ozone" in by_category["allotropes"]
    assert "allotropes.cyclooctasulfur" in by_category["allotropes"]
    assert "allotropes.tetraphosphorus" in by_category["allotropes"]
    assert "reactive_species.superoxide" in by_category["reactive_species"]
    assert "reactive_species.hydroxyl" in by_category["reactive_species"]
    assert "reactive_species.nitric_oxide" in by_category["reactive_species"]


def test_shipped_entries_that_match_candidates_keep_verified_identity_and_reviewed_stereo():
    import json
    from pathlib import Path

    from rdkit.Chem.inchi import MolToInchiKey

    raw = json.loads(Path("docs/STRUCTURE_TEMPLATE_CANDIDATES.json").read_text(encoding="utf-8"))
    candidates = {entry["id"]: entry for entry in raw["entries"]}
    engine = ChemistryEngine()
    allowed_stereo = {"verified", "not_applicable"}
    matched = 0
    for category in load_shipped(engine):
        for entry in category.entries:
            stem = entry.id.split(".", 1)[1]
            candidate = candidates.get(stem)
            if candidate is None:
                continue
            matched += 1
            assert candidate["identity"]["status"] == "verified", entry.id
            stereo = candidate["structure_form"]["stereochemistry"]["status"]
            named_nucleoside = stem in {
                "adenosine",
                "guanosine",
                "cytidine",
                "uridine",
                "inosine",
                "deoxyadenosine",
                "deoxyguanosine",
                "deoxycytidine",
                "thymidine",
            }
            if named_nucleoside:
                assert stereo in allowed_stereo | {"not_reviewed"}, entry.id
            else:
                assert stereo in allowed_stereo, f"{entry.id} stereo {stereo}"
            assert candidate["validation"]["editor_eligible"] is True, entry.id
            mol = engine.mol_from_smiles(entry.smiles)
            assert MolToInchiKey(mol) == candidate["inchikey"], entry.id
    assert matched >= 34


def test_allotrope_and_reactive_species_identities_are_the_pubchem_records():
    from rdkit.Chem.inchi import MolToInchiKey

    engine = ChemistryEngine()
    by_id = {e.id: e for c in load_shipped(engine) for e in c.entries}
    expected = {
        "allotropes.singlet_oxygen": "MYMOFIZGZYHOMD-UHFFFAOYSA-N",
        "allotropes.ozone": "CBENFWSGALASAD-UHFFFAOYSA-N",
        "allotropes.atomic_oxygen": "QVGXLLKOCUKJST-UHFFFAOYSA-N",
        "allotropes.cyclooctasulfur": "JLQNHALFVCURHW-UHFFFAOYSA-N",
        "allotropes.hexasulfur": "FEXCMMPRRBSCRG-UHFFFAOYSA-N",
        "allotropes.tetraphosphorus": "OBSZRRSYVTXPNB-UHFFFAOYSA-N",
        "reactive_species.superoxide": "MXDZWXWHPVATGF-UHFFFAOYSA-N",
        "reactive_species.hydroxyl": "TUJKJAMUKRIRHC-UHFFFAOYSA-N",
        "reactive_species.hydrogen_peroxide": "MHAJPDPJQMAIIY-UHFFFAOYSA-N",
        "reactive_species.nitric_oxide": "MWUXSHHQAYIFBG-UHFFFAOYSA-N",
        "reactive_species.nitrogen_dioxide": "JCXJVPUVTGWSNB-UHFFFAOYSA-N",
        "reactive_species.nitrous_oxide": "GQPLMRYTRLFLPF-UHFFFAOYSA-N",
    }
    for entry_id, key in expected.items():
        mol = engine.mol_from_smiles(by_id[entry_id].smiles)
        assert MolToInchiKey(mol) == key, entry_id
    triplet = engine.mol_from_smiles(by_id["allotropes.triplet_oxygen"].smiles)
    singlet = engine.mol_from_smiles(by_id["allotropes.singlet_oxygen"].smiles)
    assert sum(a.GetNumRadicalElectrons() for a in triplet.GetAtoms()) == 2
    assert sum(a.GetNumRadicalElectrons() for a in singlet.GetAtoms()) == 0
    assert by_id["allotropes.triplet_oxygen"].smiles != by_id["allotropes.singlet_oxygen"].smiles
    # InChIKey is the same connectivity layer for both drawings. The Lewis forms differ.


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


def test_the_two_galactopyranose_anomers_are_different_molecules():
    engine = ChemistryEngine()
    [sugars] = [c for c in load_shipped(engine) if c.id == "sugars"]
    alpha = next(e for e in sugars.entries if e.id == "sugars.alpha_d_galactopyranose")
    beta = next(e for e in sugars.entries if e.id == "sugars.beta_d_galactopyranose")
    assert engine.molblock_to_smiles(molblock_for(alpha, engine)) != engine.molblock_to_smiles(
        molblock_for(beta, engine)
    )


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
