"""The numbers drawn beside the atoms in the 2D editor.

TWO NUMBERINGS, AND THEY ARE DIFFERENT CLAIMS.

`index` is the atom's 1-based position in the current drawing. It is what
MarvinSketch shows and what a chemist counts along a chain with. It is NOT a
stable identifier: it follows the molfile, so deleting an atom renumbers
everything after it, and it means nothing to another program.

`locants` is IUPAC numbering, from the naming engine. It is a chemical claim
-- C-3 of the parent -- and it is SPARSE by nature: over the 187-molecule
naming corpus the engine numbers 38.4% of heavy atoms and leaves 76 molecules
with none at all, because a retained name carries no derived numbering. So
this module returns a status line beside the labels, and the three states it
must keep apart are:

    numbered           "12 of 16 atoms numbered ..."
    nothing to number  "0 of 24 atoms numbered ..." -- ran, found none
    failed             "IUPAC numbering failed: ..." -- did not run

Collapsing the last two into a blank canvas is what makes a working
calculator read as broken, which this project has now recorded several times.
"""

from __future__ import annotations

from functools import lru_cache

from rdkit import Chem

from openchem.chem.structure_annotation import annotate

#: Nothing is drawn.
OFF = "off"
#: The atom's 1-based position in the current DRAWING -- what the Atom
#: Inspector's `#` column shows, and not a stable identifier.
INDEX = "index"
#: The naming engine's IUPAC numbering, which is a chemical claim and covers
#: only the atoms it can name.
LOCANTS = "locants"

#: What each mode is called where a user reads it. "Drawing atom numbers",
#: not "atom index": the number is a position in the current drawing, and
#: calling it an index invites reading it as a stable id.
MODE_LABELS: dict[str, str] = {
    OFF: "Off",
    INDEX: "Drawing atom numbers",
    LOCANTS: "IUPAC locants",
}


def labels_for_molblock(molblock: str, mode: str) -> tuple[dict[int, str], str]:
    """`({molfile position: label}, status line)` for `mode`.

    Keyed by the atom's position in `molblock`, which is the index space the
    page speaks and the same one `structure_annotation` uses -- so a label
    computed here and a locant shown in the Atom Inspector are about the
    same atom by construction rather than by coincidence.

    **CACHED ON (molblock, mode)**, because TWO readers ask the same question
    about the same structure: the canvas overlay when the molecule changes,
    and the Atom Inspector when its table rebuilds. The locant mode runs the
    naming engine (12.1 ms mean, 86 ms worst over the 187-molecule corpus),
    and computing it twice for one edit is pure waste. Pure function of its
    arguments, so the cache cannot go stale -- a changed structure is a
    different molblock.
    """
    labels, status = _labels_cached(molblock, mode)
    # A COPY, so a caller that mutates what it gets cannot poison the cache.
    return dict(labels), status


@lru_cache(maxsize=8)
def _labels_cached(molblock: str, mode: str) -> tuple[dict[int, str], str]:
    if mode == OFF or not molblock:
        return {}, ""
    mol = Chem.MolFromMolBlock(molblock, sanitize=False, removeHs=False)
    if mol is None:
        return {}, "This structure could not be read."

    if mode == INDEX:
        total = mol.GetNumAtoms()
        return (
            {index: str(index + 1) for index in range(total)},
            f"{total} atoms numbered by drawing position.",
        )

    # IUPAC locants. `annotate` never raises; it reports.
    try:
        mol = Chem.MolFromMolBlock(molblock)
        annotation = annotate(mol)
    except Exception as exc:  # noqa: BLE001 - a display must not take the app down
        return {}, f"IUPAC numbering failed: {type(exc).__name__}: {exc}"
    if annotation.error:
        return {}, f"IUPAC numbering failed: {annotation.error}"
    labels = {locant.atom_index: locant.label for locant in annotation.locants}
    return labels, _locant_status(annotation)


def _locant_status(annotation) -> str:
    """The status line for a successful annotation, numbered or not."""
    total = annotation.atom_count
    numbered = len(annotation.locants)
    if not numbered:
        return (
            f"0 of {total} atoms numbered: this structure is named by a retained "
            "name, which carries no derived numbering."
        )
    sources = {locant.source.value for locant in annotation.locants}
    where = (
        "from this structure's own numbering"
        if sources == {"parent"}
        else "from a ring skeleton's conventional numbering"
        if sources == {"retained_ring"}
        else "from this structure's numbering and a ring skeleton's"
    )
    return f"{numbered} of {total} atoms numbered, {where}."
