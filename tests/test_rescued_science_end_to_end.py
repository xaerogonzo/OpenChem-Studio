"""Source -> registry -> presentation, for the four rescued modules.

`tests/test_calculator_reachability.py` proves reachability STRUCTURALLY
and the per-module test files prove correctness. Neither answers the
question in between: **does the registered thing actually invoke the
corrected implementation?**

That matters most exactly where several implementations now exist. The
polarizability calculator has three methods and two of them are Miller's;
TSEI has a corrected traversal and the eq-7 form it replaced reproduces
Table 1 just as well. A wiring that reached the wrong one would leave
every unit test green.

So each case below asserts a value that **could only have come from the
new code path**, through the registered calculator and out to the object
the panel renders. Not a GUI test: the boundary is the registry and the
`ReportResult`/`PerAtomDataset` a panel is handed.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
from openchem.domain.common import CacheState

#: Brij-style C12E4: dodecanol with four ethylene oxide units.
_C12E4 = "CCCCCCCCCCCCOCCOCCOCCOCCO"


def _run(calculator_id: str, smiles: str, parameters: dict | None = None):
    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == calculator_id
    )
    return definition.execution.compute(
        Chem.MolFromSmiles(smiles), "uuid", parameters or {}
    )


def _polarizability(smiles: str, method: str) -> float:
    result = _run("polarizability", smiles, {"method": method})
    assert result.cache_state is not CacheState.FAILED, result.error
    return float(result.matched[0].split(":")[1].split()[0])


def test_the_registry_reaches_millers_ahc_and_not_jensens_number():
    """A SATURATED HYDROCARBON, because that is where the two schemes
    genuinely separate -- and the calculator's own description says so.

    Measured across six molecules: CCl4 puts Jensen and Miller ahc 1.5%
    apart and benzene 1.6%, which two decimals nearly swallow. n-hexane
    puts them 11.9% apart, which is the "roughly 11% high for saturated
    hydrocarbons" the description states, because an atom-additive scheme
    has no hybridization dependence and Miller's does. So this fixture
    checks the wiring AND the sentence a user reads.
    """
    miller = _run("polarizability", "CCCCCC", {"method": "Miller ahc"})
    assert miller.provenance.method == "miller_ahc"

    value = float(miller.matched[0].split(":")[1].split()[0])
    jensen = _polarizability("CCCCCC", "Jensen (additive)")

    assert jensen > value, "Jensen should be the HIGH one on a saturated chain"
    excess = (jensen - value) / value
    assert 0.08 < excess < 0.16, (
        f"Jensen is {excess:.1%} above Miller on n-hexane; the description "
        "claims roughly 11%, so one of the two has moved"
    )

    # CCl4 is the fixture this test does NOT use, recorded so nobody
    # substitutes it back: at 1.5% apart it cannot discriminate.
    assert abs(
        _polarizability("ClC(Cl)(Cl)Cl", "Miller ahc")
        - _polarizability("ClC(Cl)(Cl)Cl", "Jensen (additive)")
    ) < 0.3


def test_the_registry_reaches_the_corrected_tsei_and_not_eq_7():
    """A FIRST-TIER CHLORINE, which is the one place the two forms differ
    by construction.

    Eq 7 gives exactly 1.000 for any first-tier atom whatever it is; the
    paper's own worked example gives 1.4190 for chlorine. So chloromethane
    with the chlorine as one substituent of the carbon separates them
    outright.
    """
    result = _run("tsei_projection", "CCl")
    assert result.cache_state is not CacheState.FAILED, result.error

    # atom 0 is the carbon; its only substituent is the chlorine.
    assert result.values[0] == pytest.approx(1.4190, abs=5e-4)
    assert result.values[0] > 1.4, (
        "the registered calculator is running eq 7, which cannot tell a "
        "chlorine from a carbon"
    )
    # ... AND THE RELATIONSHIP IS ASYMMETRIC, which is what says the
    # radius term is really in the length as well as in the numerator.
    # From the chlorine, the carbon sits across the same C-Cl bond -- a
    # LONGER bond than a C-C one -- so it screens less than a carbon
    # neighbour would: 1 / (1.762/1.544)^3 = 0.673. Eq 7 gives 1.000 from
    # both ends, and a numerator-only fix gives 1.000 from this one.
    assert result.values[1] == pytest.approx(0.6729, abs=5e-4)


def test_the_registry_refuses_tsei_on_an_element_the_book_does_not_tabulate():
    """The refusal has to survive the trip out, or a user gets an empty
    per-atom view with nothing saying why.

    ETHYLAMINE WAS THIS FIXTURE UNTIL THE HANDBOOK ARRIVED, which is worth
    saying: nitrogen had no printed TSEI to invert a radius from, so the
    projection declined every amine. Lange's Table 4.7 simply has it, and
    the case that still refuses is an element the book itself stops short
    of.
    """
    amine = _run("tsei_projection", "CCN")
    assert amine.cache_state is not CacheState.FAILED, amine.error

    result = _run("tsei_projection", "CCC[Fe]")
    assert result.cache_state is CacheState.FAILED
    assert "Fe" in (result.error or "")
    assert "Table 4.7" in (result.error or ""), (
        "the refusal does not say what is missing, so nobody can act on it"
    )
    assert result.values == {}


def test_the_registry_reaches_griffin_hlb_and_its_refusal():
    """Both halves through the registry: a value for a real surfactant and
    the NAMED refusal for a molecule outside Griffin's definition."""
    surfactant = _run("griffin_hlb", _C12E4)
    assert surfactant.cache_state is not CacheState.FAILED, surfactant.error
    # Schott Eq. [2]: 881 x 4 / (44.05 x 4 + 186.3) = 9.72
    assert float(surfactant.facts[0].display_value) == pytest.approx(9.72, abs=0.01)

    aspirin = _run("griffin_hlb", "CC(=O)Oc1ccccc1C(=O)O")
    assert aspirin.cache_state is CacheState.FAILED
    assert "polyoxyethylene" in (aspirin.error or "")
    assert not aspirin.facts, "a refused result must carry no value to misread"


def test_the_hlb_refusal_text_is_generated_from_the_enum():
    """`IsotopeRefusal`'s rule, applied: a value rather than a sentence,
    so `if "polyoxyethylene" in message` never becomes application logic
    and no panel invents a second wording."""
    from openchem.chem.hlb import HlbRefusal, griffin_hlb, refusal_text

    result = griffin_hlb(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    assert result.refusal is HlbRefusal.NO_POLYOXYETHYLENE
    assert refusal_text(result) == (_run("griffin_hlb", "CC(=O)Oc1ccccc1C(=O)O").error)


def test_the_registry_reaches_gutmann_through_the_solubility_report():
    """Not its own calculator: DN and AN are facts ABOUT the chosen
    solvent, reported beside the Abraham shift they do not feed."""
    result = _run("solubility", "c1ccccc1", {"solvent": "acetonitrile"})
    assert result.cache_state is not CacheState.FAILED, result.error
    labels = {f.label: f.display_value for f in result.facts if "Gutmann" in f.label}
    assert labels["Gutmann donor number (DN)"] == "14.1"
    assert labels["Gutmann acceptor number (AN)"] == "18.9"


def test_the_registry_reaches_gutmann_through_the_lewis_report():
    """The other door, and the one `domain/lewis.py` was written for:
    "The shape also has room for what is coming -- donor and acceptor
    numbers"."""
    result = _run("lewis_sites", "CS(C)=O")
    labels = {f.label: f.display_value for f in result.facts if "Gutmann" in f.label}
    assert labels["Gutmann donor number (DN)"] == "29.8 kcal/mol"
    assert labels["Gutmann acceptor number (AN)"] == "19.3"


def test_a_molecule_that_is_not_a_table_solvent_gets_no_donicity():
    """Silence rather than a nearest match. Gutmann measured 68 liquids,
    and "no donor number is published for this structure" is the honest
    answer for everything else."""
    result = _run("lewis_sites", "CC(=O)Oc1ccccc1C(=O)O")
    assert not [f for f in result.facts if "Gutmann" in f.label]
