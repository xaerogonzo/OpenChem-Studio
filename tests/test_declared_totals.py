"""A per-atom dataset's molecular total is DECLARED by its producer.

The bug this closes was reported from the running app: the Properties
panel showed `mol_logp 3.624` while the LogP Contribution dialog beside
it showed `Overall: 0.8585`, with nothing on screen explaining the gap.

Neither number was a chemistry error. `Overall:` was
`sum(result.values.values())`, on the belief that everything shown there
was additive over the atoms present -- and that belief was wrong in three
separate ways at once. Measured on aspirin before the fix:

    crippen_logp_contrib       Overall: 0.1511   real LogP 1.3101
    crippen_mr_contrib         Overall: 35.51    real MR   44.71
    gasteiger_charge_at_ph     Overall: -1.359   molecule is NEUTRAL
    orbital_electronegativity  Overall: 134.8    summed eV, meaningless
    topology_eccentricity      Overall: 65       summed hops, meaningless
    topology_distance_degree   Overall: 492      2x Wiener, unnamed
    atom_sasa / polarizability / huckel          correct, but unnamed

The first three share a cause: the editor's hydrogens are implicit, so
the increments Crippen and PEOE give them have no atom to sit on.

`Overall:` had already been narrowed twice -- once for spectra, once for
categorical results -- each time by discovering another special case the
hard way. So the default is inverted rather than narrowed a third time:
a producer declares a total or declares that it has none, and a consumer
that finds no declaration shows nothing.

THE FILE'S MOST IMPORTANT TEST IS THE REGISTRY AUDIT, because it is the
only one that covers a calculator nobody has written yet.
"""

from __future__ import annotations

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, Crippen

from openchem.bootstrap import build_service_container
from openchem.chem.calculator_options import (
    EXPLICIT_HYDROGENS,
    HEAVY_ATOMS_ONLY,
    HYDROGEN_MODE_DESCRIPTIONS,
    HYDROGEN_MODES,
    INCREMENT_OF_HS,
)
from openchem.chem.descriptor_providers import (
    RDKitDescriptorProvider,
    crippen_contributions,
    compute_crippen_logp_contrib_calculator,
    compute_crippen_mr_contrib_calculator,
)
from openchem.domain.calculator import RegistryExecution
from openchem.domain.common import (
    ATOM_BASES,
    TOTAL,
    declare_total,
    decline_total,
    valid_total_declaration,
)
from openchem.domain.scientific_result import PerAtomDataset
from openchem.ui.visualization import atom_basis, declared_total, is_categorical

RDLogger.DisableLog("rdApp.*")

#: The molecule from the bug report, read out of
#: `D:\Xaero Stuff\Documents\Molecules\Failure.ocsproj` and committed here
#: because that file lives outside the repository and CI could never open
#: it. Verified to reproduce every number in the screenshot: C18H21NO2,
#: 21 heavy atoms, LogP 3.6239 (shown as "3.624"), heavy-atom sum 0.8585
#: (the reported "Overall"), contributions running -1.019 to 0.5437.
REPORTED_SMILES = "C[C@@H](N)Cc1c2c3c(c4occc14)[C@H]1CC[C@@]3(CC1)CO2"


def _mol(smiles: str = "CC(=O)Oc1ccccc1C(=O)O") -> Chem.Mol:
    return Chem.MolFromSmiles(smiles)


@pytest.fixture(scope="module")
def registry():
    return build_service_container().calculator_registry


@pytest.fixture(scope="module")
def per_atom_results(registry):
    """Every registered calculator that returns a `PerAtomDataset`, run
    once at its declared defaults.

    ENUMERATED FROM THE LIVE REGISTRY, never from a list of ids kept
    beside it. That is the whole point: a list is what
    `inapplicable_calculators` was, and it rotted into 27 wrong entries
    because nothing ever brought anybody back to it. A calculator
    registered tomorrow is audited tomorrow.

    With a conformer, or every geometry-dependent calculator comes back
    FAILED and is skipped -- `atom_sasa` is one, and it is one of the four
    whose total was correct-but-unnamed.
    """
    mol = Chem.AddHs(_mol())
    AllChem.EmbedMolecule(mol, randomSeed=0xF00D)
    AllChem.MMFFOptimizeMolecule(mol)

    found = []
    for category in registry.categories():
        for definition in registry.by_category(category):
            if not isinstance(definition.execution, RegistryExecution):
                continue
            try:
                result = registry.compute(
                    definition.calculator_id,
                    mol,
                    "uuid",
                    {p.name: p.default for p in definition.parameters},
                )
            except Exception:  # noqa: BLE001 - a calculator that raises is not this file's subject
                continue
            if isinstance(result, PerAtomDataset) and result.values:
                found.append((definition.calculator_id, result))
    return found


# --- the audit ------------------------------------------------------------


def test_every_per_atom_calculator_declares_or_declines_a_total(per_atom_results):
    """No calculator gets a total merely by BEING a `PerAtomDataset`.

    The failure names the calculator, so the fix is obvious to whoever
    added it. A categorical dataset is accepted without a `TOTAL` key --
    `CATEGORICAL_SCALE` is already the producer saying its values are
    category ids rather than magnitudes, which is the same statement, and
    requiring it twice would put one claim in two places.
    """
    assert per_atom_results, "the registry produced no per-atom results -- the audit tested nothing"

    undeclared = [
        calculator_id
        for calculator_id, result in per_atom_results
        if not is_categorical(result)
        and TOTAL not in ((result.provenance.parameters if result.provenance else None) or {})
    ]
    assert not undeclared, (
        f"{undeclared} produce per-atom values but never say whether those values have a "
        f"molecular total. Add declare_total(...) or decline_total(reason) to the "
        f"provenance parameters -- see domain/common.TOTAL. The default is 'no total'; "
        f"an absent key is the one thing that is not an answer."
    )


def test_every_declaration_that_exists_is_well_formed(per_atom_results):
    """Structural validity, checked over the real registry rather than
    over hand-written fixtures -- a declaration that only a fixture ever
    exercises is not covered."""
    malformed = [
        (calculator_id, (result.provenance.parameters or {}).get(TOTAL))
        for calculator_id, result in per_atom_results
        if result.provenance
        and TOTAL in (result.provenance.parameters or {})
        and not valid_total_declaration((result.provenance.parameters or {})[TOTAL])
    ]
    assert not malformed, f"malformed total declarations: {malformed}"


def test_every_declared_basis_is_in_the_closed_vocabulary(per_atom_results):
    """A free string would admit `heavy_atoms`/`heavy-atoms`/`heavy atom`,
    and a typo routes a dataset to no branch while looking fine -- the
    reason `applies_to` is closed too."""
    for calculator_id, result in per_atom_results:
        assert atom_basis(result) in ATOM_BASES, calculator_id


def test_the_two_meaningless_sums_are_declined_by_name(per_atom_results):
    """The two `Overall:` printed that were not merely wrong but had no
    correct value at all. Named individually, because a generic "some
    calculators decline" assertion passes on an empty set."""
    by_id = dict(per_atom_results)
    # `tsei_projection` joined this list because a MUTATION found the gap:
    # declaring a plausible total on it -- `declare_total(0.0, "TSEI
    # projection total")` -- passed every guard in this file and every
    # guard in `tests/test_tsei.py`. The audit checks that a declaration
    # EXISTS and is well formed; only naming the calculator says which
    # answer is right. Same reason the two above are named individually.
    for calculator_id in (
        "orbital_electronegativity",
        "topology_eccentricity",
        "tsei_projection",
    ):
        assert calculator_id in by_id, f"{calculator_id} did not run -- the guard tested nothing"
        result = by_id[calculator_id]
        declaration = (result.provenance.parameters or {})[TOTAL]
        assert declaration["declared"] is False, f"{calculator_id} should have no total"
        assert declaration["reason"].strip(), f"{calculator_id} declines without saying why"
        assert declared_total(result) is None


def test_a_declined_total_still_carries_a_reason():
    """`decline_total` exists so that "no total" is a decision on the
    record rather than an omission -- the same move as the assembly
    gate's `catches_composition_order: false` carrying its
    justification."""
    assert valid_total_declaration(decline_total("no molecular sum is defined"))
    assert not valid_total_declaration({"declared": False})
    assert not valid_total_declaration({"declared": False, "reason": "   "})


# --- the negative guard ---------------------------------------------------


def test_a_plausible_lie_passes_the_validator_and_fails_the_chemistry(per_atom_results):
    """THE TEST THAT PINS THE ARCHITECTURE IN PLACE.

    A producer declaring `label="LogP (Crippen)", value=sum(values)` is
    exactly the original bug wearing the new metadata. It is WELL-FORMED,
    so the structural validator must accept it -- if the validator caught
    this, it would be deciding what numbers mean, which is the job this
    key exists to take away from the generic machinery.

    Catching it is the domain test's job, and
    `test_the_crippen_total_is_the_molecules_own_logp` below is what does
    it. Both halves are asserted here so that neither can be weakened
    without this failing:

        generic machinery -> validates the SHAPE of scientific metadata
        domain tests      -> validate its TRUTH
    """
    mol = _mol()
    honest = compute_crippen_logp_contrib_calculator(mol, "uuid", {})
    lie = declare_total(sum(honest.values.values()), "LogP (Crippen)")

    assert valid_total_declaration(lie), (
        "the structural validator rejected a well-formed declaration -- scientific "
        "semantics have leaked into the validator, which is the wrong layer"
    )
    assert lie["value"] != pytest.approx(Crippen.MolLogP(mol)), (
        "the lie and the truth agree, so this fixture cannot discriminate"
    )
    assert declared_total(honest)["value"] == pytest.approx(Crippen.MolLogP(mol))


# --- the chemistry --------------------------------------------------------


@pytest.mark.parametrize(
    "name,smiles",
    [
        # Spanning cases, deliberately. Ethanol is simple enough that a
        # broken AddHs still looks plausible; morphine has the
        # heteroatoms, branching and varied implicit-H environments that
        # make it not.
        ("ethanol", "CCO"),
        ("benzene", "c1ccccc1"),
        ("aspirin", "CC(=O)Oc1ccccc1C(=O)O"),
        ("caffeine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C"),
        ("morphine", "CN1CC[C@]23[C@H]4Oc5c(O)ccc(C[C@@H]1[C@@H]2C=C[C@@H]4O)c35"),
    ],
)
def test_the_crippen_total_is_the_molecules_own_logp(registry, name, smiles):
    """Reached THROUGH THE REGISTRY, not by importing the function.

    This project has already had a direct-import test pass while the
    registration bound to a shadowed two-argument function, so a
    calculator is tested the way the app reaches it.
    """
    mol = Chem.MolFromSmiles(smiles)
    result = registry.compute("crippen_logp_contrib", mol, "uuid", {})
    assert declared_total(result)["value"] == pytest.approx(Crippen.MolLogP(mol), abs=1e-9)


@pytest.mark.parametrize(
    "name,smiles",
    [
        ("ethanol", "CCO"),
        ("aspirin", "CC(=O)Oc1ccccc1C(=O)O"),
        ("caffeine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C"),
        ("morphine", "CN1CC[C@]23[C@H]4Oc5c(O)ccc(C[C@@H]1[C@@H]2C=C[C@@H]4O)c35"),
    ],
)
def test_two_of_the_three_hydrogen_modes_really_add_up(registry, name, smiles):
    """And the default deliberately does NOT.

    That asymmetry is the feature rather than a shortcoming: the default
    shows what the atoms on screen actually carry, and the balance
    sentence is what reconciles it. A version of this test asserting all
    three add up would be asserting the default away.
    """
    mol = Chem.MolFromSmiles(smiles)
    reference = Crippen.MolLogP(mol)

    def visible_sum(mode: str) -> float:
        return sum(registry.compute("crippen_logp_contrib", mol, "uuid", {"hydrogens": mode}).values.values())

    assert visible_sum(INCREMENT_OF_HS) == pytest.approx(reference, abs=1e-9)
    assert visible_sum(EXPLICIT_HYDROGENS) == pytest.approx(reference, abs=1e-9)
    assert visible_sum(HEAVY_ATOMS_ONLY) != pytest.approx(reference, abs=1e-6), (
        "the heavy-atom sum matched LogP, so this molecule cannot show the difference "
        "the hydrogen modes exist for -- pick one with hydrogens"
    )


def test_the_declared_total_is_the_same_in_every_hydrogen_mode(registry):
    """The setting changes the REPRESENTATION, never the chemistry.

    If this ever fails, the plumbing has started feeding a different
    molecule to `Crippen.MolLogP` depending on a display option, which
    would be a far worse bug than the one being fixed.
    """
    mol = _mol()
    totals = {
        mode: declared_total(
            registry.compute("crippen_logp_contrib", mol, "uuid", {"hydrogens": mode})
        )["value"]
        for mode in HYDROGEN_MODES
    }
    assert len(set(totals.values())) == 1, totals
    assert next(iter(totals.values())) == pytest.approx(Crippen.MolLogP(mol), abs=1e-9)


def test_only_explicit_hydrogens_changes_the_atom_count_and_the_basis(registry):
    """`Increment of Hs` folds onto the SAME atoms, which is what keeps
    the depiction, the atom indices and the 3D pane valid for it."""
    mol = _mol()
    results = {
        mode: registry.compute("crippen_logp_contrib", mol, "uuid", {"hydrogens": mode})
        for mode in HYDROGEN_MODES
    }
    assert len(results[HEAVY_ATOMS_ONLY].values) == mol.GetNumAtoms()
    assert len(results[INCREMENT_OF_HS].values) == mol.GetNumAtoms()
    assert len(results[EXPLICIT_HYDROGENS].values) == Chem.AddHs(mol).GetNumAtoms()

    assert atom_basis(results[HEAVY_ATOMS_ONLY]) == "heavy_atoms"
    assert atom_basis(results[INCREMENT_OF_HS]) == "heavy_atoms"
    assert atom_basis(results[EXPLICIT_HYDROGENS]) == "explicit_h"


def test_cycling_the_hydrogen_modes_leaves_nothing_stale(registry):
    """A -> B -> C -> A, each step matching a fresh computation.

    The total now travels in provenance BESIDE the values, which is the
    most realistic place for one of them to outlive a parameter change
    and quietly describe the previous run.
    """
    mol = _mol()

    def snapshot(mode: str):
        result = registry.compute("crippen_logp_contrib", mol, "uuid", {"hydrogens": mode})
        return (
            len(result.values),
            atom_basis(result),
            round(sum(result.values.values()), 10),
            declared_total(result)["value"],
            "balance" in declared_total(result),
        )

    fresh = {mode: snapshot(mode) for mode in HYDROGEN_MODES}
    for mode in (HEAVY_ATOMS_ONLY, INCREMENT_OF_HS, EXPLICIT_HYDROGENS, HEAVY_ATOMS_ONLY):
        assert snapshot(mode) == fresh[mode], f"{mode} differed when reached in sequence"


def test_only_the_default_mode_carries_a_balance_explanation(registry):
    """The two that add up have no gap to explain, and offering one would
    be an explanation of floating-point noise."""
    mol = _mol()
    assert "balance" in declared_total(
        registry.compute("crippen_logp_contrib", mol, "uuid", {"hydrogens": HEAVY_ATOMS_ONLY})
    )
    for mode in (INCREMENT_OF_HS, EXPLICIT_HYDROGENS):
        assert "balance" not in declared_total(
            registry.compute("crippen_logp_contrib", mol, "uuid", {"hydrogens": mode})
        )


def test_the_fold_does_not_double_count_a_hydrogen_that_is_already_drawn():
    """A structure imported from a molblock keeps its explicit hydrogens
    (`mol_from_molblock` passes `removeHs=False`, deliberately), so
    `Increment of Hs` can be handed a molecule where some hydrogens are
    already atoms in their own right.

    Those must keep their own entry rather than ALSO being folded into
    their neighbour -- the guard in `crippen_contributions` that skips any
    hydrogen already present in the input. Without it a fully-hydrogenated
    input would count every hydrogen twice, and the total is exactly the
    kind of plausible-looking number nobody would question.
    """
    plain = Chem.MolFromSmiles("CCO")
    hydrogenated = Chem.AddHs(plain)
    reference = Crippen.MolLogP(plain)

    for mode in (HEAVY_ATOMS_ONLY, INCREMENT_OF_HS, EXPLICIT_HYDROGENS):
        values, _basis = crippen_contributions(hydrogenated, mode)
        assert sum(values.values()) == pytest.approx(reference, abs=1e-9), mode

    # And the setup is asserted: if AddHs ever stopped adding atoms this
    # would be testing the implicit case twice and would pass anyway.
    assert hydrogenated.GetNumAtoms() > plain.GetNumAtoms()


def test_the_molar_refractivity_total_is_the_molecules_own_mr(registry):
    """The second Crippen calculator, which had the identical defect --
    aspirin printed 35.51 against a real molar refractivity of 44.71."""
    mol = _mol()
    result = registry.compute("crippen_mr_contrib", mol, "uuid", {})
    assert declared_total(result)["value"] == pytest.approx(Crippen.MolMR(mol), abs=1e-9)
    assert sum(result.values.values()) != pytest.approx(Crippen.MolMR(mol), abs=1e-6)


def test_the_gasteiger_total_is_not_called_a_formal_charge(registry):
    """A SEMANTIC guard, and the one most worth having.

    PEOE conserves total charge, so with hydrogens included the sum does
    equal the formal charge exactly -- measured to 1e-6 on an anion, a
    cation, a zwitterion and a neutral molecule. But what was COMPUTED is
    a sum of calculated partial charges, and the coincidence is a fact
    about the method rather than the thing measured. Labelling it "formal
    charge" would smuggle an imprecise chemistry definition into metadata
    whose entire purpose is to stop the UI inventing meanings.
    """
    result = registry.compute("gasteiger_charge_at_ph", _mol(), "uuid", {"pH": 7.4})
    label = declared_total(result)["label"].lower()
    assert "formal" not in label, (
        f"the Gasteiger total is labelled {label!r}. It is a sum of calculated partial "
        f"charges that happens to equal the formal charge; say what was computed."
    )
    assert "charge" in label


@pytest.mark.parametrize(
    "smiles,formal",
    [("CC(=O)[O-]", -1), ("C[NH3+]", 1), ("[NH3+]CC(=O)[O-]", 0), ("CC(=O)Oc1ccccc1C(=O)O", 0)],
)
def test_the_gasteiger_identity_that_justifies_the_wording(smiles, formal):
    """The measurement the docstring above rests on, asserted rather than
    quoted -- so if a future RDKit stops conserving charge, the wording is
    re-examined instead of being trusted."""
    from openchem.chem.descriptor_providers import compute_gasteiger_charges

    mol = Chem.MolFromSmiles(smiles)
    assert sum(compute_gasteiger_charges(mol, include_hydrogens=True).values()) == pytest.approx(
        formal, abs=1e-6
    )


def test_the_distance_degree_total_is_the_wiener_index_not_the_raw_sum(registry):
    """Each atom's distance degree counts every path from it, so the raw
    sum counts each pair twice -- aspirin's 492 against a Wiener index of
    246. Declaring 492 would have been the "correct but unnamed" failure
    in a new place."""
    from openchem.chem.topology_analysis import wiener_index

    for smiles in ("CC(=O)Oc1ccccc1C(=O)O", "c1ccccc1", "CCCC"):
        mol = Chem.MolFromSmiles(smiles)
        result = registry.compute("topology_distance_degree", mol, "uuid", {})
        total = declared_total(result)
        assert total["value"] == pytest.approx(wiener_index(mol))
        assert total["value"] * 2 == pytest.approx(sum(result.values.values()))
        assert "wiener" in total["label"].lower()


def test_the_always_on_batch_declares_too(registry):
    """`compute_per_atom` is not registry-driven, so the audit above
    cannot see it -- and it feeds the same dialog."""
    datasets = RDKitDescriptorProvider().compute_per_atom(_mol(), "uuid")
    assert datasets
    for dataset in datasets:
        assert TOTAL in (dataset.provenance.parameters or {}), dataset.property_id
        assert valid_total_declaration((dataset.provenance.parameters or {})[TOTAL])


# --- the option itself ----------------------------------------------------


def test_every_hydrogen_mode_says_what_it_does():
    """A user seeing 0.8585 / 3.624 / 3.624 will reasonably ask why the
    first is not simply wrong. It is not -- they are three
    representations of one calculation -- and the descriptions are what
    say so."""
    for mode in HYDROGEN_MODES:
        assert HYDROGEN_MODE_DESCRIPTIONS[mode].strip()


def test_the_hydrogen_option_defaults_to_changing_nothing(registry):
    """A stored project must not change meaning under its owner."""
    definition = registry.get("crippen_logp_contrib")
    parameter = next(p for p in definition.parameters if p.name == "hydrogens")
    assert parameter.default == HEAVY_ATOMS_ONLY
    assert list(parameter.choices) == list(HYDROGEN_MODES)


# --- the exact case that was reported -------------------------------------


def test_the_reported_molecule_reproduces_the_screenshot(registry):
    """Every number in the bug report, from the structure it was reported
    on. Kept alongside the general guards rather than instead of them:
    those prove the class of bug is closed, this preserves its exact
    shape.
    """
    mol = Chem.MolFromSmiles(REPORTED_SMILES)
    result = registry.compute("crippen_logp_contrib", mol, "uuid", {})

    assert mol.GetNumAtoms() == 21
    assert len(result.values) == 21
    assert sum(result.values.values()) == pytest.approx(0.8585, abs=5e-5)  # the reported "Overall"
    assert min(result.values.values()) == pytest.approx(-1.019, abs=5e-4)
    assert max(result.values.values()) == pytest.approx(0.5437, abs=5e-5)
    # ...and the headline is now the number the panel was showing all along.
    assert declared_total(result)["value"] == pytest.approx(3.6239, abs=5e-5)


def test_the_dialog_and_the_panel_agree_on_the_reported_molecule(qapp):
    """The report in one sentence: two places showed different numbers
    for one molecule. They are read from the same declaration now, so
    they cannot disagree -- but "cannot" is worth a test."""
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.molecule import MoleculeModel
    from openchem.ui.panels.property_panel import _summarise

    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="reported")
    engine.set_structure_from_smiles(molecule, REPORTED_SMILES)
    mol = Chem.MolFromMolBlock(molecule.molblock)

    result = compute_crippen_logp_contrib_calculator(mol, "uuid", {})
    panel_row = _summarise(result)
    headline = f"{declared_total(result)['label']} {declared_total(result)['value']:.2f}"

    assert panel_row.startswith(headline)
    assert "3.62" in panel_row
