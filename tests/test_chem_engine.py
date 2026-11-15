from __future__ import annotations

import pytest

from openchem.chem.engine import ChemistryEngine, InvalidStructureError
from openchem.domain.molecule import MoleculeModel


def test_set_structure_from_smiles_canonicalizes():
    engine = ChemistryEngine()
    model = MoleculeModel()

    engine.set_structure_from_smiles(model, "C1=CC=CC=C1")

    assert model.canonical_smiles == "c1ccccc1"
    assert model.inchikey == "UHOVQNZJYSORNB-UHFFFAOYSA-N"
    assert model.molblock is not None


def test_molblock_roundtrip_preserves_identity():
    engine = ChemistryEngine()
    original = MoleculeModel()
    engine.set_structure_from_smiles(original, "CCO")

    reloaded = MoleculeModel()
    engine.set_structure_from_molblock(reloaded, original.molblock)

    assert reloaded.canonical_smiles == original.canonical_smiles
    assert reloaded.inchikey == original.inchikey


def test_invalid_smiles_raises():
    engine = ChemistryEngine()
    model = MoleculeModel()

    with pytest.raises(InvalidStructureError):
        engine.set_structure_from_smiles(model, "not a smiles!!")


def test_mol_from_model_without_molblock_raises():
    engine = ChemistryEngine()
    model = MoleculeModel()

    with pytest.raises(InvalidStructureError):
        engine.mol_from_model(model)


def test_mol_from_molblock_preserves_explicit_hydrogen_positions():
    """Regression test: confirmed live against a real ORCA install that
    RDKit's Chem.MolFromMolBlock defaults to removeHs=True, which folds
    every explicit hydrogen into implicit H-count on its neighbor -- correct
    for the molecular formula, but it silently discards that hydrogen's own
    3D position. A conformer molblock built via Chem.AddHs() + embedding
    (RDKitConformerProvider's normal path for real 3D geometry) round-
    tripped through the old default came back as a bare heavy-atom-only mol
    with NO hydrogen atoms at all -- for water, an oxygen atom instead of
    H2O -- which OrcaQuantumEngineProvider then silently sent to ORCA as-is,
    computing the wrong molecule's energy instead of failing loudly.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol_3d = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=42)
    molblock = Chem.MolToMolBlock(mol_3d)

    engine = ChemistryEngine()
    roundtripped = engine.mol_from_molblock(molblock)

    assert roundtripped.GetNumAtoms() == 3  # O + 2 H, not just O
    symbols = sorted(atom.GetSymbol() for atom in roundtripped.GetAtoms())
    assert symbols == ["H", "H", "O"]


def _ethanol_molblock() -> str:
    """Ethanol as the 2D editor holds it: three heavy atoms, hydrogens
    implicit. The molecule the crash below was measured on."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles("CCO")
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


def test_render_2d_svg_ignores_out_of_range_atom_indices():
    """An out-of-range highlight index used to lose the WHOLE depiction.

    `atom_colors` went to `PrepareAndDrawMolecule(highlightAtoms=...)`
    unguarded while `atom_labels` was already range-checked, so a single
    surplus index raised `ValueError: list element larger than allowed
    value` and nothing rendered at all.

    Equality against the in-range-only rendering is the assertion, rather
    than "no exception": it pins down that the surplus indices are dropped
    and the legitimate ones still take effect, which "it didn't crash"
    would also pass if the guard threw the highlights away entirely.
    """
    engine = ChemistryEngine()
    molblock = _ethanol_molblock()  # 3 atoms, valid indices 0-2

    plain = engine.render_2d_svg(molblock)
    in_range_only = engine.render_2d_svg(molblock, {1: "#ff0000"}, {1: "1.23"})
    with_surplus = engine.render_2d_svg(
        molblock,
        {1: "#ff0000", 8: "#00ff00", -1: "#0000ff"},
        {1: "1.23", 8: "9.99", -1: "0.00"},
    )

    assert with_surplus == in_range_only
    assert in_range_only != plain  # the in-range highlight/label did land


def test_render_2d_svg_survives_a_hydrogen_bearing_calculator_result():
    """The real path this guard exists for, end to end.

    `compute_atomic_polarizability` runs on `Chem.AddHs(mol)` and returns a
    value for every hydrogen -- measured: 9 values for ethanol's 3 drawable
    atoms -- and the Calculator Inspector feeds that dataset's layer
    straight into `render_2d_svg` alongside the editor molblock. Built from
    the live calculator rather than a hand-written dict so the test fails if
    that producer's index space ever changes.
    """
    from rdkit import Chem

    from openchem.chem.electronic_properties import compute_atomic_polarizability
    from openchem.ui.visualization import build_visualization_layer

    engine = ChemistryEngine()
    molblock = _ethanol_molblock()
    dataset = compute_atomic_polarizability(
        Chem.MolFromMolBlock(molblock, removeHs=False), "uuid", {}
    )
    assert max(dataset.values) >= 3  # the overrun is real, not assumed

    layer = build_visualization_layer(dataset, include_labels=True)
    svg = engine.render_2d_svg(molblock, layer.atom_colors, layer.atom_labels)

    assert svg.startswith("<?xml")


# --- the 2D property heat map -------------------------------------------
#
# Asserting "something got drawn" is worthless here: the depiction is
# opaque and full of black bond strokes before the field adds a single
# pixel, so any pixel-count check passes a blanked contour call. What
# CANNOT pass a blanked or sign-inverted implementation is WHERE the two
# extreme colours land -- so these tests hold the molecule and the layout
# fixed, put a negative weight at one end of a chain and a positive one at
# the other, and check which end went red.


def _raster(svg: str, width: int = 420, height: int = 360):
    """Rasterise through the SAME Qt renderer the dialog uses.

    Not RDKit's Cairo backend: Qt's SVG support is Tiny 1.2, and the
    contour fill arrives as ~900 separate <path> elements, so "RDKit drew
    it" and "the app can show it" are genuinely different claims.
    """
    import numpy as np
    from PySide6.QtCore import QByteArray
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    assert renderer.isValid(), "Qt could not parse the SVG at all"
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    raw = np.frombuffer(image.constBits(), dtype=np.uint8)
    return raw.reshape(height, width, 4)[:, :, :3][:, :, ::-1].astype(int)


def _extreme_columns(pixels):
    """Mean x of the most red and the most blue pixels.

    A mean over the strongly-tinted pixels rather than a single argmax,
    so one stray antialiased pixel on a bond cannot decide the result.
    """
    import numpy as np

    redness = pixels[:, :, 0] - pixels[:, :, 2]
    xs = np.tile(np.arange(pixels.shape[1]), (pixels.shape[0], 1))
    red = redness > 40
    blue = redness < -40
    assert red.any(), "no red region at all -- the field was not drawn"
    assert blue.any(), "no blue region at all -- the field was not drawn"
    return float(xs[red].mean()), float(xs[blue].mean())


def _decane_molblock() -> str:
    from rdkit import Chem
    from rdkit.Chem import rdDepictor

    mol = Chem.MolFromSmiles("CCCCCCCCCC")
    rdDepictor.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


_COLOUR_MAP = [(0.83, 0.18, 0.18), (1.0, 1.0, 1.0), (0.10, 0.46, 0.82)]


def test_a_negative_weight_renders_red_and_a_positive_one_blue(qapp):
    """The sign convention, anchored ABSOLUTELY rather than relatively.

    An earlier version of this test rendered a negative and a positive
    atom together and asserted only that swapping them swapped the ends.
    Mutation testing killed it: negating every weight swaps BOTH renders,
    so the relative comparison is invariant under exactly the bug the test
    was written to catch, and it passed the mutant.

    One weight at a time removes the reference frame. A lone negative may
    produce red and no blue at all; a lone positive the reverse. Nothing
    about that survives an inversion.
    """
    import numpy as np

    engine = ChemistryEngine()
    molblock = _decane_molblock()

    def tints(values):
        pixels = _raster(
            engine.render_2d_heatmap_svg(molblock, values, _COLOUR_MAP, width=420, height=360)
        )
        redness = pixels[:, :, 0] - pixels[:, :, 2]
        return bool((redness > 40).any()), bool((redness < -40).any())

    negative_red, negative_blue = tints({0: -1.0})
    positive_red, positive_blue = tints({0: 1.0})

    assert negative_red and not negative_blue, "a lone negative weight must render red only"
    assert positive_blue and not positive_red, "a lone positive weight must render blue only"


def test_the_two_signs_land_at_the_ends_they_belong_to(qapp):
    """Position, given the sign convention the test above pins down: with
    opposite weights at opposite ends of a chain, the red and blue regions
    are far apart and swap when the weights swap. Catches weights being
    read against the wrong atom indices."""
    engine = ChemistryEngine()
    molblock = _decane_molblock()

    red_x, blue_x = _extreme_columns(
        _raster(engine.render_2d_heatmap_svg(molblock, {0: -1.0, 9: 1.0}, _COLOUR_MAP, width=420, height=360))
    )
    swapped_red_x, swapped_blue_x = _extreme_columns(
        _raster(engine.render_2d_heatmap_svg(molblock, {0: 1.0, 9: -1.0}, _COLOUR_MAP, width=420, height=360))
    )

    assert abs(red_x - blue_x) > 100, "the two signs must land at opposite ends"
    assert (red_x < blue_x) != (swapped_red_x < swapped_blue_x)


def test_the_heat_map_differs_from_the_atom_colour_rendering(qapp):
    """Proves the mode is a different picture, not the same one relabelled
    -- a `_render_2d` that ignored the combo would pass everything else."""
    engine = ChemistryEngine()
    molblock = _decane_molblock()

    heat = engine.render_2d_heatmap_svg(molblock, {0: -1.0, 9: 1.0}, _COLOUR_MAP)
    plain = engine.render_2d_svg(molblock, {0: "#d32f2f", 9: "#1976d2"})

    assert heat != plain
    assert heat.count("<path") > plain.count("<path") * 5


def test_an_all_positive_property_reads_as_one_colour(qapp):
    """Measured, not assumed: RDKit centres the contour colour map on zero
    and scales by the largest magnitude, so a property that is never
    negative must not be stretched across the diverging range and shown
    with a false red end."""
    import numpy as np

    engine = ChemistryEngine()

    pixels = _raster(
        engine.render_2d_heatmap_svg(
            _decane_molblock(), {0: 0.2, 9: 1.0}, _COLOUR_MAP, width=420, height=360
        )
    )

    redness = pixels[:, :, 0] - pixels[:, :, 2]
    assert (redness < -40).any(), "the positive values should read blue"
    assert not (redness > 40).any(), "nothing is negative, so nothing may read red"


def test_out_of_range_indices_do_not_crash_the_heat_map(qapp):
    """Same trap `render_2d_svg` already guards: several calculators run on
    `Chem.AddHs(mol)` and return a value per hydrogen, which this
    implicit-hydrogen depiction has no index for."""
    engine = ChemistryEngine()

    svg = engine.render_2d_heatmap_svg(
        _decane_molblock(), {0: -1.0, 9: 1.0, 40: 5.0, -3: 5.0}, _COLOUR_MAP
    )

    assert svg.startswith("<?xml") or "<svg" in svg
    red_x, blue_x = _extreme_columns(_raster(svg))
    assert abs(red_x - blue_x) > 100, "the in-range values must still be drawn"


def test_empty_space_is_left_unpainted(qapp):
    """The grid must not paint its own rectangle.

    Found by looking at the running app: the fill covered the whole grid
    extent, so a hard-edged tinted box sat behind the molecule and stopped
    mid-pane. It was not even neutral -- a per-atom charge dataset omits
    implicit hydrogens, so it sums negative, and the Gaussian tails carried
    that across the grid and tinted empty space pink.

    Asserted at the canvas corner, which is as far from any atom as the
    drawing gets, together with the signal still being present -- a
    threshold set high enough to blank the picture entirely would satisfy
    the first half alone.
    """
    import numpy as np

    engine = ChemistryEngine()

    pixels = _raster(
        engine.render_2d_heatmap_svg(
            _decane_molblock(), {0: -1.0, 9: 1.0}, _COLOUR_MAP, width=420, height=360
        )
    )

    import numpy as np

    from openchem.chem import engine as engine_module

    def wash_and_signal(threshold):
        original = engine_module.HEATMAP_FILL_THRESHOLD
        engine_module.HEATMAP_FILL_THRESHOLD = threshold
        try:
            pixels = _raster(
                engine.render_2d_heatmap_svg(
                    _decane_molblock(), {0: -1.0, 9: 1.0}, _COLOUR_MAP, width=420, height=360
                )
            )
        finally:
            engine_module.HEATMAP_FILL_THRESHOLD = original
        page = (pixels == 255).all(axis=2)
        redness = pixels[:, :, 0] - pixels[:, :, 2]
        signal = np.abs(redness) > 40
        # Painted, but too faint to carry meaning: this is the wash that
        # drew the box. Counted rather than sampled at a fixed coordinate,
        # because the grid's extent moves with the molecule and an earlier
        # version of this test sampled a corner OUTSIDE the grid, where
        # both variants are white -- it passed the mutant.
        wash = (~page) & (~signal) & (pixels.min(axis=2) > 200)
        return int(wash.sum()), int(signal.sum())

    thresholded_wash, thresholded_signal = wash_and_signal(engine_module.HEATMAP_FILL_THRESHOLD)
    unthresholded_wash, unthresholded_signal = wash_and_signal(0.0)

    assert thresholded_wash < unthresholded_wash * 0.75, (
        f"the threshold should remove most of the meaningless wash "
        f"({unthresholded_wash} -> {thresholded_wash})"
    )
    assert thresholded_signal == unthresholded_signal, (
        "and it must not cost any of the real signal"
    )


def test_a_refused_molblock_says_which_atom_and_why():
    """RDKit returns None and says nothing; the error must carry its reason (ClF3: chlorine one bond)."""
    molblock = (
        "\n  Ketcher\n\n  4  3  0  0  0  0  0  0  0  0999 V2000\n"
        "    0.0000    0.0000    0.0000 Cl  0  0  0  0  0  0  0  0  0  0  0  0\n"
        "    0.0000    1.0000    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "   -1.0000   -0.5000    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "    1.0000   -0.5000    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "  1  2  1  0\n  1  3  1  0\n  1  4  1  0\nM  END\n"
    )
    with pytest.raises(InvalidStructureError) as caught:
        ChemistryEngine().mol_from_molblock(molblock)
    assert "Cl" in str(caught.value) and "valence" in str(caught.value)


# --- hypervalent structures OpenChem accepts and RDKit refuses (Phase 2) ---------------------------


def _hypervalent_molblock(centre: str, ligand: str, count: int, charge: int = 0) -> str:
    """A star molecule `centre`(`ligand`)n as the canvas would write it."""
    import math

    atoms = [f"    0.0000    0.0000    0.0000 {centre:<3} 0  0  0  0  0  0  0  0  0  0  0  0"]
    for i in range(count):
        angle = 2 * math.pi * i / count
        atoms.append(
            f"{math.cos(angle):10.4f}{math.sin(angle):10.4f}    0.0000 {ligand:<3} 0  0  0  0  0  0  0  0  0  0  0  0"
        )
    bonds = [f"{1:3d}{i + 2:3d}  1  0" for i in range(count)]
    header = f"\n  test\n\n{count + 1:3d}{count:3d}  0  0  0  0  0  0  0  0999 V2000\n"
    charge_line = f"M  CHG  1   1 {charge:3d}\n" if charge else ""
    return header + "\n".join(atoms) + "\n" + "\n".join(bonds) + "\n" + charge_line + "M  END\n"


@pytest.mark.parametrize(("centre", "ligand", "count"), [("Cl", "F", 3), ("Br", "F", 3), ("Cl", "F", 5)])
def test_the_strict_parse_still_refuses_hypervalent_structures_but_says_why(centre, ligand, count):
    from openchem.chem.engine import UnsanitizableStructureError

    with pytest.raises(UnsanitizableStructureError) as caught:
        ChemistryEngine().mol_from_molblock(_hypervalent_molblock(centre, ligand, count))
    assert isinstance(caught.value, InvalidStructureError), "existing callers must keep catching it"
    assert caught.value.atom_indices == (0,)
    assert "hypervalent table accepts" in str(caught.value)


def test_the_strict_set_structure_is_unchanged_for_hypervalent_input():
    model = MoleculeModel(display_name="x")
    with pytest.raises(InvalidStructureError):
        ChemistryEngine().set_structure_from_molblock(model, _hypervalent_molblock("Cl", "F", 3))
    assert model.molblock is None


@pytest.mark.parametrize(
    ("centre", "ligand", "count", "smiles", "inchi"),
    [
        ("Cl", "F", 3, "FCl(F)F", "InChI=1S/ClF3/c2-1(3)4"),
        ("Br", "F", 3, "FBr(F)F", "InChI=1S/BrF3/c2-1(3)4"),
        ("Cl", "F", 5, "FCl(F)(F)(F)F", "InChI=1S/ClF5/c2-1(3,4,5)6"),
    ],
)
def test_the_opt_in_path_holds_the_structure_with_a_stable_identity(centre, ligand, count, smiles, inchi):
    engine = ChemistryEngine()
    model = MoleculeModel(display_name="x")
    engine.set_structure_from_molblock(model, _hypervalent_molblock(centre, ligand, count), allow_hypervalent=True)
    assert model.canonical_smiles == smiles
    assert model.inchi == inchi
    again = engine.hypervalent_mol_from_molblock(model.molblock)
    assert [a.GetSymbol() for a in again.GetAtoms()] == [centre] + [ligand] * count
    # the STORED molblock still fails the strict parse, which is what keeps every other caller safe
    with pytest.raises(InvalidStructureError):
        engine.mol_from_model(model)


def test_the_opt_in_path_still_refuses_what_the_table_does_not_accept():
    """Cl with carbon ligands is outside `expanded_octet_requires_ligands`; one bad atom beside a good one fails too."""
    engine = ChemistryEngine()
    with pytest.raises(InvalidStructureError) as caught:
        engine.hypervalent_mol_from_molblock(_hypervalent_molblock("Cl", "C", 3))
    assert type(caught.value) is InvalidStructureError
    # pentavalent carbon (CF5) is not a hypervalent case at all
    with pytest.raises(InvalidStructureError) as caught:
        engine.hypervalent_mol_from_molblock(_hypervalent_molblock("C", "F", 5))
    assert type(caught.value) is InvalidStructureError


def test_an_ordinary_structure_goes_through_the_opt_in_path_unchanged():
    from rdkit import Chem

    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="x")
    engine.set_structure_from_smiles(molecule, "CCO")
    strict = engine.mol_from_molblock(molecule.molblock)
    opt_in = engine.hypervalent_mol_from_molblock(molecule.molblock)
    assert Chem.MolToSmiles(strict) == Chem.MolToSmiles(opt_in)


@pytest.mark.parametrize(
    ("centre", "ligand", "count", "charge"),
    [("Cl", "F", 4, -1), ("Xe", "F", 5, -1), ("Br", "F", 4, -1)],
)
def test_a_hypervalent_anion_rdkit_refuses_is_held_like_the_neutrals(centre, ligand, count, charge):
    """XeF5- and ClF4- (crystal structures are known) were rejected or half-handled: XeF5- sits inside xenon's own
    valence list, so a comparison with the list never flagged it although RDKit refuses it."""
    from openchem.chem.engine import UnsanitizableStructureError

    engine = ChemistryEngine()
    molblock = _hypervalent_molblock(centre, ligand, count, charge)
    with pytest.raises(UnsanitizableStructureError):
        engine.mol_from_molblock(molblock)
    model = MoleculeModel(display_name="x")
    engine.set_structure_from_molblock(model, molblock, allow_hypervalent=True)
    assert "-" in model.canonical_smiles
    assert engine.formal_charge(model) == charge
    again = engine.hypervalent_mol_from_molblock(model.molblock)
    assert again.GetAtomWithIdx(0).GetFormalCharge() == charge


def test_the_acceptance_test_is_rdkits_refusal_not_a_comparison_with_its_list():
    """SF6 and PF5 sanitise, so they are NOT 'held'; only atoms RDKit actually refuses are listed."""
    from rdkit import Chem

    from openchem.chem.checkers.valence import accepted_hypervalent_atoms

    for smiles in ("FS(F)(F)(F)(F)F", "FP(F)(F)(F)F", "F[Xe](F)(F)F", "O=Cl(=O)(=O)[O-]", "CS(C)=O"):
        assert accepted_hypervalent_atoms(Chem.MolFromSmiles(smiles, sanitize=False)) == [], smiles
    assert accepted_hypervalent_atoms(Chem.MolFromSmiles("F[Xe-](F)(F)(F)F", sanitize=False)) == [1]
    assert accepted_hypervalent_atoms(Chem.MolFromSmiles("FCl(F)F", sanitize=False)) == [1]
