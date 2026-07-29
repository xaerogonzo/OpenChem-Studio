from __future__ import annotations

from openchem.chem.engine import ChemistryEngine


class MeasurementService:
    """Thin synchronous wrapper over ChemistryEngine's geometry measurements.

    Fast enough (vector math on an already-parsed conformer) that it doesn't
    need the QThreadPool treatment DescriptorService/ConformerService use.
    """

    def __init__(self, engine: ChemistryEngine) -> None:
        self._engine = engine

    def bond_length(self, molblock: str, atom_idx_1: int, atom_idx_2: int) -> float:
        return self._engine.bond_length(molblock, atom_idx_1, atom_idx_2)

    def bond_angle(self, molblock: str, atom_idx_1: int, atom_idx_2: int, atom_idx_3: int) -> float:
        return self._engine.bond_angle(molblock, atom_idx_1, atom_idx_2, atom_idx_3)

    def dihedral_angle(
        self, molblock: str, atom_idx_1: int, atom_idx_2: int, atom_idx_3: int, atom_idx_4: int
    ) -> float:
        return self._engine.dihedral_angle(molblock, atom_idx_1, atom_idx_2, atom_idx_3, atom_idx_4)
