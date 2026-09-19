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
CAMPHOR = "CC1(C)C2CCC1(C)C(=O)C2"           # systematic since D-036; HAS locants
# CAMPHOR AND CAFFEINE ARE NO LONGER RETAINED-NAME EXAMPLES. D-036 audited
# the retained-name registry and demoted both -- `camphor` is not in the Blue
# Book's retained lists and `caffeine` appears nowhere in it -- so they name
# systematically and carry derived numbering. Tests that need "a retained
# name, therefore no numbering" use TOLUENE_RETAINED (a retained PIN by
# P-22.1.3, no rings) or BENZENE_RETAINED (a retained PIN WITH a ring and no
# atom_locants map, which is the "skeleton could not be matched" branch).
TOLUENE_RETAINED = "Cc1ccccc1"               # retained PIN, no rings numbered
BENZENE_RETAINED = "c1ccccc1"                # retained PIN, ring, no locant map
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"            # substitutive, two FGs
D_ALANINE = "C[C@@H](N)C(=O)O"               # (R)-alanine: one centre, two FGs
NAPHTHALENE = "c1ccc2ccccc2c1"               # bare ring in the retained table
NAPROXEN_SMILES = "COc1ccc2cc([C@@H](C)C(=O)O)ccc2c1"   # naphthalene in a prefix
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


def test_caffeine_ring_carbonyls_are_claimed_as_ring_ketones():
    """Caffeine used to annotate as having no groups at all: both carbonyls
    are ring-embedded and nothing claimed them. This test was written to be
    noticed when that changed, and it did: naming round 4 (A5) encoded the
    P-31.1.4.2.4 conditions under which a ring C=O on a mancude ring is the
    "-one" suffix, so the engine now claims both as ring ketones, the way it
    names them ("...purine-2,6-dione"). Whether a lactam should ALSO be shown
    as a lactam is a feature question for the app vocabulary (round 4 branch
    B), not a naming one."""
    result = annotate(_mol(CAFFEINE))
    claimed = {(g.type, g.anchor) for g in result.groups}
    assert claimed == {("ketone", 6), ("ketone", 10)}


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


def test_a_retained_skeleton_with_no_locant_map_has_no_numbering():
    """The limit that remains, now shown on benzene.

    Camphor used to be this example and is not one any more: D-036 demoted the
    retained name, so it numbers systematically. Benzene is the better case
    anyway -- it is a retained PIN whose ring carries no `atom_locants` map
    because every position is equivalent, so a skeleton numbering would be
    ARBITRARY rather than merely missing.
    """
    result = annotate(_mol(BENZENE_RETAINED))
    assert result.locants == ()
    assert result.locant_coverage() == 0.0


def test_locant_coverage_lets_a_caller_decline_to_show_a_numbering_view():
    """Half of all molecules produce no numbering. A UI needs to ask before
    offering the view, rather than rendering a blank one."""
    assert annotate(_mol(BENZENE_RETAINED)).locant_coverage() == 0.0
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
    # The note now carries the LOCANT as well, because camphor numbers
    # systematically since D-036 -- "1 bridgehead" rather than "bridgehead".
    # The subject is which atoms are identified, so the assertion is on that.
    bridgeheads = [note for note in notes.values() if "bridgehead" in note]
    assert len(bridgeheads) == 2, notes


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
    # Three kinds now: the ester, the carboxylic acid, and the benzene RING
    # SYSTEM. The ring was always perceived (`annotation.rings`) and this
    # result simply did not read it, which is half of why a fentanyl showed
    # one group -- see tests/test_functional_group_features.py.
    assert len(set(layer.atom_colors.values())) == 3


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
    assert everything.provenance.parameters["groups_detected"] == 3  # + the ring
    assert narrowed.provenance.parameters["groups_detected"] == 1
    assert list(narrowed.provenance.parameters["category_labels"].values()) == [
        "carboxylic acid"
    ]


def test_the_prefix_label_mode_uses_the_naming_prefix():
    dataset = compute_functional_groups(
        _mol(ASPIRIN), "u", {"label_mode": "Prefix form"}
    )
    assert "carboxy" in dataset.provenance.parameters["atom_notes"].values()


def test_a_lactam_carbonyl_is_claimed_as_a_lactam():
    """HALF DELIBERATE, and worth pinning precisely rather than as a vague
    'blind spot'.

    The detector carries an explicit endocyclic-amide guard: an amide whose
    carbonyl carbon and nitrogen share a ring is refused, because IUPAC
    names that carbonyl as a ketone rather than an amide. That refusal is
    correct. What is missing is the other half -- the ketone pattern will
    not claim an N-adjacent carbonyl either, so the atom falls through both.

    The contrast is the point: a plain cyclic ketone IS claimed, and an
    acyclic amide IS claimed. Only the combination falls through."""
    def functional_groups(smiles):
        """The FUNCTIONAL-GROUP features only.

        The result now also carries ring systems and structural features, so
        `values` alone no longer answers this question: caffeine's purine is
        a ring system and would make a lactam look claimed.
        """
        dataset = compute_functional_groups(_mol(smiles), "u", {})
        return [
            f for f in dataset.provenance.parameters["features"]
            if f["category"] == "functional_group"
        ]

    assert functional_groups(CYCLOHEXANONE)
    assert functional_groups("CC(=O)NC")

    # CLOSED by vocabulary v2 (FG-002): the Functional Groups view no longer
    # reads the naming engine's groups as its definition, so the carbonyl the
    # engine's two patterns both refuse is a LACTAM (Gold Book p. 815), with
    # its amide nested beside it.
    keys = sorted(f["key"] for f in functional_groups(PYRROLIDINONE))
    assert keys == ["fg:carboxamide", "fg:lactam"]
    views = {f["key"]: f["functional_groups_view"] for f in functional_groups(PYRROLIDINONE)}
    assert views == {"fg:lactam": "shown", "fg:carboxamide": "shown_nested"}


def test_a_molecule_with_no_groups_reports_that_it_found_none():
    """So a view can say 'none found' rather than leave a molecule silently
    bare and let a chemist read caffeine as unfunctionalised."""
    # Ethane, which has nothing of any kind. Caffeine no longer qualifies:
    # its purine IS reported, as a ring system, which is the point of the
    # wider vocabulary -- but it still has no functional group, and
    # `test_a_lactam_carbonyl_is_claimed_by_no_group_at_all` pins that.
    dataset = compute_functional_groups(_mol("CC"), "u", {})
    assert dataset.provenance.parameters["groups_detected"] == 0
    assert "Nothing matched" in dataset.provenance.parameters["summary"]
    assert dataset.error is None
    assert dataset.cache_state is not CacheState.FAILED


def test_penicillin_reports_its_beta_lactam_amide_and_acid():
    """Its beta-lactam used to fall through as above; under vocabulary v2 it
    is a lactam, beside the side-chain amide and the carboxylic acid."""
    dataset = compute_functional_groups(_mol(PENICILLIN_G), "u", {})
    features = dataset.provenance.parameters["features"]
    groups = {f["label"] for f in features if f["category"] == "functional_group"}
    # Its thiazolidine SULFUR is a ring thioether, which is a real feature of
    # the molecule and was found while updating this test rather than
    # predicted -- the same widening that gives THF an ether.
    # "amide" is both the side chain's and the one nested in the lactam; the
    # label is no longer "secondary amide" (Gold Book p. 69, note 1: FG-001).
    assert groups == {"amide", "lactam", "carboxylic acid", "sulfide (thioether)"}
    # And its rings are reported as ring systems rather than as groups.
    assert [f["category"] for f in features if f["key"] == "benzene"] == ["ring_system"]


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
    assert len(expected) == 3  # ester, acid, benzene ring system
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

    dataset = compute_locants(_mol(BENZENE_RETAINED), "u", {})
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
        # Ethane rather than caffeine: caffeine's purine ring system is
        # reported now, so it is no longer an empty result.
        (compute_functional_groups, "CC"),
        # Benzene rather than camphor: camphor's retained name was demoted in
        # D-036, so it now produces locants and is no longer an empty result.
        (compute_locants, BENZENE_RETAINED),
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
    """Aspirin: benzene parent, carboxylic acid in the suffix slot, acetyloxy
    as a substituent at position 2 ("4-(acetyloxy)benzoic acid (PIN)", Blue
    Book p. 628; round 4 stopped contracting acyloxy to "acetoxy")."""
    root = name_derivation(_mol(ASPIRIN))
    assert root is not None
    assert root.name == "2-(acetyloxy)benzoic acid"
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
    """A retained name's whole derivation is one node. That is not a failure
    of the debugger, it is what the engine did -- and a view must not present
    it as a missing explanation.

    Caffeine was the example until D-036 established that the book never
    retains it. Toluene is a retained PIN in as many words (P-22.1.3), so it
    will not move under a later audit.
    """
    root = name_derivation(_mol(TOLUENE_RETAINED))
    assert root is not None
    assert root.name == "toluene"
    assert root.children == ()
    assert "retained" in root.detail


def test_a_derivation_that_cannot_be_built_returns_none():
    assert name_derivation(None) is None


# --- Substituent numbering carried onto the structure (round 4, A12) ------


def _locants_by_atom(smiles):
    return {loc.atom_index: loc for loc in annotate(_mol(smiles)).locants}


def test_a_substituent_ring_is_numbered_as_its_prefix_name_says():
    """Naproxen, "(2S)-2-(6-methoxynaphthalen-2-yl)propanoic acid". Its
    naphthalene used to be numbered only by the ring table, which cannot know
    where the substituents are and chose the mirror image: the methoxy carbon
    came out 2 and the attachment carbon 6, the reverse of the name. The
    prefix subtree's own numbering now wins, carried through the carve map."""
    loc = _locants_by_atom(NAPROXEN_SMILES)
    methoxy_carbon, attachment = 2, 7
    assert (loc[methoxy_carbon].label, loc[attachment].label) == ("6", "2")
    assert loc[attachment].source is LocantSource.SUBSTITUENT
    assert loc[attachment].prefix == "6-methoxynaphthalen-2-yl"
    # The parent chain keeps its own numbering, which always wins.
    assert loc[8].label == "2" and loc[8].source is LocantSource.PARENT


def test_identical_substituents_share_a_subtree_but_not_their_atoms():
    """Both 4-chlorophenyl groups name to ONE cached subtree; each prefix
    entry carries its own carve map, so each ring is numbered on its own
    atoms (attachments 1, chlorinated carbons 4)."""
    loc = _locants_by_atom("O=C(c1ccc(Cl)cc1)c1ccc(Cl)cc1")
    assert {i: loc[i].label for i in (2, 5, 9, 12)} == {2: "1", 5: "4", 9: "1", 12: "4"}


def test_a_nested_substituent_is_carried_through_every_level():
    """DDT: the second chlorophenyl sits inside the trichloroethyl prefix, so
    its map is composed through two carves."""
    loc = _locants_by_atom("Clc1ccc(cc1)C(c1ccc(Cl)cc1)C(Cl)(Cl)Cl")
    assert (loc[4].label, loc[1].label) == ("1", "4")
    assert loc[4].prefix == "4-chlorophenyl"


def test_a_ring_table_skeleton_includes_its_fusion_carbons():
    """Indole's table entry ships without 3a/7a. The ring-table path reads the
    engine's built table, which fills them, instead of the raw data."""
    loc = _locants_by_atom("c1ccc2[nH]ccc2c1")
    assert (loc[7].label, loc[3].label) == ("3a", "7a")


def test_the_carve_map_is_checked_and_survives_renumbering():
    from openchem.vendor.iupac_namer.perception.extraction import (
        carve_substituent,
        fragment_origin,
    )

    mol = _mol(NAPROXEN_SMILES)
    ring = frozenset({2, 3, 4, 5, 6, 7, 13, 14, 15, 16, 1, 0})
    fragment, attachment, _order = carve_substituent(mol, ring, (8, 7))
    origin = dict(fragment_origin(fragment))
    assert origin[attachment] == 7
    assert sorted(origin.values()) == sorted(ring)
    for local, parent in origin.items():
        assert (fragment.GetAtomWithIdx(local).GetAtomicNum()
                == mol.GetAtomWithIdx(parent).GetAtomicNum())
