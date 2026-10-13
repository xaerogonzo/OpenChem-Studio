"""Builders for the Lewis pairing's tests that need stored runs: real `QuantumChemistryRun`s, real molecules.

Not a test module (no `test_` prefix, so it is neither collected nor sharded). It carries the documented
B3LYP/def2-SVP numbers (`tests/test_lewis_adduct.py`, `docs/RECIPES_DESIGN.md` section 10) so a test that wants "the
pair that exists for this" does not retype them.
"""

from __future__ import annotations

from rdkit import Chem

from openchem.chem.lewis_pairing_eval import PairMember
from openchem.chem.recipe_host import constitution_key
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.lewis_binder import MoleculeFacts
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus

METHOD = "B3LYP def2-SVP"
GEOMETRY_FP, DRAWING_FP = "g" * 64, "d" * 64

#: The documented numbers. The unused orbital of each is a sentinel nothing may read.
CO = dict(homo=-10.17, lumo=99.0, hardness=8.40)
BH3 = dict(homo=-99.0, lumo=-2.04, hardness=6.77)


def descriptor(molecule: str, descriptor_id: str, value) -> DescriptorValue:
    return DescriptorValue(
        descriptor_id=descriptor_id, name=descriptor_id, units="eV", category="quantum_chemistry", provider="orca",
        molecule_uuid=molecule, value=value, cache_state=CacheState.COMPLETED,
    )


def stored_run(molecule: str, run_id: str, calc: str, values: dict, **kw) -> QuantumChemistryRun:
    base = dict(
        run_id=run_id, molecule_uuid=molecule, calc_type=calc, method_basis=METHOD, charge=0, multiplicity=1,
        calculation_input="geometry", input_fingerprint=GEOMETRY_FP, input_molblock="molblock",
        started_at=1.0, completed_at=2.0, status=RunStatus.COMPLETED,
    )
    base.update(kw)
    run = QuantumChemistryRun(**base)
    run.results["descriptors"] = [descriptor(molecule, k, v) for k, v in values.items()]
    return run


def runs_of(molecule: str, numbers: dict, *, hardness: bool = True, **kw) -> list[QuantumChemistryRun]:
    runs = [stored_run(molecule, f"{molecule}-sp", "sp", {
        "orca.homo_energy": numbers["homo"], "orca.lumo_energy": numbers["lumo"]}, **kw)]
    if hardness:
        runs.append(stored_run(molecule, f"{molecule}-dscf", "delta_scf", {"orca.dscf_hardness": numbers["hardness"]}, **kw))
    return runs


def member(smiles: str, uuid: str, label: str, runs, *, charge: int = 0, describes=None) -> PairMember:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return PairMember(
        facts=MoleculeFacts(
            molecule_uuid=uuid, label=label, runs=tuple(runs),
            fingerprints={"geometry": GEOMETRY_FP, "drawing": DRAWING_FP},
            describes={r.run_id: True for r in runs} if describes is None else describes, formal_charge=charge,
        ),
        mol=mol,
        constitution_key=constitution_key(mol),
    )


def borane(**kw) -> PairMember:
    return member("B", "bh3", "BH3", runs_of("bh3", BH3, **kw))


def carbon_monoxide(**kw) -> PairMember:
    return member("[C-]#[O+]", "co", "CO", runs_of("co", CO, **kw))
