"""Reaching Gutmann's tables from this app's other solvent vocabularies.

`tests/test_gutmann.py` checks the transcription against the paper. This
file checks the JOIN -- the declared spelling bridge, the structure
lookup, and the invariant that every displayed value traces to exactly
one table row.

**THE JOIN FOUND A DEFECT IN THE SHIPPED TABLE, which is why it exists.**
Wiring the numbers to a structure needed one row per liquid, and two
liquids turned out to be carrying half their data each: `donicity`
answered for "dioxane" with an acceptor number and no donor number, while
the paper prints DN = 14.8 for it one page earlier under the spelling
"Dioxan". Glyme had the same shape, its donor number filed under
"Dimethoxyethane (DME)". Both are merged in the generator now, and the
tests below are what stop it recurring.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem import gutmann as gutmann_module
from openchem.chem.gutmann import (
    donicity,
    donicity_for,
    donicity_for_structure,
    name_bridge,
    solvent_names,
    structural_coverage,
)


def _payload() -> dict:
    return json.loads(
        (Path(gutmann_module.__file__).parent / "data" / "gutmann_solvents.json").read_text(
            encoding="utf-8"
        )
    )


# --- the two liquids that were split in half --------------------------------


def test_dioxane_carries_both_of_its_numbers():
    """DN 14.8 from the donor table's "Dioxan", AN 10.8 from the acceptor
    table's "Dioxane". One liquid, one row.

    The paper's own prose settles that they are the same: p12 reads
    "faster in THF (DN = 20) than in dioxane (DN = 14,8)", using the -e
    spelling for the row the DN table spells without one.
    """
    record = donicity("dioxan")
    assert record is not None
    assert record.donor_number == pytest.approx(14.8)
    assert record.acceptor_number == pytest.approx(10.8)
    assert donicity("dioxane") is None, (
        "both spellings are still present, so a caller can still get half "
        "the solvent depending on which one they ask for"
    )


def test_glyme_and_dimethoxyethane_are_one_row():
    """The acceptor table names it Glyme, the donor table Dimethoxyethane
    (DME). Same liquid."""
    record = donicity("dimethoxyethane")
    assert record is not None
    assert record.donor_number == pytest.approx(24.0)
    assert record.acceptor_number == pytest.approx(10.2)
    assert donicity("glyme") is None


def test_diglyme_is_NOT_merged_into_it():
    """THE ARM THAT SAYS NO, and the reason the merge is declared rather
    than fuzzy-matched. `difflib` pairs "glyme" with "diglyme" happily,
    and they are two different ethers -- diglyme keeps its own row with
    an acceptor number and no donor number, which is what the paper
    prints."""
    record = donicity("diglyme")
    assert record is not None
    assert record.acceptor_number == pytest.approx(9.9)
    assert record.donor_number is None


def test_the_declared_variants_are_the_only_ones_merged():
    """A merge nobody declared would be a value silently changing owner."""
    variants = _payload()["spelling_variants"]
    assert variants == {"dioxane": "dioxan", "glyme": "dimethoxyethane"}


# --- the name bridge --------------------------------------------------------


@pytest.mark.parametrize("alternative", sorted(name_bridge()))
def test_every_declared_bridge_resolves_to_a_real_row(alternative):
    """A bridge naming a row that does not exist is a typo that silently
    stops a solvent resolving, which reads as "Gutmann never measured it"."""
    assert donicity_for(alternative) is not None, (
        f"{alternative!r} bridges to {name_bridge()[alternative]!r}, which is not "
        "in either table"
    )


def test_two_synonyms_never_name_two_structures():
    """SEVERAL SYNONYMS FOR ONE LIQUID ARE FINE; two STRUCTURES are not.

    Dimethoxyethane is "glyme" in one vocabulary and "1,2-dimethoxyethane"
    in another, so forbidding a second alternative would be forbidding a
    real synonym. What must not happen is two of them resolving to
    different InChIKeys -- that would mean a declared synonym is not one,
    and the structure lookup would silently pick whichever came first.
    """
    from openchem.chem.gutmann import synonym_keys

    conflicts = {
        name: sorted(keys)
        for name in solvent_names()
        if len(keys := synonym_keys(name)) > 1
    }
    assert not conflicts, (
        f"these solvents' declared synonyms name different structures: {conflicts}"
    )

    # The setup assertion: at least one solvent really does have more than
    # one declared synonym, so the check above is not vacuous.
    targets = list(name_bridge().values())
    assert any(targets.count(t) > 1 for t in targets)


def test_a_bridge_never_shadows_a_real_name():
    """A bridge key that is ALSO a table name would be dead -- the direct
    lookup wins -- and would read as a working alias while doing nothing."""
    shadowed = sorted(set(name_bridge()) & set(solvent_names()))
    assert not shadowed, (
        f"these bridge keys are already real solvent names, so the bridge entry "
        f"does nothing: {shadowed}"
    )


def test_the_solubility_picker_reaches_the_table_where_it_should():
    """The measured overlap, so a bridge that stops working is visible as
    a number rather than as a quietly emptier report."""
    from openchem.chem.solubility import solvent_choices

    reached = [name for name in solvent_choices() if donicity_for(name) is not None]
    assert len(reached) >= 26, f"only {len(reached)} of the offered solvents resolve"
    assert "water" in reached and "1,4-dioxane" in reached


# --- the structure lookup ---------------------------------------------------


@pytest.mark.parametrize(
    "smiles,expected",
    [
        ("CS(C)=O", "dimethyl sulphoxide"),
        ("O", "water"),
        ("c1ccncc1", "pyridine"),
        ("C1CCOC1", "tetrahydrofuran"),
        ("CC(C)=O", "acetone"),
        ("ClC(Cl)Cl", "chloroform"),
    ],
)
def test_a_drawn_solvent_resolves_by_inchikey(smiles, expected):
    record = donicity_for_structure(Chem.MolFromSmiles(smiles))
    assert record is not None, f"{smiles} did not resolve"
    assert record.name == expected


def test_a_molecule_that_is_not_a_table_solvent_resolves_to_nothing():
    """Silence rather than a nearest match. The tables hold 66 liquids."""
    assert donicity_for_structure(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")) is None
    assert donicity_for_structure(None) is None


def test_every_structure_key_names_exactly_one_solvent():
    """EVERY DISPLAYED VALUE TRACES TO EXACTLY ONE TABLE ROW.

    The failure this guards is a later "deduplication" of the transcribed
    tables: two names collapsing onto one InChIKey means one liquid
    wearing two rows, which is the defect that was already there.
    """
    coverage = structural_coverage()
    names = list(coverage.values())
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert not duplicates, f"these solvents claim more than one structure: {duplicates}"
    assert len(set(coverage)) == len(coverage)


def test_the_structure_map_is_derived_and_not_a_typed_list_of_smiles():
    """SIXTY HAND-WRITTEN SMILES WOULD BE SIXTY CHANCES TO SHIP A
    PLAUSIBLE WRONG MOLECULE, for liquids like selenium oxychloride and
    phenylphosphonic difluoride. The structures come from
    `abraham_solutes.json` instead -- shipped, sourced, keyed by InChIKey.

    Asserted structurally rather than by reading the code: the module must
    contain no SMILES-shaped constant table, and the coverage must be a
    strict subset of what the solute table can supply.
    """
    source = Path(gutmann_module.__file__).read_text(encoding="utf-8")
    assert "MolFromSmiles" not in source, (
        "chem/gutmann.py now builds structures from typed SMILES; the whole "
        "point of the derived join is that it does not"
    )

    solutes = json.loads(
        (Path(gutmann_module.__file__).parent / "data" / "abraham_solutes.json").read_text(
            encoding="utf-8"
        )
    )["solutes"]
    assert set(structural_coverage()) <= set(solutes)


def test_the_structural_coverage_is_partial_and_that_is_the_honest_state():
    """A guard on the NUMBER, so a change that silently halves the reach
    fails here rather than showing up as a quieter panel.

    35 of 66 today. The rest are liquids the Abraham solute table does not
    carry, and inventing a structure for them is exactly what this design
    refuses.

    **66 AND NOT 68**, which is worth stating because the pre-merge union of
    the two tables was 68: `dioxane`/`dioxan` and `glyme`/`dimethoxyethane`
    were each ONE liquid wearing two names.
    `test_the_solvent_count_is_the_merged_one` derives it so the number
    cannot drift from the data again.
    """
    coverage = structural_coverage()
    assert 30 <= len(coverage) <= len(solvent_names())
    assert len(coverage) < len(solvent_names()), (
        "every solvent now resolves, which would mean structures came from "
        "somewhere other than the solute table"
    )


# --- the two scales stay two scales -----------------------------------------


def test_the_solubility_report_labels_DN_and_AN_separately():
    """NOT `Gutmann: 29.8 / 19.3`. A later tidy-up into one field would
    erase the distinction without breaking any numeric test, so this
    asserts on the PRESENTATION object rather than trusting prose.

    HMPA is the fixture that proves they are not one ordering -- but it is
    not in the solubility picker, so water does the job here: 18.0 DN
    against 54.8 AN, plus a THIRD number, the bulk donicity at 33.0.
    """
    from openchem.chem.solubility import compute_solubility

    result = compute_solubility(Chem.MolFromSmiles("c1ccccc1"), "uuid", {"solvent": "water"})
    labels = {f.label: f.display_value for f in result.facts if "Gutmann" in f.label}
    assert labels == {
        "Gutmann donor number (DN)": "18.0",
        "Gutmann bulk donicity": "33.0",
        "Gutmann acceptor number (AN)": "54.8",
    }


def test_hmpa_is_why_the_two_scales_may_never_be_merged():
    """Highest-but-one donor number, and an acceptor number near diethyl
    ether's. Anything that reported "the Gutmann number" would have to
    pick one and would be wrong about this solvent either way."""
    record = donicity("hexamethylphosphoramide")
    assert record is not None
    assert record.donor_number == pytest.approx(38.8)
    assert record.acceptor_number == pytest.approx(10.6)

    # Measured across the whole table: HMPA is 2nd of 46 by donor number
    # and 8th of 32 from the BOTTOM by acceptor number. Its AN neighbours
    # are dimethoxyethane at 10.2 and dioxan at 10.8 -- ordinary ethers,
    # nothing like the second-strongest donor in the set.
    donors = sorted(
        (r for r in map(donicity, solvent_names()) if r.donor_number is not None),
        key=lambda r: -r.donor_number,
    )
    acceptors = sorted(
        (r for r in map(donicity, solvent_names()) if r.acceptor_number is not None),
        key=lambda r: r.acceptor_number,
    )
    assert [r.name for r in donors].index("hexamethylphosphoramide") == 1
    assert [r.name for r in acceptors].index("hexamethylphosphoramide") < len(acceptors) / 3


def test_the_lewis_report_keeps_them_as_two_facts():
    """The other consumer, asserted the same way and for the same reason."""
    from openchem.chem.lewis import compute_lewis_sites

    result = compute_lewis_sites(Chem.MolFromSmiles("CS(C)=O"), "uuid")
    labels = [f.label for f in result.facts if "Gutmann" in f.label]
    assert labels == [
        "Gutmann donor number (DN)",
        "Gutmann acceptor number (AN)",
    ]


def test_gutmann_numbers_never_enter_the_abraham_calculation():
    """**A FACT ABOUT THE SOLVENT, NEVER ANOTHER DESCRIPTOR.** The creep
    is obvious and would be plausible -- "since we have DN, use it as a
    predictor" -- and nothing in either source establishes that
    relationship.

    Asserted structurally, because the numeric version would need a
    solvent whose DN moved, and there is none: `chem/abraham.py` must not
    reference the donicity tables at all.
    """
    source = Path(gutmann_module.__file__).parent.parent
    abraham = (source / "chem" / "abraham.py").read_text(encoding="utf-8")
    assert "gutmann" not in abraham.lower(), (
        "chem/abraham.py now references the Gutmann tables. Donor and acceptor "
        "numbers are reported BESIDE the solvation shift, never fed into it."
    )


def test_the_solvent_count_is_the_merged_one():
    """66, NOT the 68 the two tables hold between them before merging.

    `dioxane`/`dioxan` and `glyme`/`dimethoxyethane` are each ONE liquid
    under two names, so the union of the donor and acceptor tables
    overcounts by exactly the number of declared spelling variants. Five
    places quoted 68 -- including prose written in the same commit that did
    the merging -- so the relationship is derived here rather than trusted
    to anyone remembering.
    """
    payload = _payload()
    donors, acceptors = set(payload["donor_numbers"]), set(payload["acceptor_numbers"])
    variants = payload["spelling_variants"]

    assert len(solvent_names()) == len(donors | acceptors)
    assert len(solvent_names()) == 66
    assert len(variants) == 2
    # The pre-merge union is what the stale number was, and naming it here
    # is what stops somebody "correcting" 66 back to it.
    assert len(solvent_names()) + len(variants) == 68
