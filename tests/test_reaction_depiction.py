"""The drawing of one step of a planned route (`openchem.chem.reaction_depiction`): reactants, arrow, product, from the planner's plain molecules and never from its mapped reaction, and an error naming the molecule it cannot read."""

from __future__ import annotations

import re

import pytest

from openchem.chem import reaction_depiction as depiction
from openchem.domain.synthesis_route import RouteStep

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
ANHYDRIDE = "CC(=O)OC(C)=O"
SALICYLIC = "O=C(O)c1ccccc1O"
MAPPED = "[CH3:1][C:2](=[O:3])[O:4][c:5]1[cH:6][cH:7][cH:8][cH:9][c:10]1[C:11](=[O:12])[OH:13]>>[CH3:1][C:2](=[O:3])[O:4][c:5]1[cH:6][cH:7][cH:8][cH:9][c:10]1[C:11](=[O:12])[OH:13]"


def step(**overrides) -> RouteStep:
    fields = {"product": ASPIRIN, "reactants": (ANHYDRIDE, SALICYLIC)}
    fields.update(overrides)
    return RouteStep(**fields)


def size_of(svg: str) -> tuple[int, int]:
    match = re.search(r"width='(\d+)px' height='(\d+)px'", svg)
    assert match, svg[:300]
    return int(match.group(1)), int(match.group(2))


def test_a_step_is_drawn_as_an_svg_of_the_height_asked_for():
    svg = depiction.render_step_svg(step())
    assert svg.lstrip().startswith("<?xml") and "<svg" in svg and svg.rstrip().endswith("</svg>")
    assert size_of(svg)[1] == depiction.STEP_HEIGHT
    assert size_of(depiction.render_step_svg(step(), height=120))[1] == 120


def test_the_picture_is_made_from_the_plain_molecules_never_from_the_mapped_reaction():
    # Atom-map numbers would be printed beside the atoms; the same step with and without a mapped reaction must give the same picture.
    assert depiction.render_step_svg(step(reaction_smiles=MAPPED)) == depiction.render_step_svg(step())


def test_the_picture_grows_with_the_number_of_molecules_and_stops_growing():
    two = size_of(depiction.render_step_svg(step()))[0]
    three = size_of(depiction.render_step_svg(step(reactants=(ANHYDRIDE, SALICYLIC, "CCO"))))[0]
    many = size_of(depiction.render_step_svg(step(reactants=tuple(["CCO"] * 30))))[0]
    assert two == depiction.WIDTH_PER_MOLECULE * 4 and three == depiction.WIDTH_PER_MOLECULE * 5
    assert many == depiction.MAX_WIDTH


def test_the_arrow_points_from_the_reactants_to_the_product():
    # Built independently here, as RDKit would draw reactants >> product at the same size, so a swapped direction is a different picture.
    from rdkit.Chem import rdChemReactions
    from rdkit.Chem.Draw import rdMolDraw2D

    def drawn(smarts: str) -> str:
        drawer = rdMolDraw2D.MolDraw2DSVG(depiction.WIDTH_PER_MOLECULE * 4, depiction.STEP_HEIGHT)
        drawer.DrawReaction(rdChemReactions.ReactionFromSmarts(smarts, useSmiles=True))
        drawer.FinishDrawing()
        return drawer.GetDrawingText()

    ours = depiction.render_step_svg(step())
    assert ours == drawn(f"{ANHYDRIDE}.{SALICYLIC}>>{ASPIRIN}")
    assert ours != drawn(f"{ASPIRIN}>>{ANHYDRIDE}.{SALICYLIC}")


@pytest.mark.parametrize("bad", ["not a smiles(", "C1CC", "[Xx]"])
def test_a_molecule_that_cannot_be_read_is_named_and_nothing_is_drawn(bad):
    with pytest.raises(depiction.DepictionError, match="could not be read") as caught:
        depiction.render_step_svg(step(reactants=(ANHYDRIDE, bad)))
    assert repr(bad) in str(caught.value)
    with pytest.raises(depiction.DepictionError) as caught:
        depiction.render_step_svg(step(product=bad))
    assert repr(bad) in str(caught.value)


def test_an_unreadable_molecule_is_a_value_error_so_a_caller_can_catch_it_broadly():
    assert issubclass(depiction.DepictionError, ValueError)
