from __future__ import annotations

import sys
import time
from importlib import import_module
from types import ModuleType

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Descriptors3D, Lipinski, QED, rdMolDescriptors, rdPartialCharges
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

from openchem.domain.common import CacheState, Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.scientific_result import AlertResult, PerAtomDataset
from openchem.plugins.interfaces import DescriptorProvider

# RDKitDescriptorProvider implements the same DescriptorProvider ABC a future
# plugin would (openchem.plugins.interfaces.DescriptorProvider) — DescriptorService
# can't tell a built-in provider from a plugin-supplied one.


# (descriptor_id, display name, units, category) — the original Phase 1 set.
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
    # Phase 10a additions below — all zero-new-dependency RDKit calls.
    ("molar_refractivity", "Molar Refractivity", "", "physicochemical"),
    ("labute_asa", "Approx. Surface Area (Labute)", "Å²", "physicochemical"),
    ("qed", "QED (Drug-likeness)", "", "medicinal_chemistry"),
    ("sa_score", "Synthetic Accessibility", "", "medicinal_chemistry"),
    ("lipinski_pass", "Lipinski Ro5 (≤1 violation)", "", "medicinal_chemistry"),
    ("veber_pass", "Veber Rule", "", "medicinal_chemistry"),
    ("ghose_pass", "Ghose Filter", "", "medicinal_chemistry"),
    ("egan_pass", "Egan Filter", "", "medicinal_chemistry"),
]

# Shape descriptors need a REAL 3D conformer, not just "a conformer block" --
# a molblock built from the 2D editor always parses into exactly one
# conformer (all-zero/flat z-coordinates), so `mol.GetNumConformers() > 0`
# is always true and useless as a check here. `Conformer.Is3D()` is what
# actually distinguishes them -- confirmed live that RDKit sets it correctly
# based on real (non-zero, non-degenerate) z-coordinates, and that this
# survives a full molblock round-trip (write then re-parse), which is
# exactly what `ChemistryEngine.mol_from_model` does before handing `mol` to
# this provider. No `DescriptorProvider`/`DescriptorService` signature
# change needed -- this is entirely a `compute()`-local check.
_SHAPE_DESCRIPTOR_SPECS: list[tuple[str, str, str]] = [
    ("radius_of_gyration", "Radius of Gyration", "Å"),
    ("asphericity", "Asphericity", ""),
    ("spherocity_index", "Spherocity Index", ""),
    ("inertial_shape_factor", "Inertial Shape Factor", ""),
    ("pmi1", "Principal Moment of Inertia 1", ""),
    ("pmi2", "Principal Moment of Inertia 2", ""),
    ("pmi3", "Principal Moment of Inertia 3", ""),
    ("npr1", "Normalized PMI Ratio 1", ""),
    ("npr2", "Normalized PMI Ratio 2", ""),
    ("pbf", "Plane of Best Fit", "Å"),
]

_NEEDS_CONFORMER_ERROR = "Needs a real 3D conformer — generate one first (3D Viewer tab)."

_sascorer_module: ModuleType | None = None


def _load_sascorer() -> ModuleType:
    """Dynamically imports RDKit's own bundled synthetic-accessibility
    scorer (`Contrib/SA_Score/sascorer.py`) via `RDConfig.RDContribDir` --
    confirmed live this resolves correctly for the installed RDKit wheel.
    Deliberately NOT vendored/copied into this repo: `Contrib/` isn't a
    normally-importable package, but it ships inside the installed `rdkit`
    distribution itself, so this only ever reuses RDKit's own code, never
    forks it. Cached at module level since the import (and its own
    fragment-score data file load) only needs to happen once per process.
    """
    global _sascorer_module
    if _sascorer_module is not None:
        return _sascorer_module
    from rdkit import RDConfig

    contrib_dir = f"{RDConfig.RDContribDir}/SA_Score"
    if contrib_dir not in sys.path:
        sys.path.append(contrib_dir)
    _sascorer_module = import_module("sascorer")
    return _sascorer_module


_pains_catalog: FilterCatalog | None = None


def _load_pains_catalog() -> FilterCatalog:
    """Cached at module level -- building the catalog (480 entries,
    confirmed live) isn't free and its contents never change at runtime."""
    global _pains_catalog
    if _pains_catalog is None:
        params = FilterCatalogParams()
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
        _pains_catalog = FilterCatalog(params)
    return _pains_catalog


class RDKitDescriptorProvider(DescriptorProvider):
    """Computes the built-in descriptor set using RDKit only."""

    provider_id = "rdkit"

    def descriptor_ids(self) -> list[str]:
        return [spec[0] for spec in _DESCRIPTOR_SPECS] + [spec[0] for spec in _SHAPE_DESCRIPTOR_SPECS]

    def compute(self, mol: Chem.Mol, molecule_uuid: str) -> list[DescriptorValue]:
        now = time.time()
        provenance = Provenance(created_by="core", method=self.provider_id, timestamp=now)
        chiral_centers = Chem.FindMolChiralCenters(
            mol, includeUnassigned=True, useLegacyImplementation=False
        )
        mol_wt = Descriptors.MolWt(mol)
        mol_logp = Crippen.MolLogP(mol)
        num_hbd = Lipinski.NumHDonors(mol)
        num_hba = Lipinski.NumHAcceptors(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        num_rotatable_bonds = Lipinski.NumRotatableBonds(mol)
        molar_refractivity = Crippen.MolMR(mol)
        heavy_atom_count = mol.GetNumHeavyAtoms()

        # Standard threshold formulations (Lipinski 1997, Veber 2002, Ghose
        # 1999, Egan 2000) -- heavy-atom count is used for Ghose's "20-70
        # atoms" bound rather than a total-atom (incl. H) count, since a
        # molblock isn't guaranteed to carry explicit hydrogens; a documented
        # approximation, not the literal original criterion.
        lipinski_violations = sum(
            [mol_wt > 500, mol_logp > 5, num_hbd > 5, num_hba > 10]
        )
        veber_pass = num_rotatable_bonds <= 10 and tpsa <= 140
        ghose_pass = (
            160 <= mol_wt <= 480
            and -0.4 <= mol_logp <= 5.6
            and 40 <= molar_refractivity <= 130
            and 20 <= heavy_atom_count <= 70
        )
        egan_pass = -1 <= mol_logp <= 5.88 and tpsa <= 131.6

        raw_values = {
            "mol_wt": mol_wt,
            "exact_mass": Descriptors.ExactMolWt(mol),
            "formula": rdMolDescriptors.CalcMolFormula(mol),
            "mol_logp": mol_logp,
            "tpsa": tpsa,
            "num_rotatable_bonds": num_rotatable_bonds,
            "num_hbd": num_hbd,
            "num_hba": num_hba,
            "formal_charge": Chem.GetFormalCharge(mol),
            "ring_count": rdMolDescriptors.CalcNumRings(mol),
            "heavy_atom_count": heavy_atom_count,
            "num_stereocenters": len(chiral_centers),
            "molar_refractivity": molar_refractivity,
            "labute_asa": rdMolDescriptors.CalcLabuteASA(mol),
            "qed": QED.qed(mol),
            "sa_score": _load_sascorer().calculateScore(mol),
            "lipinski_pass": lipinski_violations <= 1,
            "veber_pass": veber_pass,
            "ghose_pass": ghose_pass,
            "egan_pass": egan_pass,
        }
        values = [
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
        values.extend(self._compute_shape_descriptors(mol, molecule_uuid, now, provenance))
        return values

    def _compute_shape_descriptors(
        self, mol: Chem.Mol, molecule_uuid: str, now: float, provenance: Provenance
    ) -> list[DescriptorValue]:
        has_real_conformer = mol.GetNumConformers() > 0 and mol.GetConformer().Is3D()
        if not has_real_conformer:
            return [
                DescriptorValue(
                    descriptor_id=descriptor_id,
                    name=name,
                    units=units,
                    category="shape",
                    provider=self.provider_id,
                    molecule_uuid=molecule_uuid,
                    timestamp=now,
                    cache_state=CacheState.FAILED,
                    error=_NEEDS_CONFORMER_ERROR,
                    provenance=provenance,
                )
                for descriptor_id, name, units in _SHAPE_DESCRIPTOR_SPECS
            ]

        shape_raw_values = {
            "radius_of_gyration": Descriptors3D.RadiusOfGyration(mol),
            "asphericity": Descriptors3D.Asphericity(mol),
            "spherocity_index": Descriptors3D.SpherocityIndex(mol),
            "inertial_shape_factor": Descriptors3D.InertialShapeFactor(mol),
            "pmi1": Descriptors3D.PMI1(mol),
            "pmi2": Descriptors3D.PMI2(mol),
            "pmi3": Descriptors3D.PMI3(mol),
            "npr1": Descriptors3D.NPR1(mol),
            "npr2": Descriptors3D.NPR2(mol),
            "pbf": Descriptors3D.PBF(mol),
        }
        return [
            DescriptorValue(
                descriptor_id=descriptor_id,
                name=name,
                units=units,
                category="shape",
                provider=self.provider_id,
                molecule_uuid=molecule_uuid,
                value=shape_raw_values[descriptor_id],
                timestamp=now,
                cache_state=CacheState.COMPLETED,
                provenance=provenance,
            )
            for descriptor_id, name, units in _SHAPE_DESCRIPTOR_SPECS
        ]

    def compute_alerts(self, mol: Chem.Mol, molecule_uuid: str) -> list[AlertResult]:
        catalog = _load_pains_catalog()
        matched = [entry.GetDescription() for entry in catalog.GetMatches(mol)]
        return [
            AlertResult(
                alert_id="pains",
                name="PAINS",
                molecule_uuid=molecule_uuid,
                matched=matched,
                provenance=Provenance(created_by="core", method=self.provider_id),
            )
        ]

    def compute_per_atom(self, mol: Chem.Mol, molecule_uuid: str) -> list[PerAtomDataset]:
        provenance = Provenance(created_by="core", method=self.provider_id)

        contribs = rdMolDescriptors._CalcCrippenContribs(mol)
        logp_contrib = {idx: logp for idx, (logp, _mr) in enumerate(contribs)}
        mr_contrib = {idx: mr for idx, (_logp, mr) in enumerate(contribs)}

        # Mutates `mol` in place (sets a "_GasteigerCharge" property per
        # atom) -- harmless here: nothing else reading `mol` in this
        # provider's other methods depends on that property's absence.
        rdPartialCharges.ComputeGasteigerCharges(mol)
        gasteiger_charge = {
            atom.GetIdx(): atom.GetDoubleProp("_GasteigerCharge") for atom in mol.GetAtoms()
        }

        return [
            PerAtomDataset(
                property_id="crippen_logp_contrib",
                name="LogP Contribution (Crippen)",
                units="",
                method=self.provider_id,
                molecule_uuid=molecule_uuid,
                values=logp_contrib,
                provenance=provenance,
            ),
            PerAtomDataset(
                property_id="crippen_mr_contrib",
                name="Molar Refractivity Contribution (Crippen)",
                units="",
                method=self.provider_id,
                molecule_uuid=molecule_uuid,
                values=mr_contrib,
                provenance=provenance,
            ),
            PerAtomDataset(
                property_id="gasteiger_charge",
                name="Partial Charge (Gasteiger)",
                units="e",
                method=self.provider_id,
                molecule_uuid=molecule_uuid,
                values=gasteiger_charge,
                provenance=provenance,
            ),
        ]
