"""One way for a consumer to get partial charges, and everything needed to trust them.

Round 3, Track 2 (`benchmarks/charges/consumers/preregistration.md`). The
dipole and both electrostatic-potential views recomputed Gasteiger charges on
the conformer, with no way to use the EEM or QEq charges this application
also computes. This module is where a consumer asks for a model by its stable
key and gets back either charges or the model's own refusal -- never another
model's charges in their place.

CALCULATION SPACE: charges are keyed by the atoms of the molecule handed in,
hydrogens included, because every consumer here computes on that same
molecule. Placing values on DRAWN atoms is `atom_identity`'s job.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import rdkit
from rdkit import Chem
from rdkit.Chem import rdPartialCharges

from openchem.chem import charge_equilibration as ce
from openchem.chem import geometry_charges as gc
from openchem.domain.calculator import DRAWING, GEOMETRY

GASTEIGER = "gasteiger"
EEM = gc.EEM_BULTINCK2002_PART1
QEQ = gc.QEQ_RG1991_LAMBDA_HALF_H_EXPERIMENTAL
#: Stable codes, in the order a user is offered them. Gasteiger first and the default.
CHARGE_MODELS = (GASTEIGER, EEM, QEQ)
CHARGE_MODEL_LABELS = {
    GASTEIGER: "Gasteiger (PEOE)",
    EEM: gc.GEOMETRY_CHARGE_METHOD_LABELS[EEM],
    QEQ: gc.GEOMETRY_CHARGE_METHOD_LABELS[QEQ],
}
#: Each model's OWN input requirement. Gasteiger is topological; a consumer that
#: needs 3D coordinates for its physics says so itself, and never imposes it here.
INPUT_REQUIREMENT = {GASTEIGER: DRAWING, EEM: GEOMETRY, QEQ: GEOMETRY}
#: Where each parameter set comes from (docs/sources.toml keys).
SOURCE_KEYS = {GASTEIGER: "gasteiger1980", EEM: "bultinck2002a", QEQ: "rappe1991"}
CLAIM_KIND = "APPLICATION"


def _payload_checksum(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def parameter_payload(model_key: str) -> Any:
    """The parameters a model actually runs with, as data -- hashed so a silent
    edit to a shipped number changes the recorded checksum."""
    if model_key == EEM:
        return {e: list(v) for e, v in sorted(ce.EEM_BULTINCK2002_PART1.items())}
    if model_key == QEQ:
        return {"table_i": {e: list(v) for e, v in sorted(ce.QEQ_TABLE_I.items())},
                "hydrogen": list(ce.HYDROGEN_SETS["experimental"]), "readings": repr(ce.ADOPTED)}
    if model_key == GASTEIGER:
        return {"implementation": "rdkit.Chem.rdPartialCharges.ComputeGasteigerCharges", "rdkit": rdkit.__version__}
    raise ValueError(f"unknown charge model {model_key!r}")


@dataclass(frozen=True)
class ChargeEvaluation:
    """Charges from one model on one molecule, or that model's refusal.

    `charges` is None exactly when `refusal` is set. There is no field for
    "the charges another model gave instead", on purpose.
    """

    model_key: str
    charges: dict[int, float] | None
    input_requirement: str
    source_key: str
    parameter_checksum: str
    refusal: str = ""
    message: str = ""
    notes: tuple[str, ...] = ()
    claim_kind: str = CLAIM_KIND
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return CHARGE_MODEL_LABELS[self.model_key]


def _gasteiger(mol: Chem.Mol) -> dict[int, float]:
    """Exactly what `dipole.dipole_vector` computed before this module existed:
    RDKit's PEOE on this molecule, NaN (no parameters) as zero."""
    charged = Chem.Mol(mol)
    rdPartialCharges.ComputeGasteigerCharges(charged)
    out = {}
    for atom in charged.GetAtoms():
        value = atom.GetDoubleProp("_GasteigerCharge") if atom.HasProp("_GasteigerCharge") else 0.0
        out[atom.GetIdx()] = 0.0 if value != value else value
    return out


def evaluate_charges(mol: Chem.Mol, model_key: str, molecule_uuid: str = "") -> ChargeEvaluation:
    """`model_key`'s charges on `mol`, or its refusal. Never a substitute."""
    if model_key not in CHARGE_MODELS:
        raise ValueError(f"unknown charge model {model_key!r}; expected one of {CHARGE_MODELS}")
    common = dict(model_key=model_key, input_requirement=INPUT_REQUIREMENT[model_key], source_key=SOURCE_KEYS[model_key],
                  parameter_checksum=_payload_checksum(parameter_payload(model_key)))
    if model_key == GASTEIGER:
        return ChargeEvaluation(charges=_gasteiger(mol), **common)
    dataset = gc.compute_geometry_charges(mol, molecule_uuid, {"method": model_key})
    parameters = dict(getattr(dataset.provenance, "parameters", {}) or {})
    refusal = parameters.get("refusal", "")
    notes = tuple(n for n in (parameters.get("source_discrepancy"),) if n)
    if refusal or getattr(dataset, "inapplicable", False):
        return ChargeEvaluation(charges=None, refusal=refusal or "REFUSED", message=dataset.error or "", notes=notes,
                                provenance=parameters, **common)
    return ChargeEvaluation(charges=dict(dataset.values), notes=notes, provenance=parameters, **common)


#: What a computed (not refused) result from a charge consumer must record to be
#: reproducible and attributable. `input_source` is stamped by the dispatcher
#: (`descriptor_service._with_geometry_provenance`), the rest by the consumer.
REQUIRED_CONSUMER_PROVENANCE = ("charge_model", "charge_parameter_checksum", "charge_source", "claim_kind", "rdkit_version",
                                "input_source")


def provenance_problems(result) -> list[str]:
    """Which required fields a charge consumer's result lacks, [] when complete.

    Scoped to results THESE consumers create (round 3 Track 2); the
    application's other calculators are not held to it, and that is recorded
    in the pre-registration rather than implied. A refusal is complete when
    it names its model and its refusal code and carries no computed value.
    """
    parameters = dict(getattr(getattr(result, "provenance", None), "parameters", None) or {})
    if getattr(result, "inapplicable", False):
        problems = [key for key in ("charge_model", "refusal") if not parameters.get(key)]
        return problems + [f"refused result carries {key}" for key in ("debye", "vector") if key in parameters]
    return [key for key in REQUIRED_CONSUMER_PROVENANCE if parameters.get(key) in (None, "")]
