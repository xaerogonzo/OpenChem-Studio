"""Writing an isotope onto a drawn structure.

Setting one used to mean Ketcher's Atom Properties dialog and typing a
mass number blind. The picker in `periodic_table_dialog` is the readable
way in; this is what it writes through, and what the undo stack pushes.

## The element is DERIVED, never passed in

`set_isotope` takes an atom INDEX and reads the element off that atom.
A signature that also took a symbol would make "apply C-13 to every
oxygen" expressible, and then the only thing standing between a user and
that mistake is every caller remembering to pass the same element twice.
The periodic table is a browsing tool -- somebody can easily be reading
carbon's isotopes with an oxygen selected -- so it is worth making
unexpressible rather than validated after the fact.

## The chemistry layer validates; it does not trust the UI

The picker should never offer Po-999, and this function must not depend
on that being true. A drive script, a plugin or a future second caller
has no such guarantee, and a molblock carrying an isotope no nuclide
table recognises is a structure every downstream consumer will treat as
real.
"""

from __future__ import annotations

from enum import Enum

from rdkit import Chem

from openchem.chem import nuclides as nuclide_data


class IsotopeRefusal(str, Enum):
    """Why a mass-number write cannot be made.

    **A VALUE RATHER THAN A SENTENCE**, so `if "isomer" in message` never
    becomes application logic -- the same reason `BcsReason` and the
    decay leaf reasons are values. The UI text is generated from it.
    """

    #: **A MOLFILE HAS NO PLACE TO PUT A NUCLEAR STATE.** `M  ISO` carries
    #: a mass number and nothing else, so Tc-99m and Tc-99 write the same
    #: bytes and every downstream reader -- RDKit, the calculators, a
    #: saved project -- would treat the metastable structure as the
    #: ground state. **THE REFUSAL IS THE FEATURE**: the alternative is
    #: silently discarding the one thing the user asked for. The Isotopes
    #: tab still shows the isomer's half-life and decay modes; only Apply
    #: is refused.
    ISOMER_NOT_IN_MOLFILE = "isomer_not_in_molfile"


#: What each refusal says to a reader. Generated from the value so the
#: wording lives in one place and a test can assert the mapping is total.
REFUSAL_TEXT: dict[IsotopeRefusal, str] = {
    IsotopeRefusal.ISOMER_NOT_IN_MOLFILE: (
        "A molfile records a mass number, not a nuclear state, so a "
        "metastable isomer cannot be written to the structure. Its "
        "half-life and decay modes are shown above."
    ),
}


class IsotopeError(ValueError):
    """A write was refused, with a reason a user can act on.

    `refusal` is set when the refusal is one of the declared kinds; it is
    None for the ordinary arithmetic refusals (no such atom, no such
    nuclide) whose message is already specific.
    """

    def __init__(self, message: str, refusal: "IsotopeRefusal | None" = None):
        super().__init__(message)
        self.refusal = refusal


def refuse_isomer() -> IsotopeError:
    """The refusal, built in ONE place.

    Both the write path and the button-enabling path need it, and writing
    the sentence twice is how two refusals drift into disagreeing -- the
    lesson `predicted_only_reason()` already records for solvents.
    """
    return IsotopeError(
        REFUSAL_TEXT[IsotopeRefusal.ISOMER_NOT_IN_MOLFILE],
        IsotopeRefusal.ISOMER_NOT_IN_MOLFILE,
    )


def set_isotope(
    molblock: str,
    index: int,
    mass_number: int,
    *,
    all_of_element: bool = False,
) -> str:
    """Label one atom -- or every atom of its element -- with a mass number.

    `all_of_element` reads the element off the SAME atom `index` names, so
    the scope can only ever be the selected atom's own element.

    Returns a new molblock; the input is not touched. **Coordinates and
    atom order are unchanged**, which is what lets the caller keep using
    the indices it already has and lets the conformers survive.
    """
    mol = _parse(molblock)
    if not 0 <= index < mol.GetNumAtoms():
        raise IsotopeError(
            f"atom {index} is not in this structure, which has {mol.GetNumAtoms()}"
        )
    if mass_number <= 0:
        raise IsotopeError(f"{mass_number} is not a mass number")

    atom = mol.GetAtomWithIdx(index)
    symbol, atomic_number = atom.GetSymbol(), atom.GetAtomicNum()
    if nuclide_data.nuclide(atomic_number, mass_number) is None:
        raise IsotopeError(
            f"{symbol}-{mass_number} is not in the nuclide table"
        )

    targets = (
        [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == atomic_number]
        if all_of_element
        else [index]
    )
    for target in targets:
        mol.GetAtomWithIdx(target).SetIsotope(mass_number)
    return Chem.MolToMolBlock(mol)


def element_at(molblock: str | None, index: int) -> str | None:
    """The element symbol of one atom, or None if the index does not name one.

    **BOUNDS-CHECKED, and that is the whole reason this exists** rather
    than the caller reaching for RDKit: an index arriving from the editor
    can outrun the structure the model holds -- an erase between the click
    and the read -- and RDKit answers an out-of-range index with a
    `RuntimeError` raised inside a Qt signal handler. `_atom_is_in_report`
    is the same guard one panel along.

    It also keeps the "an element is derived from an index" rule in ONE
    module: the window that asks which element is selected and the
    function that writes to it agree by construction rather than by both
    remembering to pass `removeHs=False`.
    """
    if not molblock or index < 0:
        return None
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    if mol is None or index >= mol.GetNumAtoms():
        return None
    return mol.GetAtomWithIdx(index).GetSymbol()


def isotope_free_smiles(smiles: str | None) -> str | None:
    """The canonical SMILES with every mass label removed, or None.

    **This is what makes an isotope edit keep its conformers**, and it is
    DERIVED rather than a flag on the command for one concrete reason:
    Ketcher's own Atom Properties dialog can set an isotope too, and that
    arrives as an ordinary editor change with nothing anywhere to mark it.
    A flag would cover the picker and miss the dialog beside it.

    **Stereochemistry survives the stripping**, which is the thing that
    had to be measured rather than assumed -- an isotope can CREATE a
    stereocentre (H/D/F/Cl on one carbon), so stripping could in principle
    make a wedge flip invisible and preserve conformers through a genuine
    mirror-image change. It does not: RDKit keeps the explicit hydrogen
    and the chiral tag, so `[2H][C@](F)(Cl)Br` and its `[C@@]` twin still
    differ after stripping. Measured on both an ordinary centre and an
    isotopic one.
    """
    if smiles is None:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    for atom in mol.GetAtoms():
        atom.SetIsotope(0)
    return Chem.MolToSmiles(mol)


def _parse(molblock: str) -> Chem.Mol:
    """**`removeHs=False`, and it is load-bearing.**

    The default strips explicit hydrogens, which renumbers every atom
    after the first one removed -- so the index the caller passed would
    silently come to mean a different atom. A drawing carrying explicit
    hydrogens is exactly where somebody wants to write a deuterium.
    """
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    if mol is None:
        raise IsotopeError("this structure could not be read")
    return mol
