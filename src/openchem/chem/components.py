"""Which components of a drawing a calculator is handed, per its scope.

Round 5's multicomponent sweep found every calculator handed the whole
drawing, whatever it was: a C23 counter-ion made metformin fail Lipinski,
sodium made acetate's logP -4.24, and graph-distance indices printed RDKit's
1e8 "unreachable" sentinel as a Wiener index of 400000009. This module is the
one place a `CalculatorScope` is applied, so every route into a calculator
(Properties, Batch, the 3D overlay) selects the same way.

**THE PARENT IS CHEMBL'S, NOT A SALT STRIPPER OF OUR OWN.**
`vendor/chembl_structure_pipeline` carries ChEMBL's GetParent verbatim with
its salt and solvent lists; see `ComponentSelection.CHEMBL_PARENT` for the
sources. Two decisions here are ours, and both follow the paper's text:

- it is applied only to a drawing of MORE THAN ONE component. Bento et al.
  2020 [source:bento2020] apply GetParent "to just those compounds" that are multicomponent or
  isotopic; run on one component the function also neutralises it, which
  would silently turn glycine drawn as a zwitterion into NCC(=O)O.
- when ChEMBL's rule keeps more than one component -- every component listed
  (sodium acetate) or none (choline salicylate) -- the calculator is handed
  the LARGEST component, re-neutralised, and the answer says so (`Selection.note`,
  recorded as the result's `caveat` and its first limitation). ChEMBL itself
  registers such a parent as the mixture, and a property model has nothing
  honest to say about a mixture, so the mixture is never what is computed;
  but refusing left a person with nothing for sodium acetate, where the
  organic ion is plainly the species meant (Alex, 2026-10-25: a calculator
  refuses what it cannot compute, and labels the rest). Two cases STILL
  refuse, because there is no species to hand over: components of equal size
  that are different species (NaCl, a mixture of two small organics), and
  ChEMBL's exclusion flag (a transition metal, or more than seven borons),
  where the ligand ions' properties would describe a different compound from
  the complex that was drawn.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from rdkit import Chem

from openchem.domain.calculator import (
    METAL_CONTAINING_UNSUPPORTED,
    MULTICOMPONENT_UNSUPPORTED,
    NO_ORGANIC_COMPONENT,
    Aggregation,
    CalculationRefusal,
    CalculatorScope,
    ComponentSelection,
    MethodDomain,
)

#: Atom property set on every atom of a SELECTED structure: its index in the
#: drawing (counting from 0). A report that names atoms in text (the pKa site, "at O4") reads
#: it, through `drawing_label`, so the number it prints is the one on the user's drawing.
DRAWING_INDEX_PROP = "ocs_drawing_index"

#: How close the second-largest species must come to the largest (in heavy atoms, as a fraction of the largest)
#: for the label to say the choice is close and so a guess. Choline salicylate (7 and 10) is the case that
#: sets it; sodium acetate (1 and 4) is not. It changes a sentence, never which component is taken.
COMPARABLE_SIZE = 0.5


@dataclass(frozen=True)
class Selection:
    """What a calculator is handed, and how to read its answer back."""

    mol: Chem.Mol
    #: The drawing index of each atom of `mol`, in order; None when `mol` IS
    #: the drawing.
    drawing_atoms: tuple[int, ...] | None
    #: Indices of the drawing's components (`Chem.GetMolFrags` order) used.
    components: tuple[int, ...]
    #: Canonical SMILES of the ChEMBL parent, when one was taken.
    parent_smiles: str = ""
    #: What the reader must be told about how the components were chosen, when it was a choice and not ChEMBL's
    #: rule (the largest component of a drawing with no single parent). Empty otherwise.
    note: str = ""
    #: Canonical SMILES of the drawing's components that were left out, when `note` is set.
    left_out: tuple[str, ...] = ()


def drawing_index(atom: Chem.Atom) -> int:
    """The drawing index of an atom of a selected structure."""
    if atom.HasProp(DRAWING_INDEX_PROP):
        return atom.GetIntProp(DRAWING_INDEX_PROP)
    return atom.GetIdx()


def drawing_label(atom: Chem.Atom) -> str:
    """`O4`: an atom's symbol and its number on the canvas, which counts from 1.

    **ONE SPELLING OF "WHICH ATOM" FOR TEXT.** The drawing index above counts from 0, like every
    RDKit index, and the canvas, the Atom Inspector and the bond reports all show `index + 1`. The
    pKa line printed the zero-based one, so acetic acid's acidic oxygen read "O3" -- the number the
    canvas gives the carbonyl oxygen next to it. A report that names an atom in words uses this.
    """
    return f"{atom.GetSymbol()}{drawing_index(atom) + 1}"


def _stamp(mol: Chem.Mol, drawing_atoms: tuple[int, ...] | None) -> Chem.Mol:
    for atom in mol.GetAtoms():
        index = drawing_atoms[atom.GetIdx()] if drawing_atoms is not None else atom.GetIdx()
        atom.SetIntProp(DRAWING_INDEX_PROP, index)
    return mol


def _refuse(code: str, summary: str, detail: str) -> CalculationRefusal:
    return CalculationRefusal(code, summary, detail, inapplicable=True)


def _chembl_parent(mol: Chem.Mol, name: str) -> Selection:
    from openchem.vendor.chembl_structure_pipeline.getparent import get_fragment_parent_mol

    fragments = Chem.GetMolFrags(mol)
    parent, excluded = get_fragment_parent_mol(Chem.Mol(mol), check_exclusion=True, neutralize=True)
    # ChEMBL splits with `sanitizeFrags=False` and only updates the property
    # cache, so ring perception has never run on what it returns: TPSA,
    # CNS MPO and the BBB inputs raised "RingInfo not initialized" on every
    # salt the first time this was wired (round 5 sweep). The drawing it came
    # from was sanitised, so the parent sanitises.
    Chem.SanitizeMol(parent)
    if excluded:
        raise _refuse(
            METAL_CONTAINING_UNSUPPORTED,
            "Metal complex: no parent compound",
            f"{name} is computed on the parent compound, and ChEMBL's parent rule excludes "
            "structures with a transition metal or more than seven boron atoms. There is no "
            "parent molecule to hand it.",
        )
    parent_fragments = Chem.GetMolFrags(parent)
    if len(parent_fragments) > 1:
        return _largest_component(mol, fragments, parent)
    # WHICH drawing component the parent is. The vendored function returns a
    # copy of one input fragment, neutralised; neutralising moves hydrogens
    # and charges but never heavy atoms, so the component whose heavy-atom
    # element sequence matches is the one, and the first such is taken --
    # exactly as ChEMBL keeps the first of identical fragments.
    wanted = [a.GetAtomicNum() for a in parent.GetAtoms()]
    for component, atoms in enumerate(fragments):
        if [mol.GetAtomWithIdx(i).GetAtomicNum() for i in atoms] == wanted:
            drawing_atoms = tuple(atoms)
            break
    else:  # pragma: no cover - the vendored rule returns an input fragment
        raise AssertionError("the ChEMBL parent matches no drawing component")
    return Selection(
        mol=_stamp(parent, drawing_atoms),
        drawing_atoms=drawing_atoms,
        components=(component,),
        parent_smiles=Chem.MolToSmiles(parent),
    )


def _largest_component(mol: Chem.Mol, fragments: tuple[tuple[int, ...], ...], parent: Chem.Mol) -> Selection:
    """The drawing's largest component, when ChEMBL's rule leaves several; else the refusal.

    **RE-NEUTRALISED, AND SAID SO.** ChEMBL's rule re-neutralises the one component left once the counter-ions
    are gone (sodium phenolate's parent is phenol), and the panel's controls for these salts are the neutral
    acids. Computed on the trianion as drawn, citrate's Crippen logP was -5.25: a model fitted on neutral
    molecules has nothing to say about the ion, and the number would have been the lie. The label names the
    drawn species and the one computed. A permanent charge (choline) stays, as `uncharge_mol` leaves it.

    **EXCEPT WHEN THE STRUCTURE HAS 3D COORDINATES**: neutralising adds a hydrogen with no position, and the 3D
    calculators (partial charges from the conformer) rightly refuse a hydrogen that is not an atom -- the census
    found `geometry_partial_charge` refusing sodium acetate that way. A conformer's component is kept as drawn,
    which is also what those calculators describe, and the label says so. **"3D" MATTERS**: the application's own
    molecule comes from a molblock and so carries the drawing's 2D coordinates, and the first version of this check
    ("has a conformer") fired on every drawing and computed sodium acetate as the ion (logP -1.24, not acetic
    acid's 0.09); only the real window showed it.

    Candidates are the components ChEMBL kept (a listed solvent it removed stays removed), matched back to the
    drawing by element sequence exactly as the single-parent path does. Size is heavy atoms. Two identical
    components (calcium acetate's anions) are one species; two different species of the largest size have no
    larger one, and that refuses.
    """
    from openchem.vendor.chembl_structure_pipeline.getparent import uncharge_mol

    kept = [[a.GetAtomicNum() for a in f.GetAtoms()] for f in Chem.GetMolFrags(parent, asMols=True, sanitizeFrags=False)]
    pieces = Chem.GetMolFrags(mol, asMols=True)
    candidates: list[tuple[int, int, str]] = []  # (component, heavy atoms, canonical SMILES as drawn)
    taken: set[int] = set()
    for sequence in kept:
        for component, atoms in enumerate(fragments):
            if component not in taken and [mol.GetAtomWithIdx(i).GetAtomicNum() for i in atoms] == sequence:
                taken.add(component)
                candidates.append((component, pieces[component].GetNumHeavyAtoms(), Chem.MolToSmiles(pieces[component])))
                break
    candidates.sort(key=lambda c: -c[1])
    component, size, smiles = candidates[0]
    rivals = sorted({s for _c, n, s in candidates if n == size and s != smiles})
    if rivals:
        raise _refuse(
            MULTICOMPONENT_UNSUPPORTED,
            "Mixture: no single parent",
            f"This drawing has {len(fragments)} components and ChEMBL's parent rule leaves "
            f"{len(candidates)}, and the largest are different species of the same size "
            f"({', '.join([smiles, *rivals])}), so none of them is the one meant. Draw the one species you mean.",
        )
    neutral = uncharge_mol(Chem.Mol(pieces[component]))
    Chem.SanitizeMol(neutral)  # `uncharge_mol` only updates the property cache; see `_chembl_parent`
    would_change = Chem.MolToSmiles(neutral) != smiles
    keep_as_drawn = would_change and any(conformer.Is3D() for conformer in pieces[component].GetConformers())
    chosen = Chem.Mol(pieces[component]) if keep_as_drawn else neutral
    computed = Chem.MolToSmiles(chosen)
    left_out = tuple(sorted(Chem.MolToSmiles(p) for i, p in enumerate(pieces) if i != component))
    others = ", ".join(sorted(set(left_out) - {smiles})) or "only further copies of the same species"
    close = [n for _c, n, s in candidates if s != smiles and n >= COMPARABLE_SIZE * size and n > 1]
    note = (
        f"Computed on {computed}"
        + (f" (the drawn {smiles}, neutralised)" if would_change and not keep_as_drawn else "")
        + (" (as drawn in the 3D structure, not neutralised, since a hydrogen cannot be added without a position)" if keep_as_drawn else "")
        + f", the largest of this drawing's {len(fragments)} components ({size} heavy atoms). "
        f"ChEMBL's parent rule leaves no single parent here, so the components were not combined; not included: {others}. "
        + (
            f"The next largest has {max(close)} heavy atoms, close in size, so this is a guess at the species meant. "
            if close
            else ""
        )
        + "Draw the one species you mean to compute on it."
    )
    return Selection(
        mol=_stamp(chosen, tuple(fragments[component])),
        drawing_atoms=tuple(fragments[component]),
        components=(component,),
        parent_smiles=computed,
        note=note,
        left_out=left_out,
    )


def select(mol: Chem.Mol, scope: CalculatorScope, name: str) -> Selection:
    """Apply `scope` to `mol`, or raise the refusal it implies.

    `name` is the calculator's display name, for the sentence a user reads.
    """
    fragments = Chem.GetMolFrags(mol)
    everything = tuple(range(len(fragments)))
    if scope.selection is ComponentSelection.CHEMBL_PARENT and len(fragments) > 1:
        selection = _chembl_parent(mol, name)
    elif scope.selection is ComponentSelection.REFUSE_MULTICOMPONENT and len(fragments) > 1:
        raise _refuse(
            MULTICOMPONENT_UNSUPPORTED,
            "Salt or mixture: not a pure component",
            f"{name} is stated for a single pure substance, and this structure has "
            f"{len(fragments)} components. {scope.note}".strip(),
        )
    else:
        selection = Selection(mol=_stamp(Chem.Mol(mol), None), drawing_atoms=None, components=everything)
    if scope.domain is MethodDomain.ORGANIC and not any(
        a.GetAtomicNum() == 6 for a in selection.mol.GetAtoms()
    ):
        raise _refuse(
            NO_ORGANIC_COMPONENT,
            "No carbon: outside the method",
            f"{name} is defined for organic compounds, and there is no carbon here.",
        )
    return selection


def scope_parameters(scope: CalculatorScope, selection: Selection) -> dict[str, Any]:
    """What a result records about the components it was computed over."""
    recorded: dict[str, Any] = {
        "component_selection": scope.selection.value,
        "aggregation": scope.aggregation.value,
        "components_used": list(selection.components),
    }
    if selection.parent_smiles:
        recorded["parent_smiles"] = selection.parent_smiles
    if selection.note:
        recorded["component_choice"] = "largest"
        recorded["components_left_out"] = list(selection.left_out)
    return recorded


def read_back(result: Any, scope: CalculatorScope, selection: Selection) -> Any:
    """`result`, with atom indices in drawing numbering and the scope recorded.

    Only `values` keyed by atom index are remapped, and only when the
    producer did not name its own structure (`structure_molblock`): a
    pH-dependent charge set keyed by a microspecies is already about a
    structure it carries.
    """
    changes: dict[str, Any] = {}
    if (
        selection.drawing_atoms is not None
        and scope.aggregation is Aggregation.PER_ATOM
        and isinstance(getattr(result, "values", None), dict)
        and not getattr(result, "structure_molblock", "")
    ):
        beyond = sorted(i for i in result.values if not 0 <= i < len(selection.drawing_atoms))
        if beyond:
            # A key past the parent's atoms is a hydrogen the calculator
            # added, and neutralising the parent changes how many there are,
            # so it has no drawing atom to land on. FAIL, visibly, rather
            # than put a value on the wrong atom: a per-atom calculator that
            # adds hydrogens is scoped EACH_COMPONENT instead.
            raise ValueError(
                f"per-atom result keyed beyond its parent structure ({beyond[:5]}); "
                "a calculator that adds hydrogens cannot be scoped CHEMBL_PARENT"
            )
        changes["values"] = {selection.drawing_atoms[i]: v for i, v in result.values.items()}
    provenance = getattr(result, "provenance", None)
    if provenance is not None:
        parameters = {**provenance.parameters, **scope_parameters(scope, selection)}
        if selection.note:
            # The producer's own caveat, if it recorded one, follows ours: this is the one that says WHAT was computed.
            earlier = parameters.get("caveat")
            parameters["caveat"] = f"{selection.note} {earlier}" if isinstance(earlier, str) and earlier.strip() else selection.note
        changes["provenance"] = replace(provenance, parameters=parameters)
    limitations = getattr(result, "limitations", None)
    if selection.note and isinstance(limitations, tuple):
        changes["limitations"] = (selection.note, *limitations)
    return replace(result, **changes) if changes else result


def as_drawn(result: Any, scope: CalculatorScope, mol: Chem.Mol) -> Any:
    """`result` recorded as computed over the whole drawing under `scope`,
    for producers outside the registry (the always-on provider)."""
    everything = tuple(range(len(Chem.GetMolFrags(mol))))
    return read_back(result, scope, Selection(mol=mol, drawing_atoms=None, components=everything))
