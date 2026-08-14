"""A result must say what it was computed WITH, not only what it was computed ON.

The routing layer has recorded which conformer a calculator was handed
since the calculation-input work; it never recorded the settings. Anything
replaying a calculation -- the 3D overlay recomputing for the conformer on
screen -- would otherwise have used today's defaults and produced a
different calculation under the original's name.

The load-bearing test here is the NON-DEFAULT one: everything else passes
just as happily against a recompute that ignores the record.
"""

from __future__ import annotations

import json

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.calculation_input import INPUT_PREFIX, recordable_parameters
from openchem.chem.steric import compute_steric_analysis
from openchem.domain.calculator import GEOMETRY
from openchem.domain.molecule import MoleculeModel
from openchem.services.descriptor_service import _with_geometry_provenance

PARAMETERS_KEY = f"{INPUT_PREFIX}parameters"


def _ligand() -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles("c1ccccc1P(c1ccccc1)c1ccccc1"))
    params = AllChem.ETKDGv3()
    params.randomSeed = 5
    AllChem.EmbedMolecule(mol, params)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def test_only_persistable_values_are_recorded():
    """`Provenance.to_dict` puts these straight into the saved project, so
    one unserialisable value breaks saving for the whole project rather
    than for the calculator that produced it."""
    kept = recordable_parameters(
        {
            "decimals": 4,
            "sphere_radius": 3.5,
            "label": "Normal",
            "enabled": True,
            "nothing": None,
            "window": [1.0, 2.0],
            "pair": (3, 4),
        }
    )
    assert kept == {
        "decimals": 4,
        "sphere_radius": 3.5,
        "label": "Normal",
        "enabled": True,
        "nothing": None,
        "window": [1.0, 2.0],
        "pair": [3, 4],
    }
    # And it really is persistable, which is the whole point.
    assert json.loads(json.dumps(kept)) == kept


def test_a_value_that_cannot_be_replayed_is_dropped_not_stringified():
    """A `repr()` is not a parameter: it cannot be fed back to `compute()`.
    Storing one would turn "I cannot replay this" into something that
    LOOKS replayable, which is worse than its absence -- a caller that
    finds a parameter missing must refuse to replay."""
    kept = recordable_parameters({"good": 1.0, "callback": len, "mol": Chem.Mol()})
    assert kept == {"good": 1.0}


def test_the_parameters_a_calculator_ran_with_reach_its_provenance():
    model = MoleculeModel()
    result = compute_steric_analysis(_ligand(), model.uuid, {"sphere_radius": 3.5})
    recorded = _with_geometry_provenance(result, model, GEOMETRY, {"sphere_radius": 3.5})
    assert recorded.provenance.parameters[PARAMETERS_KEY] == {"sphere_radius": 3.5}


def test_a_recorded_parameter_beats_the_current_default_on_replay():
    """THE TEST THIS FIELD EXISTS FOR.

    A replay must reproduce the calculation that ran, not the one today's
    settings would produce. Steric's `sphere_radius` is the discriminator
    because it genuinely moves the answer: recompute at the recorded
    value and the buried volume matches; recompute at a different one and
    it does not. Without the recorded parameters a replay silently takes
    the second path while looking identical.
    """
    mol = _ligand()
    model = MoleculeModel()
    used = 5.0  # deliberately NOT DEFAULT_SPHERE_RADIUS
    original = compute_steric_analysis(mol, model.uuid, {"sphere_radius": used})
    recorded = _with_geometry_provenance(original, model, GEOMETRY, {"sphere_radius": used})

    replayed = compute_steric_analysis(
        mol, model.uuid, recorded.provenance.parameters[PARAMETERS_KEY]
    )
    assert replayed.provenance.parameters["buried_volume_percent"] == pytest.approx(
        original.provenance.parameters["buried_volume_percent"]
    )

    # The control: the discriminator really does discriminate, or the
    # assertion above would hold for a replay that ignored the record.
    from openchem.chem.steric import DEFAULT_SPHERE_RADIUS

    assert used != DEFAULT_SPHERE_RADIUS
    at_default = compute_steric_analysis(mol, model.uuid, {"sphere_radius": DEFAULT_SPHERE_RADIUS})
    assert at_default.provenance.parameters["buried_volume_percent"] != pytest.approx(
        original.provenance.parameters["buried_volume_percent"]
    )


def test_a_calculators_own_keys_still_win_over_the_routing_layers():
    """Unchanged contract, re-asserted because a new key was added to the
    merge: the calculator knows what it computed, this layer only knows
    what it was computed on and asked for."""
    model = MoleculeModel()
    result = compute_steric_analysis(_ligand(), model.uuid, None)
    recorded = _with_geometry_provenance(result, model, GEOMETRY, {"sphere_radius": 9.0})
    # The calculator records its own sphere_radius_a; the routing layer's
    # copy lives under the prefix and does not overwrite it.
    assert recorded.provenance.parameters["sphere_radius_a"] != 9.0
    assert recorded.provenance.parameters[PARAMETERS_KEY]["sphere_radius"] == 9.0
