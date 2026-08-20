"""The Griffin HLB calculator: the value, and the refusal as a result.

`tests/test_hlb.py` checks the chemistry against Schott's closed form.
This file is about what a user is handed -- in particular that a molecule
outside Griffin's definition gets a NAMED refusal rather than a number.

**APPLICABILITY IS A RESULT, NOT A FOOTNOTE.** Griffin's definition opens
"for nonionic surfactants with polyoxyethylene as the sole hydrophilic
moiety", which is a structural condition answered per molecule. Returning
4.14 for aspirin and relying on documentation to say it is meaningless is
the failure the `AlertResult` migration spent a phase removing.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.hlb import HlbRefusal, compute_griffin_hlb, griffin_hlb, refusal_text
from openchem.domain.common import CacheState

#: C12E4 -- dodecanol with four ethylene oxide units, the Brij family's
#: shape and the one Schott's Eq. [2] is stated for.
_C12E4 = "CCCCCCCCCCCCOCCOCCOCCOCCO"


def _result(smiles: str, parameters: dict | None = None):
    return compute_griffin_hlb(Chem.MolFromSmiles(smiles), "uuid", parameters or {})


def test_a_real_surfactant_gets_schotts_own_number():
    """Eq. [2]: 881 p / (44.05 p + A), with p = 4 and A = 186.3 for the
    dodecanol lipophile. 9.72."""
    result = _result(_C12E4)
    assert result.cache_state is not CacheState.FAILED, result.error
    assert float(result.facts[0].display_value) == pytest.approx(9.72, abs=0.01)
    assert result.provenance.parameters["ethylene_oxide_units"] == 4


def test_the_unit_count_is_reported_beside_the_number():
    """A reader checking the arithmetic needs p, and it is the one input
    a substructure count can get wrong -- this project's own first version
    matched the chain from both ends and made C12E4 nine units."""
    result = _result(_C12E4)
    units = next(f for f in result.facts if f.label == "Ethylene oxide units")
    assert units.display_value == "4"


@pytest.mark.parametrize(
    "label,smiles,refusal",
    [
        ("aspirin", "CC(=O)Oc1ccccc1C(=O)O", HlbRefusal.NO_POLYOXYETHYLENE),
        ("dodecanol", "CCCCCCCCCCCCO", HlbRefusal.NO_POLYOXYETHYLENE),
        ("SDS", "CCCCCCCCCCCCOS(=O)(=O)[O-].[Na+]", HlbRefusal.NO_POLYOXYETHYLENE),
    ],
)
def test_a_molecule_outside_griffins_definition_is_refused(label, smiles, refusal):
    """DODECANOL IS THE CASE MOST WORTH HAVING. It is the lipophile Brij
    is built FROM, it has no polyoxyethylene at all, and this project's
    first SMARTS accepted it and gave it a number."""
    result = _result(smiles)
    assert result.cache_state is CacheState.FAILED, label
    assert not result.facts, f"{label} was refused and still carries a value"
    assert result.provenance.parameters["refusal"] == refusal.name


def test_the_refusal_text_is_generated_from_the_enum_in_one_place():
    """`IsotopeRefusal`'s rule: a VALUE rather than a sentence, so
    `if "polyoxyethylene" in message` never becomes application logic and
    no consumer invents a second wording for one refusal."""
    mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
    assert _result("CC(=O)Oc1ccccc1C(=O)O").error == refusal_text(griffin_hlb(mol))


def test_every_refusal_reason_has_text_and_none_is_a_placeholder():
    """A refusal with no explanation is worse than a blank result: it
    reads as a failure of the app rather than a statement about the
    molecule."""
    from openchem.chem.hlb import _REFUSAL_TEXT

    assert set(_REFUSAL_TEXT) == set(HlbRefusal)
    for reason, text in _REFUSAL_TEXT.items():
        assert len(text) > 30, f"{reason.name}'s text says nothing: {text!r}"


def test_the_sorbitan_refusal_names_what_it_found():
    """SPAN AND TWEEN ARE THE CASE MOST LIKELY TO BE GOT WRONG. Griffin's
    EXPERIMENTS produced their published values, but his FORMULA does not
    apply to them -- sorbitan is a polyhydric alcohol, so polyoxyethylene
    is not the sole hydrophile. A refusal that did not say so would read
    as a bug, given those numbers are in every formulation textbook."""
    tween_like = "OCC(O)C1OCC(OCCOCCO)C1OCCO"
    result = _result(tween_like)
    assert result.cache_state is CacheState.FAILED
    assert result.provenance.parameters["refusal"] == HlbRefusal.NOT_SOLE_HYDROPHILE.name
    assert "sorbitan" in (result.error or "").lower()


def test_the_result_says_which_scale_it_is_on():
    """"HLB" names Griffin's scale and Davies', they disagree substantially
    across the whole range of practical applications, and a bare number is
    ambiguous between them."""
    result = _result(_C12E4)
    text = " ".join(result.facts[0].limitations) + " ".join(result.limitations)
    assert "Davies" in text and "Griffin" in text


def test_no_total_is_declared_because_hlb_is_not_a_sum_over_atoms():
    """A weight ratio has no per-atom decomposition, so `TOTAL` is
    declined rather than left absent -- the difference between "this is
    not a sum" and "nobody thought about it"."""
    from openchem.domain.common import TOTAL

    declaration = _result(_C12E4).provenance.parameters[TOTAL]
    assert declaration["declared"] is False
    assert "atoms" in declaration["reason"]
