"""The analysis engine and the core checkers.

The verdict tables below were MEASURED before they were asserted -- each
structure was run through the real registry and the output recorded -- so
this file is the record of what the checkers do, not a statement of what
they were meant to do.

Every table carries negative controls. A checker that flagged everything
would pass a table of only-bad structures, which is why aspirin, benzene,
ethanol and an untouched depiction appear in each one.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Geometry import Point3D

from openchem.chem.structure_check import (
    COORDINATES,
    PARSED_MOLECULE,
    SANITIZED_MOLECULE,
    Basis,
    Category,
    CheckContext,
    CheckerDefinition,
    CheckerRegistry,
    CheckerResult,
    Severity,
    StructureIssue,
    build_context,
    build_default_registry,
    run_checks,
)


def molblock_for(smiles: str, mutate=None) -> str:
    """A depiction, optionally with its coordinates damaged.

    `sanitize=False` throughout: half these structures are ones RDKit
    refuses, and refusing to build them here would make the interesting
    half of the table untestable.
    """
    mol = Chem.MolFromSmiles(smiles, sanitize=False)
    assert mol is not None, smiles
    mol.UpdatePropertyCache(strict=False)
    AllChem.Compute2DCoords(mol)
    if mutate is not None:
        mutate(mol.GetConformer())
    return Chem.MolToMolBlock(mol, kekulize=False)


@pytest.fixture(scope="module")
def registry() -> CheckerRegistry:
    return build_default_registry()


def check(registry: CheckerRegistry, smiles: str, mutate=None) -> CheckerResult:
    return run_checks(registry, build_context(molblock_for(smiles, mutate)), "molecule-uuid")


def ids_of(result: CheckerResult) -> set[str]:
    return {issue.checker_id for issue in result.issues}


# --- valence: the two deliberate disagreements ------------------------------
#
# The canvas is vendored Ketcher, whose valence model is inside Indigo's
# compiled WASM -- unpatchable, and this build has no highlighting API. So
# these checkers are a second opinion, and where they differ they have to
# be right for a reason that can be stated.


@pytest.mark.parametrize(
    "label, smiles",
    [
        ("iron(II) oxide", "O=[Fe]"),
        ("iron(III) oxide", "O=[Fe]O[Fe]=O"),
        ("magnetite", "O=[Fe]O[Fe](O[Fe]=O)=O"),
    ],
)
def test_iron_oxides_raise_no_valence_complaint(registry, label, smiles):
    """The reported bug: "Iron also strangely shows valence issues with all
    the oxides."

    The canvas will still draw its warning -- we cannot stop it -- but our
    verdict is that there is nothing wrong, and the reason is not a special
    case for iron. RDKit reports iron's valence list as `[-1]`: a
    transition metal has no defined valence, so main-group octet arithmetic
    does not apply and the checker declines to do it.
    """
    result = check(registry, smiles)

    assert "valence" not in ids_of(result)
    assert "unusual_valence" not in ids_of(result)


def test_if7_is_accepted_although_rdkit_refuses_to_sanitize_it(registry):
    """Iodine heptafluoride is a real compound. RDKit's valence list for
    iodine is `[1, 3, 5]` and it rejects IF7 outright -- so a checker that
    reported RDKit's verdict would inherit that error."""
    result = check(registry, "FI(F)(F)(F)(F)(F)F")

    assert "valence" not in ids_of(result)
    assert "hypervalent_allowed" in ids_of(result)
    explanation = next(i for i in result.issues if i.checker_id == "hypervalent_allowed")
    assert explanation.severity is Severity.INFO
    assert explanation.explains_editor_warning


def test_if7_still_reports_that_rdkit_cannot_work_with_it(registry):
    """Accepting the chemistry does not make the toolkit able to handle it.

    Descriptors, naming and 3D generation all go through sanitization, and
    a reader who is told "this is fine" and then finds every property
    blank has been misled. Two findings, because there are two facts.
    """
    result = check(registry, "FI(F)(F)(F)(F)(F)F")

    sanitizable = next(i for i in result.issues if i.checker_id == "sanitizable")
    assert sanitizable.severity is Severity.WARNING
    assert "greater than permitted" in sanitizable.message


def test_hexamethyliodine_is_an_error_because_six_is_unreachable(registry):
    """The first negative control for the hypervalent rules: an expanded
    octet is built from pairs of ligands, so iodine reaches 1, 3, 5, 7 and
    never 6, whatever it is bonded to."""
    result = check(registry, "C[I](C)(C)(C)(C)C")

    error = next(i for i in result.issues if i.checker_id == "valence")
    assert error.severity is Severity.ERROR
    assert error.basis is Basis.DETERMINISTIC
    assert "not reachable" in error.message


def test_neutral_if6_is_an_error_although_every_ligand_is_allowed(registry):
    """The case that separates the two hypervalent rules.

    Added because mutation testing found they were never tested apart:
    I(CH3)6 fails BOTH the reachable-valence rule and the ligand rule, so
    deleting either one left every test passing. IF6 fails only the first
    -- fluorine is exactly the ligand iodine expands with -- and a neutral
    IF6 is not a species (IF6+ and IF6- are; the neutral is a radical).
    """
    result = check(registry, "FI(F)(F)(F)(F)F")

    error = next(i for i in result.issues if i.checker_id == "valence")
    assert error.severity is Severity.ERROR
    assert "not reachable" in error.message


def test_heptamethyliodine_is_an_error_because_the_ligands_are_wrong(registry):
    """The second, and the one that proves the ligand test is doing work.

    I(CH3)7 has a valence iodine CAN reach -- it fails only on what it is
    bonded to. Without this case a rule that ignored ligands entirely would
    pass every other row in this file.
    """
    result = check(registry, "C[I](C)(C)(C)(C)(C)C")

    error = next(i for i in result.issues if i.checker_id == "valence")
    assert error.severity is Severity.ERROR
    assert "only with F/Cl/O ligands" in error.message


@pytest.mark.parametrize(
    "label, smiles",
    [
        ("iodine pentafluoride", "FI(F)(F)(F)F"),
        ("(diacetoxyiodo)benzene", "CC(=O)OI(OC(C)=O)c1ccccc1"),
        ("sulfur hexafluoride", "FS(F)(F)(F)(F)F"),
        ("xenon tetrafluoride", "F[Xe](F)(F)F"),
        ("perchlorate", "[O-][Cl](=O)(=O)=O"),
    ],
)
def test_real_hypervalent_compounds_are_not_flagged(registry, label, smiles):
    result = check(registry, smiles)

    assert "valence" not in ids_of(result), label


@pytest.mark.parametrize(
    "label, smiles",
    [
        ("methane", "C"),
        ("ethanol", "CCO"),
        ("benzene", "c1ccccc1"),
        ("aspirin", "CC(=O)Oc1ccccc1C(=O)O"),
    ],
)
def test_ordinary_molecules_produce_no_findings_at_all(registry, label, smiles):
    """The negative control for the whole engine, not just for valence.

    Nine checkers run against these and every one must stay silent. A
    threshold set too tight anywhere -- a bond-length band, a crowding
    distance, an angle -- shows up here first.
    """
    result = check(registry, smiles)

    assert result.issues == (), f"{label}: {[i.message for i in result.issues]}"
    assert result.worst_severity is None


def test_five_valent_nitrogen_is_an_error(registry):
    result = check(registry, "C[N](C)(C)(C)C")

    assert next(i for i in result.issues if i.checker_id == "valence").severity is Severity.ERROR


@pytest.mark.parametrize(
    "label, smiles",
    [
        ("ammonium (N+, four bonds)", "C[NH3+]"),
        ("nitro group (N+ and O-)", "C[N+](=O)[O-]"),
        ("borohydride (B-, four bonds)", "[BH4-]"),
    ],
)
def test_charged_atoms_are_not_mistaken_for_bad_valences(registry, label, smiles):
    """The charge adjustment flips direction across the period, and getting
    it backwards calls one of these impossible.

    Nitrogen (five outer electrons) subtracts its charge; boron (three)
    adds it. Ammonium and borohydride both have four bonds and opposite
    charges, so a rule with a single sign passes one and fails the other --
    which is exactly why both are here.
    """
    result = check(registry, smiles)

    assert "valence" not in ids_of(result), label
    assert "unusual_valence" not in ids_of(result), label


def test_a_carbene_is_a_warning_and_not_an_error(registry):
    """Marvin's yellow rather than its red. A valence below the element's
    maximum is a radical or a carbene -- things people draw on purpose --
    and calling those errors is how a user learns to ignore errors."""
    result = check(registry, "[CH2]")

    issue = next(i for i in result.issues if i.checker_id == "unusual_valence")
    assert issue.severity is Severity.WARNING


def test_a_halogen_double_bonded_to_carbon_is_flagged(registry):
    """"With iodine, those multiple bonds with carbon shouldn't be legal,
    but the fluoride should be."

    A WARNING and not an ERROR: iodonium ylides are drawn both ways in the
    literature, and this project does not call a real convention
    impossible. The message says which form is conventional.
    """
    result = check(registry, "C=I")

    issue = next(i for i in result.issues if i.checker_id == "halogen_multiple_bond")
    assert issue.severity is Severity.WARNING
    assert issue.bond_indices


def test_a_carbon_fluorine_single_bond_is_not_flagged(registry):
    """The other half of the same sentence -- the fluoride must stay legal."""
    result = check(registry, "CF")

    assert result.issues == ()


# --- geometry and layout ----------------------------------------------------


def test_two_atoms_at_the_same_point_are_an_error(registry):
    def stack(conformer):
        position = conformer.GetAtomPosition(0)
        conformer.SetAtomPosition(3, Point3D(position.x, position.y, position.z))

    result = check(registry, "CCCCCC", stack)

    issue = next(i for i in result.issues if i.checker_id == "overlapping_atoms")
    assert issue.severity is Severity.ERROR
    assert issue.basis is Basis.DETERMINISTIC
    assert issue.category is Category.GEOMETRY


def test_crossing_bonds_are_reported(registry):
    def cross(conformer):
        a = conformer.GetAtomPosition(1)
        b = conformer.GetAtomPosition(4)
        conformer.SetAtomPosition(1, Point3D(b.x, b.y, b.z))
        conformer.SetAtomPosition(4, Point3D(a.x, a.y, a.z))

    result = check(registry, "CCCCCC", cross)

    assert "overlapping_bonds" in ids_of(result)


def test_a_stretched_bond_is_layout_and_heuristic(registry):
    """Filed under LAYOUT rather than VALIDITY, and marked HEURISTIC.

    A long bond in a 2D drawing is a drawing artefact; it says nothing
    about the chemistry, and the ratio that catches it is a number
    somebody chose. Both facts are carried on the issue so the panel can
    say them out loud.
    """

    def stretch(conformer):
        position = conformer.GetAtomPosition(5)
        conformer.SetAtomPosition(5, Point3D(position.x + 8.0, position.y, position.z))

    result = check(registry, "CCCCCC", stretch)

    issue = next(i for i in result.issues if i.checker_id == "bond_length")
    assert issue.category is Category.LAYOUT
    assert issue.basis is Basis.HEURISTIC
    assert issue.severity is Severity.WARNING


def test_cyclopropane_does_not_trip_the_acute_angle_check(registry):
    """A real 60-degree ring, drawn correctly, against a 30-degree
    threshold. The check exists to catch bonds drawn on top of each other,
    not to complain about small rings."""
    result = check(registry, "C1CC1")

    assert "acute_bond_angle" not in ids_of(result)


# --- prerequisites: the cascade is the failure mode -------------------------


def test_a_structure_with_no_coordinates_skips_every_geometry_checker(registry):
    """A molblock straight from SMILES has every atom at the origin. That
    IS a conformer as far as RDKit is concerned, and geometry checks run
    against it report every atom as overlapping every other -- a synthetic
    catastrophe over a structure that is merely undepicted."""
    mol = Chem.MolFromSmiles("CCO")
    lines = Chem.MolToMolBlock(mol, includeStereo=False).splitlines()
    for n in range(4, 7):
        lines[n] = "    0.0000    0.0000    0.0000 " + lines[n][31:]

    result = run_checks(registry, build_context("\n".join(lines)), "u")

    skipped = {s.checker_id: s.reason for s in result.skipped}
    assert "overlapping_atoms" in skipped
    assert skipped["overlapping_atoms"] == "no coordinates"
    assert "overlapping_atoms" not in ids_of(result)


def test_a_structure_that_will_not_sanitize_skips_once_with_rdkits_reason(registry):
    """One skipped-with-reason per dependent checker, not a cascade of
    downstream complaints -- asserted, because the cascade is the failure
    mode this design exists to prevent.

    The reason carries RDKit's own sentence, which is nearly always the
    single most useful thing available about a structure it refuses.
    """
    result = check(registry, "C[I](C)(C)(C)(C)C")

    skipped = {s.checker_id: s.reason for s in result.skipped}
    assert skipped == {
        "unknown_stereo": (
            "the structure does not sanitize "
            "(Explicit valence for atom # 1 I, 6, is greater than permitted)"
        )
    }
    assert len(result.issues) == 2  # the valence error, and "RDKit cannot use this"


def test_an_unreadable_molblock_reports_every_checker_as_skipped(registry):
    result = run_checks(registry, build_context("this is not a molfile"), "u")

    assert result.issues == ()
    assert len(result.skipped) == len(registry.all())
    assert {s.reason for s in result.skipped} == {"the structure could not be read"}


# --- the registry -----------------------------------------------------------


def _always(issue_id: str, **kwargs):
    def run(context: CheckContext):
        return [
            StructureIssue(
                checker_id=issue_id,
                category=Category.PLUGIN,
                severity=Severity.INFO,
                basis=Basis.HEURISTIC,
                message="",
            )
        ]

    return run


def test_run_order_is_derived_from_requirements_not_registration_order():
    """A plugin declares what it needs; it does not get appended to a list
    somebody has to keep in the right order."""
    registry = CheckerRegistry()
    registry.register(
        CheckerDefinition(
            checker_id="needs_coordinates",
            display_name="",
            category=Category.PLUGIN,
            run=_always("a"),
            requires=frozenset({PARSED_MOLECULE, SANITIZED_MOLECULE, COORDINATES}),
        )
    )
    registry.register(
        CheckerDefinition(
            checker_id="needs_little",
            display_name="",
            category=Category.PLUGIN,
            run=_always("b"),
            requires=frozenset({PARSED_MOLECULE}),
        )
    )

    assert [d.checker_id for d in registry.all()] == ["needs_little", "needs_coordinates"]


def test_a_checker_that_raises_is_skipped_and_the_rest_still_run():
    """One bad plugin must not be able to silence every other opinion
    about a structure."""

    def explode(context: CheckContext):
        raise RuntimeError("boom")

    registry = CheckerRegistry()
    registry.register(
        CheckerDefinition(
            checker_id="broken",
            display_name="",
            category=Category.PLUGIN,
            run=explode,
            requires=frozenset({PARSED_MOLECULE}),
        )
    )
    registry.register(
        CheckerDefinition(
            checker_id="fine",
            display_name="",
            category=Category.PLUGIN,
            run=_always("ok"),
            requires=frozenset({PARSED_MOLECULE}),
        )
    )

    result = run_checks(registry, build_context(molblock_for("CCO")), "u")

    assert ids_of(result) == {"ok"}
    assert result.skipped[0].checker_id == "broken"
    assert "RuntimeError: boom" in result.skipped[0].reason


def test_suppressing_a_checker_records_it_rather_than_hiding_it(registry):
    """Query atoms, reaction templates and teaching examples are drawn
    wrong on purpose. Waiving a check has to stay visible, or a later
    reader cannot tell a waived check from a passed one."""
    result = run_checks(
        registry,
        build_context(molblock_for("C[N](C)(C)(C)C")),
        "u",
        suppressed=["valence"],
    )

    assert "valence" not in ids_of(result)
    assert result.suppressed == ("valence",)
    assert any(s.checker_id == "valence" and "suppressed" in s.reason for s in result.skipped)


# --- the result shape -------------------------------------------------------


def test_worst_severity_drives_the_indicator(registry):
    assert check(registry, "CCO").worst_severity is None
    assert check(registry, "[CH2]").worst_severity is Severity.WARNING
    assert check(registry, "C[N](C)(C)(C)C").worst_severity is Severity.ERROR


def test_issues_group_by_category_most_serious_first(registry):
    def stack(conformer):
        position = conformer.GetAtomPosition(0)
        conformer.SetAtomPosition(3, Point3D(position.x, position.y, position.z))

    grouped = check(registry, "C[N](C)(C)(C)C", stack).by_category()

    assert list(grouped)[0] is Category.VALIDITY
    assert Category.REPRESENTATION not in grouped or list(grouped).index(Category.REPRESENTATION) == 1


def test_a_result_carries_the_structure_version_it_was_computed_from(registry):
    """The anti-staleness field. A panel holding a result whose version is
    behind the current one must discard it -- this session already produced
    two bugs of that shape (a canvas showing the pre-undo structure, a pose
    table showing a deleted result)."""
    result = run_checks(registry, build_context(molblock_for("CCO")), "u", structure_version=7)

    assert result.structure_version == 7


def test_the_result_records_what_produced_it(registry):
    result = check(registry, "CCO")

    assert result.provenance is not None
    assert result.provenance.method == "openchem.chem.structure_check"
    assert result.provenance.parameters["checkers_run"] > 0


def test_the_hypervalent_rules_file_is_in_the_packaging_spec():
    """`chem/data` is shipped file by file, not as a directory, so a new
    data file has to be named in the spec.

    Worth a test because this failure is invisible from a checkout: every
    test above passes, the build succeeds, and the valence checker raises
    FileNotFoundError the first time somebody draws a structure in the
    frozen app. The spec's own comments record it happening twice already,
    once for `admet_runner.py`.
    """
    from pathlib import Path

    spec = Path(__file__).resolve().parent.parent / "packaging" / "openchem.spec"

    assert "hypervalent_rules.json" in spec.read_text(encoding="utf-8")


def test_every_rule_cites_a_reference_and_a_real_example():
    """No unsourced numbers. A `maximum_valence` with nothing behind it is
    exactly the kind of invented precision this project throws work away
    to avoid."""
    from openchem.chem.checkers.valence import hypervalent_rules

    rules = hypervalent_rules()
    assert rules, "the rules file loaded empty"
    for symbol, rule in rules.items():
        assert rule["reference"], symbol
        assert rule["examples"], symbol
        assert rule["maximum_valence"] == max(rule["permitted_valences"]), symbol
