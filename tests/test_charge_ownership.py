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


def test_a_carboxylate_beside_a_neutral_hydroxy_had_no_owner():
    """The defect round 7 started from, named as a verdict. When R3 lands this test
    is REWRITTEN to OWNED, in the same commit as the fix; until then it pins the hole."""
    assert _verdict(SALICYLATE) is own.Verdict.HOLE


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
        (SALICYLATE, "plan_search:unpromoted(unclaimed)"),
    ],
)
def test_the_route_the_engine_takes_is_the_route_the_claim_predicts(smiles, expected_route):
    """The static claimants and the engine's own recorded route must agree. The only
    mirrored predicate is `fg_anion`, so this is what would show it drifting."""
    report = own.charged_owners(_mol(smiles), smiles, measure=True)
    assert report.observed.route == expected_route
    assert report.verdict is (own.Verdict.HOLE if "unpromoted" in expected_route else own.Verdict.OWNED)
