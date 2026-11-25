"""Shipped structure templates parse, render, and stay complete molecules."""

from __future__ import annotations

import json
from pathlib import Path

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
    SHIPPED_CATEGORY_GROUPS,
    TemplateEntry,
    TemplateError,
    TemplateKind,
    TemplateOrigin,
    nested_category_groups,
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
        "coordination_complexes",
        "alkaloids",
        "flavonoids",
        "vitamins",
        "functional_groups",
        "polycycles",
        "peptide_building_blocks",
        "allotropes",
        "reactive_species",
        "cofactors",
        "terpenoids_steroids",
    ]
    assert all(c.origin is TemplateOrigin.SHIPPED for c in categories)
    entry_ids = [e.id for c in categories for e in c.entries]
    assert len(entry_ids) == len(set(entry_ids))
    assert all(e.kind is TemplateKind.COMPLETE_MOLECULE for c in categories for e in c.entries)
    for entry in (e for c in categories for e in c.entries):
        has_smiles = bool(entry.smiles and entry.smiles.strip())
        has_molblock = bool(entry.molblock and entry.molblock.strip())
        assert has_smiles != has_molblock, entry.id
    # A molblock-only entry is a connected coordination drawing or a curated
    # layout (an RDKit depiction that was bad); everything else is a SMILES.
    assert all(
        e.smiles and not e.molblock
        for c in categories
        for e in c.entries
        if c.id != "coordination_complexes" and e.id not in CURATED_LAYOUT_IDS
    )
    assert all(
        e.molblock and not e.smiles
        for c in categories
        for e in c.entries
        if c.id == "coordination_complexes" or e.id in CURATED_LAYOUT_IDS
    )

#: Entries whose 2D drawing is a hand-curated molblock instead of RDKit's layout.
#: The SMILES of each one that `tools/curate_template_layouts.py` replaced are
#: pinned in a fixture, which is the identity the drawing is checked against.
CURATED_SMILES = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "curated_template_smiles.json").read_text(encoding="utf-8")
)
def smiles_of(entry) -> str:
    """The entry's SMILES, or the pinned one for an entry that holds a curated drawing."""
    return entry.smiles or CURATED_SMILES[entry.id]


CURATED_LAYOUT_IDS = {"allotropes.buckminsterfullerene", *CURATED_SMILES}
#: A curated drawing may still stretch one bond (a cage's outer face) but never overlap or cross.
CURATED_MAX_BOND_RATIO = 4.2

C60_SMILES = "c12c3c4c5c1c1c6c7c2c2c8c3c3c9c4c4c%10c5c5c1c1c6c6c%11c7c2c2c7c8c3c3c8c9c4c4c9c%10c5c5c1c1c6c6c%11c2c2c7c3c3c8c4c4c9c5c1c1c6c2c3c41"


def test_curated_c60_is_still_c60_and_drawn_flat_without_crossings():
    from rdkit.Chem.inchi import MolToInchiKey

    import importlib.util
    import sys
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "template_layout_check", Path(__file__).resolve().parents[1] / "tools" / "template_layout_check.py"
    )
    checker = importlib.util.module_from_spec(spec)
    sys.modules["template_layout_check"] = checker
    spec.loader.exec_module(checker)
    layout_of_molblock = checker.layout_of_molblock

    engine = ChemistryEngine()
    by_id = {e.id: e for c in load_shipped(engine) for e in c.entries}
    entry = by_id["allotropes.buckminsterfullerene"]
    assert entry.molblock and not entry.smiles
    block = molblock_for(entry, engine)
    mol = engine.mol_from_molblock(block)
    reference = engine.mol_from_smiles(C60_SMILES)
    assert mol.GetNumAtoms() == 60 and mol.GetNumBonds() == 90
    assert MolToInchiKey(mol) == MolToInchiKey(reference) == "XMWRBQBLMFGWIX-UHFFFAOYSA-N"
    assert engine.molblock_to_smiles(block) == engine.molblock_to_smiles(
        molblock_for(entry, engine)
    )
    layout = layout_of_molblock(block)
    assert layout.crossings == 0
    assert layout.min_atom_gap > 0.5
    assert not {"overlap", "crossing"} & set(layout.flags)
    assert "2D" in block.splitlines()[1]


def _layout_checker():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "template_layout_check", Path(__file__).resolve().parents[1] / "tools" / "template_layout_check.py"
    )
    checker = importlib.util.module_from_spec(spec)
    sys.modules["template_layout_check"] = checker
    spec.loader.exec_module(checker)
    return checker


def test_curated_templates_keep_their_identity_and_are_drawn_without_overlap_or_crossing():
    from rdkit.Chem.inchi import MolToInchiKey

    checker = _layout_checker()
    engine = ChemistryEngine()
    by_id = {e.id: e for c in load_shipped(engine) for e in c.entries}
    assert len(CURATED_SMILES) >= 50
    for template_id, smiles in CURATED_SMILES.items():
        entry = by_id[template_id]
        assert entry.molblock and not entry.smiles, template_id
        block = molblock_for(entry, engine)
        expected = engine.mol_from_smiles(smiles)
        assert MolToInchiKey(engine.mol_from_molblock(block)) == MolToInchiKey(expected), template_id
        assert engine.molblock_to_smiles(block) == engine.molblock_to_smiles(
            molblock_for(
                TemplateEntry(id="x", name="x", category_id=entry.category_id, smiles=smiles), engine
            )
        ), template_id
        layout = checker.layout_of_molblock(block)
        assert not {"overlap", "crossing"} & set(layout.flags), (template_id, layout)
        assert layout.bond_ratio <= CURATED_MAX_BOND_RATIO, (template_id, layout)


#: naloxone and naltrexone: the N-substituent still crosses the ring system in every drawing tried;
#: barbaralane: its graph is not planar, so any flat drawing crosses. They keep their RDKit
#: drawing. (No test pins the whole screen result: a SMILES-only entry's layout is RDKit's, and
#: it differs between RDKit builds -- CI flagged methadone where a local run did not.)
LEFT_ALONE_HARD_FLAGS = {"alkaloids.naloxone", "alkaloids.naltrexone", "polycycles.barbaralane"}


def test_the_left_alone_templates_are_still_smiles_only_and_not_listed_as_curated():
    by_id = {e.id: e for c in load_shipped() for e in c.entries}
    for template_id in LEFT_ALONE_HARD_FLAGS:
        assert by_id[template_id].smiles and not by_id[template_id].molblock
        assert template_id not in CURATED_LAYOUT_IDS


def test_every_shipped_category_sits_in_exactly_one_dialog_group():
    grouped = [cid for _title, ids in SHIPPED_CATEGORY_GROUPS for cid in ids]
    assert grouped == list(dict.fromkeys(grouped))
    assert set(grouped) == {c.id for c in load_shipped()}
    trees = nested_category_groups(load_shipped())
    assert [title for title, _cats in trees] == [title for title, ids in SHIPPED_CATEGORY_GROUPS if ids]
    by_group = {title: [c.id for c in cats] for title, cats in trees}
    assert by_group["Scaffolds"][0] == "rings"
    assert "amino_acids" in by_group["Building blocks"]
    assert "alkaloids" in by_group["Natural products"]
    assert by_group["Laboratory"] == ["solvents_reagents", "coordination_complexes"]


def test_first_promotion_ids_are_shipped_once_and_not_the_research_dump():
    from pathlib import Path

    research = Path("docs/STRUCTURE_TEMPLATE_CANDIDATES.json")
    assert research.is_file()
    assert not (SHIPPED_DIR / "STRUCTURE_TEMPLATE_CANDIDATES.json").exists()
    assert (SHIPPED_DIR / "cycloalkanes.json").is_file()
    assert (SHIPPED_DIR / "heterocycles.json").is_file()
    assert (SHIPPED_DIR / "solvents_reagents.json").is_file()
    assert (SHIPPED_DIR / "coordination_complexes.json").is_file()

    by_category = {c.id: [e.id for e in c.entries] for c in load_shipped()}
    first_cycloalkanes = [
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
    assert by_category["cycloalkanes"][:10] == first_cycloalkanes
    assert set(first_cycloalkanes) <= set(by_category["cycloalkanes"])
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
    assert "alkaloids.morphine" in by_category["alkaloids"]
    assert "alkaloids.codeine" in by_category["alkaloids"]
    assert "alkaloids.cocaine" in by_category["alkaloids"]
    assert "alkaloids.nicotine" in by_category["alkaloids"]
    assert "alkaloids.quinine" in by_category["alkaloids"]
    assert "alkaloids.strychnine" in by_category["alkaloids"]
    assert "alkaloids.colchicine" in by_category["alkaloids"]
    assert "alkaloids.atropine" in by_category["alkaloids"]
    assert "alkaloids.hyoscyamine" in by_category["alkaloids"]
    assert "alkaloids.scopolamine" in by_category["alkaloids"]
    assert "vitamins.biotin" in by_category["vitamins"]
    assert "flavonoids.naringenin" in by_category["flavonoids"]
    assert "polycycles.norbornene" in by_category["polycycles"]
    assert "polycycles.fluoranthene" in by_category["polycycles"]
    assert "polycycles.chrysene" in by_category["polycycles"]
    assert "polycycles.perylene" in by_category["polycycles"]
    assert "polycycles.coronene" in by_category["polycycles"]
    assert "polycycles.acenaphthene" in by_category["polycycles"]
    assert "polycycles.bicyclo_2_2_2_octane" in by_category["polycycles"]
    assert "polycycles.bicyclo_1_1_1_pentane" in by_category["polycycles"]
    assert "polycycles.barrelene" in by_category["polycycles"]
    assert "heterocycles.21_crown_7" in by_category["heterocycles"]
    assert "heterocycles.dibenzo_18_crown_6" in by_category["heterocycles"]
    assert "heterocycles.benzo_15_crown_5" in by_category["heterocycles"]
    assert "heterocycles.1_10_diaza_18_crown_6" in by_category["heterocycles"]
    assert "cofactors.atp" in by_category["cofactors"]
    assert "cofactors.nad" in by_category["cofactors"]
    assert "terpenoids_steroids.cholesterol" in by_category["terpenoids_steroids"]
    assert "terpenoids_steroids.camphor" in by_category["terpenoids_steroids"]
    assert "terpenoids_steroids.beta_carotene" in by_category["terpenoids_steroids"]
    assert "terpenoids_steroids.r_limonene" in by_category["terpenoids_steroids"]
    assert "terpenoids_steroids.camphene" not in by_category.get("terpenoids_steroids", [])
    assert "solvents_reagents.n_n_dimethylformamide" in by_category["solvents_reagents"]
    assert "functional_groups.acetylsalicylic_acid" in by_category["functional_groups"]
    assert "functional_groups.oleic_acid" in by_category["functional_groups"]
    assert "heterocycles.allopurinol" in by_category["heterocycles"]
    assert "cofactors.amp" in by_category["cofactors"]
    assert "cofactors.gtp" in by_category["cofactors"]
    assert "sugars.sucrose" in by_category["sugars"]
    assert "solvents_reagents.edc" in by_category["solvents_reagents"]
    assert "functional_groups.diclofenac" in by_category["functional_groups"]
    assert "functional_groups.pimelic_acid" in by_category["functional_groups"]
    assert "heterocycles.sildenafil" in by_category["heterocycles"]
    assert "sugars.alpha_alpha_trehalose" in by_category["sugars"]
    assert "polycycles.cis_decahydronaphthalene" in by_category["polycycles"]
    assert "polycycles.trans_decahydronaphthalene" in by_category["polycycles"]
    assert "terpenoids_steroids.plus_camphene" in by_category["terpenoids_steroids"]
    assert "heterocycles.captopril" in by_category["heterocycles"]
    assert "functional_groups.propofol" in by_category["functional_groups"]
    assert "cycloalkanes.cis_1_4_dimethylcyclohexane" in by_category["cycloalkanes"]
    assert "functional_groups.bisphenol_a" in by_category["functional_groups"]
    assert "heterocycles.atrazine" in by_category["heterocycles"]
    assert "functional_groups.deet" in by_category["functional_groups"]
    assert "functional_groups.ninhydrin" in by_category["functional_groups"]
    assert "allotropes.buckminsterfullerene" in by_category["allotropes"]
    assert by_category["coordination_complexes"] == [
        "coordination_complexes.cisplatin",
        "coordination_complexes.transplatin",
        "coordination_complexes.carboplatin",
        "coordination_complexes.oxaliplatin",
        "coordination_complexes.cis_ptcl2_en",
    ]
    assert "coordination_complexes.ferrocene" not in by_category.get("coordination_complexes", [])
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
            if candidate["validation"].get("editor_eligible") is not True:
                # Parked research rows (disconnected coordination SMILES) are
                # not the shipped drawing.
                continue
            matched += 1
            assert candidate["identity"]["status"] == "verified", entry.id
            stereo = candidate["structure_form"]["stereochemistry"]["status"]
            assert stereo in allowed_stereo, f"{entry.id} stereo {stereo}"
            if entry.smiles:
                mol = engine.mol_from_smiles(entry.smiles)
            else:
                mol = engine.mol_from_molblock(molblock_for(entry, engine))
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
        mol = engine.mol_from_smiles(smiles_of(by_id[entry_id]))
        assert MolToInchiKey(mol) == key, entry_id
    triplet = engine.mol_from_smiles(by_id["allotropes.triplet_oxygen"].smiles)
    singlet = engine.mol_from_smiles(by_id["allotropes.singlet_oxygen"].smiles)
    assert sum(a.GetNumRadicalElectrons() for a in triplet.GetAtoms()) == 2
    assert sum(a.GetNumRadicalElectrons() for a in singlet.GetAtoms()) == 0
    assert by_id["allotropes.triplet_oxygen"].smiles != by_id["allotropes.singlet_oxygen"].smiles
    # InChIKey is the same connectivity layer for both drawings. The Lewis forms differ.


def _cl_pt_cl_class(molblock: str) -> str:
    import math

    mol = Chem.MolFromMolBlock(molblock, sanitize=False, removeHs=False)
    assert mol is not None
    mol.UpdatePropertyCache(strict=False)
    pt = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "Pt")
    chlorines = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "Cl"]
    assert len(chlorines) == 2
    conf = mol.GetConformer()
    centre = conf.GetAtomPosition(pt)
    a = conf.GetAtomPosition(chlorines[0])
    b = conf.GetAtomPosition(chlorines[1])
    va = (a.x - centre.x, a.y - centre.y)
    vb = (b.x - centre.x, b.y - centre.y)
    cosine = (va[0] * vb[0] + va[1] * vb[1]) / (math.hypot(*va) * math.hypot(*vb))
    angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
    if 50.0 <= angle <= 130.0:
        return "cis"
    if angle >= 150.0:
        return "trans"
    return "unknown"


def _dative_to_pt(molblock: str) -> int:
    mol = Chem.MolFromMolBlock(molblock, sanitize=False, removeHs=False)
    assert mol is not None
    mol.UpdatePropertyCache(strict=False)
    n = 0
    for bond in mol.GetBonds():
        if bond.GetBondType() != Chem.BondType.DATIVE:
            continue
        if bond.GetBeginAtom().GetSymbol() == "Pt" or bond.GetEndAtom().GetSymbol() == "Pt":
            n += 1
    return n


def test_platinum_templates_are_connected_cis_and_trans_drawings():
    engine = ChemistryEngine()
    [category] = [c for c in load_shipped(engine) if c.id == "coordination_complexes"]
    by_id = {e.id: e for e in category.entries}
    cisplatin = molblock_for(by_id["coordination_complexes.cisplatin"], engine)
    transplatin = molblock_for(by_id["coordination_complexes.transplatin"], engine)
    carboplatin = molblock_for(by_id["coordination_complexes.carboplatin"], engine)
    oxaliplatin = molblock_for(by_id["coordination_complexes.oxaliplatin"], engine)
    ptcl2_en = molblock_for(by_id["coordination_complexes.cis_ptcl2_en"], engine)
    assert _cl_pt_cl_class(cisplatin) == "cis"
    assert _cl_pt_cl_class(transplatin) == "trans"
    assert _cl_pt_cl_class(ptcl2_en) == "cis"
    assert _dative_to_pt(carboplatin) == 4
    assert _dative_to_pt(oxaliplatin) == 4
    cis_mol = engine.mol_from_molblock(cisplatin)
    assert len(Chem.GetMolFrags(cis_mol)) == 1
    assert sum(1 for a in cis_mol.GetAtoms() if a.GetSymbol() == "Pt") == 1
    ox_mol = Chem.MolFromMolBlock(oxaliplatin, sanitize=False, removeHs=False)
    assert ox_mol is not None
    ox_mol.UpdatePropertyCache(strict=False)
    chiral = [a for a in ox_mol.GetAtoms() if a.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED]
    assert len(chiral) == 2


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


def test_morphine_keeps_its_stereochemistry():
    engine = ChemistryEngine()
    [alkaloids] = [c for c in load_shipped(engine) if c.id == "alkaloids"]
    morphine = next(e for e in alkaloids.entries if e.id == "alkaloids.morphine")
    smiles = engine.molblock_to_smiles(molblock_for(morphine, engine))
    assert "@" in smiles


def test_tropane_templates_draw_default_up_down_bonds():
    from rdkit.Chem.inchi import MolToInchiKey

    engine = ChemistryEngine()
    [alkaloids] = [c for c in load_shipped(engine) if c.id == "alkaloids"]
    by_id = {e.id: e for e in alkaloids.entries}
    atropine = by_id["alkaloids.atropine"]
    hyoscyamine = by_id["alkaloids.hyoscyamine"]
    scopolamine = by_id["alkaloids.scopolamine"]
    atropine_block = molblock_for(atropine, engine)
    bond_stereo = [
        line[9:12].strip()
        for line in atropine_block.splitlines()
        if len(line) >= 12 and line[0:3].strip().isdigit() and line[3:6].strip().isdigit()
    ]
    assert {"1", "6"} & set(bond_stereo)
    assert MolToInchiKey(engine.mol_from_smiles(smiles_of(atropine))) == "RKUNBYITZUJHSG-SPUOUPEWSA-N"
    hyoscyamine_mol = engine.mol_from_smiles(smiles_of(hyoscyamine))
    scopolamine_mol = engine.mol_from_smiles(smiles_of(scopolamine))
    assert MolToInchiKey(hyoscyamine_mol).startswith("RKUNBYITZUJHSG-")
    assert MolToInchiKey(hyoscyamine_mol) == "RKUNBYITZUJHSG-FXUDXRNXSA-N"
    assert MolToInchiKey(scopolamine_mol) == "STECJAGHUSJQJN-FWXGHANASA-N"
    assert all("@" in smiles_of(e) for e in (atropine, hyoscyamine, scopolamine))


def test_camphor_is_the_verified_1r_4r_identity():
    from rdkit.Chem.inchi import MolToInchiKey

    engine = ChemistryEngine()
    by_id = {e.id: e for c in load_shipped(engine) for e in c.entries}
    camphor = by_id["terpenoids_steroids.camphor"]
    assert camphor.name == "(1R,4R)-Camphor"
    assert MolToInchiKey(engine.mol_from_smiles(smiles_of(camphor))) == "DSSYKIVIOFKYAU-XCBNKYQSSA-N"
    smiles = engine.molblock_to_smiles(molblock_for(camphor, engine))
    assert "@" in smiles


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
