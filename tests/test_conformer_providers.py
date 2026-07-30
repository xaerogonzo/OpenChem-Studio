from __future__ import annotations

from openchem.chem.conformer_providers import RDKitConformerProvider
from openchem.chem.engine import ChemistryEngine


def test_generates_requested_number_of_distinct_conformers():
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCCCO")  # a flexible chain, several distinct conformers expected
    provider = RDKitConformerProvider()

    results = provider.generate_conformers(mol, num_conformers=5, optimize=False)

    assert len(results) == 5
    molblocks = {engine.mol_to_molblock(conf_mol) for conf_mol, _ in results}
    assert len(molblocks) > 1  # coordinates actually differ between conformers


def test_energy_present_only_when_optimizing():
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCO")
    provider = RDKitConformerProvider()

    unoptimized = provider.generate_conformers(mol, num_conformers=2, optimize=False)
    assert all(energy is None for _, energy in unoptimized)

    optimized = provider.generate_conformers(mol, num_conformers=2, optimize=True)
    assert all(energy is not None for _, energy in optimized)


def test_on_progress_called_once_per_conformer():
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCO")
    provider = RDKitConformerProvider()

    calls: list[tuple[int, int]] = []
    provider.generate_conformers(mol, num_conformers=3, optimize=False, on_progress=lambda d, t: calls.append((d, t)))

    assert calls == [(1, 3), (2, 3), (3, 3)]


def test_on_progress_returning_false_stops_early():
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCO")
    provider = RDKitConformerProvider()

    calls: list[tuple[int, int]] = []

    def on_progress(done: int, total: int) -> bool:
        calls.append((done, total))
        return done < 2  # stop right after the 2nd conformer

    results = provider.generate_conformers(mol, num_conformers=5, optimize=False, on_progress=on_progress)

    assert calls == [(1, 5), (2, 5)]
    assert len(results) == 2


def test_on_progress_returning_none_keeps_going():
    """The common case -- most callers' on_progress has no return
    statement at all (implicitly None) -- must not be mistaken for a
    cancellation request."""
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCO")
    provider = RDKitConformerProvider()

    def on_progress(done: int, total: int) -> None:
        pass  # no return statement -- implicitly None

    results = provider.generate_conformers(mol, num_conformers=3, optimize=False, on_progress=on_progress)

    assert len(results) == 3
