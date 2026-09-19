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
  (sodium acetate, NaCl) or none (choline salicylate) -- the calculator is
  REFUSED rather than handed the mixture, and when its exclusion flag is set
  (a transition metal, or more than seven borons) it is refused too. ChEMBL
  itself registers such a parent as the mixture; a property model has
  nothing honest to say about one.
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
#: drawing. A report that names atoms in text (the pKa site, "at O3") reads
#: it so the number it prints is the one on the user's drawing.
DRAWING_INDEX_PROP = "ocs_drawing_index"


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


def drawing_index(atom: Chem.Atom) -> int:
    """The drawing index of an atom of a selected structure."""
    if atom.HasProp(DRAWING_INDEX_PROP):
        return atom.GetIntProp(DRAWING_INDEX_PROP)
    return atom.GetIdx()


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
        raise _refuse(
            MULTICOMPONENT_UNSUPPORTED,
            "Mixture: no single parent",
            f"{name} is computed on the parent compound, and ChEMBL's rule leaves "
            f"{len(parent_fragments)} components here: either every component is a listed salt "
            "(as in sodium acetate or NaCl) or none is (as in choline salicylate). Draw the one "
            "species you mean.",
        )
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
        changes["provenance"] = replace(
            provenance, parameters={**provenance.parameters, **scope_parameters(scope, selection)}
        )
    return replace(result, **changes) if changes else result


def as_drawn(result: Any, scope: CalculatorScope, mol: Chem.Mol) -> Any:
    """`result` recorded as computed over the whole drawing under `scope`,
    for producers outside the registry (the always-on provider)."""
    everything = tuple(range(len(Chem.GetMolFrags(mol))))
    return read_back(result, scope, Selection(mol=mol, drawing_atoms=None, components=everything))
