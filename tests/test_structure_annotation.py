"""Structural annotation from the vendored nomenclature engine.

The tests that matter most here are the ones pinning the LIMITS. This
module's coverage is uneven by nature -- rings and stereocentres are found
on every molecule, locants on barely a third of atoms -- and a future change
that silently widened or narrowed that would be invisible without a test
saying what was measured.
"""

from __future__ import annotations

from rdkit import Chem

from openchem.chem.structure_annotation import (
    LocantSource,
    StructureAnnotation,
    annotate,
    compute_functional_groups,
    compute_locants,
    compute_ring_systems,
    compute_stereocenters,
    name_derivation,
    name_fragment,
)
from openchem.domain.common import CacheState

# Named because several tests share them and the shapes matter:
CAFFEINE = "Cn1cnc2c1c(=O)n(C)c(=O)n2C"      # retained name -> bare LeafTree
CAMPHOR = "CC1(C)C2CCC1(C)C(=O)C2"           # retained name, bridged ring
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"            # substitutive, two FGs
D_ALANINE = "C[C@@H](N)C(=O)O"               # (R)-alanine: one centre, two FGs
NAPHTHALENE = "c1ccc2ccccc2c1"               # bare ring in the retained table
CHOLESTEROL = (
    "C[C@H](CCCC(C)C)[C@H]1CC[C@H]2[C@@H]3CC=C4C[C@@H](O)CC[C@]4(C)[C@H]3CC[C@]12C"
)


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, f"test fixture SMILES did not parse: {smiles}"
    return mol


# --- Never raises -------------------------------------------------------


def test_a_none_molecule_returns_an_error_rather_than_raising():
    """An annotation decorates a view. A caller that hands over nothing
    should get an empty annotation carrying the reason, not an exception
    that takes down the panel drawing it."""
    result = annotate(None)
    assert isinstance(result, StructureAnnotation)
    assert result.error is not None
    assert result.locants == ()
    assert result.groups == ()


def test_an_empty_molecule_annotates_to_nothing_without_error():
    result = annotate(Chem.MolFromSmiles(""))
    assert result.atom_count == 0
    assert result.locant_coverage() == 0.0


# --- Rings and stereo: the parts that work on every molecule -------------


def test_rings_are_found_even_when_naming_returns_a_bare_retained_string():
    """Caffeine names to a LeafTree carrying only the word "caffeine" --
    no numbering, no atom indices. Ring perception is a separate pass and
    is unaffected, which is the whole reason this module is built on
    perception rather than on the naming tree."""
    result = annotate(_mol(CAFFEINE))
    assert len(result.rings) == 1
    ring = result.rings[0]
    assert ring.kind == "fused"
    assert ring.aromatic is True
    assert len(ring.atoms) == 9


def test_a_bridged_ring_is_reported_as_bridged():
    """Camphor's bicycloheptane, again from a molecule whose name is
    retained and whose tree carries no indices."""
    result = annotate(_mol(CAMPHOR))
    assert len(result.rings) == 1
    assert result.rings[0].kind == "bridged"


def test_a_ring_system_is_one_annotation_not_one_per_ring():
    """Naphthalene is a single fused 10-atom system, not two benzenes.
    That matches how the engine names it and how a chemist talks about it."""
    result = annotate(_mol(NAPHTHALENE))
    assert len(result.rings) == 1
    assert len(result.rings[0].atoms) == 10


def test_stereocentres_agree_with_rdkit():
    """Measured across the naming corpus as exact agreement (13 of 13), so
    this detector is used in preference to RDKit's rather than checked
    against it. Pinned on a molecule with many centres."""
    mol = _mol(CHOLESTEROL)
    expected = Chem.FindMolChiralCenters(
        mol, includeUnassigned=False, useLegacyImplementation=False
    )
    result = annotate(mol)
    tetrahedral = [s for s in result.stereocenters if s.kind == "tetrahedral"]
    assert len(tetrahedral) == len(expected)
    assert {s.atom_index for s in tetrahedral} == {idx for idx, _ in expected}


def test_a_stereocentre_carries_its_cip_descriptor():
    result = annotate(_mol(D_ALANINE))
    assert len(result.stereocenters) == 1
    assert result.stereocenters[0].descriptor in ("R", "S")


# --- Functional groups --------------------------------------------------


def test_functional_groups_carry_the_atoms_they_claim():
    result = annotate(_mol(ASPIRIN))
    kinds = {g.type for g in result.groups}
    assert "carboxylic_acid" in kinds
    acid = next(g for g in result.groups if g.type == "carboxylic_acid")
    assert acid.anchor in acid.atoms
    assert len(acid.atoms) == 3
    assert acid.suffix_eligible is True


def test_group_by_atom_maps_every_claimed_atom():
    result = annotate(_mol(D_ALANINE))
    claimed = {i for g in result.groups for i in g.atoms}
    assert set(result.group_by_atom) == claimed


def test_caffeine_detects_no_functional_groups_at_all():
    """Both of caffeine's carbonyls are ring-embedded lactams and neither is
    claimed, so a molecule that plainly has functional groups annotates as
    having none. Measured at 4 of 181 corpus molecules.

    `test_a_lactam_carbonyl_is_claimed_by_no_group_at_all` below pins down
    WHY, which turns out to be half deliberate. This test just holds the
    consequence at the annotation level, so that a detector that later
    learns to claim these is noticed rather than silently improving a number
    no one was watching."""
    result = annotate(_mol(CAFFEINE))
    assert result.groups == ()


# --- Locants, and their honest limits -----------------------------------


def test_locants_come_from_the_parent_numbering_when_the_tree_has_one():
    result = annotate(_mol(D_ALANINE))
    assert result.locants
    assert all(loc.source is LocantSource.PARENT for loc in result.locants)
    assert set(result.locant_by_atom.values()) == {"1", "2", "3"}


def test_a_retained_ring_recovers_locants_the_naming_tree_never_supplied():
    """Naphthalene names to a bare retained string, so the tree offers no
    numbering at all -- but the ring is in the vendored table with a full
    locant map, and matching that template back onto the molecule recovers
    it. This is the only locant source for 24 corpus molecules."""
    result = annotate(_mol(NAPHTHALENE))
    assert len(result.locants) == 10
    assert all(
        loc.source is LocantSource.RETAINED_RING for loc in result.locants
    )
    assert "4a" in result.locant_by_atom.values()


def test_caffeine_takes_its_purine_numbering():
    """THE FIX THE OLD VERSION OF THIS TEST ASKED FOR.

    This used to assert caffeine got NO locants: carving the ring out with
    `MolFragmentToSmiles` dropped the substituents from its N-methylated
    nitrogens, giving `c1nc2ncncc2n1`, which does not parse. It now goes
    through the engine's own `get_ring_canonical_smiles`, resolves to
    `9H-purine`, and takes the whole map.

    VERIFIED AGAINST THE NAME, not against itself: caffeine is
    1,3,7-trimethylxanthine, so the three methylated nitrogens must come
    back N1, N3 and N7 and the bare one N9. An earlier attempt that assumed
    the locant map was keyed to sorted parent order produced a complete set
    of confident WRONG numbers -- N7 reported as position 2 -- which is
    exactly what this assertion catches."""
    mol = _mol(CAFFEINE)
    locants = annotate(mol).locant_by_atom

    assert locants == {
        1: "7", 2: "8", 3: "9", 4: "4", 5: "5", 6: "6",
        8: "1", 10: "2", 12: "3",
    }
    # The nitrogens carrying methyls are 1, 3 and 7; the bare one is 9.
    methylated = {
        locants[atom.GetIdx()]
        for atom in mol.GetAtoms()
        if atom.GetSymbol() == "N"
        and any(n.GetSymbol() == "C" and n.GetDegree() == 1 for n in atom.GetNeighbors())
    }
    assert methylated == {"1", "3", "7"}


def test_a_bridged_retained_skeleton_still_has_no_numbering():
    """The limit that remains. Camphor names to a retained string and its
    bridged skeleton is not a numbered entry in the ring table, so there is
    nothing to recover -- 76 of the 181 corpus molecules are like this."""
    result = annotate(_mol(CAMPHOR))
    assert result.locants == ()
    assert result.locant_coverage() == 0.0


def test_locant_coverage_lets_a_caller_decline_to_show_a_numbering_view():
    """Half of all molecules produce no numbering. A UI needs to ask before
    offering the view, rather than rendering a blank one."""
    assert annotate(_mol(CAMPHOR)).locant_coverage() == 0.0
    assert annotate(_mol(D_ALANINE)).locant_coverage() > 0.0


def test_parent_numbering_is_never_overwritten_by_a_ring_table_locant():
    """A molecule's own assigned numbering outranks a skeleton's
    conventional one where both exist."""
    result = annotate(_mol(ASPIRIN))
    parent_atoms = {
        loc.atom_index
        for loc in result.locants
        if loc.source is LocantSource.PARENT
    }
    ring_atoms = {
        loc.atom_index
        for loc in result.locants
        if loc.source is LocantSource.RETAINED_RING
    }
    assert not (parent_atoms & ring_atoms)


# --- Indices are the caller's ------------------------------------------


def test_annotations_index_the_molecule_passed_in_not_a_canonical_copy():
    """The engine does not re-canonicalise, which is the single property
    that lets this drive per-atom colouring. If it ever started to, every
    highlight in the application would land on the wrong atom -- so this is
    pinned against a molecule built in a deliberately non-canonical order."""
    mol = _mol("OC(=O)C")  # acid written first; canonical form writes it last
    result = annotate(mol)
    acid = next(g for g in result.groups if g.type == "carboxylic_acid")
    # Atom 0 is the hydroxyl oxygen as written here. It must be claimed by
    # the acid, which is only true if indices were preserved.
    assert 0 in acid.atoms
    for group in result.groups:
        assert all(0 <= i < mol.GetNumAtoms() for i in group.atoms)


def test_decisions_are_plain_strings_not_vendor_objects():
    """Nothing outside this module should have to import a vendor type."""
    result = annotate(_mol(D_ALANINE))
    assert all(isinstance(d, str) for d in result.decisions)


# --- The ring-systems calculator ----------------------------------------

BIPHENYL = "c1ccc(-c2ccccc2)cc1"
SPIRO_DECANE = "C1CCC2(C1)CCCCC2"


def test_ring_calculator_marks_data_categorical_not_continuous():
    """The values are ring system IDs. Rendering them on a sequential ramp
    would imply system 1 and system 2 are 'close', which is meaningless --
    so the dataset carries the hint that routes it to a qualitative
    palette."""
    dataset = compute_ring_systems(_mol(NAPHTHALENE), "uuid", {})
    assert dataset.provenance.parameters["scale"] == "categorical"


def test_an_acyclic_molecule_produces_an_empty_result_not_a_failed_one():
    """Ethanol having no rings is a fact about ethanol. A permanent red
    'failed' row for it would be wrong -- the same call DescriptorService
    already makes for a molecule with no structure yet."""
    dataset = compute_ring_systems(_mol("CCO"), "uuid", {})
    assert dataset.values == {}
    assert dataset.error is None
    assert dataset.cache_state is not CacheState.FAILED


def test_biphenyl_is_two_ring_systems_and_naphthalene_is_one():
    """The distinction the whole feature turns on. Both have ten aromatic
    carbons in two rings; naphthalene's share an edge and biphenyl's share
    a bond between them, which makes one a single fused system and the
    other two separate ones."""
    biphenyl = compute_ring_systems(_mol(BIPHENYL), "uuid", {})
    naphthalene = compute_ring_systems(_mol(NAPHTHALENE), "uuid", {})
    assert len(set(biphenyl.values.values())) == 2
    assert len(set(naphthalene.values.values())) == 1


def test_a_bridged_system_reports_its_bridgeheads():
    """Camphor's two bridgehead carbons -- the atoms its three bridges run
    between. Found from the graph, since the engine reports bridge sizes
    rather than endpoints."""
    dataset = compute_ring_systems(_mol(CAMPHOR), "uuid", {})
    notes = dataset.provenance.parameters["atom_notes"]
    assert sorted(notes.values()) == ["bridgehead", "bridgehead"]


def test_a_spiro_centre_keeps_its_role_even_once_it_has_a_locant():
    """A locant usually beats a role note, but not here: '4a' encodes
    fusion in the locant itself, while the spiro centre of spiro[4.5]decane
    is plain '5' and would lose the single fact worth marking if the locant
    simply overwrote it."""
    dataset = compute_ring_systems(_mol(SPIRO_DECANE), "uuid", {})
    notes = dataset.provenance.parameters["atom_notes"]
    assert any(note.endswith("spiro") for note in notes.values())


def test_a_fusion_locant_is_not_annotated_redundantly():
    """Naphthalene's ring-fusion atoms are '4a' and '8a'. The letter suffix
    already says 'fusion', so appending the word would be noise."""
    dataset = compute_ring_systems(_mol(NAPHTHALENE), "uuid", {})
    notes = dataset.provenance.parameters["atom_notes"]
    assert "4a" in notes.values()
    assert not any("fusion" in note for note in notes.values())


def test_ring_systems_are_described_for_a_legend():
    dataset = compute_ring_systems(_mol(CAMPHOR), "uuid", {})
    labels = list(dataset.provenance.parameters["category_labels"].values())
    assert labels == ["bridged [2.2.1], 7 atoms"]


def test_caffeine_gets_its_ring_system_although_it_gets_no_locants():
    """The reason rings were built before locants. Caffeine names to a bare
    retained string and annotates to zero locants and zero functional
    groups -- but its fused ring system is found like any other."""
    dataset = compute_ring_systems(_mol(CAFFEINE), "uuid", {})
    assert len(set(dataset.values.values())) == 1
    assert len(dataset.values) == 9


def test_the_label_mode_option_actually_changes_the_labels():
    """A real choice, not an option added to satisfy the convention that
    every calculator has one: which labelling is useful depends on the
    question. Fusion patterns want positions; scaffold identification wants
    roles and finds a full set of locants to be clutter."""
    mol = _mol(NAPHTHALENE)
    locants = compute_ring_systems(mol, "uuid", {"label_mode": "Locants, with roles"})
    roles = compute_ring_systems(mol, "uuid", {"label_mode": "Structural roles only"})
    system = compute_ring_systems(mol, "uuid", {"label_mode": "Ring system"})

    assert locants.provenance.parameters["atom_notes"][3] == "4a"
    assert roles.provenance.parameters["atom_notes"][3] == "fusion"
    assert system.provenance.parameters["atom_notes"][3].startswith("fused aromatic")
    # Roles mode marks only the atoms that HAVE a role; the other two label
    # every atom in the system.
    assert len(roles.provenance.parameters["atom_notes"]) == 2
    assert len(system.provenance.parameters["atom_notes"]) == 10


def test_an_unknown_label_mode_falls_back_rather_than_raising():
    """Parameters arrive from persisted settings, which can outlive a
    renamed choice."""
    dataset = compute_ring_systems(_mol(NAPHTHALENE), "uuid", {"label_mode": "nonsense"})
    assert dataset.values
    assert dataset.error is None


def test_ring_colours_actually_reach_the_2d_depiction():
    """The end-to-end check, because every other test here would pass just
    as well if the layer computed colours that nothing ever drew.

    Biphenyl rather than naphthalene: two ring systems means two DIFFERENT
    palette entries have to survive into the SVG, so a bug that collapsed
    every category to one colour would be caught. Note RDKit emits hex
    uppercase, which is why this compares case-insensitively -- a
    lowercase-only match finds nothing and looks exactly like a feature
    that never rendered."""
    import re

    from rdkit.Chem import AllChem

    from openchem.chem.engine import ChemistryEngine
    from openchem.ui.visualization import build_atom_color_layer

    mol = _mol(BIPHENYL)
    AllChem.Compute2DCoords(mol)
    layer = build_atom_color_layer(
        compute_ring_systems(mol, "uuid", {}), include_labels=True
    )
    svg = ChemistryEngine().render_2d_svg(
        Chem.MolToMolBlock(mol),
        atom_colors=layer.atom_colors,
        atom_labels=layer.atom_labels,
    )

    drawn = {found.upper() for found in re.findall(r"fill:(#[0-9a-fA-F]{6})", svg)}
    expected = {colour.upper() for colour in layer.atom_colors.values()}
    assert len(expected) == 2
    assert expected <= drawn


def test_an_acyclic_molecule_draws_no_ring_colours_at_all():
    """The other half of the check above: no rings must mean no colouring,
    not a molecule painted entirely in category one."""
    from rdkit.Chem import AllChem

    from openchem.ui.visualization import build_atom_color_layer

    mol = _mol("CCO")
    AllChem.Compute2DCoords(mol)
    layer = build_atom_color_layer(compute_ring_systems(mol, "uuid", {}))
    assert layer.atom_colors == {}


# --- The stereocentre calculator ----------------------------------------

L_ALANINE = "N[C@@H](C)C(=O)O"               # (S)-alanine
E_BUTENE = "C/C=C/C"
CIS_DIMETHYLCYCLOHEXANE = "C[C@H]1CC[C@@H](C)CC1"   # pseudo-asymmetric s/s
UNDEFINED_CENTRE = "CC(O)CC"                 # 2-butanol, stereocentre undrawn


def test_cip_descriptors_agree_with_rdkit():
    """Pinned on both hands of the same molecule, so a systematic inversion
    would be caught -- asserting only that a descriptor is 'R or S' would
    pass even if every assignment were backwards."""
    for smiles in (D_ALANINE, L_ALANINE):
        mol = _mol(smiles)
        expected = dict(
            Chem.FindMolChiralCenters(
                mol, includeUnassigned=False, useLegacyImplementation=False
            )
        )
        got = {
            s.atom_index: s.descriptor
            for s in annotate(mol).stereocenters
            if s.kind == "tetrahedral"
        }
        assert got == expected


def test_r_and_s_keep_their_own_colours_in_molecules_that_have_only_one():
    """THE REASON CATEGORY COLOURS ARE FIXED. With colours assigned in order
    of appearance, a molecule with only S centres would take the first
    palette entry -- the same blue an R centre gets elsewhere -- and the
    same colour would mean opposite things in two windows side by side."""
    from openchem.ui.visualization import build_atom_color_layer

    r_only = build_atom_color_layer(compute_stereocenters(_mol(D_ALANINE), "u", {}))
    s_only = build_atom_color_layer(compute_stereocenters(_mol(L_ALANINE), "u", {}))

    assert len(set(r_only.atom_colors.values())) == 1
    assert len(set(s_only.atom_colors.values())) == 1
    assert set(r_only.atom_colors.values()) != set(s_only.atom_colors.values())


def test_pseudo_asymmetric_centres_are_reported():
    """Lowercase r/s. Easy to forget they exist -- there are two in the
    naming corpus -- and dropping them would silently leave real
    stereocentres unmarked."""
    dataset = compute_stereocenters(_mol(CIS_DIMETHYLCYCLOHEXANE), "u", {})
    assert sorted(dataset.provenance.parameters["atom_notes"].values()) == ["s", "s"]


def test_a_double_bond_stereocentre_is_reported():
    dataset = compute_stereocenters(_mol(E_BUTENE), "u", {})
    assert "E" in dataset.provenance.parameters["atom_notes"].values()


def test_an_undrawn_stereocentre_is_marked_rather_than_left_blank():
    """The engine reports only centres whose configuration is SPECIFIED, so
    2-butanol comes back with none at all. Left that way, this view would
    show an unmarked molecule and invite the conclusion that it has no
    stereochemistry -- when the truth is that it has stereochemistry nobody
    has drawn, which is the more actionable fact."""
    assert annotate(_mol(UNDEFINED_CENTRE)).stereocenters == ()

    dataset = compute_stereocenters(_mol(UNDEFINED_CENTRE), "u", {})
    assert dataset.provenance.parameters["atom_notes"] == {1: "unassigned"}


def test_unassigned_centres_can_be_turned_off():
    dataset = compute_stereocenters(
        _mol(UNDEFINED_CENTRE), "u", {"include_unassigned": False}
    )
    assert dataset.values == {}


def test_an_achiral_molecule_produces_an_empty_result_not_a_failed_one():
    dataset = compute_stereocenters(_mol("CCO"), "u", {})
    assert dataset.values == {}
    assert dataset.error is None
    assert dataset.cache_state is not CacheState.FAILED


def test_stereo_colours_actually_reach_the_2d_depiction():
    import re

    from rdkit.Chem import AllChem

    from openchem.chem.engine import ChemistryEngine
    from openchem.ui.visualization import build_atom_color_layer

    mol = _mol(CHOLESTEROL)
    AllChem.Compute2DCoords(mol)
    layer = build_atom_color_layer(
        compute_stereocenters(mol, "u", {}), include_labels=True
    )
    svg = ChemistryEngine().render_2d_svg(
        Chem.MolToMolBlock(mol),
        atom_colors=layer.atom_colors,
        atom_labels=layer.atom_labels,
    )
    drawn = {found.upper() for found in re.findall(r"fill:(#[0-9a-fA-F]{6})", svg)}
    expected = {colour.upper() for colour in layer.atom_colors.values()}
    assert expected
    assert expected <= drawn


# --- The functional-group explorer --------------------------------------

PENICILLIN_G = "CC1(C)S[C@@H]2[C@H](NC(=O)Cc3ccccc3)C(=O)N2[C@H]1C(=O)O"
PYRROLIDINONE = "O=C1CCCN1"
CYCLOHEXANONE = "O=C1CCCCC1"


def test_each_group_type_gets_its_own_colour_within_a_molecule():
    from openchem.ui.visualization import build_atom_color_layer

    layer = build_atom_color_layer(
        compute_functional_groups(_mol(ASPIRIN), "u", {})
    )
    assert len(set(layer.atom_colors.values())) == 2


def test_group_colours_are_deterministic_for_a_given_molecule():
    """Assigned by sorted type name rather than detection order, so the same
    molecule always renders identically."""
    first = compute_functional_groups(_mol(ASPIRIN), "u", {})
    second = compute_functional_groups(_mol(ASPIRIN), "u", {})
    assert first.values == second.values


def test_only_the_anchor_atom_is_labelled():
    """A carboxylic acid covers three atoms; repeating its name on all three
    is noise on a small depiction, and the anchor is the atom the name
    belongs to."""
    dataset = compute_functional_groups(_mol(D_ALANINE), "u", {})
    notes = dataset.provenance.parameters["atom_notes"]
    coloured = dataset.values
    assert len(notes) == 2          # two groups
    assert len(coloured) > len(notes)  # but more atoms than that are coloured


def test_the_suffix_eligible_filter_narrows_to_the_naming_candidates():
    """Aspirin's ester cannot become a suffix; its carboxylic acid can."""
    everything = compute_functional_groups(_mol(ASPIRIN), "u", {})
    narrowed = compute_functional_groups(
        _mol(ASPIRIN), "u", {"only_suffix_eligible": True}
    )
    assert everything.provenance.parameters["groups_detected"] == 2
    assert narrowed.provenance.parameters["groups_detected"] == 1
    assert list(narrowed.provenance.parameters["category_labels"].values()) == [
        "carboxylic acid"
    ]


def test_the_prefix_label_mode_uses_the_naming_prefix():
    dataset = compute_functional_groups(
        _mol(ASPIRIN), "u", {"label_mode": "Prefix form"}
    )
    assert "carboxy" in dataset.provenance.parameters["atom_notes"].values()


def test_a_lactam_carbonyl_is_claimed_by_no_group_at_all():
    """HALF DELIBERATE, and worth pinning precisely rather than as a vague
    'blind spot'.

    The detector carries an explicit endocyclic-amide guard: an amide whose
    carbonyl carbon and nitrogen share a ring is refused, because IUPAC
    names that carbonyl as a ketone rather than an amide. That refusal is
    correct. What is missing is the other half -- the ketone pattern will
    not claim an N-adjacent carbonyl either, so the atom falls through both.

    The contrast is the point: a plain cyclic ketone IS claimed, and an
    acyclic amide IS claimed. Only the combination falls through."""
    assert compute_functional_groups(_mol(CYCLOHEXANONE), "u", {}).values
    assert compute_functional_groups(_mol("CC(=O)NC"), "u", {}).values

    assert compute_functional_groups(_mol(PYRROLIDINONE), "u", {}).values == {}
    assert compute_functional_groups(_mol(CAFFEINE), "u", {}).values == {}


def test_a_molecule_with_no_groups_reports_that_it_found_none():
    """So a view can say 'none found' rather than leave a molecule silently
    bare and let a chemist read caffeine as unfunctionalised."""
    dataset = compute_functional_groups(_mol(CAFFEINE), "u", {})
    assert dataset.provenance.parameters["groups_detected"] == 0
    assert dataset.error is None
    assert dataset.cache_state is not CacheState.FAILED


def test_penicillin_reports_its_exocyclic_amide_and_acid():
    """Its beta-lactam is endocyclic and falls through as above; the side
    chain amide and the carboxylic acid are both claimed."""
    dataset = compute_functional_groups(_mol(PENICILLIN_G), "u", {})
    labels = set(dataset.provenance.parameters["category_labels"].values())
    assert labels == {"secondary amide", "carboxylic acid"}


def test_group_colours_actually_reach_the_2d_depiction():
    import re

    from rdkit.Chem import AllChem

    from openchem.chem.engine import ChemistryEngine
    from openchem.ui.visualization import build_atom_color_layer

    mol = _mol(ASPIRIN)
    AllChem.Compute2DCoords(mol)
    layer = build_atom_color_layer(
        compute_functional_groups(mol, "u", {}), include_labels=True
    )
    svg = ChemistryEngine().render_2d_svg(
        Chem.MolToMolBlock(mol),
        atom_colors=layer.atom_colors,
        atom_labels=layer.atom_labels,
    )
    drawn = {found.upper() for found in re.findall(r"fill:(#[0-9a-fA-F]{6})", svg)}
    expected = {colour.upper() for colour in layer.atom_colors.values()}
    assert len(expected) == 2
    assert expected <= drawn


# --- The locants calculator, and its honest emptiness -------------------


def test_locant_labels_are_the_numbers_and_the_colour_is_the_source():
    """Colouring by locant VALUE would mean twenty categories for a
    twenty-atom molecule, separating nothing. What a reader needs beyond the
    number is where it came from."""
    from openchem.ui.visualization import build_atom_color_layer

    layer = build_atom_color_layer(
        compute_locants(_mol(NAPHTHALENE), "u", {}), include_labels=True
    )
    assert layer.atom_labels[3] == "4a"
    assert len(set(layer.atom_colors.values())) == 1  # all one source


def test_the_two_locant_sources_are_coloured_consistently_across_molecules():
    """Fixed per-source colours, for the same reason R/S are fixed: which
    mechanism produced a number must not depend on which mechanisms some
    other molecule happened to use."""
    from openchem.ui.visualization import build_atom_color_layer

    parent_only = build_atom_color_layer(compute_locants(_mol(D_ALANINE), "u", {}))
    ring_only = build_atom_color_layer(compute_locants(_mol(NAPHTHALENE), "u", {}))

    assert set(parent_only.atom_colors.values()) != set(ring_only.atom_colors.values())


def test_a_molecule_with_no_numbering_explains_itself():
    """THE POINT OF THIS CALCULATOR'S DESIGN. 82 of 181 corpus molecules
    produce no locants -- every retained name. A chemist who asks for IUPAC
    numbering and sees an unmarked structure will read it as a failure
    unless told why."""
    from openchem.ui.visualization import summary_note

    dataset = compute_locants(_mol(CAMPHOR), "u", {})
    assert dataset.values == {}
    assert dataset.error is None
    assert dataset.cache_state is not CacheState.FAILED

    note = summary_note(dataset)
    assert "retained name" in note
    # Must NOT claim the skeleton is absent from the tables: purine is in
    # them with a full locant map, and it is the MATCH that fails. Sending
    # someone to the wrong place is worse than saying less.
    assert "not one of" not in note


def test_the_summary_reports_partial_coverage_honestly():
    from openchem.ui.visualization import summary_note

    note = summary_note(compute_locants(_mol(ASPIRIN), "u", {}))
    assert "6 of 13" in note


def test_a_retained_ring_says_the_numbering_came_from_the_skeleton():
    from openchem.ui.visualization import summary_note

    note = summary_note(compute_locants(_mol(NAPHTHALENE), "u", {}))
    assert "ring skeleton" in note
    assert "retained name" in note


# --- The misleading-total bug the annotation calculators introduced ------


def test_categorical_results_get_no_summed_total():
    """Summing category IDS gives "Overall: 15" for a molecule's ring
    systems -- a number that looks like a measurement and means nothing.

    This is the same trap the inspector already documents for spectra, and
    the annotation calculators walked into it: the comment there said the
    sum "IS the molecular total for every PerAtomDataset this dialog shows
    today", which stopped being true the moment they landed."""
    from openchem.ui.visualization import is_categorical

    for compute in (compute_ring_systems, compute_stereocenters,
                    compute_functional_groups, compute_locants):
        assert is_categorical(compute(_mol(ASPIRIN), "u", {}))


def test_ordinary_per_atom_results_are_still_summable():
    """The exclusion must be opt-in -- Crippen contributions and partial
    charges are additive by construction and still want their total."""
    from openchem.domain.scientific_result import PerAtomDataset
    from openchem.ui.visualization import is_categorical

    assert not is_categorical(
        PerAtomDataset(
            property_id="gasteiger_charge",
            name="Partial Charge",
            units="e",
            method="rdkit",
            molecule_uuid="m",
            values={0: -0.5, 1: 0.5},
        )
    )


def test_every_annotation_calculator_explains_an_empty_result():
    """Ethanol has no rings, no stereocentres and no groups; caffeine has no
    locants. None of those is a failure, and all four must say so rather
    than render an uncoloured molecule beside a blank line."""
    from openchem.ui.visualization import summary_note

    cases = [
        (compute_ring_systems, "CCO"),
        (compute_stereocenters, "CCO"),
        (compute_functional_groups, CAFFEINE),
        (compute_locants, CAMPHOR),
    ]
    for compute, smiles in cases:
        dataset = compute(_mol(smiles), "u", {})
        assert dataset.values == {}, compute.__name__
        assert summary_note(dataset), compute.__name__


def test_locants_can_carry_the_element_symbol():
    """Heterocycle numbering is conventionally cited as N1/N3/N7 rather than
    as bare digits. Quinoline's nitrogen is position 1, so this is also a
    check that the recovered ring numbering is the right way round."""
    plain = compute_locants(_mol("c1ccc2ncccc2c1"), "u", {})
    with_element = compute_locants(
        _mol("c1ccc2ncccc2c1"), "u", {"include_element": True}
    )
    assert "1" in plain.provenance.parameters["atom_notes"].values()
    assert "N1" in with_element.provenance.parameters["atom_notes"].values()


# --- Naming a selected fragment (deliverable 8) -------------------------

TOLUENE = "Cc1ccccc1"          # atom 0 = methyl, atoms 1-6 = ring
ISOBUTYL_CHAIN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"


def test_a_selected_ring_is_named_as_a_substituent_not_as_a_molecule():
    """The substituent form is the question being asked: someone pointing at
    part of a structure wants the name it carries IN the whole name, so
    toluene's ring is 'phenyl' rather than 'benzene'."""
    result = name_fragment(_mol(TOLUENE), set(range(1, 7)))
    assert result.name == "phenyl"
    assert result.error is None
    assert result.attachment_atom == 1


def test_the_attachment_point_changes_the_name():
    """'propyl' and 'propan-2-yl' are the same three atoms attached at
    different positions, which is why the attachment is derived rather than
    ignored."""
    result = name_fragment(_mol(ISOBUTYL_CHAIN), {0, 1, 2})
    assert result.name == "propan-2-yl"


def test_a_single_atom_selection_is_named():
    assert name_fragment(_mol(TOLUENE), {0}).name == "methyl"


def test_selecting_the_whole_molecule_gives_its_standalone_name():
    """No free valence means no substituent form -- it is just the molecule."""
    assert name_fragment(_mol(TOLUENE), set(range(7))).name == "toluene"


def test_a_selection_attached_in_two_places_is_refused_not_guessed():
    """A bridging group needs a different naming form (yldiyl and friends).
    Naming it as if it attached once would be quietly wrong."""
    result = name_fragment(_mol(TOLUENE), {1, 2})
    assert result.name == ""
    assert "two places" in result.error or "2 places" in result.error


def test_an_empty_or_invalid_selection_reports_rather_than_raises():
    assert name_fragment(_mol(TOLUENE), set()).error
    assert name_fragment(_mol(TOLUENE), {99}).error
    assert name_fragment(None, {0}).error


# --- The nomenclature debugger (deliverable 6) --------------------------


def test_the_derivation_exposes_parent_suffix_and_substituents():
    """Aspirin: benzene parent, carboxylic acid in the suffix slot, acetoxy
    as a substituent at position 2."""
    root = name_derivation(_mol(ASPIRIN))
    assert root is not None
    assert root.name == "2-(acetoxy)benzoic acid"
    roles = {child.role for child in root.children}
    assert {"parent hydride", "principal characteristic group", "substituent"} <= roles


def test_a_substituent_subtree_can_be_expanded_like_its_own_molecule():
    """THE REASON THIS IS A TREE AND NOT A LIST. Naproxen's naphthalenyl
    substituent has its own parent and its own methoxy substituent below
    it -- the nesting is where the real explanatory depth is, since
    `choices_made` on any single node is thin."""
    root = name_derivation(_mol("COc1ccc2cc(ccc2c1)C(C)C(=O)O"))
    substituents = [c for c in root.children if c.role == "substituent"]
    assert substituents
    naphthalenyl = substituents[0]
    assert "naphthalen" in naphthalenyl.name
    assert any("naphthalene" in g.name for g in naphthalenyl.children)
    assert any(c.name == "methoxy" for c in naphthalenyl.children)


def test_a_retained_name_derives_to_a_single_leaf():
    """Caffeine's whole derivation is one node. That is not a failure of the
    debugger, it is what the engine did -- and a view must not present it as
    a missing explanation."""
    root = name_derivation(_mol(CAFFEINE))
    assert root is not None
    assert root.name == "caffeine"
    assert root.children == ()
    assert "retained" in root.detail


def test_a_derivation_that_cannot_be_built_returns_none():
    assert name_derivation(None) is None
