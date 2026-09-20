from __future__ import annotations

import contextlib
import io
import sys
import time
from dataclasses import replace
from importlib import import_module
from types import ModuleType
from typing import Any

from rdkit import Chem
from rdkit.Chem import (
    Crippen,
    Descriptors,
    Descriptors3D,
    GraphDescriptors,
    Lipinski,
    QED,
    rdMolDescriptors,
    rdPartialCharges,
)
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

from openchem.chem.elemental_analysis import compute_elemental_analysis
from openchem.chem.mass_spectrum import (
    DEFAULT_MINIMUM_PERCENT,
    EXACT_RESOLUTION,
    UNIT_RESOLUTION,
    compute_mass_spectrum,
)
from openchem.chem.geometry_analysis import compute_geometry_analysis
from openchem.chem.geometry_charges import (
    EEM_BULTINCK2002_PART1,
    GEOMETRY_CHARGE_METHOD_LABELS,
    GEOMETRY_CHARGE_METHODS,
    compute_geometry_charges,
)
from openchem.chem.interaction_analysis import compute_interaction_analysis
from openchem.chem.markush import DEFAULT_MAX_STRUCTURES as MARKUSH_DEFAULT_MAX
from openchem.chem.calculator_options import (
    EXPLICIT_HYDROGENS,
    HEAVY_ATOMS_ONLY,
    DEFAULT_PH,
    decimal_places_parameter,
    decimals,
    fmt,
    hydrogen_mode,
    hydrogen_mode_parameter,
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
from openchem.chem.charge_evaluation import CHARGE_MODEL_LABELS, CHARGE_MODELS, GASTEIGER
from openchem.chem.dipole import compute_dipole_moment
from openchem.chem.electronic_properties import (
    POLARIZABILITY_METHODS,
    compute_atomic_polarizability,
    ORBITAL_COMPONENTS,
    compute_orbital_electronegativity,
    compute_polarizability,
)
from openchem.chem.hlb import compute_griffin_hlb
from openchem.chem.energetics import compute_detonation, compute_oxygen_balance
from openchem.chem.aromaticity import compute_aromaticity, compute_bird_index
from openchem.chem.hansen import compute_hansen
from openchem.chem.joback import compute_joback
from openchem.chem.huckel import compute_huckel_analysis, compute_pi_electron_density
from openchem.chem.lewis import compute_lewis_sites
from openchem.chem.lewis_adduct import (
    ROLE_ACID,
    ROLE_AUTO,
    ROLE_BASE,
    ROLE_LABELS,
    compute_lewis_adduct,
)
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
from openchem.chem.solubility import (
    AQSOLDB,
    DISPLAY_UNITS,
    ESOL,
    LOG_S,
    compute_solubility,
    solvent_choices,
)
from openchem.chem.solubility import esol_logs as _esol_logs
from openchem.chem.solubility import mcgowan_volume as _mcgowan_volume
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
from openchem.chem.report_adapter import report_from_fields
from openchem.chem.feature_vocabulary import VOCABULARY_VERSION, ObjectTreatment, Projection
from openchem.chem.structural_features import project
from openchem.domain.result_store import FRAGMENT_COUNTS_METHOD
from openchem.chem.structure_annotation import (
    FG_LABEL_MODES,
    RING_LABEL_MODES,
    canonical_features,
    compute_functional_groups,
    compute_locants,
    compute_ring_systems,
    compute_stereocenters,
)
from openchem.chem.substructure import COMMON_PATTERNS, compute_substructure_search
from openchem.chem.surface_analysis import compute_sasa_dataset, compute_surface_analysis
from openchem.chem.substance import compute_substance_analysis
from openchem.chem.tsei import compute_tsei_projection
from openchem.chem.topology_analysis import (
    compute_distance_degree_dataset,
    compute_eccentricity_dataset,
    compute_topology_analysis,
)
from openchem.domain.mass_spectrum import DEFAULT_ION, SUPPORTED_IONS
from openchem.chem import components
from openchem.chem.components import drawing_index
from openchem.domain.calculator import (
    ELEMENT_OUTSIDE_PARAMETER_SET,
    GEOMETRY,
    SIDECAR_NOT_CONFIGURED,
    Aggregation,
    CalculatorDefinition,
    CalculatorParameter,
    CalculationRefusal,
    CalculatorScope,
    ComponentSelection,
    MethodDomain,
    RegistryExecution,
)
from openchem.domain.common import (
    ATOM_BASIS,
    EXPLICIT_H,
    HEAVY_ATOMS,
    TOTAL,
    CacheState,
    Provenance,
    declare_total,
)
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.scientific_result import AlertResult, PerAtomDataset
from openchem.domain.report import Fact, ReportResult
from openchem.domain.structure_issue import Basis, Severity
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
    # Ertl's topological PSA [source:ertl2000] -- fragment-based, so it
    # needs no conformer, which is why this is a DRAWING descriptor.
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
    # McGowan characteristic volume: purely constitutional, no geometry and
    # no fitted parameters, and the one Abraham solvation descriptor this
    # project can compute exactly. See `chem/solubility.py`.
    ("mcgowan_volume", "McGowan Volume", "cm³/mol ÷ 100", "physicochemical"),
    # QED [source:bickerton2012] -- a desirability AGGREGATE over eight
    # properties, not a probability that a molecule is a drug.
    ("qed", "QED (Drug-likeness)", "", "medicinal_chemistry"),
    ("sa_score", "Synthetic Accessibility", "", "medicinal_chemistry"),
    # NP-likeness [source:ertl2008] via RDKit's 2015 public-corpus re-fit
    # [source:npscorer2015] -- a BAYESIAN COMPARISON AGAINST A CORPUS, never a
    # statement about where a molecule came from. Caffeine is a natural product
    # and scores -1.09; morphine scores +2.59.
    #
    # THE CONFIDENCE IS A SEPARATE ROW BECAUSE THE SCORE CANNOT CARRY IT.
    # `scoreMolWConfidence` reports the fraction of the molecule's Morgan
    # fragments that were in the training model, and an unfound fragment
    # contributes ZERO to the sum -- so a molecule at confidence 0 scores
    # exactly 0.0 BY CONSTRUCTION, indistinguishable from one genuinely
    # scored as neutral. Methane is that case. Two named rows, for the same
    # reason oxygen balance ships as two: a single value lets a screenshot
    # collapse the distinction the naming exists to preserve.
    ("np_likeness", "NP-Likeness (Natural Product)", "", "medicinal_chemistry"),
    ("np_likeness_confidence", "NP-Likeness Confidence", "", "medicinal_chemistry"),
    # Bertz's complexity index [source:bertz1981] via RDKit, WHICH
    # DELIBERATELY DEPARTS FROM THE PAPER FOR AROMATICS [source:rdkit_bertz].
    # Two molecules can share a value: methane and propane are both 0.
    ("bertz_ct", "Molecular Complexity (Bertz CT)", "", "medicinal_chemistry"),
    # Lovering's "escape from flatland" fraction [source:lovering2009]:
    # sp3-hybridised carbons over all carbons. Benzene is 0.00, cyclohexane
    # 1.00. A molecule with NO carbon is 0.0 rather than undefined -- RDKit's
    # own convention, recorded because it is a division by zero that returns.
    ("fsp3", "Fraction sp3 Carbon", "", "medicinal_chemistry"),
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
    # Moved out of `admet` when the Solubility section arrived: the row and
    # the two calculator buttons that build on it belong under one heading.
    # A button in one section whose answer lands in another is the exact
    # split `docs/NAVIGATION_AUDIT.md` was written about.
    ("esol_logs", "Aqueous Solubility (ESOL, log mol/L)", "", "solubility"),
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

#: The CELL form. Measured in the running application at Segoe UI 9,
#: which is the font a user actually gets -- NOT under `offscreen`, whose
#: default font is more than twice as wide and would have made this look
#: hopeless:
#:
#:     panel width   caption   value cell   this string needs
#:           280       116          120                   118
#:           420       116          230                   118
#:
#: So it fits whole even at the panel's own minimum, by 2 px. That margin
#: is thin on purpose rather than by luck: past it the label ELIDES and
#: the tooltip still carries the reason, which is the same graceful
#: degradation `_ELIDED_LABEL_MIN_WIDTH` documents for captions. What it
#: must never do again is be a sentence.
_NEEDS_CONFORMER_SUMMARY = "Needs a 3D conformer"

#: The full explanation, for the hover and for "Copy all".
#:
#: **ASCII, and the previous wording was not.** It carried an em dash and
#: a U+25B8 triangle as the menu separator, and result text reaches
#: Windows console streams -- `regulatory/calculator.py` records the rule
#: and `_without_glyphs` enforces it on the glyph side. Measured on this
#: string: the em dash raises under cp437 and cp850, and the TRIANGLE
#: raises under cp1252 as well, so it was unprintable on every Windows
#: console codepage rather than only the DOS ones. `>` is the separator
#: `_PKA_NOT_INSTALLED_MESSAGE` already uses for "Tools > External Tools".
_NEEDS_CONFORMER_ERROR = (
    "This descriptor is measured from a real 3D conformer, and this molecule "
    "has only a flat 2D drawing. Generate one with "
    "Structure > Generate Conformers..."
)

_sascorer_module: ModuleType | None = None


def _load_sascorer() -> ModuleType:
    """Ertl & Schuffenhauer's SA score [source:ertl2009], via RDKit.

    **NOT THE PAPER'S IMPLEMENTATION, AND sascorer.py SAYS SO ITSELF**: its
    header records a different macrocyclic penalty and an added symmetry
    term, and puts agreement with Ertl's original at r2 = 0.97 rather than
    1.0. So the paper is the definition and this is the implementation --
    do not gate the shipped number on the paper's printed values.

    Dynamically imports RDKit's own bundled synthetic-accessibility
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


_npscorer_module: ModuleType | None = None
_np_model: dict | None = None

#: Why a zero-confidence NP-likeness is refused rather than reported as 0.0.
#: Not a rounding statement -- `scoreMolWConfidence` sums `fscore[bit]` only
#: over fragments PRESENT in the model, so a molecule sharing none of them
#: scores exactly 0.0 arithmetically. The scalar alone cannot distinguish
#: "balanced" from "recognised nothing", which is the `AlertResult`
#: empty-versus-FAILED distinction in a new place.
#: THE CELL FORM AND THE FULL ONE, which is what `error_summary` bought.
#:
#: This was ONE string for exactly one commit, and it was the short one:
#: the panel wrote a single field into both the value cell and its tooltip,
#: the cell is about 100 px at the dock's minimum width, and the first draft
#: was cut mid-word at "None of this molecule's fragments ap" in the running
#: app. The reasoning had to move into this module and
#: [source:npscorer2015], where a USER never reads it.
#:
#: With the pair, the cell keeps the fact and the hover gets the reason back.
_NP_NO_KNOWN_FRAGMENTS_SUMMARY = "Not in the training corpus"
_NP_NO_KNOWN_FRAGMENTS_ERROR = (
    "None of this molecule's fragments appear in the NP-likeness training "
    "corpus, so no score can be given -- an unfound fragment contributes "
    "nothing to the sum, so a reported 0.00 would be arithmetic rather than "
    "a measurement. The confidence beside this row is 0.00 for the same "
    "reason."
)

#: The cell text when an element is outside McGowan's published set; the
#: hover is the refusal's own sentence, which names the element. Its own
#: block, not inserted above the NP pair: that is how a `#:` comment ends up
#: documenting the wrong constant (`tests/test_constant_docs.py`).
_MCGOWAN_OUTSIDE_SET_SUMMARY = "Element outside McGowan's set"


def _load_npscorer() -> tuple[ModuleType, dict]:
    """Ertl's NP-likeness [source:ertl2008], via RDKit's own re-fit model.

    **NOT THE PAPER'S MODEL, AND npscorer.py SAYS SO ITSELF**
    [source:npscorer2015]: its header records ~50,000 natural products from
    open databases against ~1M ZINC molecules as background, "for the
    training of this model only openly available data have been used", dated
    2015. The 2008 paper's model was Novartis's. For a BAYESIAN score the
    corpus is part of what the number means, so the paper is the method and
    this is a different fit of it -- do not gate the shipped number on the
    paper's printed values. Same split as `vogel_drago1996`'s
    `_parameter_scale`.

    **THE API IS NOT `_load_sascorer`'s, AND COPYING THAT PATTERN RAISES.**
    `npscorer` has no `calculateScore` -- that name belongs to `sascorer`.
    Its surface is `readNPModel()` / `scoreMol(mol, fscore)` /
    `scoreMolWConfidence(mol, fscore)`, and the model is a SECOND argument
    that must be loaded first, where the SA scorer loads its own data on
    import. Measured: 0.09 s for 266,104 fragments, so both are cached at
    module level.

    **`readNPModel` PRINTS TO STDERR, NOT STDOUT** -- `print(..., file=sys.stderr)`
    inside RDKit's Contrib script, "reading NP model ..." then "model in".
    Harmless in a notebook and console noise in a GUI process, so it is
    captured here rather than by editing RDKit. **The stream was measured
    rather than assumed**: a `redirect_stdout` written first captured nothing
    and the lines still appeared, which is the whole reason this sentence
    names the stream. Suppressed only around the load; a real exception still
    propagates.

    Reached exactly as `_load_sascorer` reaches the SA scorer -- via
    `RDConfig.RDContribDir`, never vendored, so this only ever reuses
    RDKit's own code.
    """
    global _npscorer_module, _np_model
    if _npscorer_module is not None and _np_model is not None:
        return _npscorer_module, _np_model
    from rdkit import RDConfig

    contrib_dir = f"{RDConfig.RDContribDir}/NP_Score"
    if contrib_dir not in sys.path:
        sys.path.append(contrib_dir)
    _npscorer_module = import_module("npscorer")
    with contextlib.redirect_stderr(io.StringIO()):
        _np_model = _npscorer_module.readNPModel()
    return _npscorer_module, _np_model


_pains_catalog: FilterCatalog | None = None


def _load_pains_catalog() -> FilterCatalog:
    """Baell & Holloway's PAINS filters [source:baell2010], via RDKit.

    Cached at module level -- building the catalog (480 entries, confirmed
    live) isn't free and its contents never change at runtime.

    A HIT IS A STATEMENT ABOUT ASSAY INTERFERENCE, not about toxicity or
    activity: these are substructures that turn up as frequent hitters
    across unrelated assays."""
    global _pains_catalog
    if _pains_catalog is None:
        params = FilterCatalogParams()
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
        _pains_catalog = FilterCatalog(params)
    return _pains_catalog


_brenk_catalog: FilterCatalog | None = None


def _load_brenk_catalog() -> FilterCatalog:
    """Brenk et al. 2008's [source:brenk2008] catalog of reactive/unstable/toxicophore-
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


def compute_fragment_group_alert(mol: Chem.Mol, molecule_uuid: str) -> AlertResult:
    """How many of each structural feature and ring system `mol` has.

    **THE FRAGMENT COUNTS PROJECTION of the canonical feature set** (vocabulary
    v3, `chem/structure_annotation.canonical_features`) -- the same detection
    Functional Groups draws, counted rather than drawn. A lactam is counted as
    a lactam and not ALSO as an amide; an acetal's oxygens are not also two
    ethers; a carboxylate is counted under its own label, not as the acid.

    UNTIL 2026-09-18 THIS WAS 24 OF RDKIT'S `fr_*` COUNTERS, a second
    definition of the same features, and measured it disagreed with the
    first in ways a reader would take for chemistry: an imine, oxime, azo
    group, nitro group, azide, isocyanate or pyridine N counted as a
    "Tertiary Amine" (caffeine: four), urea's NH2 and an amide N counted as
    amines, a lactone and an anhydride counted as esters plus an ether, an
    acetate as a carboxylic acid, DMSO as nothing (FG-001..FG-009 in
    `tests/test_feature_known_defects.py`). A stored result of that method
    is kept and labelled as it (`result_store.LEGACY_METHOD_VERSIONS`).

    NAMED FOR ITS HISTORY, not for what it reports: it was once called
    `compute_functional_groups`, which shadowed the same-named import from
    `chem/structure_annotation` so the registered `functional_groups`
    calculator bound this two-argument alert and raised for every molecule.
    """
    canonical = canonical_features(mol)
    counted: dict[tuple[str, str], int] = {}
    for projected in project(canonical.features, Projection.FRAGMENT_COUNTS):
        if projected.treatment is ObjectTreatment.HIDDEN:
            continue
        key = (projected.feature.feature_id, projected.feature.label)
        counted[key] = counted.get(key, 0) + 1
    rings: dict[str, int] = {}
    for ring in canonical.rings:
        name = f"{ring.name or ring.kind} ring"
        rings[name] = rings.get(name, 0) + 1
    # Declared vocabulary order (the instances arrive in it), then rings by
    # name: deterministic whatever the atom order.
    matched = [f"{label} ({n})" for (_fid, label), n in counted.items()]
    matched += [f"{name} ({n})" for name, n in sorted(rings.items())]
    # **STILL AN `AlertResult`.** This is a report wearing an alert's clothes,
    # but it is published through the ALWAYS-ON channel, and that channel is
    # typed: `descriptor_service` sends every `compute_alerts` result out as an
    # `AlertComputed`, and both `_on_alert_computed` and
    # `batch_service._run_alerts` read `alert_id`, which a `ReportResult`
    # does not have.
    return AlertResult(
        # **RENAMED FROM `functional_groups`, WHICH THE REGISTERED CALCULATOR
        # OF THAT ID ALSO USED**, so the two shared one store slot and each
        # replaced the other. `result_store.migrate_legacy_result_id` re-files
        # an old stored entry; `test_result_ids_are_unique` stops the next one.
        alert_id="fragment_counts",
        name="Fragment Counts",
        molecule_uuid=molecule_uuid,
        matched=matched,
        provenance=Provenance(
            created_by="core",
            method=FRAGMENT_COUNTS_METHOD,
            parameters={
                "vocabulary_version": VOCABULARY_VERSION,
                "counts": {f"{fid}|{label}": n for (fid, label), n in counted.items()},
                "rings": rings,
            },
        ),
        # **`substructure`, MATCHING THE CALCULATOR OF THE SAME ID.** It once
        # said `admet`, filing one result in two sections depending on which
        # producer answered; `test_a_calculators_result_lands_in_its_own_section`.
        category="substructure",
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


def _gasteiger_total(mol: Chem.Mol, include_hydrogens: bool) -> dict[str, Any]:
    """The declared total for a Gasteiger dataset.

    "NET CALCULATED CHARGE", NOT "FORMAL CHARGE", and the distinction is
    deliberate rather than fussy. PEOE conserves total charge, so with the
    hydrogens included the sum does equal the formal charge exactly --
    measured to 1e-6 on an anion, a cation, a zwitterion and a neutral
    molecule:

        acetate  -1.000000 / -1     ammonium   +1.000000 / +1
        glycine  -0.000000 /  0     aspirin    -0.000000 /  0

    But what was COMPUTED is a sum of calculated partial charges, and that
    it coincides with a graph property is a fact about the method rather
    than the thing measured. Labelling it "formal charge" would smuggle an
    imprecise chemistry definition into metadata whose entire purpose is to
    stop the UI inventing meanings -- the same mistake in a new place.

    THE TOTAL IS ALWAYS THE WHOLE MOLECULE'S, never the visible atoms'
    sum, and that is the load-bearing choice. RDKit keeps each heavy atom's
    implicit-H charge in a separate property, so with the hydrogens
    excluded neutral aspirin's visible atoms sum to -0.6555 -- and
    declaring THAT as the net charge would print exactly the number this
    whole change exists to stop printing. The molecule's net charge does
    not depend on which of its atoms are on screen; the gap does, and the
    gap is what gets explained.
    """
    total = declare_total(
        sum(compute_gasteiger_charges(Chem.Mol(mol), include_hydrogens=True).values()),
        "Net calculated charge",
        units="e",
    )
    if not include_hydrogens:
        total["balance"] = {
            "visible_basis": "heavy-atom charges",
            "explanation": "implicit hydrogens",
        }
    return total


#: The always-on descriptors that describe the DRAWING rather than the
#: compound: ChEMBL computes exactly these two on the full salt (FULL_MWT,
#: FULL_MOLFORMULA), and exact mass and net charge are the same kind of
#: statement about what was drawn.
_WHOLE_DESCRIPTORS = frozenset({"mol_wt", "exact_mass", "formula", "formal_charge"})
#: The always-on descriptors that describe the drawing (`_WHOLE_DESCRIPTORS`).
_DESCRIPTOR_WHOLE_SCOPE = CalculatorScope(
    ComponentSelection.WHOLE_STRUCTURE, Aggregation.SCALAR,
    note="ChEMBL's FULL_MWT and FULL_MOLFORMULA: the drawing, salt and all")
#: The always-on alerts and Gasteiger charges: a substructure alert on a
#: counter-ion is true of the substance (maleate IS a Michael acceptor), and
#: charge equalisation runs within each component.
_ALERT_SCOPE = CalculatorScope(
    ComponentSelection.EACH_COMPONENT, Aggregation.COLLECTION,
    note="an alert on any component is true of the substance")
#: The always-on Gasteiger charges: equalisation runs within each component.
_GASTEIGER_SCOPE = CalculatorScope(
    ComponentSelection.EACH_COMPONENT, Aggregation.PER_ATOM,
    note="equalisation runs within each component")
#: Every other always-on descriptor: a compound property, on the parent.
_DESCRIPTOR_PARENT_SCOPE = CalculatorScope(
    ComponentSelection.CHEMBL_PARENT, Aggregation.SCALAR,
    note="every other descriptor is a property of the compound (ChEMBL COMPOUND_PROPERTIES)")


def _refused_descriptor(value: DescriptorValue, refusal: CalculationRefusal) -> DescriptorValue:
    provenance = value.provenance
    parameters = {**(provenance.parameters if provenance else {}), "refusal": refusal.code}
    return replace(
        value, value=None, cache_state=CacheState.FAILED, error=refusal.detail,
        error_summary=refusal.summary, inapplicable=refusal.inapplicable,
        provenance=replace(provenance, parameters=parameters) if provenance else None,
    )


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
        """The descriptor set, each on the structure its scope names.

        `_WHOLE_DESCRIPTORS` describe the drawing -- ChEMBL's FULL_MWT and
        FULL_MOLFORMULA -- and everything else the ChEMBL parent, which for
        a single component IS the drawing. A salt whose parent is refused
        (sodium acetate: every component a listed salt) gets those
        descriptors as coded, inapplicable refusals rather than numbers
        about Na+ and acetate together.
        """
        whole = [
            components.as_drawn(value, _DESCRIPTOR_WHOLE_SCOPE, mol)
            if value.descriptor_id in _WHOLE_DESCRIPTORS else value
            for value in self._compute_all(mol, molecule_uuid)
        ]
        try:
            selection = components.select(mol, _DESCRIPTOR_PARENT_SCOPE, "This descriptor")
        except CalculationRefusal as refusal:
            return [
                value if value.descriptor_id in _WHOLE_DESCRIPTORS
                else _refused_descriptor(value, refusal)
                for value in whole
            ]
        on_parent = whole if selection.drawing_atoms is None else self._compute_all(selection.mol, molecule_uuid)
        by_id = {value.descriptor_id: value for value in on_parent}
        return [
            value if value.descriptor_id in _WHOLE_DESCRIPTORS
            else components.read_back(by_id[value.descriptor_id], _DESCRIPTOR_PARENT_SCOPE, selection)
            for value in whole
        ]

    def _compute_all(self, mol: Chem.Mol, molecule_uuid: str) -> list[DescriptorValue]:
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

        # ESOL lives in `chem/solubility.py` now, because the solubility
        # calculators need the identical number as their baseline and two
        # copies of a fitted regression is two chances to drift.
        esol_logs = _esol_logs(mol)
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

        # ONE call for both halves: `scoreMolWConfidence` returns them
        # together, and computing the score and the confidence separately
        # would fingerprint the molecule twice for one answer.
        _npscorer, _np_fscore = _load_npscorer()
        np_result = _npscorer.scoreMolWConfidence(mol, _np_fscore)

        # A descriptor whose value would be arithmetic rather than a
        # measurement is FAILED with a reason, following the shape
        # descriptors' `_NEEDS_CONFORMER_ERROR` path. The CONFIDENCE is
        # still reported -- 0.000 is a real statement about the molecule,
        # and blanking it too would hide why the score is absent.
        # (summary for the cell, full explanation for the hover) -- the pair
        # `describe_failure` reads. A producer writing only one gets today's
        # behaviour, so this carries both deliberately.
        refusals: dict[str, tuple[str, str]] = {}
        #: The declared code of each refusal, for `provenance.parameters`.
        refusal_codes: dict[str, str] = {}
        if np_result.confidence == 0.0:
            refusals["np_likeness"] = (
                _NP_NO_KNOWN_FRAGMENTS_SUMMARY,
                _NP_NO_KNOWN_FRAGMENTS_ERROR,
            )
            refusal_codes["np_likeness"] = "NO_KNOWN_FRAGMENTS"
            # Nothing in the drawing to fix: the corpus has none of it.
            inapplicable_np = True
        else:
            inapplicable_np = False
        #: Refusals that are a LIMIT OF THE METHOD rather than a fault
        #: (`DescriptorValue.inapplicable`): nothing the user can fix.
        inapplicable: set[str] = set()
        # **THE McGOWAN SET IS TWELVE ELEMENTS, AND ONE SODIUM TOOK EVERYTHING
        # WITH IT.** It raised inside the dict below, so the whole provider
        # failed and a sodium salt got no descriptor at all -- and, because the
        # service returned early, no alert and no per-atom data either
        # (measured 2026-09-18, driving master on sodium acetate). A method
        # that does not cover an element refuses ITSELF.
        try:
            mcgowan = _mcgowan_volume(mol)
        except ValueError as exc:
            mcgowan = None
            refusals["mcgowan_volume"] = (_MCGOWAN_OUTSIDE_SET_SUMMARY, str(exc))
            refusal_codes["mcgowan_volume"] = ELEMENT_OUTSIDE_PARAMETER_SET
            inapplicable.add("mcgowan_volume")
        if inapplicable_np:
            inapplicable.add("np_likeness")

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
            "mcgowan_volume": mcgowan,
            "qed": QED.qed(mol),
            "sa_score": _load_sascorer().calculateScore(mol),
            "np_likeness": np_result.nplikeness,
            "np_likeness_confidence": np_result.confidence,
            "bertz_ct": GraphDescriptors.BertzCT(mol),
            "fsp3": Descriptors.FractionCSP3(mol),
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
                value=None if descriptor_id in refusals else raw_values[descriptor_id],
                timestamp=now,
                cache_state=(
                    CacheState.FAILED
                    if descriptor_id in refusals
                    else CacheState.COMPLETED
                ),
                error=(
                    refusals[descriptor_id][1] if descriptor_id in refusals else None
                ),
                error_summary=(
                    refusals[descriptor_id][0] if descriptor_id in refusals else None
                ),
                inapplicable=descriptor_id in inapplicable,
                provenance=(
                    replace(provenance, parameters={"refusal": refusal_codes[descriptor_id]})
                    if descriptor_id in refusal_codes else provenance
                ),
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
                    error_summary=_NEEDS_CONFORMER_SUMMARY,
                    # A fault with a remedy (generate a conformer), coded so
                    # a view need not read it out of the sentence.
                    provenance=replace(provenance, parameters={"refusal": "NEEDS_CONFORMER"}),
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
            "fragment_counts": "Fragment Counts",
            "herg_risk_factors": _HERG_RISK_NAME,
            "mutagenicity_alerts": MUTAGENICITY_ALERT_NAME,
        }

    def compute_alerts(self, mol: Chem.Mol, molecule_uuid: str) -> list[AlertResult]:
        """The five catalogs, each recorded as read over every component."""
        return [components.as_drawn(alert, _ALERT_SCOPE, mol) for alert in self._compute_alerts(mol, molecule_uuid)]

    def _compute_alerts(self, mol: Chem.Mol, molecule_uuid: str) -> list[AlertResult]:
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
        """The always-on batch. Not registry-driven, so it takes no
        parameters and is fixed at `HEAVY_ATOMS_ONLY` -- the registered
        calculators are where a hydrogen mode can be chosen.

        Each dataset still DECLARES its total, for the same reason the
        registered ones do: nothing downstream may derive one, and this
        batch feeds the same Calculator Inspector.

        **AND EACH DECLARES ITS CATEGORY, because this batch is not in
        the registry the panel would otherwise ask.** Two of the three
        used to resolve anyway and did so BY COINCIDENCE -- a registered
        calculator happens to share their id, offering a hydrogen mode
        this batch is fixed on. `gasteiger_charge` has no such twin (the
        registered one is `gasteiger_charge_at_ph`), so it fell through
        to a generic "Other" section it was the sole occupant of.
        Declaring all three makes the two that worked deliberate rather
        than lucky.
        """
        # Wildman-Crippen atom typing [source:wildman1999] -- 68 atomic
        # logP contributions and a separate MR set, via RDKit.
        #
        # On EVERY component, as atom-local table look-ups (round 5 scope,
        # `_EACH_CONTRIBUTION`): each atom's type is defined wherever it is
        # drawn. The scalar logP beside them is the parent's; on a salt the two
        # therefore describe different structures, and each says which.
        contribs = rdMolDescriptors._CalcCrippenContribs(mol)
        logp_contrib = {idx: logp for idx, (logp, _mr) in enumerate(contribs)}
        mr_contrib = {idx: mr for idx, (_logp, mr) in enumerate(contribs)}
        gasteiger_charge = compute_gasteiger_charges(mol)

        def batch_provenance(declaration: dict) -> Provenance:
            return Provenance(
                created_by="core",
                method=self.provider_id,
                parameters={ATOM_BASIS: HEAVY_ATOMS, TOTAL: declaration},
            )

        heavy_atom_balance = {
            "visible_basis": "heavy-atom contributions",
            "explanation": "implicit hydrogens",
        }
        gasteiger = components.as_drawn(PerAtomDataset(
            property_id="gasteiger_charge",
            name="Partial Charge (Gasteiger)",
            category="charge",
            units="e",
            method=self.provider_id,
            molecule_uuid=molecule_uuid,
            values=gasteiger_charge,
            provenance=batch_provenance(_gasteiger_total(mol, include_hydrogens=False)),
        ), _GASTEIGER_SCOPE, mol)
        logp_total = declare_total(Crippen.MolLogP(mol), "LogP (Crippen)")
        logp_total["balance"] = heavy_atom_balance
        mr_total = declare_total(Crippen.MolMR(mol), "Molar refractivity (Crippen)")
        mr_total["balance"] = heavy_atom_balance

        return [components.as_drawn(dataset, _EACH_CONTRIBUTION, mol) for dataset in (
            PerAtomDataset(
                property_id="crippen_logp_contrib",
                name="LogP Contribution (Crippen)",
                category="lipophilicity",
                units="",
                method=self.provider_id,
                molecule_uuid=molecule_uuid,
                values=logp_contrib,
                provenance=batch_provenance(logp_total),
            ),
            PerAtomDataset(
                property_id="crippen_mr_contrib",
                name="Molar Refractivity Contribution (Crippen)",
                category="electronic",
                units="",
                method=self.provider_id,
                molecule_uuid=molecule_uuid,
                values=mr_contrib,
                provenance=batch_provenance(mr_total),
            ),
        )] + [gasteiger]


# --- Phase 18: CalculatorRegistry-registered calculators --------------------
# Each function matches CalculatorRegistry's compute signature
# (mol, molecule_uuid, parameters) -> ScientificResult. Registered against
# CALCULATOR_DEFINITIONS in bootstrap.build_service_container() rather than
# here, keeping this module's job "know how to compute things," not "know
# about the registry."


def _microspecies_note(drawn: Chem.Mol, species, ph: float) -> str:
    """One sentence naming the species the charges belong to, or "".

    SILENT WHEN NOTHING CHANGED, deliberately. A molecule with no
    ionizable centre is charged exactly as drawn, and a line saying so on
    every neutral result is noise given a voice -- the same tolerance
    discipline `_balance_text` applies to a balance of 1e-16.
    """
    drawn_charge = Chem.GetFormalCharge(drawn)
    if species.formal_charge == drawn_charge:
        return ""
    note = (
        f"Computed on the dominant microspecies at pH {ph:g}, which carries "
        f"a net charge of {species.formal_charge:+d} -- the structure as "
        f"drawn is {drawn_charge:+d}."
    )
    if species.corrected_atoms:
        note += (
            " An amide-like nitrogen reported as protonated was corrected:"
            " its lone pair is delocalised into the adjacent carbonyl, so"
            " it is not a base at this pH."
        )
    return note


#: Gasteiger-Marsili PEOE, the charge calculator's original and default
#: method. A STORED code: the settings dialog shows `CHARGE_METHOD_LABELS`.
GASTEIGER = "gasteiger"
#: Halgren's MMFF94 bond-charge-increment charges, validated against his
#: Table V. A stored code, like `GASTEIGER`.
MMFF94 = "mmff94"
#: Every method the pH-dependent charge calculator offers, in the order its
#: combo box lists them. Anything else is refused rather than defaulted.
CHARGE_METHODS = (GASTEIGER, MMFF94)
#: What each method is called on screen and in a result's name.
CHARGE_METHOD_LABELS = {GASTEIGER: "Gasteiger", MMFF94: "MMFF94"}

#: How far an MMFF94 charge set may miss the formal charge before it is
#: refused. MMFF charges are formal charges redistributed by bond
#: increments, so the sum is exact up to float noise: measured 0 to 1e-15 on
#: every molecule and ion of Halgren's Table V.
_MMFF_CONSERVATION_TOLERANCE = 1e-6


def compute_mmff94_charges(
    mol: Chem.Mol, include_hydrogens: bool = False
) -> tuple[dict[int, float], float] | None:
    """MMFF94 partial charges keyed to `mol`'s own atom indices, and the sum
    over EVERY atom -- or None when MMFF94 cannot type the molecule.

    **WHAT A "FOLDED" VALUE IS, stated because it is not an MMFF94 charge.**
    MMFF94 assigns charges to every atom, hydrogens included, and needs the
    hydrogens present to type anything. `mol` holds hydrogens implicitly, so
    they are added (`AddHs` appends, which keeps every existing index), and:

        include_hydrogens=False   each atom's own MMFF94 charge; the added
                                  hydrogens' charges are not reported
        include_hydrogens=True    each atom's own charge PLUS the charges of
                                  the hydrogens added to it -- an aggregation
                                  this application performs, the same one
                                  Gasteiger's "Increment of Hs" performs

    A hydrogen the drawing holds as an ATOM keeps its own index and value in
    both modes; only hydrogens this function added are folded.

    Validated against Halgren (1996) part II Table V
    [source:halgren1996_mmff2] -- every charge and atom type of the atoms it
    prints, for 19 of 20 molecules and ions, and the 20th disagrees with the
    table's own acetate row. Reached through RDKit's port
    [source:tosco2014]. See `tests/test_mmff94_charges.py`.
    """
    from rdkit.Chem import rdForceFieldHelpers

    count = mol.GetNumAtoms()
    full = Chem.AddHs(Chem.Mol(mol))
    properties = rdForceFieldHelpers.MMFFGetMoleculeProperties(full)
    if properties is None:
        return None
    every = [properties.GetMMFFPartialCharge(i) for i in range(full.GetNumAtoms())]
    values = {i: every[i] for i in range(count)}
    if include_hydrogens:
        for index in range(count, full.GetNumAtoms()):
            parent = full.GetAtomWithIdx(index).GetNeighbors()[0].GetIdx()
            values[parent] += every[index]
    return values, sum(every)


def compute_gasteiger_charge_at_ph(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any], interpreter_path: str | None = None
) -> PerAtomDataset:
    """The "charge" category's calculator. Protonates `mol` to the
    pH-appropriate dominant microspecies via Dimorphite-DL
    (`chem.pka_providers.protonate_at_ph`) before computing partial
    charges, so the result reflects that pH's ionization state rather than
    whatever protonation state the molecule happened to be drawn in.

    **THE METHOD IS A PARAMETER, AND THE ID DID NOT CHANGE WITH IT.** Named
    for Gasteiger because that was its only method; renaming it would orphan
    every stored result for no gain. The result's NAME and provenance carry
    the method, and `parameters_key` -- part of every stored identity --
    carries it too, so a Gasteiger result is never served as an MMFF94 one.
    Like every other parameter in this application, running it again with a
    different method REPLACES the previous result rather than adding one.

    **THE SPECIES IS DIMORPHITE-DL'S, AND IT SAYS WHERE PKASOLVER DIFFERS.**
    With a pkasolver environment configured (`interpreter_path`), the
    ionization-model cross-check sets its per-site prediction against this
    species and names any disagreement in the summary. It changes no charge:
    the values are computed on the species exactly as without it.
    """
    _places = decimals(parameters)
    from openchem.chem.pka_providers import cross_check_lines, cross_check_record, dominant_microspecies

    ph = parameters.get("pH", 7.4)
    include_hydrogens = bool(parameters.get("include_hydrogens", False))
    method = str(parameters.get("method", GASTEIGER))
    if method not in CHARGE_METHODS:
        raise ValueError(f"Unknown charge method {method!r}; expected one of {CHARGE_METHODS}")
    label = CHARGE_METHOD_LABELS[method]
    species = dominant_microspecies(mol, ph)
    protonated = species.mol
    suffix = " incl. H" if include_hydrogens else ""
    name = f"Partial Charge ({label}) at pH {ph:g}{suffix}"
    if method == MMFF94:
        computed = compute_mmff94_charges(protonated, include_hydrogens=include_hydrogens)
        if computed is None:
            # A LIMIT OF THE METHOD, not a fault: MMFF94 has no atom type for
            # something in this structure, and nothing the user does short
            # of changing the molecule will give it one.
            return PerAtomDataset(
                property_id="gasteiger_charge_at_ph", name=name, units="e",
                method="rdkit-mmff94+dimorphite_dl", molecule_uuid=molecule_uuid,
                cache_state=CacheState.FAILED, inapplicable=True,
                error="MMFF94 has no atom type for part of this structure.",
                error_summary="Not covered by MMFF94",
            )
        charges, every_atom = computed
        formal = Chem.GetFormalCharge(protonated)
        # CONSERVATION, CHECKED RATHER THAN ASSUMED. A dropped or doubled
        # hydrogen in the folding above would still produce plausible
        # numbers; it would not produce the right sum.
        if abs(every_atom - formal) > _MMFF_CONSERVATION_TOLERANCE or (
            include_hydrogens and abs(sum(charges.values()) - formal) > _MMFF_CONSERVATION_TOLERANCE
        ):
            raise ValueError(
                f"MMFF94 charges sum to {every_atom:+.6f} on a species of formal charge {formal:+d}"
            )
        total = declare_total(every_atom, "Net calculated charge", units="e")
        if not include_hydrogens:
            total["balance"] = {
                "visible_basis": "heavy-atom charges",
                "explanation": "implicit hydrogens",
            }
        provenance_method = "rdkit-mmff94+dimorphite_dl"
    else:
        charges = compute_gasteiger_charges(protonated, include_hydrogens=include_hydrogens)
        total = _gasteiger_total(protonated, include_hydrogens=include_hydrogens)
        provenance_method = "rdkit+dimorphite_dl"
    # AFTER the charges: nothing above reads it, which is what "changes no
    # number" rests on.
    cross_check = _cross_check_species(mol, protonated, ph, interpreter_path)
    return PerAtomDataset(
        property_id="gasteiger_charge_at_ph",
        name=name,
        units="e",
        method=provenance_method,
        molecule_uuid=molecule_uuid,
        values=charges,
        provenance=Provenance(
            created_by="core",
            method=provenance_method,
            parameters={
                "pH": ph,
                "include_hydrogens": include_hydrogens,
                "charge_method": method,
                # WHAT A VALUE IS, beside which method made it: "folded" is
                # an atom's charge plus its implicit hydrogens', which this
                # application sums -- not a quantity either method defines.
                "hydrogen_aggregation": "folded" if include_hydrogens else "separate",
                "decimal_places": _places,
                ATOM_BASIS: HEAVY_ATOMS,
                # THE PRODUCER SAYS WHICH SPECIES IT CHARGED, because the
                # view cannot work it out and must not try. Reading
                # `total - formal_charge(drawn)` and concluding "so it was
                # protonated" is a mechanism invented from a residual,
                # which is the mistake `_balance_text` already refuses.
                #
                # Reported as a fact rather than as prose about a fact: a
                # neutral molecule whose charges are computed on a +1 cation
                # is the whole reason "Net calculated charge: 1.00 e" sat
                # beside a panel reading "Total charge 0" and read as a bug.
                "summary": " ".join(
                    part for part in (_microspecies_note(mol, species, ph), *cross_check_lines(cross_check, ph))
                    if part
                ),
                # From the PROTONATED molecule, which is the one whose
                # charges these are -- taking it from `mol` would report the
                # drawn structure's net charge beside values computed for a
                # different ionization state.
                TOTAL: total,
                **cross_check_record(cross_check),
            },
        ),
    )


def _cross_check_species(mol: Chem.Mol, species: Chem.Mol, ph: float, interpreter_path: str | None):
    """The ionization-model cross-check for a species a calculator already built.

    Takes the species rather than building one, so a calculator that computed
    on it compares exactly that species. pkasolver's answer comes through
    `compute_pka`'s kept payloads, so a structure asked about by logD,
    solubility or pKa already costs nothing here.
    """
    from openchem.chem.pka_providers import (
        IonizationCrossCheck,
        compute_pka,
        ionization_model_cross_check,
        pka_predictor_available,
    )

    if not pka_predictor_available(interpreter_path):
        return IonizationCrossCheck(status="not configured")
    try:
        predictions = compute_pka(mol, interpreter_path) or []
    except RuntimeError as exc:
        return IonizationCrossCheck(status=f"failed: {exc}")
    return ionization_model_cross_check(species, predictions, ph)


def crippen_contributions(mol: Chem.Mol, mode: str, want_mr: bool = False) -> tuple[dict[int, float], str]:
    """Per-atom Crippen contributions under one hydrogen mode, plus the
    `ATOM_BASIS` the result is keyed to.

    THE SUM OF THE HEAVY-ATOM CONTRIBUTIONS IS NOT THE MOLECULE'S LogP, and
    that discrepancy is what this whole option exists for. Crippen types
    hydrogens (H1..HS) and gives each its own increment, so on the
    implicit-hydrogen structure the editor draws, every one of those
    increments has no atom to sit on and is simply absent. Measured:

        molecule   heavy-atom sum   folded    Crippen.MolLogP
        ethanol          -0.3487   -0.0014            -0.0014
        benzene           0.9486    1.6866             1.6866
        aspirin           0.1511    1.3101             1.3101
        caffeine         -2.2593   -1.0293            -1.0293
        morphine         -0.3575    1.1981             1.1981

    So `INCREMENT_OF_HS` and `EXPLICIT_HYDROGENS` both reproduce `MolLogP`
    exactly (to 1e-9); `HEAVY_ATOMS_ONLY` does not, and is still the default
    because it is what the atoms on screen actually carry.

    `AddHs` APPENDS, so heavy-atom indices 0..n-1 are unchanged in every
    mode -- which is what lets the fold address `values[parent]` directly
    and what keeps a 2D depiction of the drawing valid for two of the three
    modes. `EXPLICIT_HYDROGENS` is the one that needs a depiction of its
    own, which is why it declares a different basis rather than relying on
    the caller to notice the atom count changed.
    """
    which = 1 if want_mr else 0
    if mode == HEAVY_ATOMS_ONLY:
        contribs = rdMolDescriptors._CalcCrippenContribs(mol)
        return {idx: pair[which] for idx, pair in enumerate(contribs)}, HEAVY_ATOMS

    with_h = Chem.AddHs(mol)
    contribs = [pair[which] for pair in rdMolDescriptors._CalcCrippenContribs(with_h)]
    if mode == EXPLICIT_HYDROGENS:
        return dict(enumerate(contribs)), EXPLICIT_H

    values = {idx: contribs[idx] for idx in range(mol.GetNumAtoms())}
    for atom in with_h.GetAtoms():
        if atom.GetAtomicNum() == 1:
            # A hydrogen added by AddHs has exactly one neighbour by
            # construction. A hydrogen the user drew EXPLICITLY is already in
            # `mol` and so keeps its own entry above rather than being folded
            # twice -- the loop only reaches indices past `mol.GetNumAtoms()`
            # for those, and `values[parent]` for a parent that is itself a
            # drawn hydrogen would be a molecule nobody draws.
            if atom.GetIdx() < mol.GetNumAtoms():
                continue
            values[atom.GetNeighbors()[0].GetIdx()] += contribs[atom.GetIdx()]
    return values, HEAVY_ATOMS


def _crippen_dataset(
    mol: Chem.Mol,
    molecule_uuid: str,
    parameters: dict[str, Any],
    *,
    property_id: str,
    name: str,
    total_label: str,
    want_mr: bool,
) -> PerAtomDataset:
    """The two Crippen calculators differ only in which half of RDKit's
    `(logp, mr)` pair they read, so they share everything else -- including
    the declaration, which must be computed HERE from the same `mol` the
    values came from. A total assembled anywhere else could outlive a
    parameter change and describe the previous run."""
    mode = hydrogen_mode(parameters)
    values, basis = crippen_contributions(mol, mode, want_mr=want_mr)
    # RDKit's own molecular routine, not a sum of the values above -- so the
    # headline stays right even in the mode whose atoms deliberately do not
    # add up to it, and so a broken fold shows as a stated balance rather
    # than as a quietly wrong total.
    total = Crippen.MolMR(mol) if want_mr else Crippen.MolLogP(mol)
    declaration = declare_total(total, total_label, units="", basis=basis)
    if mode == HEAVY_ATOMS_ONLY:
        # The producer supplies only the INTERPRETATION of the gap; the view
        # subtracts. Saying "the balance is implicit hydrogens" is a
        # chemistry claim and belongs to whoever knows the atom typing --
        # inferring it from `total - sum(values)` would be arithmetic
        # pretending to be a mechanism.
        declaration["balance"] = {
            "visible_basis": "heavy-atom contributions",
            "explanation": "implicit hydrogens",
        }
    return PerAtomDataset(
        property_id=property_id,
        name=name,
        units="",
        method="rdkit",
        molecule_uuid=molecule_uuid,
        values=values,
        provenance=Provenance(
            created_by="core",
            method="rdkit",
            parameters={
                "decimal_places": decimals(parameters),
                "hydrogens": mode,
                ATOM_BASIS: basis,
                TOTAL: declaration,
            },
        ),
    )


def compute_crippen_logp_contrib_calculator(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any]
) -> PerAtomDataset:
    """The "logp" category's calculator -- same Crippen contribution call
    `compute_per_atom` uses for its always-on batch, so the registry-driven
    path and that batch never compute this two different ways."""
    return _crippen_dataset(
        mol,
        molecule_uuid,
        parameters,
        property_id="crippen_logp_contrib",
        name="LogP Contribution (Crippen)",
        total_label="LogP (Crippen)",
        want_mr=False,
    )


def compute_crippen_mr_contrib_calculator(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any]
) -> PerAtomDataset:
    """The "molar_refractivity" category's calculator -- same Crippen
    contribution call `compute_per_atom` uses for its always-on batch."""
    return _crippen_dataset(
        mol,
        molecule_uuid,
        parameters,
        property_id="crippen_mr_contrib",
        name="Molar Refractivity Contribution (Crippen)",
        total_label="Molar refractivity (Crippen)",
        want_mr=True,
    )


#: The CELL form of `_PKA_NOT_INSTALLED_MESSAGE`, which is 344 characters
#: of prose and was being written into a one-line value cell whole.
_PKA_NOT_INSTALLED_SUMMARY = "pkasolver not configured"

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
        return report_from_fields(
            alert_id="pka",
            name="pKa",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="pka",
            provenance=Provenance(created_by="core", method="pkasolver",
                                  parameters={"refusal": SIDECAR_NOT_CONFIGURED}),
            cache_state=CacheState.FAILED,
            error=_PKA_NOT_INSTALLED_MESSAGE,
            error_summary=_PKA_NOT_INSTALLED_SUMMARY,
        )
    try:
        pairs = compute_pka(mol, interpreter_path)
    except RuntimeError as exc:
        return report_from_fields(
            alert_id="pka",
            name="pKa",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="pka",
            provenance=Provenance(created_by="core", method="pkasolver"),
            cache_state=CacheState.FAILED,
            error=str(exc),
        )
    return report_from_fields(
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
            # The DRAWING's number: on a salt the pKa is computed on the
            # ChEMBL parent, whose atoms are renumbered once a counter-ion
            # drawn before it is removed (`chem/components.py`).
            site = f" at {atom.GetSymbol()}{drawing_index(atom)}"
    line = f"pKa {value}{site}"
    if not prediction.stddev:
        return line
    return f"{line} +/- {fmt(prediction.stddev, parameters)} (ensemble spread)"


def compute_logd(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any], interpreter_path: str | None = None
) -> ReportResult:
    """The "logd" category's calculator (Phase 23) -- pH-adjustable
    distribution coefficient, and the curve it lies on.

    Uses real Henderson-Hasselbalch when numeric pKa is available
    (pkasolver, out of process), and clearly says so. Otherwise falls back
    to the LogP of the dominant microspecies at that pH via Dimorphite-DL:
    a real pH-dependent number, but NOT true logD, and labelled as such
    rather than presented as equivalent.

    **THE CURVE WAS A SECOND CALCULATOR, AND IS NOW THIS ONE'S PICTURE.**
    `logd_curve` sampled the same Henderson-Hasselbalch function across pH
    in a separate registration, so reading logD at one pH and seeing where
    it sits on the curve meant running two things. The curve is declared on
    this report now, and `logd_curve` is retired (`RETIREMENTS`).

    **THE SCALAR IS UNCHANGED, BRANCH FOR BRANCH**, and the curve is only
    ADDED. The three branches below pick the number exactly as before; the
    chart is built from the SAME pKa list and the SAME function, with the
    chosen pH inserted as a sample, so the curve at that pH is the scalar
    rather than a neighbour of it. Asserted in `tests/test_logd_report.py`
    against values recorded before the change.

    KNOWN LIMITATION, ZWITTERIONS -- carried over from `compute_logd_curve`:
    Henderson-Hasselbalch assumes the partitioning species has no site
    ionized, which breaks for amphoteric molecules (glycine: about -4.7
    modelled against about -3.2 measured).
    """
    from openchem.chem.logd import classify_ionizable_centres, logd_from_microspecies, logd_from_pkas
    from openchem.chem.pka_providers import (
        IonizationCrossCheck,
        compute_pka,
        cross_check_lines,
        cross_check_record,
        pka_predictor_available,
    )
    from openchem.chem.ph_curves import ph_grid_from
    from openchem.domain.calculator_taxonomy import category_for
    from openchem.domain.report import LineChartAnnotation, LineSeries

    ph = float(parameters.get("pH", 7.4))
    logp = Crippen.MolLogP(mol)
    acids, bases = classify_ionizable_centres(mol)
    category = category_for("lipophilicity")

    def fact(label, value, display, *, evidence=(), limitations=(), source="core"):
        return Fact(
            category=category, label=label, value=value, display_value=display,
            source=source, basis=Basis.HEURISTIC, evidence=tuple(evidence),
            limitations=tuple(limitations),
        )

    def curve(values_at, title):
        grid = sorted(set(ph_grid_from(parameters)) | {ph})
        return LineChartAnnotation(
            series=(LineSeries(points=tuple((x, float(values_at(x))) for x in grid), name="logD"),),
            x_label="pH",
            y_label="logD",
            x_descending=False,
            title=title,
            caption=(
                "Henderson-Hasselbalch on the pKa values listed below. Hover to read logD at a "
                "sampled pH; click to keep the reading. Zwitterions are under-predicted."
            ),
        )

    facts: list[Fact] = []
    charts: tuple = ()
    limitations: list[str] = []
    # Only the Henderson-Hasselbalch branch has pkasolver's predictions to
    # set against the species; the other two say why nothing was compared.
    cross_check = IonizationCrossCheck(status="not configured")
    if acids == 0 and bases == 0:
        method = "rdkit"
        facts.append(fact(
            f"LogD at pH {ph:g}", logp, f"{logp:.2f}",
            evidence=("No ionizable centre, so logD equals LogP at every pH.",),
            source="RDKit",
        ))
        charts = (curve(
            lambda _x: logp,
            "LogD vs pH - no modelled ionizable centre, so logD is pH-independent under this method",
        ),)
    elif pka_predictor_available(interpreter_path):
        try:
            predictions = compute_pka(mol, interpreter_path) or []
        except RuntimeError as exc:
            return ReportResult(
                report_id="logd", name="LogD", molecule_uuid=molecule_uuid, category="lipophilicity",
                provenance=Provenance(created_by="core", method="pkasolver"),
                cache_state=CacheState.FAILED, error=str(exc),
            )
        pkas = [p.value for p in predictions]
        # BESIDE the number, never inside it: the scalar and the curve below
        # read `pkas` exactly as before, and this only says where the
        # Dimorphite-DL species other calculators use lands differently.
        cross_check = ionization_cross_check_for(mol, predictions, ph)
        limitations.extend(cross_check_lines(cross_check, ph))
        value = logd_from_pkas(mol, ph, pkas)
        facts.append(fact(
            f"LogD at pH {ph:g}", value, f"{value:.2f}",
            evidence=("Henderson-Hasselbalch on the predicted pKa values.",),
        ))
        facts.append(fact("LogP", logp, f"{logp:.2f}", evidence=("Crippen fragment method",), source="RDKit"))
        facts.append(fact(
            "pKa", tuple(sorted(pkas)), ", ".join(f"{p:.2f}" for p in sorted(pkas)), source="pkasolver",
        ))
        method = "rdkit+pkasolver"
        # From the SAME list the scalar used, in the same order: the curve at
        # the chosen pH must be the number above, not a re-derived one.
        charts = (curve(lambda x, _p=tuple(pkas): logd_from_pkas(mol, x, list(_p)), "LogD vs pH"),)
        limitations.append(
            "Henderson-Hasselbalch assumes the partitioning species has no site ionized, so it "
            "under-predicts logD for zwitterions (amino acids); monoprotic acids and bases are "
            "unaffected."
        )
    else:
        value = logd_from_microspecies(mol, ph)
        approximation = (
            "Approximation: LogP of the dominant microspecies at this pH (Dimorphite-DL), "
            "not true Henderson-Hasselbalch logD \u2014 configure a pkasolver environment in "
            "Tools > External Tools for real numeric pKa."
        )
        facts.append(fact(
            f"LogD at pH {ph:g} (approximation)", value, f"{value:.2f}",
            limitations=(approximation,),
        ))
        facts.append(fact("LogP", logp, f"{logp:.2f}", evidence=("Crippen fragment method",), source="RDKit"))
        method = "rdkit+dimorphite_dl"
        limitations.append(approximation)
        # NO CURVE on this branch, and the reason is said rather than left
        # as a missing picture: sampling a microspecies' LogP across pH would
        # draw steps between charge states and read as a logD curve.
        limitations.append(
            "No LogD-vs-pH curve without numeric pKa: the approximation is not a curve."
        )

    facts.append(fact("Ionizable centres", (acids, bases), f"{acids} acidic, {bases} basic"))
    return ReportResult(
        report_id="logd",
        name=f"LogD at pH {ph:g}",
        molecule_uuid=molecule_uuid,
        category="lipophilicity",
        facts=tuple(facts),
        charts=charts,
        limitations=tuple(limitations),
        provenance=Provenance(
            created_by="core", method=method, parameters={"pH": ph, **cross_check_record(cross_check)}
        ),
    )


def ionization_cross_check_for(mol: Chem.Mol, predictions, ph: float):
    """Dimorphite-DL's species for `mol` at `ph`, set against `predictions`.

    A species that cannot be built is reported as a FAILED cross-check, never
    as agreement -- and never as a failure of the calculation it sits beside.
    """
    from openchem.chem.pka_providers import (
        IonizationCrossCheck,
        dominant_microspecies,
        ionization_model_cross_check,
    )

    try:
        species = dominant_microspecies(mol, ph).mol
    except Exception as exc:  # noqa: BLE001 - a diagnostic that cannot run says so
        return IonizationCrossCheck(status=f"failed: no Dimorphite-DL species ({exc})")
    return ionization_model_cross_check(species, predictions, ph)


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
    return report_from_fields(
        alert_id="polar_surface_area",
        name="Polar Surface Area (2D)",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="surface",
        provenance=Provenance(created_by="core", method="rdkit+dimorphite_dl", parameters={"pH": ph}),
    )



def compute_admet_endpoints(
    mol, molecule_uuid, parameters=None, interpreter_path=None
) -> "AlertResult":
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
    # **STILL AN `AlertResult`, AND THE REASON IS ITS OWN SHAPE.** Like the
    # four migrated in stage 3 this is a report wearing an alert's clothes,
    # and a mechanical migration measurably HALF works: the endpoint lines
    # are `name: value` and become proper facts -- "hERG blockade" with the
    # value "0.93", which is an improvement -- but the `[Toxicity and
    # safety]` group HEADINGS have no colon, so `facts_from_alert` labels
    # each with the calculator's own name and files the bracket text as the
    # value. Four noise facts all called "ADMET (ADMET-AI)".
    #
    # `ReportResult.matched` also does not round-trip the two-space indent
    # those headings group with, so the visual structure is lost for any
    # consumer still reading lines.
    #
    # Migrating it properly means giving the endpoints a `FactCategory`
    # instead of a bracket heading -- which is a change to what ADMET
    # REPORTS, not to how it is carried, and belongs with whoever decides
    # that. It is in none of stage 3's merge candidates.
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
            provenance=Provenance(created_by="admet_ai", method="chemprop multi-task",
                                  parameters={"refusal": SIDECAR_NOT_CONFIGURED}),
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

# --- which components each calculator is handed (round 5, branch S2) -------
#
# ONE RULE, from ChEMBL: a PROPERTY OF THE COMPOUND (logP, polar surface
# area, pKa, drug-likeness, a model's prediction) is computed on the parent
# compound, and a DESCRIPTION OF WHAT WAS DRAWN (formula, mass, name,
# perception, the given 3D geometry) on the whole structure. ChEMBL 37's
# schema documentation says of its own calculated properties: "all but
# FULL_MWT and FULL_MOLFORMULA are calculated on the parent structure".
# Measured before this (tests/fixtures/multicomponent_matrix_s1.json):
# metformin pamoate failed Lipinski on its counter-ion, sodium acetate's logD
# was -4.24 with "0 ionizable centres", and the distance indices printed
# RDKit's unreachable-pair sentinel (Wiener index 400000009 for NaOAc).

#: A compound property reported as a set of facts, on the ChEMBL parent.
_PARENT_PROPERTY = CalculatorScope(
    ComponentSelection.CHEMBL_PARENT, Aggregation.COLLECTION,
    note="a property of the compound, so of its ChEMBL parent")
#: The molecular polarizability: a compound property, within Jensen's element set.
_PARENT_POLARIZABILITY = CalculatorScope(
    ComponentSelection.CHEMBL_PARENT, Aggregation.SCALAR, MethodDomain.METHOD_SPECIFIC,
    note="a property of the compound; Jensen's additive table covers a fixed element set")
#: A protonation curve or microspecies set, of the parent only.
_PARENT_CURVE = CalculatorScope(
    ComponentSelection.CHEMBL_PARENT, Aggregation.COLLECTION,
    note="the parent's protonation states over pH; a counter-ion is not a microspecies")
#: Charges equilibrated over the parent, mapped back onto the drawing's atoms.
_PARENT_PER_ATOM = CalculatorScope(
    ComponentSelection.CHEMBL_PARENT, Aggregation.PER_ATOM,
    note="charges of the compound, equilibrated over its parent and reported on the drawing's atoms")
#: ATOM-LOCAL table look-ups (Crippen's atom types, Jensen's increments): each
#: atom's value is defined wherever the atom is, so each component answers.
#: Also the only honest scope for a calculator that ADDS hydrogens, which a
#: parent's atoms cannot be mapped back through (`components.read_back`).
_EACH_CONTRIBUTION = CalculatorScope(
    ComponentSelection.EACH_COMPONENT, Aggregation.PER_ATOM,
    note="an atom-local table look-up, defined for every atom drawn")
#: Jensen's per-atom increments: atom-local, within his element set.
_EACH_ATOMIC_POLARIZABILITY = CalculatorScope(
    ComponentSelection.EACH_COMPONENT, Aggregation.PER_ATOM, MethodDomain.METHOD_SPECIFIC,
    note="Jensen's atom-additive increments, each atom's own")
#: Solubility refuses a salt: its own pH correction models the salt forming.
_PURE_SOLUBILITY = CalculatorScope(
    ComponentSelection.REFUSE_MULTICOMPONENT, Aggregation.COLLECTION, MethodDomain.METHOD_SPECIFIC,
    note=("A salt or mixture is already the species the pH correction models forming, so applying "
          "it again would answer a different question. Draw the single parent compound instead."))
#: Joback refuses a salt: a pure component's properties, which a salt is not.
_PURE_JOBACK = CalculatorScope(
    ComponentSelection.REFUSE_MULTICOMPONENT, Aggregation.COLLECTION, MethodDomain.METHOD_SPECIFIC,
    note="Joback estimates properties of a pure component; a salt's boiling point is not its parent's.")
#: Hansen refuses a salt: group contributions for a pure liquid.
_PURE_HANSEN = CalculatorScope(
    ComponentSelection.REFUSE_MULTICOMPONENT, Aggregation.COLLECTION, MethodDomain.METHOD_SPECIFIC,
    note="Stefanis-Panayiotou group contributions describe a pure liquid.")
#: What the drawn substance is: formula, mass, name, regulatory status.
_WHOLE_SUBSTANCE = CalculatorScope(
    ComponentSelection.WHOLE_STRUCTURE, Aggregation.COLLECTION,
    note="describes the substance as drawn, counter-ions included")
#: An energetic formulation's composition, counter-ions and all.
_WHOLE_ENERGETIC = CalculatorScope(
    ComponentSelection.WHOLE_STRUCTURE, Aggregation.SCALAR, MethodDomain.METHOD_SPECIFIC,
    note="a formulation's composition is the whole drawing (ammonium nitrate is a salt); C/H/N/O only")
#: Griffin's HLB, whose own definition decides what it covers.
_WHOLE_SURFACTANT = CalculatorScope(
    ComponentSelection.WHOLE_STRUCTURE, Aggregation.SCALAR, MethodDomain.METHOD_SPECIFIC,
    note="Griffin's HLB is defined for nonionic polyoxyethylene surfactants")
#: A description of the given 3D coordinates, which may be a real ion pair.
_WHOLE_GEOMETRY = CalculatorScope(
    ComponentSelection.WHOLE_STRUCTURE, Aggregation.COLLECTION,
    note="describes the given coordinates, which may be a real ion pair")
#: The given coordinates, atom by atom (solvent-accessible area).
_WHOLE_GEOMETRY_PER_ATOM = CalculatorScope(
    ComponentSelection.WHOLE_STRUCTURE, Aggregation.PER_ATOM,
    note="describes the given coordinates, atom by atom")
#: Atom-local perception or values, answered by each component.
_EACH_PER_ATOM = CalculatorScope(
    ComponentSelection.EACH_COMPONENT, Aggregation.PER_ATOM,
    note="atom-local, so each component answers for itself")
#: Perception each component answers for itself (isomers, rings, sites).
_EACH_COLLECTION = CalculatorScope(
    ComponentSelection.EACH_COMPONENT, Aggregation.COLLECTION,
    note="perception that each component answers for itself")

CALCULATOR_DEFINITIONS: list[CalculatorDefinition] = [
    CalculatorDefinition(
        calculator_id="gasteiger_charge_at_ph",
        scope=_PARENT_PER_ATOM,
        display_name="Partial Charge (pH-dependent)",
        category="charge",
        description=(
            "Partial charges, recomputed on the dominant protonation state at a given pH, "
            "by Gasteiger's PEOE or by MMFF94's bond-charge increments. The two are "
            "different models and give different numbers for the same atom."
        ),
        execution=RegistryExecution(compute=compute_gasteiger_charge_at_ph),
        parameters=[
            CalculatorParameter(
                name="method",
                label="Charge method",
                kind="choice",
                default=GASTEIGER,
                choices=list(CHARGE_METHODS),
                choice_labels=[CHARGE_METHOD_LABELS[m] for m in CHARGE_METHODS],
            ),
            CalculatorParameter(name="pH", label="pH", kind="float", default=7.4, minimum=0.0, maximum=14.0),
            CalculatorParameter(
                name="include_hydrogens",
                label="Increment of Hs (add implicit H charge)",
                kind="bool",
                default=False,
            ),
        ],
        tags=["charge", "ph", "per-atom", "gasteiger", "mmff94", "partial charge"],
    ),
    CalculatorDefinition(
        # ONE CALCULATOR FOR BOTH MODES since 2026-09-17; the pH mode was once its own entry,
        # "Partial Charge (3D, pH-dependent)". That split was justified as protecting stored results
        # keyed by this calculator's parameters, but nothing reads that key back: the result store
        # keys a result by (dataset id, input, fingerprint) alone (`SessionResultStore.put`), so a
        # parameter orphans nothing. What the split did cause was two answers for one molecule side by
        # side in Results. Old pH results are dropped on load (`result_store.RETIRED_RESULT_IDS`).
        calculator_id="geometry_partial_charge",
        scope=_PARENT_PER_ATOM,
        calculation_input=GEOMETRY,
        display_name="Partial Charge (3D)",
        category="charge",
        description=(
            "Partial charges that depend on the 3D geometry, by one of three models. EEM: Bultinck's "
            "electronegativity equalization (2002, part I) with that paper's own parameters for H, C, "
            "N, O and F. QEq: Rappé and Goddard's charge equilibration (1991) with lambda = 1/2 and "
            "its experimental hydrogen parameters, for the 16 elements of its Table I; it refuses "
            "molecules where its iteration does not settle or a charge reaches its bound. Ionescu EEM: "
            "Ionescu et al.'s 2013 protein-fragment models (Mulliken, 6-31G* or 6-31G**, gas phase) for "
            "H, C, N, O, S and Ca, reported as an extrapolation on anything else; it refuses a sulfur "
            "bonded to oxygen and any charge beyond 2.051 e. By default the charges are computed on "
            "the stored conformer as it is, with its own hydrogens and net charge. Tick pH-dependent "
            "to compute them on the dominant ionization state at that pH instead: the state is carried "
            "onto the conformer, every heavy atom and every kept hydrogen holds its coordinates "
            "exactly, and only added hydrogens are placed (MMFF94, everything else fixed). Ionization "
            "states only, never tautomers, and it refuses rather than choose when a proton leaves an "
            "atom whose hydrogens are not equivalent. The result shows the structure it was computed "
            "on. Only the sum of the charges equals the net charge. Needs a conformer with explicit "
            "hydrogens; an element the chosen method has no parameters for is refused."
        ),
        execution=RegistryExecution(compute=compute_geometry_charges),
        parameters=[
            CalculatorParameter(
                name="method",
                label="Charge method",
                kind="choice",
                default=EEM_BULTINCK2002_PART1,
                choices=list(GEOMETRY_CHARGE_METHODS),
                choice_labels=[GEOMETRY_CHARGE_METHOD_LABELS[m] for m in GEOMETRY_CHARGE_METHODS],
            ),
            CalculatorParameter(
                name="ph_dependent",
                label="pH-dependent (dominant ionization state)",
                kind="bool",
                default=False,
            ),
            CalculatorParameter(
                name="pH", label="pH", kind="float", default=7.4, minimum=0.0, maximum=14.0,
                enabled_by="ph_dependent",
            ),
            CalculatorParameter(
                name="include_hydrogens",
                label="Increment of Hs (fold hydrogen charges onto their atom)",
                kind="bool",
                default=False,
            ),
            decimal_places_parameter(),
        ],
        tags=["charge", "3d", "per-atom", "eem", "electronegativity equalization", "partial charge", "bultinck", "qeq", "charge equilibration", "rappe", "ionescu", "ph", "protonation", "ionization"],
    ),
    CalculatorDefinition(
        calculator_id="crippen_logp_contrib",
        scope=_EACH_CONTRIBUTION,
        tags=['logp', 'lipophilicity', 'partition', 'crippen', 'per-atom'],
        display_name="LogP Contribution",
        category="lipophilicity",
        description=(
            "Per-atom Crippen LogP contribution -- which atoms increase vs. decrease "
            "LogP. The molecule's own LogP is reported alongside them; on the "
            "structure as drawn the visible atoms do not sum to it, because Crippen "
            "gives each hydrogen its own increment and the editor's hydrogens are "
            "implicit. The Hydrogens option decides where those increments go."
        ),
        execution=RegistryExecution(compute=compute_crippen_logp_contrib_calculator),
        parameters=[
            decimal_places_parameter(),
            hydrogen_mode_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="crippen_mr_contrib",
        scope=_EACH_CONTRIBUTION,
        tags=['refractivity', 'polarizability', 'crippen', 'per-atom'],
        display_name="Molar Refractivity Contribution",
        category="electronic",
        description=(
            "Per-atom Crippen molar refractivity contribution, with the molecule's "
            "own molar refractivity alongside. Same implicit-hydrogen caveat as LogP "
            "Contribution, and the same Hydrogens option for it."
        ),
        execution=RegistryExecution(compute=compute_crippen_mr_contrib_calculator),
        parameters=[
            decimal_places_parameter(),
            hydrogen_mode_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="admet_ml",
        scope=_PARENT_PROPERTY,
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
        scope=_PARENT_PROPERTY,
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
        scope=_PARENT_PROPERTY,
        tags=['logd', 'lipophilicity', 'partition', 'ph', 'distribution', 'curve', 'logd vs ph'],
        display_name="LogD (pH-dependent)",
        category="lipophilicity",
        description=(
            "Distribution coefficient at a given pH, and the curve across pH it lies on. "
            "Real Henderson-Hasselbalch when a pkasolver environment is configured; otherwise "
            "the LogP of the dominant microspecies at that pH, labelled as an approximation and "
            "drawn as no curve. Hover the curve to read logD at a sampled pH. Under-predicts "
            "zwitterions (amino acids)."
        ),
        execution=RegistryExecution(compute=compute_logd),
        prediction_basis="empirical",
        parameters=[
            CalculatorParameter(name="pH", label="pH", kind="float", default=7.4, minimum=0.0, maximum=14.0),
            # The curve's range. Absorbed from the retired `logd_curve`, whose
            # whole contribution was offering these.
            *ph_range_parameters(),
        ],
    ),
    # ---- Phase 26 ----------------------------------------------------
    CalculatorDefinition(
        calculator_id="elemental_analysis",
        scope=_WHOLE_SUBSTANCE,
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
        calculator_id="mass_spectrum",
        scope=_WHOLE_SUBSTANCE,
        display_name="Mass Spectrum",
        # **IDENTITY, NOT A SECTION OF ITS OWN.** A category holding one
        # calculator is the shape this panel was measured in and moved
        # away from -- 26 sections held 49 buttons and eleven of them held
        # exactly one. And it belongs here on the merits rather than by
        # elimination: it sits directly beside Elemental Analysis, shares
        # its engine, and answers the same question about what a structure
        # is and what it weighs.
        category="identity",
        description=(
            "The isotope envelope of a chosen ion, calculated from natural "
            "abundances: m/z and relative intensity per peak, with the "
            "monoisotopic, average and base-peak masses. Deterministic "
            "arithmetic, not a measurement -- no fragmentation is modelled, so "
            "every line is the molecular ion's own isotope distribution. "
            "Elemental Analysis draws the same envelope for the molecular ion; "
            "this is where the ionisation modes live."
        ),
        execution=RegistryExecution(compute=compute_mass_spectrum),
        tags=["mass", "spectrometry", "isotopes", "adduct"],
        parameters=[
            CalculatorParameter(
                name="ion",
                label="Ion",
                kind="choice",
                default=DEFAULT_ION.label,
                # **THE CLOSED VOCABULARY IS THE ONLY WAY TO CHOOSE ONE**,
                # and the charge rides on the ion rather than on a control
                # of its own -- a charge spinbox beside a short species
                # list is how [M+2H]2+ comes to mean "charge 2, and the
                # composition of something else".
                choices=[ion.label for ion in SUPPORTED_IONS],
            ),
            CalculatorParameter(
                name="resolution",
                label="Resolution",
                kind="choice",
                default=UNIT_RESOLUTION,
                choices=[UNIT_RESOLUTION, EXACT_RESOLUTION],
            ),
            CalculatorParameter(
                name="minimum_percent",
                label="Minimum relative intensity (%)",
                kind="float",
                default=DEFAULT_MINIMUM_PERCENT,
                minimum=0.0,
                maximum=100.0,
            ),
            *microspecies_parameters(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="substance_analysis",
        scope=_WHOLE_SUBSTANCE,
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
        scope=_PARENT_PROPERTY,
        display_name="Topology Analysis",
        category="topology",
        description=(
            "Graph-theoretic descriptors: ring and chain counts, cyclomatic number, "
            "Platt/Randic/Balaban/Harary/Wiener/hyper-Wiener/Szeged indices, Wiener "
            "polarity, and stereo centre counts. Szeged is validated by identity rather "
            "than by a reference value -- it equals Wiener for any acyclic graph and "
            "strictly exceeds it for a cyclic one. The Cao-Liu steric index is measured "
            "toward a named reaction centre, so it is not a whole-molecule number and "
            "has its own per-atom calculator."
        ),
        execution=RegistryExecution(compute=compute_topology_analysis),
        tags=["topology", "graph", "indices"],
        parameters=[
            decimal_places_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="topology_eccentricity",
        scope=_EACH_PER_ATOM,
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
        calculator_id="tsei_projection",
        scope=_EACH_PER_ATOM,
        display_name="Cao-Liu TSEI projection (per atom)",
        category="topology",
        description=(
            "Cao & Liu's topological steric effect index with every atom in turn as "
            "the reaction centre -- how much of each atom's approach the rest of the "
            "molecule screens, read off the graph. Dimensionless. TSEI is defined for "
            "a SUBSTITUENT measured toward a named reaction centre; running it at every "
            "atom is OpenChem's projection of it, not a quantity the paper defines. "
            "Topological, so two conformers of one molecule score identically. Covers "
            "the 28 elements Lange's Handbook tabulates a covalent radius for, and "
            "refuses the rest by name. The equation is geometric, so any of those 28 "
            "computes -- but Cao and Liu validated it on alkyl, halogen and ether "
            "substituents, so a result on an organometallic is an extrapolation."
        ),
        execution=RegistryExecution(compute=compute_tsei_projection),
        prediction_basis="empirical",
        tags=["topology", "steric", "per-atom"],
        parameters=[
            decimal_places_parameter(),
            CalculatorParameter(
                name="include_hydrogens",
                label="Count hydrogens",
                kind="bool",
                # The paper uses BOTH conventions and labels each: eq 6
                # ignores hydrogens and Tables 1, 2 and 4 follow it, while
                # Table 6's footnote c says its values include them. Off
                # matches the series this implementation is gated on.
                default=False,
            ),
            CalculatorParameter(
                name="crowded_branches",
                label="Apply the 6.5x crowding correction",
                kind="bool",
                # Every TSEI the paper publishes uses it -- t-Bu is 1.8125,
                # never the 1.3750 plain additivity gives.
                default=True,
            ),
        ],
    ),
    CalculatorDefinition(
        calculator_id="topology_distance_degree",
        scope=_EACH_PER_ATOM,
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
        scope=_WHOLE_GEOMETRY,
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
        scope=_WHOLE_GEOMETRY,
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
        scope=_WHOLE_GEOMETRY_PER_ATOM,
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
        scope=_PARENT_PROPERTY,
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
        scope=_EACH_PER_ATOM,
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
        scope=_EACH_PER_ATOM,
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
        scope=_WHOLE_SUBSTANCE,
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
            # Blank is the default and means every loaded rule, exactly as
            # before this existed. A date withholds rules that took effect
            # after it, which answers "was this listed when the sample was
            # made". A date that cannot be read REFUSES rather than falling
            # back to a current-rules screen -- see the calculator.
            CalculatorParameter(
                name="as_of",
                label="Screen as of (YYYY-MM-DD, blank = every loaded rule)",
                kind="text",
                default="",
            ),
        ],
        tags=["regulatory", "compliance", "screening", "safety", "historical"],
    ),
    CalculatorDefinition(
        calculator_id="locants",
        scope=_EACH_PER_ATOM,
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
        scope=_EACH_PER_ATOM,
        display_name="Functional Groups",
        category="substructure",
        description=(
            "Functional groups, ring systems and structural features, coloured by kind "
            "and labelled at the atom each belongs to. Every feature is defined in one "
            "vocabulary, each cited to an IUPAC definition (the Gold Book, or the Blue "
            "Book where the Gold Book has none), and detected once: Fragment "
            "Counts counts the same detection this draws, and the Atom Inspector lists "
            "it per atom. Where one feature is the better description of another's "
            "atoms, the other is hidden here (an acetal's two oxygens are not also shown "
            "as ethers) and a more specific one is shown beside its general one (a "
            "lactam beside its amide). Charged forms are labelled as drawn -- a "
            "carboxylate is not called a carboxylic acid -- and nothing is inferred "
            "about pH. A ring system is reported as a ring system -- benzene, "
            "1H-indole -- not as a group. Tick \"Suffix-eligible groups only\" to "
            "narrow it to the groups the naming engine would consider for a suffix."
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
        scope=_EACH_PER_ATOM,
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
        scope=_EACH_PER_ATOM,
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
        scope=_WHOLE_GEOMETRY,
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
        scope=_EACH_COLLECTION,
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
        scope=_EACH_COLLECTION,
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
        scope=_EACH_COLLECTION,
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
        scope=_EACH_COLLECTION,
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
        scope=_PARENT_CURVE,
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
        scope=_PARENT_CURVE,
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
        scope=_PARENT_PROPERTY,
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
        calculator_id="hbond_vs_ph",
        scope=_PARENT_CURVE,
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
    # ---- Solubility ----------------------------------------------------
    # Registered UNCONDITIONALLY, both of them. The AqSolDB baseline and the
    # pKa prediction each live in a sidecar that may not be configured, and
    # the answer to that is a named refusal at compute time -- never a
    # registry that changes shape with what is installed, which would make
    # a calculator's very existence depend on the machine.
    CalculatorDefinition(
        calculator_id="solubility",
        scope=_PURE_SOLUBILITY,
        display_name="Solubility",
        category="solubility",
        description=(
            "Predicted intrinsic aqueous solubility in logS, mg/mL and mol/L, its "
            "Low/Moderate/High category, the value at a chosen pH, an ICH M9 "
            "high-solubility screening estimate, and the solubility-versus-pH curve "
            "across the range you choose. Ampholytes and salts are refused rather "
            "than modelled; a molecule with no ionizable centre gets a flat line, "
            "which is an answer rather than a failure."
        ),
        execution=RegistryExecution(compute=compute_solubility),
        parameters=[
            CalculatorParameter(
                name="model", label="Baseline model", kind="choice",
                default=ESOL, choices=[ESOL, AQSOLDB],
            ),
            CalculatorParameter(
                name="pH", label="at pH", kind="float", default=DEFAULT_PH,
                minimum=0.0, maximum=14.0,
            ),
            CalculatorParameter(
                name="pka_values", label="pKa values (optional, e.g. 3.49, 9.4)",
                kind="text", default="",
            ),
            CalculatorParameter(
                name="dose_mg", label="Highest single dose (mg, for BCS)", kind="float",
                default=0.0, minimum=0.0, maximum=100000.0,
            ),
            CalculatorParameter(
                name="solvent", label="Solvent", kind="choice",
                default="water", choices=solvent_choices(),
            ),
            # Costs ~6 s when the ADMET sidecar is configured, and nothing
            # at all when it is not. On by default because two independent
            # models disagreeing by half a log unit is the most useful
            # thing on the panel; switchable because it is not free.
            CalculatorParameter(
                name="compare_models", label="Compare against the other model",
                kind="bool", default=True,
            ),
            # **THIS CALCULATOR ALREADY HONOURED THESE; IT JUST DID NOT
            # OFFER THEM.** `solubility_chart` reads ph_min/ph_max/ph_step
            # straight out of `parameters`, so passing them moved the chart
            # long before `solubility_curve` was retired -- measured at the
            # merge, 5 points over pH 6-8 against the default 57 over 0-14.
            # The second registration's only real contribution was a dialog
            # that showed them.
            *ph_range_parameters(),
        ],
        prediction_basis="empirical",
        tags=["solubility", "logs", "esol", "admet", "ph", "bcs", "curve"],
    ),
    # **`solubility_curve` WAS RETIRED HERE.** It reported the same nine
    # facts and the same curve points as `Solubility` -- measured identical
    # on aspirin -- and the one fact it added is reported above now. The
    # only thing it really contributed was a dialog exposing the pH range,
    # which `Solubility` already honoured and now offers.
    #
    # RETIRED IS NOT DELETED: the id is simply not offered as a new
    # calculation. A stored `solubility_curve` result stays readable,
    # because the reader reads what it was handed rather than asking the
    # registry, and an old cache key MISSES and recomputes under the new
    # identity rather than being aliased to it.
    # ---- Phase 29: naming --------------------------------------------
    CalculatorDefinition(
        calculator_id="iupac_name",
        scope=_WHOLE_SUBSTANCE,
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
        scope=_EACH_COLLECTION,
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
        scope=_WHOLE_SUBSTANCE,
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
                label="Partner molecule",
                # `"smiles"` names what the VALUE is, not the widget: the
                # dialog offers the project's own molecules where it has
                # them and a text box otherwise, and either way what is
                # stored is SMILES.
                kind="smiles",
                default="",
            ),
            CalculatorParameter(
                name="role",
                label="Role of this molecule",
                kind="choice",
                # CODES, with the prose in `choice_labels`. The stored
                # value is hashed into every retained result's identity,
                # so rewording a label must not orphan the cache.
                default=ROLE_AUTO,
                choices=[ROLE_AUTO, ROLE_ACID, ROLE_BASE],
                choice_labels=[
                    ROLE_LABELS[ROLE_AUTO],
                    ROLE_LABELS[ROLE_ACID],
                    ROLE_LABELS[ROLE_BASE],
                ],
            ),
        ],
    ),
    # ---- Phase 30: quantum, dynamics, dipole, MPO --------------------
    CalculatorDefinition(
        calculator_id="huckel_analysis",
        scope=_EACH_COLLECTION,
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
        scope=_EACH_PER_ATOM,
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
        scope=_WHOLE_GEOMETRY,
        calculation_input=GEOMETRY,
        display_name="Dipole Moment",
        category="charge",
        description=(
            "Net molecular dipole as a vector and magnitude in Debye, from partial charges and this "
            "conformer's geometry: Gasteiger by default, or the 3D EEM or QEq charges of the same "
            "conformer. Needs a conformer. A charge model that declines the molecule is reported as "
            "such, never replaced by another. Direction and symmetry are reliable; the magnitude "
            "inherits the charge model's accuracy."
        ),
        execution=RegistryExecution(compute=compute_dipole_moment),
        tags=["charge", "3d", "polarity", "eem", "qeq"],
        parameters=[
            CalculatorParameter(
                name="charge_model",
                label="Charge model",
                kind="choice",
                default=GASTEIGER,
                choices=list(CHARGE_MODELS),
                choice_labels=[CHARGE_MODEL_LABELS[m] for m in CHARGE_MODELS],
            ),
            decimal_places_parameter(),
        ],
    ),
    CalculatorDefinition(
        calculator_id="molecular_dynamics",
        scope=_WHOLE_GEOMETRY,
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
        scope=_PARENT_PROPERTY,
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
        scope=_WHOLE_GEOMETRY,
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
        scope=_EACH_PER_ATOM,
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
        scope=_PARENT_PROPERTY,
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
        scope=_EACH_COLLECTION,
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
        scope=_EACH_COLLECTION,
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
    CalculatorDefinition(
        calculator_id="griffin_hlb",
        scope=_WHOLE_SURFACTANT,
        display_name="HLB (Griffin)",
        category="surface",
        description=(
            "Griffin's hydrophile-lipophile balance: the weight percentage of ethylene "
            "oxide over five. Defined only for nonionic surfactants with polyoxyethylene "
            "as the SOLE hydrophilic moiety, so anything else -- an ionic surfactant, a "
            "sorbitan ester, an ordinary drug -- is refused with the reason rather than "
            "given a meaningless number. Davies' HLB is not offered: it shares the name "
            "and disagrees substantially across the whole range of practical "
            "applications, so the two must not be reported under one label."
        ),
        execution=RegistryExecution(compute=compute_griffin_hlb),
        prediction_basis="empirical",
        tags=["surface", "surfactant", "hlb", "formulation"],
        parameters=[decimal_places_parameter()],
    ),
    CalculatorDefinition(
        calculator_id="detonation",
        scope=_WHOLE_ENERGETIC,
        display_name="Detonation (Kamlet-Jacobs)",
        category="energetic",
        description=(
            "Detonation pressure and velocity for a C/H/N/O explosive, by Kamlet and "
            "Jacobs' 1968 correlation. REQUIRES two inputs it cannot derive: the "
            "initial loading density of the charge, which is not a crystal density and "
            "which the pressure depends on as its square, and a measured "
            "condensed-phase enthalpy of formation, because the published rule for "
            "estimating one from an ideal-gas value excludes every classic energetic "
            "material. Without either, it refuses and says which is missing. An "
            "empirical correlation fitted to reproduce a 1968 computer code -- not a "
            "measurement, and not a safety assessment."
        ),
        execution=RegistryExecution(compute=compute_detonation),
        prediction_basis="empirical",
        tags=["energetic", "detonation", "kamlet-jacobs", "performance"],
        parameters=[
            decimal_places_parameter(1),
            CalculatorParameter(
                name="loading_density_g_cm3",
                label="Loading density (g/cm³) — required",
                kind="float",
                default=0.0,
                minimum=0.0,
                maximum=3.0,
            ),
            CalculatorParameter(
                name="enthalpy_of_formation_kcal_mol",
                label="Enthalpy of formation, solid (kcal/mol) — required, measured",
                kind="float",
                default=-1000.0,
                minimum=-1000.0,
                maximum=500.0,
            ),
            CalculatorParameter(
                name="ruby_correction",
                label="Apply the −6% RUBY-matching correction (G > 0.93)",
                kind="bool",
                default=False,
            ),
        ],
    ),
    CalculatorDefinition(
        calculator_id="oxygen_balance",
        scope=_WHOLE_ENERGETIC,
        display_name="Oxygen Balance",
        category="energetic",
        description=(
            "Whether a substance carries enough oxygen to burn its own carbon and "
            "hydrogen, as a percentage of its mass. BOTH published conventions are "
            "reported, because they are different quantities for the same substance: "
            "TNT is -74.0% burning carbon to CO2 and -24.7% burning it only to CO, and "
            "a substance can be negative on one and positive on the other. Defined for "
            "C/H/N/O only, so a sulfur, a halogen or a metal is refused with the element "
            "named rather than silently ignored. A composition figure, not a performance "
            "one -- it says nothing on its own about how powerful or how sensitive "
            "something is."
        ),
        execution=RegistryExecution(compute=compute_oxygen_balance),
        prediction_basis="empirical",
        tags=["energetic", "oxygen balance", "combustion", "stoichiometry"],
        parameters=[decimal_places_parameter(1)],
    ),
    CalculatorDefinition(
        calculator_id="bird_aromaticity",
        scope=_EACH_COLLECTION,
        display_name="Aromaticity (Bird)",
        category="aromaticity",
        description=(
            "Bird's aromaticity index per ring: every bond length is converted to a "
            "Gordy bond order, and the index measures how UNIFORM those orders are "
            "rather than how close the lengths are to one ideal. That is a different "
            "question from HOMA on the same geometry -- a ring whose bonds are all "
            "equal but all wrong scores 100 here. Reported as I5 or I6 because the "
            "paper says outright that values for different ring sizes are not "
            "comparable, the Kekule reference being 35 for a five-membered ring and "
            "33.3 for a six-membered one. Any other ring size is refused rather than "
            "given a reference by analogy. Needs a 3D conformer."
        ),
        execution=RegistryExecution(compute=compute_bird_index),
        calculation_input=GEOMETRY,
        prediction_basis="empirical",
        tags=["aromaticity", "bird", "ring", "geometry", "bond order"],
        parameters=[decimal_places_parameter(1)],
    ),
    CalculatorDefinition(
        calculator_id="homa_aromaticity",
        scope=_EACH_COLLECTION,
        display_name="Aromaticity (HOMA)",
        category="aromaticity",
        description=(
            "The harmonic oscillator model of aromaticity, per ring, from Krygowski's "
            "reference bond lengths. 1 is a ring whose bonds all sit at the optimal "
            "length and 0 is the reference Kekule structure -- there is NO lower "
            "bound, so a bond-alternating or saturated ring goes negative. Reported "
            "per RING rather than per molecule, because fusing rings changes each "
            "one's local aromatic character. It reads real bond lengths, so it needs "
            "a 3D conformer and refuses a drawing: a 2D layout gives every bond about "
            "the same length whatever its order. A geometric index -- it says how "
            "equalised the bonds are, not whether the ring sustains a ring current."
        ),
        execution=RegistryExecution(compute=compute_aromaticity),
        calculation_input=GEOMETRY,
        prediction_basis="empirical",
        tags=["aromaticity", "homa", "ring", "geometry", "krygowski"],
        parameters=[decimal_places_parameter(3)],
    ),
    CalculatorDefinition(
        calculator_id="hansen_solubility",
        scope=_PURE_HANSEN,
        display_name="Hansen Solubility Parameters",
        category="solubility",
        description=(
            "The three Hansen partial solubility parameters -- dispersion, polar and "
            "hydrogen bonding -- and their Hildebrand total, from the structure alone by "
            "Stefanis and Panayiotou's group contributions. Two passes: first-order "
            "UNIFAC groups partition the molecule, then second-order conjugation groups "
            "correct it where they apply, which is what the paper's W switch selects. "
            "Below 3 MPa^0.5 the polar and hydrogen-bonding parameters come from the "
            "paper's SEPARATE low-range regression rather than from the main equations, "
            "and the result says which was used. Needs three or more carbons excluding "
            "the characteristic group's own atom, and refuses a structure carrying an "
            "atom in no group rather than returning a partial sum."
        ),
        execution=RegistryExecution(compute=compute_hansen),
        prediction_basis="empirical",
        tags=["solubility", "hansen", "hildebrand", "solvent", "group contribution"],
        parameters=[decimal_places_parameter(2)],
    ),
    CalculatorDefinition(
        calculator_id="joback_properties",
        scope=_PURE_JOBACK,
        display_name="Thermophysical Properties (Joback)",
        category="thermophysical",
        description=(
            "Eleven pure-component properties from the structure alone, by Joback and "
            "Reid's group contributions: normal boiling and freezing points, the three "
            "critical constants, standard enthalpy and Gibbs energy of formation, "
            "ideal-gas heat capacity, enthalpies of vaporization and fusion, and liquid "
            "viscosity. Additive over a COMPLETE decomposition, so a structure carrying "
            "an atom in no Joback group is refused with the atom named rather than given "
            "a partial sum -- the table has no ring tertiary amine and stops at divalent "
            "sulfur. Critical temperature takes a boiling point: supply a measured one "
            "where you have it, because the paper warns that estimating it costs several "
            "times the error."
        ),
        execution=RegistryExecution(compute=compute_joback),
        prediction_basis="empirical",
        tags=["thermophysical", "critical", "boiling", "joback", "group contribution"],
        parameters=[
            decimal_places_parameter(),
            CalculatorParameter(
                name="temperature_k",
                label="Temperature (K)",
                kind="float",
                default=298.15,
                minimum=1.0,
                maximum=1500.0,
            ),
            CalculatorParameter(
                name="experimental_boiling_point_k",
                label="Measured boiling point (K), optional",
                kind="float",
                default=0.0,
                minimum=0.0,
                maximum=1500.0,
            ),
        ],
    ),
    # ---- Polarizability and orbital electronegativity ----------------
    CalculatorDefinition(
        calculator_id="polarizability",
        scope=_PARENT_POLARIZABILITY,
        display_name="Polarizability (molecular)",
        category="electronic",
        description=(
            "Molecular polarizability in A^3, by one of three methods. Jensen et al.'s "
            "additive atomic scheme is accurate to about 1% for aromatics and halogenated "
            "compounds and roughly 11% high for saturated hydrocarbons, since an "
            "atom-additive scheme has no hybridization dependence. Miller's two methods are "
            "hybridization-aware: ahc squares a sum over the whole molecule and lands within "
            "1% on benzene and CCl4, ahp is plain additivity. The three are different "
            "quantities, not settings of one -- pick one and read the reported method."
        ),
        execution=RegistryExecution(compute=compute_polarizability),
        prediction_basis="empirical",
        parameters=[
            CalculatorParameter(
                # THREE METHODS ON ONE ROW, NOT THREE CALCULATORS. They
                # answer the same question about the same molecule, so
                # comparing them is the useful gesture and a settings
                # change is the cheapest way to make it.
                name="method",
                label="Method",
                kind="choice",
                default="Jensen (additive)",
                choices=list(POLARIZABILITY_METHODS),
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
        tags=["electronic", "polarizability", "physchem"],
    ),
    CalculatorDefinition(
        calculator_id="atomic_polarizability",
        scope=_EACH_ATOMIC_POLARIZABILITY,
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
        scope=_EACH_PER_ATOM,
        display_name="Orbital Electronegativity",
        category="electronic",
        description=(
            "Orbital electronegativity (eV) at each atom, in either component. Sigma is "
            "Gasteiger-Marsili PEOE at the converged sigma charge. Pi is Marsili & "
            "Gasteiger's own pi parameters at that same sigma charge -- their starting POE "
            "values, covering the conjugated atoms only and NOT iterated to pi "
            "self-consistency, so it does not reflect pi charge redistribution. Absolute "
            "values depend on the parameter set and will differ between implementations; "
            "the ordering between atoms is the meaningful part, and the pi ordering is not "
            "the sigma one."
        ),
        execution=RegistryExecution(compute=compute_orbital_electronegativity),
        prediction_basis="empirical",
        parameters=[
            decimal_places_parameter(),
            CalculatorParameter(
                # A CLOSED vocabulary shared with the chemistry layer, so the
                # label the user picks and the branch that runs cannot drift.
                name="component",
                label="Component",
                kind="choice",
                default="Sigma (PEOE)",
                choices=list(ORBITAL_COMPONENTS),
            ),
            CalculatorParameter(
                # SAYS "sigma only" BECAUSE THE PI BRANCH IGNORES IT, and a
                # tick box that silently does nothing is worse than an
                # absent one. Hydrogen has no pi orbital and no row in
                # Marsili & Gasteiger's Table I; the settings dialog builds
                # one widget per parameter with no conditional visibility,
                # so the honest place to say so is the label.
                name="include_hydrogens",
                label="Include hydrogens (sigma only)",
                kind="bool",
                default=False,
            ),
            CalculatorParameter(
                # Both components, unlike the one above: `_maybe_microspecies`
                # runs BEFORE the component branch, so protonation changes
                # the sigma charges the pi values are evaluated at too.
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
        scope=_WHOLE_SUBSTANCE,
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
