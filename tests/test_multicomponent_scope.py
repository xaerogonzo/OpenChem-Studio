"""Every calculator declares which components it is handed, and keeps to it.

Round 5, branch S2. The S1 sweep (tests/fixtures/multicomponent_matrix_s1.json)
ran all 59 registry calculators and the always-on set over a panel fixed in
advance, and found no calculator had ever been asked which components of a
salt it described: a counter-ion failed metformin's Lipinski check, sodium
gave acetate a logP of -4.24, distance indices printed RDKit's unreachable
sentinel (Wiener index 400000009), and protonation dropped every inorganic
ion and then refused the result. `domain.calculator.CalculatorScope` is the
declaration and `chem.components` applies it.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem import components
from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
from openchem.domain.calculator import (
    MULTICOMPONENT_UNSUPPORTED,
    Aggregation,
    CalculationRefusal,
    CalculatorScope,
    ComponentSelection,
    RegistryExecution,
)
from openchem.domain.scientific_result import PerAtomDataset
from tests.multicomponent_sweep import classify, load_panel, run_sweep

REGISTRY_DEFINITIONS = [d for d in CALCULATOR_DEFINITIONS if isinstance(d.execution, RegistryExecution)]

#: A FAILED result the panel may carry without it being a finding. **EMPTY NOW**:
#: the two that were listed here -- an experimental database this machine has
#: not built, and a 3D descriptor asked of the drawing before the conformer run
#: answered it -- are classified refusals (NEEDS_SETUP and NEEDS_INPUT in
#: `domain.refusal_kinds`), which the sweep counts as their own outcomes. Kept as
#: a name so the guard below still reads "a failure with an expected code", and
#: so the next entry has to argue for itself.
EXPECTED_FAULTS: set[str] = set()


def _unscoped(definitions) -> list[str]:
    """The guard: registry calculators with no declared scope."""
    return [
        d.calculator_id for d in definitions
        if isinstance(d.execution, RegistryExecution) and not isinstance(d.scope, CalculatorScope)
    ]


def test_every_registry_calculator_declares_a_scope():
    """A missing scope is not a scope; an explicit WHOLE_STRUCTURE is."""
    assert not _unscoped(CALCULATOR_DEFINITIONS)
    assert len(REGISTRY_DEFINITIONS) == 59


def test_the_guard_names_a_calculator_whose_scope_was_stripped():
    """Broken on purpose, and through the guard itself rather than a copy of
    it: one declaration removed must come back by name."""
    import dataclasses

    victim = REGISTRY_DEFINITIONS[17]
    stripped = [dataclasses.replace(d, scope=None) if d is victim else d for d in CALCULATOR_DEFINITIONS]
    assert _unscoped(stripped) == [victim.calculator_id]


def test_a_parent_scoped_per_atom_result_lands_on_the_drawings_atoms():
    """The counter-ion drawn FIRST shifts every parent index by one."""
    scope = CalculatorScope(ComponentSelection.CHEMBL_PARENT, Aggregation.PER_ATOM)
    drawing = Chem.MolFromSmiles("Cl.CN(C)C(=N)N=C(N)N")
    selection = components.select(drawing, scope, "test")
    assert selection.drawing_atoms == tuple(range(1, 10)) and selection.components == (1,)
    parent_values = PerAtomDataset(
        property_id="p", name="p", units="", method="m", molecule_uuid="u",
        values={i: float(i) for i in range(selection.mol.GetNumAtoms())},
    )
    read = components.read_back(parent_values, scope, selection)
    assert read.values == {i + 1: float(i) for i in range(9)}
    assert all(
        drawing.GetAtomWithIdx(components.drawing_index(a)).GetSymbol() == a.GetSymbol()
        for a in selection.mol.GetAtoms()
    )


def test_a_hydrogen_the_calculator_added_fails_rather_than_landing_on_a_wrong_atom():
    scope = CalculatorScope(ComponentSelection.CHEMBL_PARENT, Aggregation.PER_ATOM)
    selection = components.select(Chem.MolFromSmiles("Cl.CN"), scope, "test")
    result = PerAtomDataset(property_id="p", name="p", units="", method="m", molecule_uuid="u",
                            values={0: 1.0, 1: 2.0, 2: 0.1})
    with pytest.raises(ValueError, match="beyond its parent"):
        components.read_back(result, scope, selection)


@pytest.mark.parametrize(
    "smiles,code",
    [
        ("CC(=O)[O-].[Na+]", MULTICOMPONENT_UNSUPPORTED),        # every component a listed salt
        ("C[N+](C)(C)CCO.OC1=CC=CC=C1C([O-])=O", MULTICOMPONENT_UNSUPPORTED),  # none listed
        ("[cH-]1cccc1.[cH-]1cccc1.[Fe+2]", "METAL_CONTAINING_UNSUPPORTED"),
    ],
)
def test_no_single_parent_is_a_coded_refusal(smiles, code):
    scope = CalculatorScope(ComponentSelection.CHEMBL_PARENT, Aggregation.SCALAR)
    with pytest.raises(CalculationRefusal) as refused:
        components.select(Chem.MolFromSmiles(smiles), scope, "test")
    assert refused.value.code == code and refused.value.inapplicable


def test_a_single_charged_component_is_not_neutralised():
    """Bento et al. apply GetParent only to multicomponent input; the
    vendored function would turn a drawn zwitterion into neutral glycine."""
    scope = CalculatorScope(ComponentSelection.CHEMBL_PARENT, Aggregation.SCALAR)
    selection = components.select(Chem.MolFromSmiles("[NH3+]CC([O-])=O"), scope, "test")
    assert Chem.MolToSmiles(selection.mol) == "[NH3+]CC(=O)[O-]" and selection.drawing_atoms is None


# --- the panel, through the service -------------------------------------------

#: A subset of the S0 panel that covers every shape, kept small because it
#: runs every calculator through the real service (about 3 s a row).
GUARD_ROWS = (
    "sodium_acetate", "acetic_acid", "metformin_hcl", "metformin", "choline_salicylate",
    "metformin_pamoate", "sertraline_hcl", "sertraline", "glycine_zwitterion",
    "caffeine_hydrate", "sodium_chloride", "ionic_ferrocene",
    # One component WITH a metal: the only shape that reaches a calculator's
    # own element refusal (Jensen, MMFF/UFF, Lange's radii) rather than the
    # parent rule's.
    "bonded_ferrocene",
)


@pytest.fixture(scope="module")
def guard_sweep(qapp, tmp_path_factory):
    """With NO experimental NMR database, whatever this machine has built.

    The sidecars are already unconfigured here -- the suite's settings are
    isolated -- but the database lives at a data path, so a developer who had
    built it saw a different panel from CI. This guard went green locally and
    red on CI for exactly that reason (PR #133).
    """
    from openchem.chem import nmr_database

    rows = [r for r in load_panel() if r.id in GUARD_ROWS]
    missing = tmp_path_factory.mktemp("no-nmr-db") / "absent.sqlite"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(nmr_database, "default_database_path", lambda: missing)
        sweep = run_sweep(qapp, rows)
    return sweep, classify(sweep, rows)


def test_the_panel_has_no_suspect_and_no_uncoded_refusal(guard_sweep):
    sweep, classified = guard_sweep
    assert not sweep["timeouts"]
    problems = [
        (c["row"], c["producer"], c["result_id"], c["outcome"], c.get("refusal"), (c.get("error") or "")[:80])
        for c in classified
        if c["outcome"] in ("suspect", "missing")
        or (c["outcome"] == "inapplicable" and not c.get("refusal"))
        or (c["outcome"] == "failed" and c.get("refusal") not in EXPECTED_FAULTS)
    ]
    assert not problems


def test_the_panels_parent_values_are_the_parents(guard_sweep):
    sweep, _ = guard_sweep
    cells = {
        (c["row"], c["result_id"]): c for c in sweep["cells"]
        if c["producer"] == "rdkit" and c.get("input") == "drawing"
    }

    def value(row, descriptor):
        return cells[(row, f"descriptor:rdkit:{descriptor}")]["gist"]

    # A counter-ion LARGER than the drug no longer fails it (it did: C23 pamoate).
    assert value("metformin_pamoate", "lipinski_pass") == "value=True"
    assert value("metformin_hcl", "mol_logp") == value("metformin", "mol_logp")
    # Stereo survives component extraction; the weight is still the salt's.
    assert value("sertraline_hcl", "num_stereocenters") == value("sertraline", "num_stereocenters") == "value=2"
    assert value("sertraline_hcl", "mol_wt") != value("sertraline", "mol_wt")


def test_no_graph_distance_prints_the_unreachable_sentinel(guard_sweep):
    sweep, _ = guard_sweep
    for c in sweep["cells"]:
        if c["producer"] in ("topology_eccentricity", "topology_distance_degree") and c["state"] == "completed":
            assert "e+0" not in c["gist"] and "100000000" not in c["gist"], c["row"]
