"""The preferred IUPAC name first, and a retained name beside it when one exists.

Naming round 3's product decision was "PIN by default, retained name beside
it". D-036 delivered the first half by auditing the retained-name registry and
demoting the entries the Blue Book does not retain -- caffeine, camphor,
ibuprofen, chloroform. Without the second half those names would vanish from
the app entirely, because PubChem answers with the systematic string as well:
a user who knew the compound as "caffeine" would no longer see the word.

Two things the tests below keep apart, because they are easy to conflate:

* `toluene` is a retained name AND the preferred IUPAC name (P-22.1.3). It is
  shown ONCE, flagged as both -- never twice, and never as an "alternative"
  to itself.
* `caffeine` is a retained name and NOT the preferred one. It is shown SECOND,
  labelled as not the IUPAC name, beside the systematic name.

Only entries the audit marked `RETAINED_NOT_PIN` earn the second line. The
registry also holds 274 unaudited entries, and surfacing whatever alias is
stored under an "IUPAC Name" heading would present unvetted strings as
authoritative.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.chem import naming_providers as n

pytestmark = pytest.mark.skipif(
    shutil.which("java") is None,
    reason="the retained line is round-trip verified, which needs OPSIN's JRE",
)

CAFFEINE = "Cn1cnc2c1c(=O)n(C)c(=O)n2C"
TOLUENE = "Cc1ccccc1"
IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
NOVEL_UREA = "O=C(Nc1ccc(-c2ccncc2)cc1)Nc1cccc(C(F)(F)F)c1"


def _lines(smiles: str) -> list[str]:
    result = n.compute_iupac_name(Chem.MolFromSmiles(smiles), "u", {"use_pubchem": False})
    return list(result.matched)


def test_a_demoted_retained_name_is_shown_beside_the_preferred_one():
    lines = _lines(CAFFEINE)

    assert len(lines) == 2, lines
    assert "caffeine" not in lines[0], "the preferred line must be the systematic name"
    assert lines[1].startswith("caffeine "), lines


def test_the_preferred_name_comes_first():
    """The order is part of the meaning: the second line is explicitly not
    the IUPAC name, so it must never be the one a reader meets first."""
    lines = _lines(IBUPROFEN)

    assert "[Nomenclature engine, derived]" in lines[0]
    assert "[Nomenclature engine, retained name]" in lines[1]


def test_the_retained_line_says_it_is_not_the_iupac_name():
    """It sits under an "IUPAC Name" heading. Leaving the reader to infer
    from the order that it is not one is the same mistake as the registry's
    name, which asserted PIN status for 292 entries by omission."""
    retained_line = _lines(CAFFEINE)[1]

    assert "not the preferred IUPAC name" in retained_line


def test_a_retained_name_that_IS_preferred_is_shown_once():
    """Toluene is retained and preferred at once. Two lines would present
    the same string as an alternative to itself."""
    lines = _lines(TOLUENE)

    assert lines == ["toluene  [Nomenclature engine, derived]"], lines


def test_the_result_carries_preferred_and_retained_as_separate_facts():
    toluene = n.derived_name_for_structure(Chem.MolFromSmiles(TOLUENE))
    assert toluene.preferred is True
    assert toluene.retained is True

    caffeine_pin = n.derived_name_for_structure(Chem.MolFromSmiles(CAFFEINE))
    assert caffeine_pin.preferred is True
    assert caffeine_pin.retained is False

    alternative = n.retained_name_for_structure(
        Chem.MolFromSmiles(CAFFEINE), caffeine_pin.name
    )
    assert alternative is not None
    assert alternative.name == "caffeine"
    assert alternative.preferred is False
    assert alternative.retained is True


def test_a_structure_with_no_retained_name_gets_one_line():
    assert len(_lines(NOVEL_UREA)) == 1


def test_an_unaudited_registry_entry_earns_no_second_line(monkeypatch):
    """The audit is what earns the line. Breaking the guard: a record with no
    `pin_status` -- 274 of the 292 -- must not be surfaced even when its name
    differs from the preferred one."""
    monkeypatch.setattr(
        n,
        "_retained_registry_record",
        lambda smiles: {"name": "some-harvested-alias"},
    )
    mol = Chem.MolFromSmiles(CAFFEINE)

    assert n.retained_name_for_structure(mol, "anything") is None


def test_a_retained_name_that_does_not_round_trip_is_not_shown(monkeypatch):
    """Verified like the preferred name. A registry string that parses to a
    different molecule is dropped rather than shown with a caveat, because a
    wrong name under an IUPAC heading looks exactly as authoritative as a
    right one."""
    monkeypatch.setattr(
        n,
        "_retained_registry_record",
        lambda smiles: {"name": "benzene", "pin_status": "RETAINED_NOT_PIN"},
    )
    mol = Chem.MolFromSmiles(CAFFEINE)

    assert n.retained_name_for_structure(mol, "anything") is None


def test_existing_callers_that_build_a_name_result_are_unaffected():
    """The two fields are additive with defaults, so the PubChem path and any
    other constructor keep working without knowing about them."""
    plain = n.NameResult(name="x", source="PubChem", kind=n.EXACT)

    assert plain.preferred is None
    assert plain.retained is False
