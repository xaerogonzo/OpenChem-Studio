"""An energetic FORMULATION: several substances mixed in stated proportions.

Not a molecule, and deliberately not stored as one. A formulation is
ANFO, Composition B, a dynamite -- a recipe whose detonation behaviour
belongs to the mixture and to nothing in it.

## Why it earns a document of its own

`chem/energetics.py` estimates detonation pressure and velocity for a
single C/H/N/O substance, and Kamlet-Jacobs' arbitrary decomposition is
stated only "for a compound with at least enough oxygen to convert
hydrogen to H2O but no more than is also required to convert carbon to
CO2". Measured through the shipped calculator, the classic FORMULATION
components each fall outside it:

    TNT                  answered
    RDX                  answered
    ammonium nitrate     REFUSED  over-oxidised: needs 2 <= O <= 2, has 3
    nitroglycerin        REFUSED  over-oxidised: needs 2.5 <= O <= 8.5, has 9
    dodecane (fuel oil)  REFUSED  too little oxygen to form water

...and their MIXTURE lands inside it. ANFO at 94.5/5.5 by mass:

    composite      C0.3195 H4.5857 N1.9468 O2.9201
    the window     2.2928 <= O <= 2.9317, has 2.9201   INSIDE

So this reaches cases the single-substance path structurally cannot
answer, rather than being a convenience over it.

## MASS FRACTIONS IN, MOLES FOR THE FORMULA -- and they are different

A formulation is specified the way it is mixed: by MASS. The composite
`CaHbNcOd` is a per-mole quantity and needs mole fractions
(`n_i = w_i / M_i`), while Q is per GRAM and is mass-weighted. Both
conversions are real and they are not interchangeable.

**The error to guard is treating the user's mass fractions AS mole
fractions**, and it is silent. Measured on ANFO:

    mass -> mole (correct)   C0.3195 H4.5857 N1.9468 O2.9201   INSIDE
    mass AS mole (wrong)     C0.6600 H5.2100 N1.8900 O2.8350   INSIDE

Both land inside the arbitrary and the oxygen counts differ by 3%, so no
domain check can catch it -- only a fixture asserting the composite
formula.

## What is STORED is what the user typed

`CrystalModel`'s rule, for `CrystalModel`'s reason: the components and
their mass fractions as entered, never the normalised or composite
result. A later improvement to the compositing then reaches formulations
already saved; freezing the derived numbers would stick them to whatever
the arithmetic was on the day they were entered.

The SMILES is stored rather than a `MoleculeModel` uuid, deliberately. A
formulation must still open on a machine where the project's molecule
list has been edited, and a component that silently became a dangling
reference would produce a composite formula quietly missing a term.

## Scope: property calculation, never synthesis

This models what a stated mixture would DO. It does not describe how to
prepare one, and nothing here should grow in that direction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

#: How far the stated mass fractions may sum from 1 before the
#: formulation is refused. Loose enough for a recipe typed as 94.5/5.5,
#: tight enough that a forgotten component cannot pass: a missing 5%
#: binder is 0.05, fifty times this.
FRACTION_TOLERANCE = 1e-3


@dataclass(frozen=True)
class FormulationComponent:
    """One substance in the mixture, as the user stated it."""

    #: The structure, as SMILES. See the module docstring for why this is
    #: not a `MoleculeModel` uuid.
    smiles: str
    #: MASS fraction, as entered. Not normalised -- `Formulation` checks
    #: the sum and the compositing converts to moles.
    mass_fraction: float
    #: CONDENSED-phase standard enthalpy of formation, kcal/mol.
    #: Required, never estimated: Joback gives the ideal-GAS value and the
    #: published bridge to the solid excludes every classic energetic
    #: material, its domain stopping at two internal rotors where the
    #: nitro groups ARE the rotors.
    enthalpy_kcal_per_mol: float
    display_name: str = ""


@dataclass(frozen=True)
class FormulationModel:
    """A formulation as a project DOCUMENT: identity, a name, a recipe.

    Separate from the arithmetic in `chem/energetics.py`, which has no
    business carrying a uuid -- the same split as `CrystalModel` beside
    `Crystal` and `MoleculeModel` beside an RDKit `Mol`.
    """

    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    display_name: str = "Untitled formulation"
    components: tuple[FormulationComponent, ...] = ()
    #: The MEASURED bulk density the charge was loaded to, g/cm3.
    #:
    #: **NEVER a weighted average of the components' crystal densities.**
    #: That substitution is arithmetically reasonable, produces a
    #: plausible pressure and is wrong: detonation pressure goes as the
    #: SQUARE of this, so an error here is not a small one, and a packed
    #: charge is nowhere near the density of its ingredients' crystals.
    #: There is no source-backed route from a recipe to this number, so it
    #: is supplied or the estimate is refused.
    loading_density: float | None = None
    notes: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def stated_fraction_total(self) -> float:
        return sum(component.mass_fraction for component in self.components)

    @property
    def fractions_are_consistent(self) -> bool:
        """Whether the stated mass fractions sum to 1.

        Checked rather than silently normalised: 94.5 + 5.0 renormalises
        to a perfectly ordinary-looking recipe that is not the one the
        user meant, and the missing 0.5 is exactly the kind of typo a
        renormalisation hides forever.
        """
        if not self.components:
            return False
        return abs(self.stated_fraction_total - 1.0) <= FRACTION_TOLERANCE

    def to_dict(self) -> dict:
        return {
            "uuid": self.uuid,
            "display_name": self.display_name,
            "components": [
                {
                    "smiles": component.smiles,
                    "mass_fraction": component.mass_fraction,
                    "enthalpy_kcal_per_mol": component.enthalpy_kcal_per_mol,
                    "display_name": component.display_name,
                }
                for component in self.components
            ],
            "loading_density": self.loading_density,
            "notes": self.notes,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> FormulationModel:
        return cls(
            uuid=data.get("uuid") or str(uuid.uuid4()),
            display_name=data.get("display_name", "Untitled formulation"),
            components=tuple(
                FormulationComponent(
                    smiles=entry.get("smiles", ""),
                    mass_fraction=float(entry.get("mass_fraction", 0.0)),
                    enthalpy_kcal_per_mol=float(entry.get("enthalpy_kcal_per_mol", 0.0)),
                    display_name=entry.get("display_name", ""),
                )
                for entry in data.get("components", [])
            ),
            loading_density=data.get("loading_density"),
            notes=data.get("notes", ""),
            metadata=dict(data.get("metadata", {})),
        )
