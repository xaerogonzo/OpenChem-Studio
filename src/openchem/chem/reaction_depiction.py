"""A picture of one step of a planned route (`docs/SYNTHESIS_HELPER_DESIGN.md`, Stage 1 slice 8): the reactants, an arrow, the product, as an SVG.

THE STEP IS DRAWN FROM THE PLANNER'S PLAIN MOLECULES, NEVER FROM ITS MAPPED REACTION. `RouteStep.reaction_smiles` carries atom-map numbers (when the planner supplied any) and
RDKit prints them beside the atoms, which on a figure reads as a locant or a label nobody asked for; `reactants` and `product` are the same molecules without them, and the step
is the same step. A figure that said more than the planner said would be wrong.

THE ARROW POINTS FORWARD, as the route is run (reactants, then product), though the planner searched backward: `RouteStep` is already in forward order.

THIS DRAWS A STEP, IT DOES NOT SAY THE STEP WORKS. No conditions, reagents or yield are drawn, because the planner supplies none; the panel's standing limitations say so beside the picture.

Never raises on a molecule it cannot read: it raises `DepictionError` naming which, and the caller shows a sentence in place of the picture (a `QSvgWidget` scales whatever it is given, so a message must never be put in an SVG).
"""

from __future__ import annotations

from rdkit import Chem, rdBase
from rdkit.Chem import rdChemReactions
from rdkit.Chem.Draw import rdMolDraw2D

from openchem.domain.synthesis_route import RouteStep

#: The height of the picture, in SVG units. The width follows the number of molecules.
STEP_HEIGHT = 200
#: The width given to each molecule (and the arrow), in SVG units.
WIDTH_PER_MOLECULE = 190
#: The most width a picture is given, however many reactants a step has.
MAX_WIDTH = 1100


class DepictionError(ValueError):
    """A molecule of the step could not be read, so the step cannot be drawn."""


def _check_readable(smiles: tuple[str, ...]) -> None:
    for text in smiles:
        # SanitizeMol failures are logged by RDKit as well as returned; the log line is the caller's to keep quiet, the error is ours to raise.
        with rdBase.BlockLogs():
            mol = Chem.MolFromSmiles(text)
        if mol is None:
            raise DepictionError(f"the molecule {text!r} could not be read, so this step cannot be drawn")


def render_step_svg(step: RouteStep, *, height: int = STEP_HEIGHT) -> str:
    """The step as an SVG string: its reactants, an arrow and its product. Raises `DepictionError` when a molecule cannot be read."""
    _check_readable((*step.reactants, step.product))
    reaction_smiles = f"{'.'.join(step.reactants)}>>{step.product}"
    with rdBase.BlockLogs():
        reaction = rdChemReactions.ReactionFromSmarts(reaction_smiles, useSmiles=True)
    if reaction is None:
        raise DepictionError("this step could not be drawn as one reaction")
    width = min(MAX_WIDTH, WIDTH_PER_MOLECULE * (len(step.reactants) + 2))
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    drawer.DrawReaction(reaction)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()
