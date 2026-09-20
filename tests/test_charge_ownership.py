"""Who owns a formally charged atom: exactly one route, or a visible hole.

Naming round 7 found that a carboxylate beside a neutral OH had NO owner: the
classifier deferred it to plan search and plan search excluded it in favour of
the classifier. `perception/charge_ownership.py` makes ownership something a test
can assert, and this file holds the two failure shapes as permanent tests rather
than one-off mutations:

* a ZERO-owner state (the hole this round started from);
* a TWO-owner state (the failure the next fix is likeliest to introduce: both
  routes claim, and whichever runs first wins).

Everything here is static except the `observed` cross-checks, which run the real
engine (not OPSIN) and compare the route it actually took with the route the static
claim predicts. The static view mirrors exactly one route (`fg_anion`), and that
cross-check is what would notice the mirror drifting.
"""

from __future__ import annotations

import pytest
from rdkit import Chem, RDLogger

from openchem.vendor.iupac_namer import diagnostics
from openchem.vendor.iupac_namer.perception import charge_ownership as own
from openchem.vendor.iupac_namer.perception import charge_perception as cp

RDLogger.DisableLog("rdApp.*")

ACETATE = "CC(=O)[O-]"
SALICYLATE = "Oc1ccccc1C(=O)[O-]"
PHENOLATE = "[O-]c1ccccc1"
THIOLATE_BESIDE_SH = "[S-]c1ccccc1S"
GLYCINE_ZWITTERION = "[NH3+]CC([O-])=O"
SULFINATE = "[O-]S(=O)c1ccccc1"


def _mol(smiles: str):
    return Chem.MolFromSmiles(smiles)


def _verdict(smiles: str, *, measure: bool = False):
    return own.charged_owners(_mol(smiles), smiles, measure=measure).verdict


# ------------------------------------------------------------ the two hooks change nothing
@pytest.mark.parametrize("smiles", [ACETATE, SALICYLATE, PHENOLATE, "C[N+](C)(C)C", "[NH4+]", "CC"])
def test_asking_for_the_raw_claims_does_not_change_the_result(smiles):
    mol = _mol(smiles)
    sink: list = []
    assert cp.classify_charges(mol, claims_out=sink) == cp.classify_charges(mol)
    # every classification returned was seen in the raw claims
    returned = cp.classify_charges(mol)
    assert all(any(c is cls or c == cls for _n, c in sink) for cls in returned)


def test_the_route_recorder_is_inert_unless_a_capture_is_open():
    diagnostics.reset()
    diagnostics.record_route("carved_anion", smiles="X")
    assert diagnostics.current().routes  # ambient recorder is written when called directly...
    diagnostics.reset()
    assert not diagnostics.current().routes  # ...and reset clears it

    from openchem.vendor.iupac_namer import name_smiles

    diagnostics.reset()
    name_smiles(THIOLATE_BESIDE_SH)  # no capture, no env var: the engine must not record
    assert not diagnostics.current().routes


def test_a_capture_sees_the_plan_search_route():
    from openchem.vendor.iupac_namer import name_smiles

    with diagnostics.capture() as rec:
        name_smiles(THIOLATE_BESIDE_SH)
    assert ("carved_anion", Chem.MolToSmiles(_mol(THIOLATE_BESIDE_SH))) in rec.routes


# ------------------------------------------------------------ what a structural anion site IS
@pytest.mark.parametrize(
    "smiles,klass",
    [
        (ACETATE, own.ACID_ANION),
        ("[O-]S(=O)(=O)c1ccccc1", own.ACID_ANION),          # sulfonate
        (SULFINATE, own.ACID_ANION),                        # sulfinate: the classifier gate does not know it
        ("OP(=O)([O-])c1ccccc1", own.ACID_ANION),           # phosphonate: nor this
        ("OP(=O)([O-])Oc1ccccc1", own.ACID_ANION),          # phosphate ester
        (PHENOLATE, own.OLATE_ANION),
        ("CC[O-]", own.OLATE_ANION),
        ("[S-]c1ccccc1", own.OLATE_ANION),
    ],
)
def test_a_site_is_classified_from_the_site_alone(smiles, klass):
    assert set(own.structural_sites(_mol(smiles)).values()) == {klass}


@pytest.mark.parametrize(
    "smiles",
    [
        "C[N+](C)(C)C",                     # a cation
        "[O-][N+](=O)c1ccccc1",             # a nitro group's O- is not an acid anion
        "[O-][n+]1ccccc1",                  # a pyridine N-oxide: O- is on N, not on an acid centre
        "CC",
    ],
)
def test_other_charged_atoms_are_not_anion_sites(smiles):
    assert own.structural_sites(_mol(smiles)) == {}


# ------------------------------------------------------------ verdicts on real structures
def test_a_pure_carboxylate_is_owned_by_the_classifier():
    assert _verdict(ACETATE) is own.Verdict.OWNED
    (site,) = own.structural_sites(_mol(ACETATE))
    assert any("acidic_anion_carboxylate" in c for c in own.claimants(_mol(ACETATE))[site])


def test_a_carboxylate_beside_a_neutral_hydroxy_is_owned_by_the_classifier():
    """The defect round 7 started from. It had NO owner (verdict HOLE); the shared decision
    function now hands a junior group's anion to the classifier."""
    assert _verdict(SALICYLATE) is own.Verdict.OWNED
    (site,) = own.structural_sites(_mol(SALICYLATE))
    assert any("acidic_anion_carboxylate" in c for c in own.claimants(_mol(SALICYLATE))[site])
    assert own._CARVED not in own.claimants(_mol(SALICYLATE))[site]


def test_the_mono_anion_of_a_diacid_is_owned_by_the_carved_route_and_not_the_classifier():
    """Another NEUTRAL acid is present, so the neutral parent would make the wrong group
    principal: the plan search must force the deprotonated site."""
    smiles = "OC(=O)CCC(=O)[O-]"
    (site,) = own.structural_sites(_mol(smiles))
    claims = own.claimants(_mol(smiles))[site]
    assert own._CARVED in claims
    assert not any(c.startswith("classifier:") for c in claims)
    assert _verdict(smiles) is own.Verdict.OWNED


@pytest.mark.parametrize(
    "smiles,route",
    [
        (ACETATE, "classifier"),                       # pure
        (SALICYLATE, "classifier"),                    # a junior group: OH
        ("Nc1ccc(cc1)C(=O)[O-]", "classifier"),        # NH2
        ("CCOC(=O)CCC(=O)[O-]", "classifier"),         # an ester is junior to the acid
        ("[O-]C(=O)CCC([O-])=O", "classifier"),        # a dianion, both sites the same class
        ("OC(=O)CCC(=O)[O-]", "carved"),               # another NEUTRAL acid
        ("OC(=O)c1ccc(cc1)S(=O)(=O)[O-]", "carved"),   # another neutral acid of a different class
        ("[O-]C(=O)c1ccc(cc1)[N+](=O)[O-]", "carved"), # a charge-separated neutral group (nitro)
        (GLYCINE_ZWITTERION, None),                    # net charge 0: a zwitterion, the FG route owns it
        ("[NH3+]C(CCC([O-])=O)C([O-])=O", "carved"),   # net NEGATIVE with a cation: glutamate at pH 7
        ("[NH3+]C(CC(=O)[O-])C([O-])=O", "carved"),    # aspartate at pH 7
        ("C[N+](C)(C)CCC(=O)[O-]", None),              # a quaternary cation with ONE carboxylate: net 0
        ("[O-]c1ccccc1C([O-])=O", None),               # two acid CLASSES of anion: not decided here
        (PHENOLATE, None),                             # an olate keeps its own cascade
        ("C[N+](C)(C)C", None),
        ("CC", None),
    ],
)
def test_the_decision_function_names_the_route(smiles, route):
    assert cp.acid_anion_route(_mol(smiles)) == route


def test_the_two_routes_never_both_claim_an_acid_anion():
    """The point of ONE function: for every acid-anion molecule, exactly one of the classifier
    and the carved route claims the site, whatever the molecule. A sweep over the shapes above
    plus the panel's isolated ions."""
    import tomllib
    from pathlib import Path

    panel = tomllib.loads((Path(__file__).resolve().parents[1] / "benchmarks/naming/charged_panel.toml")
                          .read_text(encoding="utf-8"))["row"]
    seen = 0
    for row in panel:
        mol = _mol(row["smiles"])
        if cp.acid_anion_route(mol) is None:
            continue
        seen += 1
        claims = own.claimants(mol)
        for site, klass in own.structural_sites(mol).items():
            if klass != own.ACID_ANION:
                continue
            by_classifier = any(c.startswith("classifier:") for c in claims[site])
            by_carved = own._CARVED in claims[site]
            assert by_classifier != by_carved, (row["id"], claims[site])
    assert seen >= 40, seen


def test_an_olate_is_a_declared_cascade_not_an_overlap():
    """A pure phenolate is claimed by the classifier AND the carved route; the
    classifier answers first, and the pair is declared, so it is OWNED."""
    claims = own.claimants(_mol(PHENOLATE))
    (site_claims,) = [v for v in claims.values()]
    assert own._CARVED in site_claims
    assert any(c.startswith("classifier:") for c in site_claims)
    assert _verdict(PHENOLATE) is own.Verdict.OWNED


def test_the_carved_route_owns_a_thiolate_the_classifier_defers():
    assert _verdict(THIOLATE_BESIDE_SH) is own.Verdict.OWNED
    assert not any(c.startswith("classifier:") for v in own.claimants(_mol(THIOLATE_BESIDE_SH)).values() for c in v)


def test_the_fg_route_owns_a_zwitterions_carboxylate_and_a_sulfinate():
    for smiles in (GLYCINE_ZWITTERION, SULFINATE):
        claims = own.claimants(_mol(smiles))
        anion_atoms = own.structural_sites(_mol(smiles))
        assert anion_atoms
        assert all(own._FG_ANION in claims[i] for i in anion_atoms), smiles
        assert _verdict(smiles) is own.Verdict.OWNED


# ------------------------------------------------------------ the two failure shapes, as mutations
def test_a_zero_owner_state_is_reported_as_a_hole(monkeypatch):
    """Delete the classifier's claim on an ordinary acetate: nothing else claims it."""
    monkeypatch.setattr(cp, "_classify_acidic_anion", lambda mol: iter(()))
    assert _verdict(ACETATE) is own.Verdict.HOLE


def test_a_two_owner_state_is_reported_as_an_overlap_not_silently_resolved(monkeypatch):
    """Re-enable the carved route on a carboxylate, which it excludes on purpose:
    both routes now claim one site and ordering, not design, would pick the winner."""
    from openchem.vendor.iupac_namer import engine

    real = engine._carved_acid_anion_sites

    def also_the_carboxylate(mol):
        return real(mol) | {a.GetIdx() for a in mol.GetAtoms() if a.GetFormalCharge() == -1}

    monkeypatch.setattr(engine, "_carved_acid_anion_sites", also_the_carboxylate)
    assert _verdict(ACETATE) is own.Verdict.OVERLAP


def test_an_fg_claim_on_a_site_the_classifier_owns_is_an_overlap(monkeypatch):
    monkeypatch.setattr(own, "_fg_anion_sites", lambda mol: frozenset(
        a.GetIdx() for a in mol.GetAtoms() if a.GetFormalCharge() == -1))
    assert _verdict(ACETATE) is own.Verdict.OVERLAP


def test_a_third_claimant_on_an_olate_breaks_the_declared_cascade(monkeypatch):
    """Classifier + carved is the declared pair; add the FG route and it is not."""
    monkeypatch.setattr(own, "_fg_anion_sites", lambda mol: frozenset(
        a.GetIdx() for a in mol.GetAtoms() if a.GetFormalCharge() == -1))
    assert _verdict(PHENOLATE) is own.Verdict.OVERLAP


def test_a_claim_the_engine_did_not_honour_is_inconsistent():
    """One claimant, but the observed route is not that route."""
    claims = ("classifier:_classify_acidic_anion:acidic_anion_carboxylate",)
    nothing_rendered = own.Observed(name="x", classifier_rendered=(), handed_back=("unclaimed",),
                                    plan_search_routes=())
    assert own._verdict(own.ACID_ANION, claims, nothing_rendered) is own.Verdict.INCONSISTENT
    rendered = own.Observed(name="x", classifier_rendered=("acidic_anion_carboxylate",),
                            handed_back=(), plan_search_routes=())
    assert own._verdict(own.ACID_ANION, claims, rendered) is own.Verdict.OWNED


# ------------------------------------------------------------ static claim versus real route
@pytest.mark.parametrize(
    "smiles,expected_route",
    [
        (ACETATE, "classifier:acidic_anion_carboxylate"),
        (PHENOLATE, "classifier:acidic_anion_olate"),
        (THIOLATE_BESIDE_SH, "plan_search:carved_anion"),
        (GLYCINE_ZWITTERION, "plan_search:fg_anion"),
        (SULFINATE, "plan_search:fg_anion"),
        (SALICYLATE, "classifier:acidic_anion_carboxylate"),       # R3: it had no owner before
        ("OC(=O)CCC(=O)[O-]", "plan_search:carved_anion"),          # R3: another neutral acid
        ("NC(=O)[O-]", "curated_inorganic"),                        # a retained whole-molecule name
        ("OP(=O)([O-])c1ccccc1", "plan_search:unpromoted(unclaimed)"),  # still a HOLE (R4)
    ],
)
def test_the_route_the_engine_takes_is_the_route_the_claim_predicts(smiles, expected_route):
    """The static claimants and the engine's own recorded route must agree. The only
    mirrored predicate is `fg_anion`, so this is what would show it drifting."""
    report = own.charged_owners(_mol(smiles), smiles, measure=True)
    assert report.observed.route == expected_route
    assert report.verdict is (own.Verdict.HOLE if "unpromoted" in expected_route else own.Verdict.OWNED)


def test_a_curated_name_answers_before_any_classifier_and_is_not_an_overlap():
    """'carbamate' is a retained whole-molecule name. The classifier ALSO claims the site, and
    the curated table is asked first on purpose, so this is a declared cascade: OWNED by the
    curated route, with the observed route agreeing."""
    smiles = "NC(=O)[O-]"
    (site,) = own.structural_sites(_mol(smiles))
    claims = own.claimants(_mol(smiles))[site]
    assert claims[0] == own._CURATED
    assert any(c.startswith("classifier:") for c in claims)
    report = own.charged_owners(_mol(smiles), smiles, measure=True)
    assert report.verdict is own.Verdict.OWNED
    assert report.observed.route == own._CURATED


@pytest.mark.parametrize(
    "smiles,name",
    [
        ("[Na+].[O-]c1ccccc1", "sodium phenolate"),
        ("[K+].CC(C)(C)[O-]", "potassium 2-methylpropan-2-olate"),
        ("[Na+].CC(=O)[O-]", "sodium acetate"),
    ],
)
def test_a_pure_anion_in_a_salt_stays_on_the_classifier_route(smiles, name):
    """The salt path asks for the ANION form only for a fragment the CARVED route owns. A pure
    olate is claimed by the classifier first, and taking it off that path changed
    'sodium phenolate' to 'sodium benzenolate' during R3. (Both are non-preferred: the book's PIN
    is 'phenoxide', a retained-name question for R4. This pins that R3 does not move it.)"""
    from openchem.vendor.iupac_namer import name_smiles

    assert name_smiles(smiles) == name


def test_the_net_negative_zwitterion_had_no_owner_and_the_carved_route_takes_it():
    """Glutamate as drawn at pH 7 (two carboxylates, one ammonium, net charge -1). FG perception
    detects a charged carboxylic acid only when the charges cancel, and the classifier declines any
    genuine cation, so nothing claimed it and the charge fell to 'oxido' prefixes on an azanium parent."""
    smiles = "[NH3+]C(CCC([O-])=O)C([O-])=O"
    report = own.charged_owners(_mol(smiles), smiles, measure=True)
    assert report.verdict is own.Verdict.OWNED
    assert report.observed.route == "plan_search:carved_anion"


def test_the_ledger_offers_only_the_charged_instance_of_a_mixed_type():
    """The number of anion suffixes must equal the number of deprotonated sites. A zwitterion with ONE
    carboxylate and ONE neutral COOH offered both as the principal group and came out as the dianion."""
    from openchem.vendor.iupac_namer import name_smiles

    assert name_smiles("[NH3+]C(CCC(O)=O)C([O-])=O") == "2-azaniumyl-4-carboxybutanoate"
    # both charged: nothing to restrict
    assert name_smiles("[NH3+]C(CCC([O-])=O)C([O-])=O") == "2-azaniumylpentanedioate"
