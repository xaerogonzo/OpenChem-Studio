"""A calculator declares where it stands, and the list of those that have not yet only shrinks.

Found in a live session on a nitramine: Thermophysical Properties (Joback) and
Detonation both read "Not applicable", for different reasons, sitting in the
launcher beside Elemental Analysis as though they were equals. See
`domain/calculator_support.py` for the two axes (stage, visibility) and why they
are not merged.
"""

from __future__ import annotations

import dataclasses

import pytest
from rdkit import Chem

from openchem import help as help_docs
from openchem.domain.calculator_support import (
    LEGACY_UNCLASSIFIED,
    UNCLASSIFIED,
    CalculatorSupport,
    SupportStage,
    Visibility,
    help_anchor_for,
    is_classified,
    is_offered_by_default,
    is_visible,
    support_of,
)

#: THE RATCHET. The ids that were listed as unclassified when this was
#: introduced (2026-09-24), copied here on purpose: `LEGACY_UNCLASSIFIED` may
#: only ever be a subset of it. Classifying a calculator means giving it a
#: `support` AND deleting its name from the set in the source; a name added
#: there for a NEW calculator would satisfy every other check in this file, and
#: this is the one that refuses it.
_RECORDED_LEGACY = frozenset({
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


@pytest.fixture(scope="module")
def built_in():
    from openchem.bootstrap import build_service_container

    registry = build_service_container().calculator_registry
    return [d for category in registry.categories() for d in registry.by_category(category)]


# --- the declaration -----------------------------------------------------------


def test_a_calculator_that_is_not_stable_must_say_why():
    with pytest.raises(ValueError, match="must say why"):
        CalculatorSupport(SupportStage.LIMITED, Visibility.SHOWN)
    with pytest.raises(ValueError, match="must say why"):
        CalculatorSupport(SupportStage.STABLE, Visibility.HIDDEN, support_reason="  ")


def test_a_stable_calculator_that_is_shown_needs_no_reason():
    assert CalculatorSupport(SupportStage.STABLE, Visibility.SHOWN).needs_a_reason is False


def test_an_experimental_calculator_is_never_shown_by_default():
    with pytest.raises(ValueError, match="hidden by default"):
        CalculatorSupport(SupportStage.EXPERIMENTAL, Visibility.SHOWN, support_reason="x")


def test_stage_and_visibility_are_different_axes():
    """Detonation is the case: STABLE (checked against the source's own tables)
    and hidden (specialist). Merging the axes would have to call it one or the
    other."""
    support = CalculatorSupport(SupportStage.STABLE, Visibility.HIDDEN, support_reason="specialist")
    assert support.stage is SupportStage.STABLE and support.default_visibility is Visibility.HIDDEN


def test_an_unclassified_definition_is_treated_as_stable_and_shown():
    """A plugin's calculator, or a test double, that never heard of this."""
    bare = type("Bare", (), {})()
    assert support_of(bare) is UNCLASSIFIED and not is_classified(bare)
    assert is_offered_by_default(bare)


# --- effective visibility ------------------------------------------------------


def _definition(default: Visibility):
    reason = "why" if default is Visibility.HIDDEN else ""
    return type("D", (), {"support": CalculatorSupport(SupportStage.STABLE, default, reason)})()


@pytest.mark.parametrize(
    "default,show_hidden,override,expected",
    [
        (Visibility.SHOWN, False, None, True),
        (Visibility.SHOWN, True, None, True),
        (Visibility.HIDDEN, False, None, False),
        (Visibility.HIDDEN, True, None, True),
        # The person's own choice for THIS calculator wins over everything.
        (Visibility.HIDDEN, False, Visibility.SHOWN, True),
        (Visibility.SHOWN, True, Visibility.HIDDEN, False),
        (Visibility.HIDDEN, True, Visibility.HIDDEN, False),
    ],
)
def test_effective_visibility(default, show_hidden, override, expected):
    assert is_visible(_definition(default), show_hidden=show_hidden, override=override) is expected


# --- the guards ----------------------------------------------------------------


def test_every_built_in_is_classified_or_named_as_not_yet(built_in):
    """The list is exactly the unclassified built-ins: neither a calculator
    nobody decided about, nor a stale name for one that was classified."""
    unclassified = {d.calculator_id for d in built_in if not is_classified(d)}
    assert unclassified == set(LEGACY_UNCLASSIFIED), (
        f"unclassified and not listed: {sorted(unclassified - LEGACY_UNCLASSIFIED)}; "
        f"listed but classified or gone: {sorted(set(LEGACY_UNCLASSIFIED) - unclassified)}"
    )


def test_the_legacy_list_only_shrinks(built_in):
    """Adding a name for a NEW calculator would satisfy the check above."""
    assert LEGACY_UNCLASSIFIED <= _RECORDED_LEGACY, sorted(LEGACY_UNCLASSIFIED - _RECORDED_LEGACY)


def test_the_ratchet_records_every_built_in_that_predates_this(built_in):
    """The ratchet's own control arm: it must actually name the migration set,
    or "only shrinks" is vacuous."""
    assert len(_RECORDED_LEGACY) == 66
    assert {d.calculator_id for d in built_in} >= _RECORDED_LEGACY


def test_every_built_in_has_a_help_anchor_on_its_own_section(built_in):
    """A "Learn more" for a calculator must land on THAT calculator's section."""
    topics = {topic.key: topic for topic in help_docs.topics()}
    anchors = [help_anchor_for(d.calculator_id) for d in built_in]
    assert len(set(anchors)) == len(anchors), "two calculators share one anchor"
    missing = [a for a in anchors if a not in topics]
    assert not missing, f"no help section for: {missing}"
    for definition in built_in:
        assert topics[help_anchor_for(definition.calculator_id)].document == "CALCULATOR_REFERENCE.md"


def test_the_generator_and_the_launcher_spell_an_anchor_the_same_way():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from build_calculator_reference import anchor_for

    for calculator_id in ("joback_properties", "orca.opt_freq", "docking.vina", "pka"):
        assert anchor_for(calculator_id) == help_anchor_for(calculator_id)
    assert help_anchor_for("orca.opt_freq") == "calc-orca-opt-freq"


# --- the two calculators the census case classified -----------------------------


def _definition_by_id(built_in, calculator_id):
    return next(d for d in built_in if d.calculator_id == calculator_id)


def test_joback_is_limited_and_hidden_with_its_reason(built_in):
    support = support_of(_definition_by_id(built_in, "joback_properties"))
    assert support.stage is SupportStage.LIMITED and support.default_visibility is Visibility.HIDDEN
    assert "ring nitrogen" in support.support_reason and support.scope_note


def test_detonation_is_stable_but_hidden_as_a_specialist_calculator(built_in):
    support = support_of(_definition_by_id(built_in, "detonation"))
    assert support.stage is SupportStage.STABLE and support.default_visibility is Visibility.HIDDEN
    assert "specialist" in support.support_reason.lower()


def test_the_joback_reason_is_still_true():
    """**A REASON IS A CLAIM, AND PROSE IS THE ONE PLACE NOTHING CHECKS IT.** It
    says RDX and HMX are refused while TNT and PETN run; if the method's
    coverage changes, the text must change with it."""
    from openchem.chem.joback import compute_joback
    from openchem.domain.calculator import CalculationRefusal

    refused = {
        "RDX": "O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]",
        "HMX": "O=[N+]([O-])N1CN(CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
    }
    ran = {
        "TNT": "Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
        "PETN": "C(C(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-])O[N+](=O)[O-]",
    }
    from openchem.domain.common import CacheState

    for name, smiles in refused.items():
        result = compute_joback(Chem.MolFromSmiles(smiles), "u", {})
        assert result.cache_state is CacheState.FAILED and result.inapplicable, name
    for name, smiles in ran.items():
        result = compute_joback(Chem.MolFromSmiles(smiles), "u", {})
        assert result.cache_state is not CacheState.FAILED, name


def test_a_definition_can_be_replaced_with_a_support_without_mutating_the_original(built_in):
    """Effective visibility is policy over the definition, which is never mutated."""
    original = _definition_by_id(built_in, "joback_properties")
    swapped = dataclasses.replace(original, support=None)
    assert is_classified(original) and not is_classified(swapped)


def test_every_family_guide_link_resolves_to_a_real_guide(built_in):
    """A "See also" that lands nowhere is worse than none. Both the heading and its
    GitHub slug must name a real topic, since the same link is read on GitHub and
    in the help window (`HelpDialog._on_link` matches the slug)."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from build_calculator_reference import FAMILY_GUIDES

    from openchem.ui.dialogs.help_dialog import _slug

    ids = {d.calculator_id for d in built_in}
    topics = help_docs.topics()
    for calculator_id, (title, slug) in FAMILY_GUIDES.items():
        assert calculator_id in ids, f"{calculator_id} is not a registered calculator"
        match = [t for t in topics if t.title == title and t.document == "USER_GUIDE.md"]
        assert len(match) == 1, f"no single guide headed {title!r}"
        assert _slug(match[0].title) == slug, (title, slug, _slug(match[0].title))


def test_a_family_guide_ranks_nothing():
    """"Descriptive, never a ranking": no "recommended" without a declared basis.
    The words that would smuggle one in are refused in the guide itself."""
    text = help_docs.topic_markdown("charge-models").lower()
    for word in ("recommended", "best choice", "most accurate", "we recommend", "use this one"):
        assert word not in text, word
