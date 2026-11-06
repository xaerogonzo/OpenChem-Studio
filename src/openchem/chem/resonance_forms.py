"""The resonance forms of a molecule, for the typed EEM models (`chem/typed_eem.py`), and the one call that charges a molecule with them.

WHY THIS EXISTS: the two oxygens of a nitro group or a carboxylate are the same atom chemically, but the drawing makes one of them double-bonded, and the EEM atom type is the
element plus the highest bond order. `benchmarks/charges/models/eem_resonance_typing_design.md` (decisions D1 to D7, approved 2026-10-30) fixes what is done about it:

* the forms are RDKit's own enumeration with its defaults (it creates no charge separation and allows no incomplete octet), of the KEKULISED molecule so that every bond is 1, 2 or 3;
* only the forms with the SMALLEST sum of absolute formal charges are kept, all weighted equally (an approximation of Gilson, Gilson and Potter 2003's "lowest-energy forms",
  without their donor-acceptor energy table: a choice, not a measurement);
* an atom is variable if its type differs between the kept forms or from the drawing's own, found by the enumeration and not by a list of groups;
* if the enumeration reaches `cap` forms (RDKit's own limit, which it applies silently) it is treated as INCOMPLETE and `averaged` refuses instead of guessing.

`typed_eem_for_molecule` is the call a calculator will make; its default is `averaged` (D1). It is not reachable from a calculator yet.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from rdkit import Chem

from openchem.chem import typed_eem as te

#: RDKit's own default for the number of forms it enumerates, so a count that reaches it is a count that was cut short.
DEFAULT_CAP = 1000

#: The molecule has more than one component; the models solve one molecule.
REFUSE_MULTIPLE_COMPONENTS = "REFUSE_MULTIPLE_COMPONENTS"
#: The molecule has an unpaired electron; neither paper parameterised one.
REFUSE_UNPAIRED_ELECTRON = "REFUSE_UNPAIRED_ELECTRON"
#: `averaged` and the enumeration of resonance forms reached the cap, so the average would be over an arbitrary part of them.
REFUSE_TOO_MANY_RESONANCE_FORMS = "REFUSE_TOO_MANY_RESONANCE_FORMS"
#: A bond that is not 1, 2 or 3 after kekulisation, or a molecule that cannot be kekulised.
REFUSE_NOT_KEKULISABLE = "REFUSE_NOT_KEKULISABLE"

Bonds = tuple[tuple[int, int, int], ...]


@dataclass(frozen=True)
class ResonanceForms:
    #: The drawing's own bonds, kekulised, over the molecule's atoms.
    drawn: Bonds
    #: The kept forms (smallest sum of |formal charge|), distinct, each over the same atoms. Never empty.
    forms: tuple[Bonds, ...]
    #: How many forms RDKit enumerated before selection.
    enumerated: int
    #: False when the enumeration reached the cap.
    complete: bool


def _bonds(mol: Chem.Mol) -> Bonds:
    out = []
    for bond in mol.GetBonds():
        order = bond.GetBondTypeAsDouble()
        if order not in (1.0, 2.0, 3.0):
            raise ValueError(f"bond {bond.GetBeginAtomIdx()}-{bond.GetEndAtomIdx()} is not single, double or triple after kekulisation")
        out.append((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx(), int(order)))
    return tuple(out)


def resonance_bond_forms(mol: Chem.Mol, cap: int = DEFAULT_CAP) -> ResonanceForms:
    """The drawing's bonds and its kept resonance forms. Raises ValueError for a molecule that cannot be kekulised."""
    work = Chem.Mol(mol)
    Chem.Kekulize(work, clearAromaticFlags=True)
    drawn = _bonds(work)
    supplier = Chem.ResonanceMolSupplier(work, maxStructs=cap)
    enumerated = len(supplier)
    candidates: list[tuple[int, Bonds]] = []
    for k in range(enumerated):
        form = supplier[k]
        if form is None:
            continue
        candidates.append((sum(abs(a.GetFormalCharge()) for a in form.GetAtoms()), _bonds(form)))
    if not candidates:
        return ResonanceForms(drawn=drawn, forms=(drawn,), enumerated=enumerated, complete=enumerated < cap)
    smallest = min(total for total, _ in candidates)
    kept: list[Bonds] = []
    for total, form_bonds in candidates:
        canonical = tuple(sorted(form_bonds))
        if total == smallest and canonical not in {tuple(sorted(f)) for f in kept}:
            kept.append(form_bonds)
    return ResonanceForms(drawn=drawn, forms=tuple(kept), enumerated=enumerated, complete=enumerated < cap)


def typed_eem_for_molecule(mol: Chem.Mol, model: str, *, resonance: str = te.RESONANCE_AVERAGED, cap: int = DEFAULT_CAP) -> te.TypedEEMResult:
    """The charges `model` assigns to `mol`, which must carry explicit hydrogens and one conformer (coordinates in angstrom).

    Refuses, each by name and before the solve: a molecule with more than one component, an unpaired electron, one that cannot be kekulised and (for `averaged`) one whose
    resonance forms reached `cap`. Everything else is `typed_eem.typed_charges`."""
    if resonance not in te.RESONANCE_VALUES:
        raise ValueError(f"unknown resonance option {resonance!r}; the values are {', '.join(te.RESONANCE_VALUES)}")
    if mol.GetNumConformers() == 0:
        raise ValueError("the molecule needs a conformer")
    if len(Chem.GetMolFrags(mol)) > 1:
        return te.TypedEEMResult(status=REFUSE_MULTIPLE_COMPONENTS, resonance=resonance, message="This structure has several components. Charge one component at a time.")
    if any(atom.GetNumRadicalElectrons() for atom in mol.GetAtoms()):
        return te.TypedEEMResult(status=REFUSE_UNPAIRED_ELECTRON, resonance=resonance, message="This structure has an unpaired electron, which neither EEM paper parameterised.")
    try:
        forms = resonance_bond_forms(mol, cap)
    except (ValueError, Chem.KekulizeException) as exc:
        return te.TypedEEMResult(status=REFUSE_NOT_KEKULISABLE, resonance=resonance, message=f"The structure cannot be written with single, double and triple bonds only: {exc}")
    if resonance == te.RESONANCE_AVERAGED and not forms.complete:
        return te.TypedEEMResult(
            status=REFUSE_TOO_MANY_RESONANCE_FORMS,
            resonance=resonance,
            message=(
                f"This structure has at least {cap} resonance forms, more than can be enumerated completely, so an average over them would not be an average over all of them. "
                "The resonance option can be set to 'as_drawn' to use the drawing as it is."
            ),
        )
    elements = [atom.GetSymbol() for atom in mol.GetAtoms()]
    coords = np.asarray(mol.GetConformer().GetPositions(), dtype=float)
    net = sum(atom.GetFormalCharge() for atom in mol.GetAtoms())
    return te.typed_charges(elements, coords, forms.drawn, model, net, resonance=resonance, bond_forms=forms.forms)
