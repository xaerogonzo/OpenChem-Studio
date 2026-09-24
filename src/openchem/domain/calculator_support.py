"""How far a calculator can be trusted to run, and whether it is offered by default.

**A CALCULATOR THAT REFUSES MOST OF WHAT YOU DRAW IS NOT BROKEN, AND SHOULD NOT
BE OFFERED AS THOUGH IT WERE EVERYDAY EQUIPMENT.** A live session drew a
nitramine and found Thermophysical Properties and Detonation both saying
"Not applicable" -- for different reasons. Joback (1987) has no group for a ring
tertiary amine, so it refuses RDX, HMX and most drug-like molecules while
running TNT and PETN; Kamlet-Jacobs is a specialist estimate that needs two
numbers no structure can supply. Both were sitting in the launcher beside
Elemental Analysis, presented as equals, and the person reading them could not
tell "this molecule is outside the method" from "this application is broken".

So every calculator can declare where it stands, and the launcher can offer only
the ones that suit the general case, with the rest one click away in Settings and
a sentence saying WHY.

**TWO DIFFERENT AXES, AND THEY MUST NOT BE MERGED.**

    stage        the maturity of THIS APPLICATION'S IMPLEMENTATION of the method.
                 It never says anything about the published method: "experimental"
                 means "this implementation is not yet validated for default use",
                 not "the literature is unsure". EXPERIMENTAL -> LIMITED -> STABLE.
    visibility   a DISCOVERY policy: whether the launcher offers it by default.
                 Hiding is not a verdict. Detonation is STABLE (its arithmetic is
                 checked against the source's own table) and hidden (specialist).

Runtime availability -- needs an input, needs a sidecar -- is a THIRD thing and
lives in a result's refusal kind (`domain.refusal_kinds`), never here: whether
Kamlet-Jacobs can run right now depends on what the person has typed, which is
not a property of the calculator.

**VISIBILITY CONTROLS DISCOVERY ONLY.** A hidden calculator is still searchable,
still documented, and its stored results are still readable; enabling one never
runs anything. Effective visibility is the default, overridden by the person's own
preference, and the definition is never mutated.

**A CALCULATOR IS CLASSIFIED OR IT IS LISTED AS NOT YET, AND THE LIST ONLY
SHRINKS.** `CalculatorDefinition.support` has no meaningful default -- `None`
means "nobody decided", and a guard fails for a built-in calculator that is
neither classified nor named in `LEGACY_UNCLASSIFIED`. That list is the set of
ids that existed when this was introduced, treated as STABLE and shown so nothing
changed under anybody; it is a migration to be emptied by the calculator census,
never a permanent exemption, and a guard refuses a name being ADDED to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SupportStage(str, Enum):
    """Maturity of this application's implementation of a method."""

    #: Implemented, not yet validated for default use. Always hidden by default.
    EXPERIMENTAL = "experimental"
    #: Validated inside a stated scope that leaves out much of what people draw
    #: (Joback has no group for a ring tertiary amine). "Limited" describes the
    #: scope and never apologises for it.
    LIMITED = "limited"
    #: Validated for the scope it declares, and offered to everyone in it.
    STABLE = "stable"


class Visibility(str, Enum):
    """Whether the launcher offers a calculator by default."""

    SHOWN = "shown"
    HIDDEN = "hidden"


@dataclass(frozen=True)
class CalculatorSupport:
    """One calculator's declared stage and default visibility, with the reason."""

    stage: SupportStage
    default_visibility: Visibility
    #: WHY it is not STABLE, or why it is hidden -- shown beside the calculator in
    #: Settings ("Why hidden?"). Required whenever either is true, and nothing
    #: else needs one.
    support_reason: str = ""
    #: The chemical coverage in a phrase ("C/H/N/O explosives"), a separate fact
    #: from the reason: a STABLE calculator still has a scope.
    scope_note: str = ""

    def __post_init__(self) -> None:
        if self.stage is SupportStage.EXPERIMENTAL and self.default_visibility is Visibility.SHOWN:
            raise ValueError("an EXPERIMENTAL calculator is hidden by default, never shown")
        if self.needs_a_reason and not self.support_reason.strip():
            raise ValueError(
                "a calculator that is not STABLE, or is hidden by default, must say why in "
                "`support_reason` -- Settings shows it beside the calculator"
            )

    @property
    def needs_a_reason(self) -> bool:
        return self.stage is not SupportStage.STABLE or self.default_visibility is Visibility.HIDDEN


#: What an unclassified calculator is treated as. Deliberately the neutral
#: answer: a plugin's calculator, or a test double, that never heard of this
#: module behaves exactly as it always did.
UNCLASSIFIED = CalculatorSupport(SupportStage.STABLE, Visibility.SHOWN)

#: The built-in calculators that predate this declaration, treated as STABLE and
#: shown. **THIS LIST ONLY SHRINKS**: `tests/test_calculator_support.py` fails for
#: a built-in calculator that is neither classified nor named here, and for a name
#: added here that was not already in it. Classifying a calculator means giving it
#: a `support` and DELETING its name from this set in the same change.
LEGACY_UNCLASSIFIED: frozenset[str] = frozenset({
    "admet_ml", "alignment_3d", "atom_sasa", "atomic_polarizability", "bbb_descriptors",
    "bird_aromaticity", "cns_mpo", "crippen_logp_contrib", "crippen_mr_contrib",
    "dipole_moment", "docking.vina", "elemental_analysis", "functional_groups",
    "gasteiger_charge_at_ph", "geometry_analysis", "geometry_partial_charge", "griffin_hlb",
    "hansen_solubility", "hbond_vs_ph", "homa_aromaticity", "huckel_analysis",
    "huckel_pi_density", "interaction_analysis", "isoelectric_point", "iupac_name",
    "lewis_adduct", "lewis_hsab", "lewis_sites", "locants", "logd", "major_microspecies",
    "markush_enumeration", "mass_spectrum", "molecular_dynamics", "nmr_database",
    "orbital_electronegativity", "orca.delta_scf", "orca.led", "orca.nmr", "orca.nmr_coupling",
    "orca.opt", "orca.opt_freq", "orca.sp", "oxidation_states", "oxygen_balance", "pka",
    "pka_microspecies", "polar_surface_area", "polarizability", "regulatory_screen",
    "resonance_forms", "ring_systems", "solubility", "stereo_descriptors", "stereocenters",
    "stereoisomers", "steric_analysis", "structural_frameworks", "substance_analysis",
    "substructure_search", "surface_analysis", "tautomers", "topology_analysis",
    "topology_distance_degree", "topology_eccentricity", "tsei_projection",
})


def support_of(definition) -> CalculatorSupport:
    """The declared support of `definition`, or `UNCLASSIFIED`'s neutral answer."""
    return getattr(definition, "support", None) or UNCLASSIFIED


def is_classified(definition) -> bool:
    return getattr(definition, "support", None) is not None


def help_anchor_for(calculator_id: str) -> str:
    """The Help anchor of a calculator's own section in the calculator reference.

    A help anchor is `[a-z0-9-]+` -- no underscores -- while a calculator id uses
    them (and the ORCA ones a dot), so the two differ by separator. **THE ONE
    RECIPE**: `tools/build_calculator_reference.py` writes the anchor with it and
    every "Learn more" resolves through it, so a link and its target cannot use
    two spellings.
    """
    return "calc-" + calculator_id.replace("_", "-").replace(".", "-")


def is_offered_by_default(definition) -> bool:
    return support_of(definition).default_visibility is Visibility.SHOWN


def is_visible(definition, *, show_hidden: bool, override: Visibility | None = None) -> bool:
    """Whether the launcher offers `definition`, given the person's preferences.

    The person's own choice for THIS calculator wins over everything; failing
    that, a calculator hidden by default follows the master toggle; and a shown
    one is shown. Pure, so the Properties panel, the Settings page and
    "Run selected" cannot disagree about it.
    """
    if override is not None:
        return override is Visibility.SHOWN
    if is_offered_by_default(definition):
        return True
    return show_hidden
