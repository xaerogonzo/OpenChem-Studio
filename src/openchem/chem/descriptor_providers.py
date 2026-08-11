from __future__ import annotations

import sys
import time
from importlib import import_module
from types import ModuleType
from typing import Any

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Descriptors3D, Fragments, Lipinski, QED, rdMolDescriptors, rdPartialCharges
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

from openchem.chem.elemental_analysis import compute_elemental_analysis
from openchem.chem.geometry_analysis import compute_geometry_analysis
from openchem.chem.interaction_analysis import compute_interaction_analysis
from openchem.chem.markush import DEFAULT_MAX_STRUCTURES as MARKUSH_DEFAULT_MAX
from openchem.chem.calculator_options import (
    decimal_places_parameter,
    decimals,
    fmt,
    microspecies_parameters,
    ph_range_parameters,
)
from openchem.chem.bbb_stereo import compute_bbb_descriptors, compute_stereo_descriptors
from openchem.chem.nmr_database import compute_database_nmr
from openchem.chem.steric import compute_steric_analysis
from openchem.chem.alignment import (
    ACCURACY_LEVELS,
    ALIGNMENT_METHODS,
    DEFAULT_ACCURACY,
    compute_3d_alignment,
)
from openchem.chem.dipole import compute_dipole_moment
from openchem.chem.electronic_properties import (
    compute_atomic_polarizability,
    compute_orbital_electronegativity,
    compute_polarizability,
)
from openchem.chem.huckel import compute_huckel_analysis, compute_pi_electron_density
from openchem.chem.lewis import compute_lewis_sites
from openchem.chem.lewis_adduct import ROLE_ACID, ROLE_BASE, compute_lewis_adduct
from openchem.chem.markush import compute_markush_enumeration
from openchem.chem.molecular_dynamics import DEFAULT_FRAME_INTERVAL as MD_DEFAULT_FRAME_INTERVAL
from openchem.chem.molecular_dynamics import DEFAULT_STEP_FS as MD_DEFAULT_STEP_FS
from openchem.chem.molecular_dynamics import DEFAULT_STEPS as MD_DEFAULT_STEPS
from openchem.chem.molecular_dynamics import DEFAULT_TEMPERATURE_K as MD_DEFAULT_TEMPERATURE
from openchem.chem.molecular_dynamics import compute_molecular_dynamics
from openchem.chem.mpo_scores import compute_cns_mpo, compute_structural_frameworks
from openchem.chem.naming_providers import compute_iupac_name
from openchem.chem.ph_curves import (
    compute_hbond_vs_ph,
    compute_isoelectric_point,
    compute_logd_curve,
    compute_major_microspecies,
    compute_pka_distribution,
)
from openchem.chem.structure_generators import (
    DEFAULT_MAX_STRUCTURES,
    RESONANCE_FLAG_SETS,
    compute_resonance_forms,
    compute_stereoisomers,
    compute_tautomers,
)
from openchem.chem.regulatory.calculator import (
    JURISDICTION_CHOICES,
    compute_regulatory_screen,
)
from openchem.chem.oxidation_states import compute_oxidation_states
from openchem.chem.structure_annotation import (
    FG_LABEL_MODES,
    RING_LABEL_MODES,
    compute_functional_groups,
    compute_locants,
    compute_ring_systems,
    compute_stereocenters,
)
from openchem.chem.substructure import COMMON_PATTERNS, compute_substructure_search
from openchem.chem.surface_analysis import compute_sasa_dataset, compute_surface_analysis
from openchem.chem.substance import compute_substance_analysis
from openchem.chem.topology_analysis import (
    compute_distance_degree_dataset,
    compute_eccentricity_dataset,
    compute_topology_analysis,
)
from openchem.domain.calculator import (
    GEOMETRY,
    CalculatorDefinition,
    CalculatorParameter,
    RegistryExecution,
)
from openchem.domain.common import CacheState, Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.scientific_result import AlertResult, PerAtomDataset
from openchem.domain.structure_issue import Severity
from openchem.plugins.interfaces import DescriptorProvider

# RDKitDescriptorProvider implements the same DescriptorProvider ABC a future
# plugin would (openchem.plugins.interfaces.DescriptorProvider) — DescriptorService
# can't tell a built-in provider from a plugin-supplied one.


# (descriptor_id, display name, units, category) — the original Phase 1 set.
# Phase 18 moved formal_charge/mol_logp/molar_refractivity into their own
# charge/logp/molar_refractivity categories (previously identity/
# physicochemical/physicochemical) so each lines up with the matching
# CalculatorRegistry category's "Open [Calculator]..." row in the Property
# Panel.
_DESCRIPTOR_SPECS: list[tuple[str, str, str, str]] = [
    ("mol_wt", "Molecular Weight", "g/mol", "physicochemical"),
    ("exact_mass", "Exact Mass", "g/mol", "physicochemical"),
    ("formula", "Molecular Formula", "", "identity"),
    ("mol_logp", "LogP", "", "lipophilicity"),
    ("tpsa", "TPSA", "Å²", "physicochemical"),
    ("num_rotatable_bonds", "Rotatable Bonds", "", "topology"),
    ("num_hbd", "H-Bond Donors", "", "topology"),
    ("num_hba", "H-Bond Acceptors", "", "topology"),
    ("formal_charge", "Formal Charge", "", "charge"),
    ("ring_count", "Ring Count", "", "topology"),
    ("heavy_atom_count", "Heavy Atom Count", "", "topology"),
    ("num_stereocenters", "Stereocenters", "", "stereochemistry"),
    # Phase 10a additions below — all zero-new-dependency RDKit calls.
    ("molar_refractivity", "Molar Refractivity", "", "electronic"),
    ("labute_asa", "Approx. Surface Area (Labute)", "Å²", "physicochemical"),
    ("qed", "QED (Drug-likeness)", "", "medicinal_chemistry"),
    ("sa_score", "Synthetic Accessibility", "", "medicinal_chemistry"),
    ("lipinski_pass", "Lipinski Ro5 (≤1 violation)", "", "medicinal_chemistry"),
    ("veber_pass", "Veber Rule", "", "medicinal_chemistry"),
    ("ghose_pass", "Ghose Filter", "", "medicinal_chemistry"),
    ("egan_pass", "Egan Filter", "", "medicinal_chemistry"),
    # Phase 19 additions below — ADMET heuristics. esol_logs is a real,
    # verified literature formula (zero new dependencies); bbb_permeant/
    # bioavailability_likely are documented approximations of published
    # heuristics, same "not the literal original criterion" convention as
    # Ghose/Veber/Egan above (see their comment) -- NOT reproductions of
    # Clark's actual BBB regression or Martin's actual categorical
    # bioavailability score.
    ("esol_logs", "Aqueous Solubility (ESOL, log mol/L)", "", "admet"),
    ("bbb_permeant", "Blood-Brain Barrier Permeant (heuristic)", "", "admet"),
    ("bioavailability_likely", "Oral Bioavailability Likely (heuristic)", "", "admet"),
    # Phase 20 additions below — real, cited threshold rules (Hughes et al.
    # 2008 Pfizer 245-compound analysis; Gleeson ~30,000-compound GSK
    # analysis; Congreve et al. 2003 Drug Discovery Today 8(19):876-877),
    # same "documented approximation of a real rule" convention as the
    # medicinal-chemistry filters above.
    ("pfizer_375_pass", "Pfizer 3/75 Rule", "", "medicinal_chemistry"),
    ("gsk_400_pass", "GSK 4/400 Rule", "", "medicinal_chemistry"),
    ("rule_of_three_pass", "Rule of Three (Fragment-likeness)", "", "medicinal_chemistry"),
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

_NEEDS_CONFORMER_ERROR = (
    "Needs a real 3D conformer — generate one first with Structure ▸ Generate Conformers...."
)

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


_brenk_catalog: FilterCatalog | None = None


def _load_brenk_catalog() -> FilterCatalog:
    """Brenk et al. 2008's catalog of reactive/unstable/toxicophore-
    adjacent functional groups (105 entries, confirmed live -- correctly
    flags acetaldehyde as "aldehyde", acetyl chloride as "acid_halide"
    +"aldehyde", leaves benzene/ethanol clean) -- a real, RDKit-bundled
    toxicity-relevant alert catalog, distinct from PAINS. Cached at module
    level for the same reason `_load_pains_catalog` is."""
    global _brenk_catalog
    if _brenk_catalog is None:
        params = FilterCatalogParams()
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.BRENK)
        _brenk_catalog = FilterCatalog(params)
    return _brenk_catalog


# Phase 20: a curated subset of RDKit's 85 built-in Fragments.fr_* counting
# functions (confirmed live: 85 total, sanity-checked on aspirin --
# fr_ester=1, fr_COO=1, fr_benzene=1, fr_phenol=0 correctly since aspirin's
# phenol oxygen is esterified) -- not all 85, most of the rest are narrow
# specializations (e.g. fr_Ar_COO vs fr_Al_COO vs fr_COO2) that would
# clutter a general-purpose functional-group panel more than inform it.
# (fr_* function, display name) pairs.
_FUNCTIONAL_GROUP_SPECS: list[tuple[str, str]] = [
    ("fr_amide", "Amide"),
    ("fr_ester", "Ester"),
    ("fr_ether", "Ether"),
    ("fr_ketone", "Ketone"),
    ("fr_aldehyde", "Aldehyde"),
    ("fr_COO", "Carboxylic Acid"),
    ("fr_Al_OH", "Aliphatic Alcohol"),
    ("fr_phenol", "Phenol"),
    ("fr_NH2", "Primary Amine"),
    ("fr_NH1", "Secondary Amine"),
    ("fr_NH0", "Tertiary Amine"),
    ("fr_nitro", "Nitro"),
    ("fr_nitrile", "Nitrile"),
    ("fr_sulfonamd", "Sulfonamide"),
    ("fr_sulfone", "Sulfone"),
    ("fr_halogen", "Halogen"),
    ("fr_epoxide", "Epoxide"),
    ("fr_imidazole", "Imidazole"),
    ("fr_pyridine", "Pyridine"),
    ("fr_furan", "Furan"),
    ("fr_thiophene", "Thiophene"),
    ("fr_benzene", "Benzene Ring"),
    ("fr_urea", "Urea"),
    ("fr_guanido", "Guanidine"),
]


def compute_fragment_group_alert(mol: Chem.Mol, molecule_uuid: str) -> AlertResult:
    """Which of a curated set of common functional groups are present
    (and how many), via RDKit's built-in `Fragments` module -- zero new
    dependencies, ChatGPT's "functional group intelligence" ask. Reuses
    `AlertResult`'s shape (a categorical result, not a single scalar) even
    though this isn't a toxicity alert -- `matched` holds formatted
    "name (count)" strings for every group with count > 0, same "empty
    list means checked, nothing found" convention as PAINS/BRENK.

    NAMED FOR ITS BACKING, not for what it reports, because it used to be
    called `compute_functional_groups` and that shadowed the same-named
    import from `chem/structure_annotation` at the top of this file. The
    `functional_groups` calculator registered below therefore bound THIS
    two-argument alert instead of the intended three-argument per-atom
    annotation, and raised `TypeError: takes 2 positional arguments but 3
    were given` for every molecule -- the registration and the definition
    are 1,000 lines apart, so nothing about either read as wrong. Found by
    running all 50 registered calculators in one pass, which is what a
    batch runner does by construction.
    """
    matched = []
    for fn_name, display_name in _FUNCTIONAL_GROUP_SPECS:
        count = getattr(Fragments, fn_name)(mol)
        if count > 0:
            matched.append(f"{display_name} ({count})")
    return AlertResult(
        alert_id="functional_groups",
        name="Functional Groups",
        molecule_uuid=molecule_uuid,
        matched=matched,
        provenance=Provenance(created_by="core", method="rdkit"),
        category="admet",
    )


# Basic-amine SMARTS for the hERG risk-factor checklist (Phase 20) --
# confirmed live against 9 reference molecules before shipping: matches
# verapamil, amitriptyline (both real tertiary-amine hERG-liability
# compounds), diethylamine, triethylamine; correctly does NOT match
# aspirin (no amine), acetamide (amide N), pyridine (aromatic N),
# benzenesulfonamide (sulfonamide N -- an earlier draft of this pattern
# false-positived here), or aniline (aromatic-attached amine, too weakly
# basic at physiological pH to count -- an earlier draft false-positived
# here too).
_BASIC_AMINE_SMARTS = Chem.MolFromSmarts("[NX3;H2,H1,H0;!$(NC=[O,S]);!$(N=*);!$(NS(=O)=O);!$(Nc);!a]")

_HERG_RISK_NAME = "hERG Risk Factors (not a prediction)"

MUTAGENICITY_ALERT_NAME = "Mutagenicity Structural Alerts"

#: Canonical mutagenicity alert classes. Deliberately a SMALL textbook
#: set rather than a reconstruction of a commercial alert system: the aim
#: is the cheap screen a chemist would run mentally, not a proprietary
#: catalogue this project has no licence to reproduce.
#:
#: UNLIKE THE hERG CHECKLIST ABOVE, THESE HAVE MEASURED PERFORMANCE. Over
#: 26 compounds -- 15 standard reference mutagens and Ames-positive drugs
#: against 11 with clean records -- they score 14 TP / 10 TN / 1 FP / 1 FN,
#: which is exactly what the ~1 GB ADMET-AI model scores on the same set.
#: They fail on DIFFERENT compounds, though, which is why both are worth
#: having: see `chem/admet_providers.py` and
#: `benchmarks/docking/ames_panel.py`.
#:
#: Every pattern is verified against compounds it must and must not match
#: in `tests/test_mutagenicity_alerts.py`, because a plausible-looking
#: SMARTS that quietly matches nothing would look identical to a clean
#: molecule.
_MUTAGENICITY_ALERTS: dict[str, str] = {
    "Aromatic nitro": "c[N+](=O)[O-]",
    "Aromatic amine": "[NX3;H2,H1;!$(NC=O)]c",
    # Hydrolysed or N-deacetylated to the aromatic amine in vivo, which is
    # the actual mutagen -- 2-acetylaminofluorene is the classic case.
    "N-aryl amide (aromatic amine precursor)": "[NX3;H1](C=O)c",
    "N-nitroso": "[NX3][NX2]=O",
    "Hydrazine": "[NX3;!$(N=*)][NX3;!$(N=*)]",
    "Epoxide": "C1OC1",
    "Aziridine": "C1CN1",
    "Azo": "c[NX2]=[NX2]c",
}
_MUTAGENICITY_PATTERNS = {
    label: Chem.MolFromSmarts(smarts) for label, smarts in _MUTAGENICITY_ALERTS.items()
}

#: Fused all-carbon aromatic systems of at least this many rings count as
#: a polycyclic-aromatic alert.
_PAH_RING_THRESHOLD = 3


def largest_fused_aromatic_carbocycle(mol: Chem.Mol) -> int:
    """Rings in the largest set of mutually fused all-carbon aromatic rings.

    Polycyclic aromatic hydrocarbons are a major mutagen class carrying no
    functional group at all -- benzo[a]pyrene is carbon and hydrogen and
    nothing else, so every SMARTS above misses it. "Three or more fused
    rings" is not expressible as a substructure query, so it is computed
    from ring membership instead.
    """
    rings = [
        ring
        for ring in mol.GetRingInfo().AtomRings()
        if all(
            mol.GetAtomWithIdx(i).GetIsAromatic() and mol.GetAtomWithIdx(i).GetSymbol() == "C"
            for i in ring
        )
    ]
    if not rings:
        return 0
    # (atoms in the system, rings in it). The ring COUNT is tracked
    # explicitly rather than derived from the atom count: the tempting
    # `(atoms - 2) // 4` inversion of "n fused rings have 4n + 2 atoms"
    # only holds for catacondensed systems. Benzo[a]pyrene is
    # pericondensed -- atoms shared by three rings at once -- so it has 20
    # carbons across 5 rings, not 22, and that formula returned 4.
    systems: list[tuple[set[int], int]] = []
    for ring in rings:
        atoms = set(ring)
        count = 1
        touching = [system for system in systems if system[0] & atoms]
        for system in touching:
            systems.remove(system)
            atoms |= system[0]
            count += system[1]
        systems.append((atoms, count))
    return max(count for _atoms, count in systems)


def compute_mutagenicity_alerts(mol: Chem.Mol, molecule_uuid: str) -> AlertResult:
    """Structural alerts associated with bacterial mutagenicity (Ames).

    A SCREEN, NOT A VERDICT, but a better-evidenced one than the hERG
    checklist beside it: measured against 26 compounds it matches the
    trained ADMET model's accuracy exactly (see `_MUTAGENICITY_ALERTS`).

    WHAT IT CANNOT DO, stated because the failure is systematic rather
    than random: an alert is a substructure, so it only sees mutagens that
    are already electrophilic or obviously become so. Aflatoxin B1 is
    missed here and caught by the model, because its electrophile is an
    epoxide formed by metabolism and simply is not present in the drawn
    structure. Conversely the N-aryl amide alert fires on paracetamol,
    which has a clean genotoxicity record.

    So a hit means "worth an Ames test", not "mutagenic", and an empty
    result does not mean safe.
    """
    matched = [
        label
        for label, pattern in _MUTAGENICITY_PATTERNS.items()
        if pattern is not None and mol.HasSubstructMatch(pattern)
    ]
    rings = largest_fused_aromatic_carbocycle(mol)
    if rings >= _PAH_RING_THRESHOLD:
        matched.append(f"Polycyclic aromatic ({rings} fused rings)")
    return AlertResult(
        alert_id="mutagenicity_alerts",
        name=MUTAGENICITY_ALERT_NAME,
        molecule_uuid=molecule_uuid,
        matched=matched,
        # A genuine catalog: a match here is something to look at, which
        # is what AlertResult was written for. Most other producers now
        # borrow it to carry report lines and stay at the INFO default.
        severity=Severity.WARNING,
        provenance=Provenance(created_by="core", method="rdkit"),
        category="admet",
    )


def compute_herg_risk_factors(mol: Chem.Mol, molecule_uuid: str) -> AlertResult:
    """Lists known STRUCTURAL CORRELATES of hERG channel liability --
    high lipophilicity, a basic amine, aromatic ring(s) for pi-stacking
    with Phe656 (all three confirmed via independent hERG SAR review/
    risk-assessment literature) -- explicitly NOT a prediction of binding
    affinity or a pass/fail verdict. No trained model backs this; it's a
    checklist of factors the literature associates with risk, nothing
    more. Real hERG/CYP prediction remains deferred pending a verified,
    redistributable model (see docs/ROADMAP.md's "ML Calculator Plugins" note).
    """
    matched = []
    mol_logp = Crippen.MolLogP(mol)
    if mol_logp > 3:
        matched.append(f"High lipophilicity (LogP {mol_logp:.1f} > 3)")
    if mol.HasSubstructMatch(_BASIC_AMINE_SMARTS):
        matched.append("Basic amine present")
    aromatic_ring_count = rdMolDescriptors.CalcNumAromaticRings(mol)
    if aromatic_ring_count > 0:
        matched.append(f"{aromatic_ring_count} aromatic ring(s)")
    return AlertResult(
        alert_id="herg_risk_factors",
        name=_HERG_RISK_NAME,
        molecule_uuid=molecule_uuid,
        matched=matched,
        severity=Severity.WARNING,
        provenance=Provenance(created_by="core", method="rdkit"),
        category="admet",
    )


def compute_gasteiger_charges(mol: Chem.Mol, include_hydrogens: bool = False) -> dict[int, float]:
    """Mutates `mol` in place (sets a "_GasteigerCharge" property per atom)
    -- harmless for every current caller, none of which reads `mol`
    again afterward expecting that property's absence. Shared by the
    always-on `compute_per_atom` and the pH-parameterized
    `compute_gasteiger_charge_at_ph` calculator (Phase 18) so the
    Gasteiger-charge logic isn't duplicated between them.

    `include_hydrogens=True` adds each heavy atom's implicit-hydrogen
    charge to its own -- Marvin's "Increment of Hs" option, the bracketed
    second number in its charge screenshots. RDKit exposes exactly this as
    `_GasteigerHCharge` (confirmed live), so it is real data rather than
    an approximation.

    A NOTE ON SIGMA/PI: Marvin also offers a sigma/pi/total selector.
    RDKit implements PEOE, which is a SIGMA-charge method -- it has no pi
    component to separate out, so that selector is deliberately not
    offered here rather than being faked by relabelling one number three
    ways.
    """
    rdPartialCharges.ComputeGasteigerCharges(mol)
    charges = {}
    for atom in mol.GetAtoms():
        value = atom.GetDoubleProp("_GasteigerCharge")
        if include_hydrogens and atom.HasProp("_GasteigerHCharge"):
            value += atom.GetDoubleProp("_GasteigerHCharge")
        charges[atom.GetIdx()] = value
    return charges


class RDKitDescriptorProvider(DescriptorProvider):
    """Computes the built-in descriptor set using RDKit only."""

    provider_id = "rdkit"

    def descriptor_ids(self) -> list[str]:
        return [spec[0] for spec in _DESCRIPTOR_SPECS] + [spec[0] for spec in _SHAPE_DESCRIPTOR_SPECS]

    def descriptor_categories(self) -> dict[str, str]:
        categories = {descriptor_id: category for descriptor_id, _name, _units, category in _DESCRIPTOR_SPECS}
        categories.update({descriptor_id: "shape" for descriptor_id, _name, _units in _SHAPE_DESCRIPTOR_SPECS})
        return categories

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

        # ESOL (Delaney 2004, refit coefficients) -- confirmed live against
        # the reference implementation (PatWalters/solubility) and
        # sanity-checked against known experimental values (aspirin: -2.09
        # predicted vs. -2.19 experimental; caffeine: -0.53 vs. -0.8, both
        # within ESOL's documented accuracy).
        aromatic_atom_count = sum(1 for atom in mol.GetAtoms() if atom.GetIsAromatic())
        # mol.GetNumAtoms() (not heavy_atom_count) to match the verified
        # reference implementation and the live-checked values above --
        # equal to heavy-atom count when the molblock has no explicit Hs
        # (the common case), differs only if it does.
        aromatic_proportion = aromatic_atom_count / mol.GetNumAtoms() if mol.GetNumAtoms() else 0.0
        esol_logs = (
            0.2612 - 0.7417 * mol_logp - 0.0066 * mol_wt + 0.0035 * num_rotatable_bonds - 0.4262 * aromatic_proportion
        )
        # Simplified, documented approximations -- NOT reproductions of
        # Clark 1999's actual BBB regression or Martin 2005's actual
        # categorical "Abbott Bioavailability Score" (see _DESCRIPTOR_SPECS'
        # comment above these three entries).
        bbb_permeant = tpsa <= 90 and mol_wt <= 450
        bioavailability_likely = 20 <= tpsa <= 130 and num_rotatable_bonds <= 10 and lipinski_violations <= 1

        # Confirmed via primary citations (see _DESCRIPTOR_SPECS' comment
        # above these three entries): Pfizer 3/75 and GSK 4/400 flag a
        # HIGHER-risk regime, so "pass" is the negation; Rule of Three's
        # thresholds are used directly (all four must hold to pass).
        pfizer_375_pass = not (mol_logp > 3 and tpsa < 75)
        gsk_400_pass = not (mol_logp > 4 and mol_wt > 400)
        rule_of_three_pass = mol_wt < 300 and mol_logp <= 3 and num_hbd <= 3 and num_hba <= 3

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
            "esol_logs": esol_logs,
            "bbb_permeant": bbb_permeant,
            "bioavailability_likely": bioavailability_likely,
            "pfizer_375_pass": pfizer_375_pass,
            "gsk_400_pass": gsk_400_pass,
            "rule_of_three_pass": rule_of_three_pass,
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

    def alert_ids(self) -> dict[str, str]:
        """The five catalogs `compute_alerts` below returns, named without
        running them. Kept adjacent to it so the two cannot drift; a new
        catalog added below and not here is simply not offerable in a batch
        run, which is a visible gap rather than a wrong answer."""
        return {
            "pains": "PAINS",
            "brenk": "BRENK (Reactive/Unstable Groups)",
            "functional_groups": "Functional Groups (fragment counts)",
            "herg_risk_factors": _HERG_RISK_NAME,
            "mutagenicity_alerts": MUTAGENICITY_ALERT_NAME,
        }

    def compute_alerts(self, mol: Chem.Mol, molecule_uuid: str) -> list[AlertResult]:
        pains_catalog = _load_pains_catalog()
        pains_matched = [entry.GetDescription() for entry in pains_catalog.GetMatches(mol)]
        brenk_catalog = _load_brenk_catalog()
        brenk_matched = [entry.GetDescription() for entry in brenk_catalog.GetMatches(mol)]
        return [
            AlertResult(
                alert_id="pains",
                name="PAINS",
                molecule_uuid=molecule_uuid,
                matched=pains_matched,
                severity=Severity.WARNING,
                provenance=Provenance(created_by="core", method=self.provider_id),
                category="medicinal_chemistry",
            ),
            AlertResult(
                alert_id="brenk",
                name="BRENK (Reactive/Unstable Groups)",
                molecule_uuid=molecule_uuid,
                matched=brenk_matched,
                severity=Severity.WARNING,
                provenance=Provenance(created_by="core", method=self.provider_id),
                category="admet",
            ),
            compute_fragment_group_alert(mol, molecule_uuid),
            compute_herg_risk_factors(mol, molecule_uuid),
            compute_mutagenicity_alerts(mol, molecule_uuid),
        ]

    def compute_per_atom(self, mol: Chem.Mol, molecule_uuid: str) -> list[PerAtomDataset]:
        provenance = Provenance(created_by="core", method=self.provider_id)

        contribs = rdMolDescriptors._CalcCrippenContribs(mol)
        logp_contrib = {idx: logp for idx, (logp, _mr) in enumerate(contribs)}
        mr_contrib = {idx: mr for idx, (_logp, mr) in enumerate(contribs)}
        gasteiger_charge = compute_gasteiger_charges(mol)

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


# --- Phase 18: CalculatorRegistry-registered calculators --------------------
# Each function matches CalculatorRegistry's compute signature
# (mol, molecule_uuid, parameters) -> ScientificResult. Registered against
# CALCULATOR_DEFINITIONS in bootstrap.build_service_container() rather than
# here, keeping this module's job "know how to compute things," not "know
# about the registry."


def compute_gasteiger_charge_at_ph(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any]
) -> PerAtomDataset:
    """The "charge" category's calculator. Protonates `mol` to the
    pH-appropriate dominant microspecies via Dimorphite-DL
    (`chem.pka_providers.protonate_at_ph`) before computing Gasteiger
    charges, so the result reflects that pH's ionization state rather than
    whatever protonation state the molecule happened to be drawn in.
    """
    _places = decimals(parameters)
    from openchem.chem.pka_providers import protonate_at_ph

    ph = parameters.get("pH", 7.4)
    include_hydrogens = bool(parameters.get("include_hydrogens", False))
    protonated = protonate_at_ph(mol, ph)
    charges = compute_gasteiger_charges(protonated, include_hydrogens=include_hydrogens)
    suffix = " incl. H" if include_hydrogens else ""
    return PerAtomDataset(
        property_id="gasteiger_charge_at_ph",
        name=f"Partial Charge (Gasteiger) at pH {ph:g}{suffix}",
        units="e",
        method="rdkit+dimorphite_dl",
        molecule_uuid=molecule_uuid,
        values=charges,
        provenance=Provenance(
            created_by="core",
            method="rdkit+dimorphite_dl",
            parameters={
                "pH": ph,
                "include_hydrogens": include_hydrogens,
                "decimal_places": _places,
            },
        ),
    )


def compute_crippen_logp_contrib_calculator(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any]
) -> PerAtomDataset:
    """The "logp" category's calculator -- same Crippen contribution call
    `compute_per_atom` uses for its always-on batch, so the registry-driven
    path and that batch never compute this two different ways."""
    _places = decimals(parameters)
    contribs = rdMolDescriptors._CalcCrippenContribs(mol)
    logp_contrib = {idx: logp for idx, (logp, _mr) in enumerate(contribs)}
    return PerAtomDataset(
        property_id="crippen_logp_contrib",
        name="LogP Contribution (Crippen)",
        units="",
        method="rdkit",
        molecule_uuid=molecule_uuid,
        values=logp_contrib,
        provenance=Provenance(created_by="core", method="rdkit", parameters={"decimal_places": _places}),
    )


def compute_crippen_mr_contrib_calculator(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any]
) -> PerAtomDataset:
    """The "molar_refractivity" category's calculator -- same Crippen
    contribution call `compute_per_atom` uses for its always-on batch."""
    _places = decimals(parameters)
    contribs = rdMolDescriptors._CalcCrippenContribs(mol)
    mr_contrib = {idx: mr for idx, (_logp, mr) in enumerate(contribs)}
    return PerAtomDataset(
        property_id="crippen_mr_contrib",
        name="Molar Refractivity Contribution (Crippen)",
        units="",
        method="rdkit",
        molecule_uuid=molecule_uuid,
        values=mr_contrib,
        provenance=Provenance(created_by="core", method="rdkit", parameters={"decimal_places": _places}),
    )


_PKA_NOT_INSTALLED_MESSAGE = (
    "No pkasolver environment configured. pkasolver runs out of process from its "
    "own virtual environment (it requires numpy<2, while this app runs numpy 2.x) "
    "-- set the interpreter path under Tools > External Tools. Until then, "
    "pH-dependent protonation via Dimorphite-DL still works through the Charge "
    "category's pH control, and LogD falls back to a labelled approximation."
)


def compute_pka_dataset(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any], interpreter_path: str | None = None
) -> AlertResult:
    """The "pka" category's calculator. pkasolver runs out of process (see
    `chem/pka_providers.py` for why); when no environment is configured
    this returns a FAILED, clearly-messaged result rather than an empty
    one with no explanation.

    Reports the pKa VALUES as an `AlertResult` list rather than a
    per-atom-keyed dataset on purpose: pkasolver's reaction-centre indices
    do not map onto our atom numbering (confirmed live -- see
    `compute_pka`), so keying a 2D/3D visualization off them would
    confidently highlight the wrong atoms.
    """
    from openchem.chem.pka_providers import compute_pka, pka_predictor_available

    if not pka_predictor_available(interpreter_path):
        return AlertResult(
            alert_id="pka",
            name="pKa",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="pka",
            provenance=Provenance(created_by="core", method="pkasolver"),
            cache_state=CacheState.FAILED,
            error=_PKA_NOT_INSTALLED_MESSAGE,
        )
    try:
        pairs = compute_pka(mol, interpreter_path)
    except RuntimeError as exc:
        return AlertResult(
            alert_id="pka",
            name="pKa",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="pka",
            provenance=Provenance(created_by="core", method="pkasolver"),
            cache_state=CacheState.FAILED,
            error=str(exc),
        )
    return AlertResult(
        alert_id="pka",
        name="pKa",
        molecule_uuid=molecule_uuid,
        matched=[_pka_line(prediction, parameters, mol) for prediction in sorted(
            pairs or [], key=lambda prediction: prediction.value
        )],
        category="pka",
        provenance=Provenance(created_by="core", method="pkasolver"),
    )


def _pka_line(prediction, parameters: dict[str, Any] | None, mol: Chem.Mol | None = None) -> str:
    """One pKa, with the ionizable atom and the ensemble spread.

    THE ATOM IS NEW AND WAS PREVIOUSLY UNSAYABLE. pkasolver's reaction
    centre indexes its own pH-7 microstate, so printing it against our
    numbering named a different atom -- for 4-aminobenzoic acid a ring
    carbon rather than the carboxylate oxygen. `pka_providers.map_site_atom`
    now translates it, and returns None where it cannot, which is why this
    still has a branch for having no atom to name.

    The spread is pkasolver's own -- how far its fifty models disagreed --
    so it is measured rather than invented, which is why it is worth
    printing at all. It is shown ONLY when non-zero: a runner predating
    the field reports 0.0, and printing "+/- 0.00" there would claim
    perfect agreement that was never measured.

    Deliberately NOT called a confidence interval. Fifty models trained on
    shared data can agree closely and be wrong together -- see the
    nitrophenols in `chem/pka_providers.py`, where the model is confident
    and 2.7 units out.
    """
    value = fmt(prediction.value, parameters)
    site = ""
    if prediction.atom_index is not None and mol is not None:
        if prediction.atom_index < mol.GetNumAtoms():
            atom = mol.GetAtomWithIdx(prediction.atom_index)
            site = f" at {atom.GetSymbol()}{prediction.atom_index}"
    line = f"pKa {value}{site}"
    if not prediction.stddev:
        return line
    return f"{line} +/- {fmt(prediction.stddev, parameters)} (ensemble spread)"


def compute_logd(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any], interpreter_path: str | None = None
) -> AlertResult:
    """The "logd" category's calculator (Phase 23) -- pH-adjustable
    distribution coefficient.

    Uses real Henderson-Hasselbalch when numeric pKa is available
    (pkasolver, out of process), and clearly says so. Otherwise falls back
    to the LogP of the dominant microspecies at that pH via Dimorphite-DL:
    a real pH-dependent number, but NOT true logD, and labelled as such
    rather than presented as equivalent.
    """
    from openchem.chem.logd import classify_ionizable_centres, logd_from_microspecies, logd_from_pkas
    from openchem.chem.pka_providers import compute_pka, pka_predictor_available

    ph = float(parameters.get("pH", 7.4))
    logp = Crippen.MolLogP(mol)
    acids, bases = classify_ionizable_centres(mol)

    lines: list[str] = []
    if acids == 0 and bases == 0:
        lines.append(f"logD = {logp:.2f} at pH {ph:g} (no ionizable centre — equal to LogP)")
        method = "rdkit"
    elif pka_predictor_available(interpreter_path):
        try:
            pkas = [p.value for p in (compute_pka(mol, interpreter_path) or [])]
        except RuntimeError as exc:
            return AlertResult(
                alert_id="logd", name="LogD", molecule_uuid=molecule_uuid, matched=[], category="lipophilicity",
                provenance=Provenance(created_by="core", method="pkasolver"),
                cache_state=CacheState.FAILED, error=str(exc),
            )
        value = logd_from_pkas(mol, ph, pkas)
        lines.append(f"logD = {value:.2f} at pH {ph:g} (Henderson-Hasselbalch)")
        lines.append(f"LogP = {logp:.2f}")
        lines.append("pKa: " + ", ".join(f"{p:.2f}" for p in sorted(pkas)))
        method = "rdkit+pkasolver"
    else:
        value = logd_from_microspecies(mol, ph)
        lines.append(f"logD ~ {value:.2f} at pH {ph:g} (approximation)")
        lines.append(f"LogP = {logp:.2f}")
        lines.append(
            "Approximation: LogP of the dominant microspecies at this pH (Dimorphite-DL), "
            "not true Henderson-Hasselbalch logD — configure a pkasolver environment in "
            "Tools > External Tools for real numeric pKa."
        )
        method = "rdkit+dimorphite_dl"

    lines.append(f"Ionizable centres: {acids} acidic, {bases} basic")
    return AlertResult(
        alert_id="logd",
        name=f"LogD at pH {ph:g}",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="lipophilicity",
        provenance=Provenance(created_by="core", method=method, parameters={"pH": ph}),
    )


def compute_polar_surface_area(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any]
) -> AlertResult:
    """The "surface" category's 2D Polar Surface Area calculator.

    Reports TPSA for the neutral structure AND for the dominant
    microspecies at a given pH -- Marvin shows both, and they genuinely
    differ: protonating an amine or deprotonating an acid changes the polar
    atom set. Reuses `protonate_at_ph` (Phase 18), the same transformation
    the pH-dependent charge calculator already applies.
    """
    from openchem.chem.pka_providers import protonate_at_ph

    ph = float(parameters.get("pH", 7.4))
    neutral_tpsa = rdMolDescriptors.CalcTPSA(mol)
    lines = [f"Polar surface area: {neutral_tpsa:.2f} Å² (as drawn)"]
    try:
        protonated = protonate_at_ph(mol, ph)
        lines.append(f"Polar surface area at pH {ph:g}: {rdMolDescriptors.CalcTPSA(protonated):.2f} Å²")
    except Exception:  # noqa: BLE001 - Dimorphite-DL is optional-ish; the neutral value still stands
        lines.append(f"Could not build the dominant microspecies at pH {ph:g}; showing the drawn form only.")
    return AlertResult(
        alert_id="polar_surface_area",
        name="Polar Surface Area (2D)",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="surface",
        provenance=Provenance(created_by="core", method="rdkit+dimorphite_dl", parameters={"pH": ph}),
    )



def compute_admet_endpoints(mol, molecule_uuid, parameters=None, interpreter_path=None):
    """ADMET-AI's hERG / CYP / Ames predictions, as an AlertResult.

    An AlertResult rather than a PerAtomDataset because these are
    whole-molecule probabilities with no per-atom meaning -- there is
    nothing to colour on a structure, and pretending otherwise would
    invite reading a molecular property as a local one.

    The values are MODEL OUTPUTS. Each line says so by carrying its
    probability rather than a verdict, and the rule-based
    `hERG Risk Factors (not a prediction)` alert stays alongside it.
    """
    from openchem.chem.admet_providers import (
        BASIC,
        compute_admet,
        describe_admet_status,
        endpoint_lines,
    )
    from openchem.domain.common import CacheState, Provenance
    from openchem.domain.scientific_result import AlertResult

    tier = str((parameters or {}).get("tier", BASIC))

    # Everything the user must read goes in `matched` (what PropertyPanel
    # and the clipboard render) or `error`. There is no `description`
    # field on AlertResult, and adding one would have been invisible --
    # no consumer reads it, so the model-output caveat below would never
    # have reached a screen.
    try:
        endpoints = compute_admet(mol, interpreter_path, tier)
    except RuntimeError as exc:
        return AlertResult(
            alert_id="admet_ml", name="ADMET (ADMET-AI)", category="admet",
            matched=[f"Prediction failed: {exc}"],
            molecule_uuid=molecule_uuid, cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=Provenance(created_by="admet_ai", method="chemprop multi-task"),
        )

    if endpoints is None:
        # `compute_admet` returns None for exactly one reason -- no
        # interpreter configured -- so `describe_admet_status` is
        # guaranteed to take its "Not configured" branch here, and the
        # install guidance it returns is the whole point of this path.
        return AlertResult(
            alert_id="admet_ml", name="ADMET (ADMET-AI)", category="admet",
            matched=[describe_admet_status(interpreter_path)],
            molecule_uuid=molecule_uuid, cache_state=CacheState.FAILED,
            error="ADMET-AI is not configured.",
            provenance=Provenance(created_by="admet_ai", method="chemprop multi-task"),
        )

    lines = endpoint_lines(endpoints, parameters)
    if lines:
        # Caveat last, not first: putting it ahead of the numbers would bury
        # the top liability under a disclaimer and undo the sort above. Only
        # when there ARE numbers -- there is nothing to caveat otherwise.
        # "Values", not "probabilities": since the Advanced tier the block
        # also carries regressions (solubility, LD50, protein binding),
        # and calling those probabilities would be wrong on its face.
        lines.append(
            "Values from ADMET-AI, a multi-task model trained on the Therapeutics "
            "Data Commons ADMET suite. These are predictions with real "
            "uncertainty, not measurements. Percentiles compare this molecule "
            "against ~2,500 approved drugs."
        )
    else:
        lines = ["The model returned no reported endpoint."]
    return AlertResult(
        alert_id="admet_ml", name="ADMET (ADMET-AI, predicted)", category="admet",
        matched=lines,
        molecule_uuid=molecule_uuid, cache_state=CacheState.COMPLETED,
        provenance=Provenance(
            created_by="admet_ai", method="chemprop multi-task (TDC ADMET)",
            parameters={"endpoints": len(endpoints)},
        ),
    )

CALCULATOR_DEFINITIONS: list[CalculatorDefinition] = [
    CalculatorDefinition(
        calculator_id="gasteiger_charge_at_ph",
        display_name="Partial Charge (pH-dependent)",
        category="charge",
        description="Gasteiger partial charges, recomputed on the dominant protonation state at a given pH.",
        execution=RegistryExecution(compute=compute_gasteiger_charge_at_ph),
        parameters=[
            CalculatorParameter(name="pH", label="pH", kind="float", default=7.4, minimum=0.0, maximum=14.0),
            CalculatorParameter(
                name="include_hydrogens",
                label="Increment of Hs (add implicit H charge)",
                kind="bool",
                default=False,
            ),
        ],
        tags=["charge", "ph", "per-atom"],
    ),
    CalculatorDefinition(
        calculator_id="crippen_logp_contrib",
        tags=['logp', 'lipophilicity', 'partition', 'crippen', 'per-atom'],
        display_name="LogP Contribution",
        category="lipophilicity",
        description="Per-atom Crippen LogP contribution -- which atoms increase vs. decrease LogP.",
        execution=RegistryExecution(compute=compute_crippen_logp_contrib_calculator),
        parameters=[
            decimal_places_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="crippen_mr_contrib",
        tags=['refractivity', 'polarizability', 'crippen', 'per-atom'],
        display_name="Molar Refractivity Contribution",
        category="electronic",
        description="Per-atom Crippen molar refractivity contribution.",
        execution=RegistryExecution(compute=compute_crippen_mr_contrib_calculator),
        parameters=[
            decimal_places_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="admet_ml",
        tags=['admet', 'toxicity', 'herg', 'cyp', 'ames', 'absorption', 'metabolism'],
        parameters=[
            decimal_places_parameter(),
            CalculatorParameter(
                # Not a display filter: the tier decides which of the
                # model's 104 columns are shown AT ALL, and the default
                # keeps the ten this calculator has always reported.
                name="tier",
                label="Endpoints (Research endpoints are not validated)",
                kind="choice",
                default="basic",
                choices=["basic", "advanced", "research"],
            ),
        ],
        display_name="ADMET (hERG, CYP, Ames, ADME)",
        category="admet",
        description=(
            "Predicted hERG blockade, CYP450 inhibition/substrate and Ames "
            "mutagenicity via ADMET-AI, run out of process from its own "
            "environment (configure it in Tools > External Tools). Complements "
            "the rule-based hERG risk-factor checklist rather than replacing it. "
            "The Advanced tier adds the ADME block benchmarked in "
            "benchmarks/admet/ — Caco-2, solubility, BBB, plasma protein "
            "binding, DILI, LD50, intestinal absorption — at no extra runtime "
            "cost, since the model computes all of them either way."
        ),
        execution=RegistryExecution(compute=compute_admet_endpoints),
        prediction_basis="empirical",
    ),
    CalculatorDefinition(
        calculator_id="pka",
        tags=['pka', 'acidity', 'basicity', 'ionisation', 'ionization', 'ph'],
        parameters=[decimal_places_parameter()],
        display_name="pKa",
        category="pka",
        description=(
            "Numeric pKa via pkasolver, run out of process from its own environment "
            "(configure it in Tools > External Tools)."
        ),
        execution=RegistryExecution(compute=compute_pka_dataset),
        prediction_basis="empirical",
    ),
    CalculatorDefinition(
        calculator_id="logd",
        tags=['logd', 'lipophilicity', 'partition', 'ph', 'distribution'],
        display_name="LogD (pH-dependent)",
        category="lipophilicity",
        description=(
            "Distribution coefficient at a given pH. Real Henderson-Hasselbalch when a "
            "pkasolver environment is configured; otherwise the LogP of the dominant "
            "microspecies at that pH, labelled as an approximation."
        ),
        execution=RegistryExecution(compute=compute_logd),
        prediction_basis="empirical",
        parameters=[
            CalculatorParameter(name="pH", label="pH", kind="float", default=7.4, minimum=0.0, maximum=14.0)
        ],
    ),
    # ---- Phase 26 ----------------------------------------------------
    CalculatorDefinition(
        calculator_id="elemental_analysis",
        display_name="Elemental Analysis",
        category="identity",
        description=(
            "Molecular formula, average and exact mass, atom count and elemental "
            "composition (w/w %). Validated against MarvinSketch's own output for "
            "tyramine hydrochloride."
        ),
        execution=RegistryExecution(compute=compute_elemental_analysis),
        tags=["identity", "composition", "mass"],
        parameters=[
            decimal_places_parameter(),
            *microspecies_parameters(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="substance_analysis",
        display_name="Substance & Bonding",
        category="identity",
        description=(
            "What the structure IS rather than what it contains: ionic salt, "
            "molecule, coordination compound, organometallic or mixture, with the "
            "evidence for the verdict. Reports ionic associations WITHOUT adding "
            "bonds, and refuses -- with its reason -- when the structure does not "
            "encode which ions constitute one formula unit. Coordination geometry "
            "is reported only from a real 3D conformer."
        ),
        execution=RegistryExecution(compute=compute_substance_analysis),
        tags=["structure", "bonding", "ionic", "coordination", "organometallic"],
        parameters=[
            CalculatorParameter(
                # Off by default because the formula unit already says it
                # for a two-ion salt: "Na+ . Cl-" and two component rows
                # are the same sentence twice. It earns its place on a
                # mixture, where the components are the answer and each
                # one can be highlighted in the drawing.
                name="list_components",
                label="List each component separately",
                kind="bool",
                default=False,
            ),
        ],
    ),
    CalculatorDefinition(
        calculator_id="topology_analysis",
        display_name="Topology Analysis",
        category="topology",
        description=(
            "Graph-theoretic descriptors: ring and chain counts, cyclomatic number, "
            "Platt/Randic/Balaban/Harary/Wiener/hyper-Wiener indices, Wiener polarity, "
            "and stereo centre counts. Szeged and the topological steric effect index "
            "are deliberately omitted -- their literature definitions conflict and no "
            "reference value was found to validate an implementation against."
        ),
        execution=RegistryExecution(compute=compute_topology_analysis),
        tags=["topology", "graph", "indices"],
        parameters=[
            decimal_places_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="topology_eccentricity",
        display_name="Eccentricity (per atom)",
        category="topology",
        description="Greatest topological distance from each atom to any other -- how peripheral each atom is.",
        execution=RegistryExecution(compute=compute_eccentricity_dataset),
        tags=["topology", "graph", "per-atom"],
        parameters=[
            decimal_places_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="topology_distance_degree",
        display_name="Distance Degree (per atom)",
        category="topology",
        description="Sum of each atom's topological distances to every other atom.",
        execution=RegistryExecution(compute=compute_distance_degree_dataset),
        tags=["topology", "graph", "per-atom"],
        parameters=[
            decimal_places_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="geometry_analysis",
        calculation_input=GEOMETRY,
        display_name="Geometry",
        category="geometry",
        description=(
            "3D extent (min/max/mean radius from the centroid), projection area and "
            "radius on the principal planes, and the force field energy of the current "
            "conformer in MMFF94, UFF and Dreiding. The three are on different scales "
            "and are never comparable with each other -- compare one of them across "
            "conformers of the same molecule. Dreiding is implemented here from the "
            "original paper and reproduces all eight rotational barriers that paper "
            "publishes; it omits charges and hydrogen bonds, as the paper's own "
            "reported results do. Needs a conformer."
        ),
        execution=RegistryExecution(compute=compute_geometry_analysis),
        tags=["geometry", "3d", "energy"],
        parameters=[
            decimal_places_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="surface_analysis",
        calculation_input=GEOMETRY,
        display_name="Molecular Surface Area (3D)",
        category="surface",
        description=(
            "Solvent-accessible surface area with Marvin's ASA+/ASA-/ASA_H/ASA_P splits, "
            "plus van der Waals volume. Needs a conformer."
        ),
        execution=RegistryExecution(compute=compute_surface_analysis),
        tags=["surface", "3d", "solvent"],
        parameters=[
            decimal_places_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="atom_sasa",
        calculation_input=GEOMETRY,
        display_name="Accessible Surface Area (per atom)",
        category="surface",
        description="Per-atom solvent-accessible surface -- which atoms are actually exposed. Needs a conformer.",
        execution=RegistryExecution(compute=compute_sasa_dataset),
        tags=["surface", "3d", "per-atom"],
        parameters=[
            decimal_places_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="polar_surface_area",
        display_name="Polar Surface Area (2D)",
        category="surface",
        description="Topological polar surface area, for the structure as drawn and for the dominant microspecies at a given pH.",
        execution=RegistryExecution(compute=compute_polar_surface_area),
        parameters=[
            CalculatorParameter(name="pH", label="pH", kind="float", default=7.4, minimum=0.0, maximum=14.0)
        ],
        tags=["surface", "polarity", "ph"],
    ),
    CalculatorDefinition(
        calculator_id="ring_systems",
        display_name="Ring Systems",
        category="topology",
        description=(
            "Which ring system each atom belongs to, classified as monocyclic, fused, "
            "bridged or spiro, with fusion atoms, bridgeheads and spiro centres marked. "
            "Perceived by the built-in nomenclature engine, so a ring system is one unit "
            "the way it is named -- naphthalene is one fused system of 10 atoms, not two "
            "benzenes. Works offline on any structure, with or without a conformer."
        ),
        execution=RegistryExecution(compute=compute_ring_systems),
        parameters=[
            CalculatorParameter(
                name="label_mode",
                label="Atom labels",
                kind="choice",
                default="Locants, with roles",
                choices=list(RING_LABEL_MODES),
            ),
        ],
        tags=["topology", "rings", "per-atom", "annotation"],
    ),
    CalculatorDefinition(
        calculator_id="oxidation_states",
        display_name="Oxidation States",
        category="charge",
        description=(
            "Oxidation state per atom, by the IUPAC electronegativity-partition rule: "
            "each bond's electrons go to the more electronegative atom, homonuclear "
            "bonds are split evenly. A formalism for electron bookkeeping, not a "
            "measurement, and it describes the structure as drawn. REFUSES rather than "
            "guesses on mixed-valence frameworks (magnetite), transition-metal "
            "organometallics (metal carbonyls, sandwich compounds), electron-deficient "
            "bridges (the boranes) and metal clusters -- the reason is reported."
        ),
        execution=RegistryExecution(compute=compute_oxidation_states),
        parameters=[
            CalculatorParameter(
                name="show_hydrogens",
                label="Include hydrogens",
                kind="bool",
                default=False,
            ),
        ],
        tags=["charge", "per-atom", "annotation", "inorganic", "formalism"],
    ),
    CalculatorDefinition(
        calculator_id="regulatory_screen",
        display_name="Regulatory Screen",
        category="admet",
        description=(
            "Which regulatory frameworks have something to say about this structure -- "
            "chemical weapons schedules, controlled substances, precursors and the rest, "
            "from whichever rulesets are loaded. NOT a compliance check and never says "
            "whether anything is legal: it reports which rules matched, which nearly did "
            "and why, and states the coverage of every ruleset consulted so that "
            "'no matches' cannot be read as 'not regulated'. Add your own or your "
            "organisation's rulesets as JSON in the app data directory."
        ),
        execution=RegistryExecution(compute=compute_regulatory_screen),
        parameters=[
            CalculatorParameter(
                name="jurisdiction",
                label="Jurisdiction",
                kind="choice",
                default="All jurisdictions",
                choices=list(JURISDICTION_CHOICES),
            ),
            CalculatorParameter(
                name="include_near_misses",
                label="Explain near misses",
                kind="bool",
                default=True,
            ),
        ],
        tags=["regulatory", "compliance", "screening", "safety"],
    ),
    CalculatorDefinition(
        calculator_id="locants",
        display_name="IUPAC Locants",
        category="naming",
        description=(
            "The IUPAC numbering drawn onto the structure -- which atom is C-3. Coloured "
            "by where the number came from: this structure's own parent numbering, or a "
            "ring skeleton's conventional numbering. Note that a structure named by a "
            "RETAINED name carries no derived numbering, so slightly over half of "
            "molecules produce none at all; the result says so rather than showing a "
            "blank structure."
        ),
        execution=RegistryExecution(compute=compute_locants),
        parameters=[
            CalculatorParameter(
                name="include_element",
                label="Include element symbol (N1 rather than 1)",
                kind="bool",
                default=False,
            ),
        ],
        tags=["naming", "iupac", "per-atom", "annotation"],
    ),
    CalculatorDefinition(
        calculator_id="functional_groups",
        display_name="Functional Groups",
        category="substructure",
        description=(
            "Every functional group the naming engine recognises, coloured by type and "
            "labelled at its anchor atom -- the same detection that decides which group "
            "becomes a name's suffix. Note that ring carbonyls next to a ring nitrogen "
            "(lactams, uracil, caffeine) are claimed by no group, so an empty result "
            "means nothing was matched rather than that the molecule is unfunctionalised."
        ),
        execution=RegistryExecution(compute=compute_functional_groups),
        parameters=[
            CalculatorParameter(
                name="label_mode",
                label="Atom labels",
                kind="choice",
                default="Group name",
                choices=list(FG_LABEL_MODES),
            ),
            CalculatorParameter(
                name="only_suffix_eligible",
                label="Suffix-eligible groups only",
                kind="bool",
                default=False,
            ),
        ],
        tags=["substructure", "functional-groups", "per-atom", "annotation"],
    ),
    CalculatorDefinition(
        calculator_id="stereocenters",
        display_name="Stereocentres",
        category="stereochemistry",
        description=(
            "Stereocentres coloured by CIP descriptor -- R against S at a glance, plus "
            "E/Z double bonds and the lowercase pseudo-asymmetric r/s. Centres whose "
            "configuration has not been drawn are shown separately in grey rather than "
            "left unmarked, since an unspecified centre reads as no centre at all."
        ),
        execution=RegistryExecution(compute=compute_stereocenters),
        parameters=[
            CalculatorParameter(
                name="include_unassigned",
                label="Show unspecified stereocentres",
                kind="bool",
                default=True,
            ),
        ],
        tags=["stereochemistry", "geometry", "per-atom", "annotation"],
    ),
    CalculatorDefinition(
        calculator_id="substructure_search",
        display_name="Substructure Search",
        category="substructure",
        description=(
            "Match a SMARTS pattern and highlight the hits in 2D and 3D. Pick from a "
            "built-in library of common functional groups or type your own."
        ),
        execution=RegistryExecution(compute=compute_substructure_search),
        parameters=[
            decimal_places_parameter(),
            CalculatorParameter(
                name="pattern",
                label="Common pattern",
                kind="choice",
                default="Carboxylic acid",
                choices=list(COMMON_PATTERNS),
            ),
            CalculatorParameter(name="smarts", label="Custom SMARTS (overrides)", kind="text", default=""),
        ],
        tags=["substructure", "smarts", "search"],
    ),
    CalculatorDefinition(
        calculator_id="interaction_analysis",
        calculation_input=GEOMETRY,
        display_name="Interaction Analysis",
        category="geometry",
        description=(
            "Intramolecular non-covalent contacts in the current conformer: hydrogen "
            "bonds, salt bridges, π-π stacking, cation-π, hydrophobic contacts, metal "
            "coordination and steric clashes. Needs a conformer."
        ),
        execution=RegistryExecution(compute=compute_interaction_analysis),
        tags=["interactions", "3d", "contacts"],
        parameters=[
            decimal_places_parameter(),
        ],
    ),
    # ---- Phase 27: structure generators ------------------------------
    CalculatorDefinition(
        calculator_id="stereoisomers",
        display_name="Stereoisomers",
        category="structures",
        description="Every stereoisomer, varying only the centres left unspecified by default.",
        execution=RegistryExecution(compute=compute_stereoisomers),
        parameters=[
            CalculatorParameter(
                name="max_structures", label="Maximum structures", kind="int",
                default=DEFAULT_MAX_STRUCTURES, minimum=1, maximum=10000,
            ),
            CalculatorParameter(
                name="only_unassigned", label="Vary only unspecified centres", kind="bool", default=True
            ),
        ],
        tags=["structures", "stereochemistry", "enumeration"],
    ),
    CalculatorDefinition(
        calculator_id="tautomers",
        display_name="Tautomers",
        category="structures",
        description="Tautomeric forms, with the canonical tautomer flagged.",
        execution=RegistryExecution(compute=compute_tautomers),
        parameters=[
            CalculatorParameter(
                name="max_structures", label="Maximum structures", kind="int",
                default=DEFAULT_MAX_STRUCTURES, minimum=1, maximum=10000,
            )
        ],
        tags=["structures", "tautomer", "enumeration"],
    ),
    CalculatorDefinition(
        calculator_id="resonance_forms",
        display_name="Resonance Forms",
        category="structures",
        description=(
            "Resonance contributors. 'Major contributors' allows charge separation; the wider "
            "set also allows incomplete octets. RDKit's own defaults return NO forms at all for "
            "some molecules, so the flag set is an explicit choice here."
        ),
        execution=RegistryExecution(compute=compute_resonance_forms),
        parameters=[
            CalculatorParameter(
                name="flag_set", label="Contributors", kind="choice",
                default="Major contributors", choices=list(RESONANCE_FLAG_SETS),
            ),
            CalculatorParameter(
                name="max_structures", label="Maximum structures", kind="int",
                default=DEFAULT_MAX_STRUCTURES, minimum=1, maximum=10000,
            ),
        ],
        tags=["structures", "resonance", "enumeration"],
    ),
    CalculatorDefinition(
        calculator_id="markush_enumeration",
        display_name="Markush Enumeration",
        category="structures",
        description=(
            "Enumerate the library of a Markush structure. Draw the core with dummy-atom "
            "attachment points ([*:1], [*:2]) and define substituents as \"R1: Cl, F, Br; "
            "R2: O, N\". Supports sequential and random enumeration, library sizing without "
            "enumerating, selected-part enumeration, and the valence filter. R-groups and atom "
            "lists are supported; bond lists and nested R-groups are not."
        ),
        execution=RegistryExecution(compute=compute_markush_enumeration),
        parameters=[
            CalculatorParameter(
                name="mode", label="Calculation", kind="choice",
                default="Sequential enumeration",
                choices=["Sequential enumeration", "Random enumeration", "Markush library size"],
            ),
            CalculatorParameter(
                name="substituents", label="R-group definitions", kind="text",
                default="R1: Cl, F, Br",
            ),
            CalculatorParameter(
                name="max_structures", label="Generate maximum", kind="int",
                default=MARKUSH_DEFAULT_MAX, minimum=1, maximum=100000,
            ),
            CalculatorParameter(
                name="only_labels", label="Enumerate only R-labels (blank = all)", kind="text", default=""
            ),
            CalculatorParameter(name="valence_filter", label="Valence filter", kind="bool", default=True),
            CalculatorParameter(
                name="seed", label="Random seed (0 = none)", kind="int", default=0, minimum=0, maximum=999999
            ),
        ],
        tags=["markush", "enumeration", "combinatorial", "patent"],
    ),
    # ---- Phase 28: pH-dependent curves --------------------------------
    CalculatorDefinition(
        calculator_id="pka_microspecies",
        parameters=ph_range_parameters(),
        display_name="Microspecies Distribution",
        category="pka",
        description=(
            "Percentage of each protonation state across pH 0-14, from predicted pKa values. "
            "Needs a configured pkasolver environment."
        ),
        execution=RegistryExecution(compute=compute_pka_distribution),
        prediction_basis="empirical",
        tags=["pka", "ph", "speciation", "curve"],
    ),
    CalculatorDefinition(
        calculator_id="major_microspecies",
        display_name="Major Microspecies",
        category="pka",
        description="The dominant protonation form at a given pH, via Dimorphite-DL.",
        execution=RegistryExecution(compute=compute_major_microspecies),
        parameters=[
            CalculatorParameter(name="pH", label="pH", kind="float", default=7.4, minimum=0.0, maximum=14.0)
        ],
        tags=["pka", "ph", "protonation"],
    ),
    CalculatorDefinition(
        calculator_id="isoelectric_point",
        parameters=ph_range_parameters(),
        display_name="Isoelectric Point",
        category="charge",
        description=(
            "Net charge across pH 0-14 and the pH where it crosses zero. Needs a configured "
            "pkasolver environment."
        ),
        execution=RegistryExecution(compute=compute_isoelectric_point),
        prediction_basis="empirical",
        tags=["charge", "ph", "pi", "curve"],
    ),
    CalculatorDefinition(
        calculator_id="logd_curve",
        parameters=ph_range_parameters(),
        display_name="LogD vs pH",
        category="lipophilicity",
        description=(
            "The distribution coefficient across pH 0-14 by Henderson-Hasselbalch. Needs a "
            "configured pkasolver environment. Note: Henderson-Hasselbalch under-predicts logD "
            "for zwitterions (e.g. amino acids), because it assumes the partitioning species has "
            "no site ionized; monoprotic acids and bases are unaffected."
        ),
        execution=RegistryExecution(compute=compute_logd_curve),
        prediction_basis="empirical",
        tags=["logd", "ph", "partitioning", "curve"],
    ),
    CalculatorDefinition(
        calculator_id="hbond_vs_ph",
        parameters=ph_range_parameters(step=0.5),
        display_name="H-Bond Donors/Acceptors vs pH",
        category="topology",
        description=(
            "Donor and acceptor counts on the dominant microspecies at each pH. Works without "
            "pkasolver -- Dimorphite-DL alone gives the dominant form."
        ),
        execution=RegistryExecution(compute=compute_hbond_vs_ph),
        tags=["topology", "ph", "hydrogen-bonding", "curve"],
    ),
    # ---- Phase 29: naming --------------------------------------------
    CalculatorDefinition(
        calculator_id="iupac_name",
        display_name="IUPAC Name",
        category="naming",
        description=(
            "Reports the IUPAC name from every configured source, each labelled with its "
            "origin and kind: PubChem records are exact, the nomenclature engine derives "
            "a name from the structure itself. "
            "PubChem lookup sends the structure to NCBI's public servers -- turn it off for "
            "confidential structures."
        ),
        execution=RegistryExecution(compute=compute_iupac_name),
        parameters=[
            CalculatorParameter(
                name="use_pubchem", label="Look up on PubChem (sends the structure)",
                kind="bool", default=True,
            )
        ],
        tags=["naming", "iupac", "identity"],
    ),
    # ---- Lewis acid/base ---------------------------------------------
    CalculatorDefinition(
        calculator_id="lewis_sites",
        display_name="Lewis Sites",
        category="lewis",
        description=(
            "Donor and acceptor sites from the structure as drawn, each with the rule that "
            "found it. Acceptors are found by mechanism -- empty valence orbital, low-lying "
            "pi* or sigma*, vacant coordination site -- rather than by looking only for an "
            "empty p orbital, which misses metals, SO3 and carbonyls. "
            "Strength is deliberately not reported: nothing offline can rank two donors, and "
            "carbon monoxide reports two candidate donor atoms without guessing between them."
        ),
        execution=RegistryExecution(compute=compute_lewis_sites),
        prediction_basis="empirical",
        tags=["lewis", "acid", "base", "donor", "acceptor", "per-atom"],
        parameters=[
            # Protonation genuinely changes the answer rather than
            # restating it: an ammonium ion has no lone pair and is not a
            # donor at all.
            *microspecies_parameters(),
            CalculatorParameter(
                name="include_heuristic",
                label="Include motif-based sites (pi*, sigma hole, coordination)",
                kind="bool",
                default=True,
            ),
        ],
    ),
    CalculatorDefinition(
        calculator_id="lewis_adduct",
        display_name="Lewis Adduct",
        category="lewis",
        description=(
            "Whether this molecule and a partner form a Lewis adduct, and what can be "
            "said about how strongly. Reports every applicable line of evidence side "
            "by side -- a Drago-Wayland enthalpy in kcal/mol where both species are "
            "parameterised, and orbital-based measures where a quantum job has run -- "
            "and deliberately gives no combined score, because the lines answer "
            "different questions and no accepted way of weighing them exists. "
            "The classic demonstration is carbon monoxide, which no pKa table has "
            "anything useful to say about and which forms an isolable adduct with borane."
        ),
        execution=RegistryExecution(compute=compute_lewis_adduct),
        prediction_basis="empirical",
        tags=["lewis", "adduct", "acid", "base", "two-molecule"],
        parameters=[
            CalculatorParameter(
                name="partner_smiles",
                label="Partner molecule (SMILES)",
                kind="text",
                default="",
            ),
            CalculatorParameter(
                name="role",
                label="Role of this molecule",
                kind="choice",
                default=ROLE_ACID,
                choices=[ROLE_ACID, ROLE_BASE],
            ),
        ],
    ),
    # ---- Phase 30: quantum, dynamics, dipole, MPO --------------------
    CalculatorDefinition(
        calculator_id="huckel_analysis",
        display_name="Huckel Analysis",
        category="quantum",
        description=(
            "Simple Huckel MO analysis of the conjugated pi system: orbital energies, total "
            "pi energy, HOMO/LUMO and their gap, all in units of beta. Treats every pi centre "
            "as an identical carbon, so heteroatom densities are indicative only."
        ),
        execution=RegistryExecution(compute=compute_huckel_analysis),
        prediction_basis="ab_initio",
        tags=["quantum", "orbitals", "aromaticity"],
        parameters=[
            decimal_places_parameter(),
            *microspecies_parameters(),
            CalculatorParameter(
                name="pi_electrons",
                label="Pi electrons (0 = from structure and charge)",
                kind="int",
                default=0,
                minimum=0,
                maximum=200,
            ),
        ],
    ),
    CalculatorDefinition(
        calculator_id="huckel_pi_density",
        display_name="Pi Electron Density (Huckel)",
        category="quantum",
        description="Per-atom pi electron density from the Huckel orbitals, projected onto 2D and 3D.",
        execution=RegistryExecution(compute=compute_pi_electron_density),
        prediction_basis="ab_initio",
        tags=["quantum", "per-atom", "density"],
        parameters=[
            decimal_places_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="dipole_moment",
        calculation_input=GEOMETRY,
        display_name="Dipole Moment",
        category="charge",
        description=(
            "Net molecular dipole as a vector and magnitude in Debye, from Gasteiger partial "
            "charges and this conformer's geometry. Needs a conformer. Direction and symmetry "
            "are reliable; the magnitude inherits the charge model's accuracy."
        ),
        execution=RegistryExecution(compute=compute_dipole_moment),
        tags=["charge", "3d", "polarity"],
        parameters=[
            decimal_places_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="molecular_dynamics",
        calculation_input=GEOMETRY,
        display_name="Molecular Dynamics (vacuum)",
        category="geometry",
        description=(
            "Velocity-Verlet dynamics over MMFF94/UFF forces. VACUUM only: no thermostat, no "
            "barostat, no constraints, no periodic boundaries, no solvent. Not Dreiding, so "
            "energies are not comparable to MarvinSketch's. Needs a conformer."
        ),
        execution=RegistryExecution(compute=compute_molecular_dynamics),
        parameters=[
            CalculatorParameter(
                name="steps", label="Simulation steps", kind="int",
                default=MD_DEFAULT_STEPS, minimum=10, maximum=100000,
            ),
            CalculatorParameter(
                name="step_fs", label="Step time (fs)", kind="float",
                default=MD_DEFAULT_STEP_FS, minimum=0.1, maximum=2.0,
            ),
            CalculatorParameter(
                name="temperature", label="Initial temperature (K)", kind="float",
                default=MD_DEFAULT_TEMPERATURE, minimum=1.0, maximum=2000.0,
            ),
            CalculatorParameter(
                name="frame_interval", label="Frame interval (steps)", kind="int",
                default=MD_DEFAULT_FRAME_INTERVAL, minimum=1, maximum=1000,
            ),
            CalculatorParameter(
                name="seed", label="Random seed (0 = none)", kind="int",
                default=0, minimum=0, maximum=999999,
            ),
        ],
        tags=["dynamics", "3d", "simulation"],
    ),
    CalculatorDefinition(
        calculator_id="cns_mpo",
        display_name="CNS MPO Score",
        category="admet",
        description=(
            "Wager et al. CNS multiparameter optimisation score, 0-6 from six desirability "
            "functions. Breakpoints validated against ChemAxon's documented aspirin example "
            "(5.75). Without a pkasolver environment the pKa term is omitted rather than "
            "assumed favourable, and the score is reported out of 5."
        ),
        execution=RegistryExecution(compute=compute_cns_mpo),
        prediction_basis="empirical",
        tags=["admet", "cns", "mpo", "druglikeness"],
        parameters=[
            decimal_places_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="steric_analysis",
        calculation_input=GEOMETRY,
        display_name="Ligand Steric Bulk",
        category="geometry",
        description=(
            "Exact cone angle (Bilbrey/Allen) and percent buried volume for a ligand, with the "
            "cone axis solved for rather than assumed along the metal-donor bond. Computed from "
            "free-ligand MMFF conformers, so values RANK ligands correctly (ordering identical "
            "to Tolman's published series, r = 0.98) but are not directly comparable to tables "
            "computed on metal-bound DFT or crystal geometries. Needs a donor atom."
        ),
        execution=RegistryExecution(compute=compute_steric_analysis),
        tags=["geometry", "steric", "ligand", "cone angle", "buried volume"],
        parameters=[
            decimal_places_parameter(),
            CalculatorParameter(
                name="conformers", label="Conformers", kind="int", default=20, minimum=1, maximum=200
            ),
            CalculatorParameter(
                name="metal_distance", label="Metal-donor distance (A)", kind="float",
                default=2.28, minimum=1.0, maximum=5.0,
            ),
            CalculatorParameter(
                name="sphere_radius", label="%Vbur sphere radius (A)", kind="float",
                default=3.5, minimum=1.0, maximum=10.0,
            ),
        ],
    ),
    CalculatorDefinition(
        calculator_id="nmr_database",
        display_name="NMR Shifts (experimental)",
        category="nmr",
        description=(
            "Predicts shifts by looking up each atom's environment in assigned experimental "
            "spectra from nmrshiftdb2, and reports a per-atom confidence earned from how many "
            "measurements matched and how well they agree. Instant, unlike the ab initio path, "
            "but limited to environments the database has seen. Held-out accuracy: 1.12 ppm mean "
            "error on atoms it rates 'good', 10.00 on atoms it rates 'rough' -- the rating is "
            "worth reading."
        ),
        execution=RegistryExecution(compute=compute_database_nmr),
        prediction_basis="empirical",
        tags=["nmr", "spectroscopy", "database", "experimental"],
        parameters=[
            CalculatorParameter(
                name="nucleus", label="Nucleus", kind="choice", default="13C",
                choices=["13C", "1H"],
            ),
        ],
    ),
    CalculatorDefinition(
        calculator_id="bbb_descriptors",
        display_name="BBB Score Descriptors",
        category="admet",
        description=(
            "The five inputs to Gupta et al.'s (2019) BBB Score: aromatic rings, heavy atoms, "
            "MWHBN, TPSA and the most basic pKa. The composite score itself is not computed -- "
            "its weight functions are unpublished, and ChemAxon's single worked example cannot "
            "validate five unknown curves. Aromatic rings, heavy atoms and MWHBN all reproduce "
            "that example exactly."
        ),
        execution=RegistryExecution(compute=compute_bbb_descriptors),
        prediction_basis="empirical",
        tags=["admet", "bbb", "cns", "permeability"],
        parameters=[
            decimal_places_parameter(),
            *microspecies_parameters(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="stereo_descriptors",
        parameters=[
            CalculatorParameter(
                name="show_undefined",
                label="Show undefined elements",
                kind="bool",
                default=True,
            )
        ],
        display_name="Stereo Descriptors",
        category="stereochemistry",
        description=(
            "R/S and E/Z labels for every stereo element, from RDKit's own CIP labeller. "
            "Topology Analysis reports how many stereocentres exist; this reports which is "
            "which, and flags the ones left undefined in the drawn structure."
        ),
        execution=RegistryExecution(compute=compute_stereo_descriptors),
        tags=["stereochemistry", "cip", "chirality"],
    ),
    CalculatorDefinition(
        calculator_id="structural_frameworks",
        parameters=[
            CalculatorParameter(
                name="include_generic",
                label="Include generic framework",
                kind="bool",
                default=True,
            )
        ],
        display_name="Structural Frameworks",
        category="structures",
        description="Bemis-Murcko scaffold and the generic (all-carbon, all-single-bond) framework.",
        execution=RegistryExecution(compute=compute_structural_frameworks),
        tags=["structures", "scaffold", "murcko"],
    ),
    # ---- Polarizability and orbital electronegativity ----------------
    CalculatorDefinition(
        calculator_id="polarizability",
        display_name="Polarizability (molecular)",
        category="electronic",
        description=(
            "Molecular polarizability in A^3 by the additive atomic scheme of Jensen et al. "
            "Accurate to about 1% for aromatics and halogenated compounds; roughly 11% high "
            "for saturated hydrocarbons, since an atom-additive scheme has no hybridization "
            "dependence. Miller's method is not offered -- its parameters are not published "
            "in ChemAxon's docs and could not be reproduced reliably."
        ),
        execution=RegistryExecution(compute=compute_polarizability),
        prediction_basis="empirical",
        parameters=[
            CalculatorParameter(
                name="major_microspecies",
                label="Take major microspecies",
                kind="bool",
                default=False,
            ),
            CalculatorParameter(
                name="pH", label="at pH", kind="float", default=7.4, minimum=0.0, maximum=14.0
            ),
        ],
        tags=["electronic", "polarizability", "physchem"],
    ),
    CalculatorDefinition(
        calculator_id="atomic_polarizability",
        display_name="Polarizability (per atom)",
        category="electronic",
        description="Per-atom polarizability contributions (Jensen et al.), projected onto 2D and 3D.",
        execution=RegistryExecution(compute=compute_atomic_polarizability),
        prediction_basis="empirical",
        parameters=[
            decimal_places_parameter(),
            CalculatorParameter(
                name="major_microspecies",
                label="Take major microspecies",
                kind="bool",
                default=False,
            ),
            CalculatorParameter(
                name="pH", label="at pH", kind="float", default=7.4, minimum=0.0, maximum=14.0
            ),
        ],
        tags=["electronic", "polarizability", "per-atom"],
    ),
    CalculatorDefinition(
        calculator_id="orbital_electronegativity",
        display_name="Orbital Electronegativity",
        category="electronic",
        description=(
            "Gasteiger-Marsili sigma orbital electronegativity (eV) at each atom's converged "
            "PEOE charge. Absolute values depend on the parameter set and will differ between "
            "implementations; the ordering between atoms is the meaningful part. The pi "
            "component is not offered -- it needs a separate pi-charge iteration."
        ),
        execution=RegistryExecution(compute=compute_orbital_electronegativity),
        prediction_basis="empirical",
        parameters=[
            decimal_places_parameter(),
            CalculatorParameter(
                name="include_hydrogens",
                label="Include hydrogens",
                kind="bool",
                default=False,
            ),
            CalculatorParameter(
                name="major_microspecies",
                label="Take major microspecies",
                kind="bool",
                default=False,
            ),
            CalculatorParameter(
                name="pH", label="at pH", kind="float", default=7.4, minimum=0.0, maximum=14.0
            ),
        ],
        tags=["electronic", "electronegativity", "per-atom"],
    ),
    # ---- 3D alignment -------------------------------------------------
    CalculatorDefinition(
        calculator_id="alignment_3d",
        display_name="3D Alignment",
        category="geometry",
        description=(
            "Aligns this molecule onto a reference structure in 3D. \"Extended atom types\" "
            "pairs atoms by MMFF type (atomic number, hybridization and aromaticity), so an "
            "aromatic nitrogen will not pair with a tertiary amine. \"Common scaffold\" fixes "
            "the pairing from the 2D maximum common substructure first, then refines the rest. "
            "Score is an overlap quality where HIGHER is better; RMSD is a distance in "
            "angstroms where LOWER is better -- they are not the same measure."
        ),
        execution=RegistryExecution(compute=compute_3d_alignment),
        parameters=[
            CalculatorParameter(
                name="reference_smiles",
                label="Reference structure (SMILES)",
                kind="text",
                default="",
            ),
            CalculatorParameter(
                name="method",
                label="Alignment method",
                kind="choice",
                default="Extended atom types",
                choices=list(ALIGNMENT_METHODS),
            ),
            CalculatorParameter(
                name="accuracy",
                label="Accuracy",
                kind="choice",
                default=DEFAULT_ACCURACY,
                choices=list(ACCURACY_LEVELS),
            ),
            decimal_places_parameter(),
        ],
        tags=["alignment", "3d", "overlay", "shape"],
    ),
]
