from __future__ import annotations

import time

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors

from openchem.domain.common import CacheState, Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.plugins.interfaces import DescriptorProvider

# RDKitDescriptorProvider implements the same DescriptorProvider ABC a future
# plugin would (openchem.plugins.interfaces.DescriptorProvider) — DescriptorService
# can't tell a built-in provider from a plugin-supplied one.


# (descriptor_id, display name, units, category) — the outline's Phase 1 descriptor set.
_DESCRIPTOR_SPECS: list[tuple[str, str, str, str]] = [
    ("mol_wt", "Molecular Weight", "g/mol", "physicochemical"),
    ("exact_mass", "Exact Mass", "g/mol", "physicochemical"),
    ("formula", "Molecular Formula", "", "identity"),
    ("mol_logp", "LogP", "", "physicochemical"),
    ("tpsa", "TPSA", "Å²", "physicochemical"),
    ("num_rotatable_bonds", "Rotatable Bonds", "", "topology"),
    ("num_hbd", "H-Bond Donors", "", "topology"),
    ("num_hba", "H-Bond Acceptors", "", "topology"),
    ("formal_charge", "Formal Charge", "", "identity"),
    ("ring_count", "Ring Count", "", "topology"),
    ("heavy_atom_count", "Heavy Atom Count", "", "topology"),
    ("num_stereocenters", "Stereocenters", "", "stereochemistry"),
]


class RDKitDescriptorProvider(DescriptorProvider):
    """Computes the Phase 1/2 descriptor set using RDKit."""

    provider_id = "rdkit"

    def descriptor_ids(self) -> list[str]:
        return [spec[0] for spec in _DESCRIPTOR_SPECS]

    def compute(self, mol: Chem.Mol, molecule_uuid: str) -> list[DescriptorValue]:
        now = time.time()
        provenance = Provenance(created_by="core", method=self.provider_id, timestamp=now)
        chiral_centers = Chem.FindMolChiralCenters(
            mol, includeUnassigned=True, useLegacyImplementation=False
        )
        raw_values = {
            "mol_wt": Descriptors.MolWt(mol),
            "exact_mass": Descriptors.ExactMolWt(mol),
            "formula": rdMolDescriptors.CalcMolFormula(mol),
            "mol_logp": Crippen.MolLogP(mol),
            "tpsa": rdMolDescriptors.CalcTPSA(mol),
            "num_rotatable_bonds": Lipinski.NumRotatableBonds(mol),
            "num_hbd": Lipinski.NumHDonors(mol),
            "num_hba": Lipinski.NumHAcceptors(mol),
            "formal_charge": Chem.GetFormalCharge(mol),
            "ring_count": rdMolDescriptors.CalcNumRings(mol),
            "heavy_atom_count": mol.GetNumHeavyAtoms(),
            "num_stereocenters": len(chiral_centers),
        }
        return [
            DescriptorValue(
                descriptor_id=descriptor_id,
                name=name,
                units=units,
                category=category,
                provider=self.provider_id,
                molecule_uuid=molecule_uuid,
                value=raw_values[descriptor_id],
                timestamp=now,
                cache_state=CacheState.COMPLETED,
                provenance=provenance,
            )
            for descriptor_id, name, units, category in _DESCRIPTOR_SPECS
        ]
