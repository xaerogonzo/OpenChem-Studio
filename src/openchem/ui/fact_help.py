"""What a FACT means, for the reader that renders it.

**A `Fact` CARRIES AN ID, NOT A TOOLTIP.** `Fact.help_id` is a stable
semantic identifier and nothing else: `HelpTooltip` is a UI object, and a
domain dataclass holding one would put Qt-shaped presentation inside
`domain/`, which is the layering this project enforces in
`tests/test_layering.py`. The producer names the concept; this module says
what the concept means; the view renders it.

**WHY THE 41 ALWAYS-ON DESCRIPTORS ARE THE WHOLE REGISTRY TODAY.** They
were the recorded hole: every success branch of the Properties panel's
descriptor row ended `setToolTip("")`, and what a reader saw on hover was
`_ElidingLabel` echoing the caption -- the degeneracy
`test_no_contract_is_a_placeholder` refuses. The rows were outside the
coverage guard's universe because its window has no molecule selected, so
the hole sat under a green guard. 2c removed those rows and the values are
read in the results panel; the contract follows the value rather than the
widget, which is what an id-keyed registry buys.

The lookup is by `help_id`, so nothing here is descriptor-specific: any
producer that stamps one on its facts joins by adding an entry.

**THE TEXT DESCRIBES WHAT SHIPS, NOT WHAT THE PAPER SAYS.** Several of
these filters are documented approximations -- Ghose bounds heavy atoms
where the original bounds all atoms, this project's Rule of Three has no
rotatable-bond term, and the two ADMET heuristics are not the published
regressions they are named after. Where the two differ the contract states
the shipped rule, because a tooltip that quotes a threshold the code does
not use is worse than no tooltip at all.
"""

from __future__ import annotations

from openchem.domain.descriptor_aggregate import descriptor_help_id as help_id_for
from openchem.ui.widgets.help_tooltip import HelpTooltip


def _contract(
    descriptor_id: str,
    text: str,
    tier: int = 2,
    *,
    source_key: str | None = None,
    help_anchor: str | None = None,
) -> tuple[str, HelpTooltip]:
    help_id = help_id_for(descriptor_id)
    return help_id, HelpTooltip(
        text=text,
        tier=tier,  # type: ignore[arg-type]
        help_id=help_id,
        topic="properties",
        source_key=source_key,
        help_anchor=help_anchor,
    )


#: `help_id` -> what that fact means.
#:
#: Tier 2 is a scientific parameter: what it is plus at least one
#: APPLICABLE qualifier. Tier 3 is interpretation-sensitive and carries the
#: limit as well -- an estimate that reads like a measurement, a score whose
#: scale is not obvious, or a rule whose "pass" is narrower than its name.
CONTRACTS: dict[str, HelpTooltip] = dict(
    [
        # --- mass and composition ---------------------------------------
        _contract(
            "mol_wt",
            "Average molecular mass in g/mol, from standard atomic weights. "
            "Isotope-averaged, so it is not the mass a molecular-ion peak "
            "matches -- Exact Mass is.",
        ),
        _contract(
            "exact_mass",
            "Monoisotopic mass in g/mol: the most abundant isotope of each "
            "element rather than the isotope average. This is the value a "
            "measured molecular ion is compared against.",
        ),
        _contract(
            "formula",
            "Atom counts in Hill order -- carbon, then hydrogen, then the "
            "rest alphabetically. It counts atoms only, so isomers of any "
            "kind share one formula.",
        ),
        _contract(
            "heavy_atom_count",
            "Atoms other than hydrogen. Independent of whether hydrogens are "
            "drawn explicitly, which is why several size filters are stated "
            "against it.",
        ),
        _contract(
            "formal_charge",
            "The sum of the formal charges drawn on the structure, in units "
            "of the elementary charge. A bookkeeping total from the drawing, "
            "not a calculated partial charge.",
        ),
        # --- lipophilicity and polarity ---------------------------------
        _contract(
            "mol_logp",
            "Estimated octanol/water partition coefficient as log10, summed "
            "from Wildman-Crippen atom contributions. A calculation from the "
            "drawing, never a measurement.",
            tier=3,
            source_key="wildman1999",
        ),
        _contract(
            "tpsa",
            "Topological polar surface area in A^2, from Ertl's fragment "
            "contributions for nitrogen and oxygen and the hydrogens on "
            "them. Needs no 3D conformer; sulfur and phosphorus are excluded "
            "by RDKit's default.",
            source_key="ertl2000",
        ),
        _contract(
            "molar_refractivity",
            "Crippen molar refractivity in cm^3/mol, an atom-contribution "
            "estimate that tracks polarizability and molecular volume.",
            source_key="wildman1999",
        ),
        _contract(
            "labute_asa",
            "Approximate solvent-accessible surface area in A^2, computed "
            "from connectivity and atomic radii rather than from a "
            "conformer -- so it is available for a flat drawing and will not "
            "agree exactly with a surface measured on 3D coordinates.",
        ),
        _contract(
            "mcgowan_volume",
            "McGowan characteristic volume in cm^3/mol divided by 100: "
            "atomic volumes over every atom including hydrogens, minus 6.56 "
            "per bond. Purely constitutional -- no geometry and no fitted "
            "parameters -- and the one Abraham solute descriptor that is "
            "exactly computable. Benzene is 0.7164; water is 0.1673.",
        ),
        # --- topology ---------------------------------------------------
        _contract(
            "num_rotatable_bonds",
            "Single bonds outside a ring joining two non-terminal heavy "
            "atoms. Amide C-N bonds are excluded by RDKit's default "
            "definition, so an amide contributes nothing to this count "
            "however flexible the rest of the molecule is.",
        ),
        _contract(
            "num_hbd",
            "Hydrogen-bond donors by Lipinski's counting rule: nitrogens and "
            "oxygens carrying at least one hydrogen. It counts the heavy "
            "atoms, not the hydrogens on them.",
        ),
        _contract(
            "num_hba",
            "Hydrogen-bond acceptors by Lipinski's counting rule, which "
            "counts nitrogen and oxygen atoms. Deliberately cruder than a "
            "geometric or electronic definition, because the filters stated "
            "against it were derived with this one.",
        ),
        _contract(
            "ring_count",
            "Rings in the smallest set of smallest rings. A fused system "
            "contributes the number of independent cycles, so naphthalene is "
            "2 rather than 3.",
        ),
        _contract(
            "num_stereocenters",
            "Tetrahedral stereocentres found on the structure, counting BOTH "
            "assigned and unassigned ones. A drawing with no wedge bonds "
            "still reports its centres, which is what makes this a count of "
            "what could be specified rather than what has been.",
        ),
        # --- scores -----------------------------------------------------
        _contract(
            "qed",
            "Quantitative Estimate of Drug-likeness, 0 to 1. A desirability "
            "AGGREGATE over eight molecular properties -- not a probability "
            "that the molecule is a drug, and not a threshold: it is only "
            "meaningful compared with other molecules scored the same way.",
            tier=3,
            source_key="bickerton2012",
        ),
        _contract(
            "sa_score",
            "Synthetic accessibility on Ertl and Schuffenhauer's 1 to 10 "
            "scale, where 1 is easy to make and 10 is hard. Estimated from "
            "fragment frequencies in a reference corpus plus a complexity "
            "penalty, so it reflects how USUAL a structure's pieces are, not "
            "whether a route exists.",
            tier=3,
            source_key="ertl2009",
        ),
        _contract(
            "np_likeness",
            "How natural-product-like the structure is, roughly -5 to +5, "
            "as a Bayesian comparison of its fragments against a corpus. "
            "NEVER a statement about where a molecule came from: caffeine is "
            "a natural product and scores about -1.1, while morphine scores "
            "about +2.6.",
            tier=3,
            source_key="ertl2008",
        ),
        _contract(
            "np_likeness_confidence",
            "The fraction of this molecule's fragments that the scoring "
            "model had seen, 0 to 1. It is reported separately because the "
            "score cannot carry it: an unseen fragment contributes zero, so "
            "a molecule at confidence 0 scores exactly 0.0 by construction "
            "and is indistinguishable from one genuinely scored as neutral.",
            tier=3,
            source_key="npscorer2015",
        ),
        _contract(
            "bertz_ct",
            "Bertz complexity index -- larger is more complex, with no upper "
            "bound and no units. RDKit's implementation departs from the "
            "paper for aromatic systems, and the value does not identify a "
            "molecule: methane and propane are both 0.",
            tier=3,
            source_key="bertz1981",
        ),
        _contract(
            "fsp3",
            "The fraction of carbon atoms that are sp3-hybridised, 0 to 1 -- "
            "a measure of three-dimensionality. Benzene is 0.00 and "
            "cyclohexane 1.00; a molecule with no carbon reports 0.0 rather "
            "than being undefined.",
            source_key="lovering2009",
        ),
        _contract(
            "esol_logs",
            "Estimated aqueous solubility as log10 of mol/L, from Delaney's "
            "ESOL regression on LogP, molecular weight, rotatable bonds and "
            "aromatic proportion. A fitted estimate with real scatter, not a "
            "measurement, and least reliable outside the drug-like chemistry "
            "it was fitted on.",
            tier=3,
            source_key="delaney2004",
            help_anchor="limits-solubility",
        ),
        # --- rule-of-thumb filters --------------------------------------
        _contract(
            "lipinski_pass",
            "Lipinski's Rule of Five, passed with at most ONE violation of: "
            "molecular weight over 500, LogP over 5, more than 5 H-bond "
            "donors, more than 10 acceptors. A guide to oral drug-likeness "
            "that whole useful classes fail by design.",
            tier=3,
        ),
        _contract(
            "veber_pass",
            "Veber's oral-bioavailability guide: at most 10 rotatable bonds "
            "AND a topological polar surface area of at most 140 A^2. Both "
            "must hold.",
            tier=3,
        ),
        _contract(
            "ghose_pass",
            "Ghose's drug-likeness window, all four required: molecular "
            "weight 160-480, LogP -0.4 to 5.6, molar refractivity 40-130, "
            "and 20-70 HEAVY atoms. The original bounds total atoms; heavy "
            "atoms are used here because a drawing need not carry explicit "
            "hydrogens.",
            tier=3,
        ),
        _contract(
            "egan_pass",
            "Egan's absorption window, as the rectangle this project "
            "applies: LogP between -1 and 5.88 AND a polar surface area of "
            "at most 131.6 A^2. The published criterion is an ellipse, so "
            "molecules near the corners are classified differently here.",
            tier=3,
        ),
        _contract(
            "pfizer_375_pass",
            "The Pfizer 3/75 toxicity-risk guide, inverted so that PASS is "
            "the safer side: it fails only when LogP is above 3 AND polar "
            "surface area is below 75 A^2, the combination associated with "
            "higher in-vivo toxicity risk in Hughes et al.'s analysis. "
            "Passing is the absence of that flag, not evidence of safety.",
            tier=3,
        ),
        _contract(
            "gsk_400_pass",
            "The GSK 4/400 guide, inverted so that PASS is the safer side: "
            "it fails only when LogP is above 4 AND molecular weight is "
            "above 400. Derived from a large internal dataset as a "
            "promiscuity and attrition signal.",
            tier=3,
        ),
        _contract(
            "rule_of_three_pass",
            "Congreve's Rule of Three for fragment screening, as applied "
            "here: molecular weight under 300, LogP at most 3, at most 3 "
            "H-bond donors and at most 3 acceptors. The published rule also "
            "bounds rotatable bonds; this implementation does not, so it is "
            "slightly more permissive.",
            tier=3,
        ),
        _contract(
            "bbb_permeant",
            "A blood-brain-barrier heuristic: polar surface area at most 90 "
            "A^2 and molecular weight at most 450. A SIMPLIFIED "
            "APPROXIMATION, not the published Clark regression it is named "
            "for, and CNS penetration depends on transport and efflux this "
            "cannot see.",
            tier=3,
            help_anchor="limits-admet",
        ),
        _contract(
            "bioavailability_likely",
            "An oral-bioavailability heuristic: polar surface area between "
            "20 and 130 A^2, at most 10 rotatable bonds, and at most one "
            "Lipinski violation. A SIMPLIFIED APPROXIMATION rather than a "
            "reproduction of the Abbott Bioavailability Score.",
            tier=3,
            help_anchor="limits-admet",
        ),
        # --- shape, which needs a real 3D conformer ----------------------
        _contract(
            "radius_of_gyration",
            "The mass-weighted root-mean-square distance of the atoms from "
            "the centre of mass, in A. Measured on a real 3D conformer, so "
            "it describes the conformer it was run on rather than the "
            "molecule in general.",
        ),
        _contract(
            "asphericity",
            "How far the mass distribution departs from spherical, 0 to 1: "
            "0 is a perfect sphere and 1 is a straight line. Computed from "
            "the principal moments of inertia of one conformer.",
        ),
        _contract(
            "spherocity_index",
            "Spherocity, 0 to 1, where 1 is a sphere. It rises as the three "
            "principal moments of inertia converge, so it separates "
            "globular shapes from rods and discs -- a property of the "
            "conformer, not of the molecule.",
        ),
        _contract(
            "inertial_shape_factor",
            "The middle principal moment divided by the product of the "
            "smallest and largest. It distinguishes rod-like from disc-like "
            "mass distributions where a single size number cannot, and it "
            "has no units.",
        ),
        _contract(
            "pmi1",
            "The smallest principal moment of inertia of this conformer. The "
            "three moments are meaningful mainly as ratios -- the absolute "
            "values scale with both mass and size.",
        ),
        _contract(
            "pmi2",
            "The middle principal moment of inertia of this conformer. Read "
            "it alongside the other two: their ratios describe shape where "
            "any one alone describes size.",
        ),
        _contract(
            "pmi3",
            "The largest principal moment of inertia of this conformer, "
            "about the axis the mass is spread furthest from.",
        ),
        _contract(
            "npr1",
            "The smallest principal moment divided by the largest, 0 to 1. "
            "With NPR2 it places the conformer on the rod/disc/sphere "
            "triangle: a rod sits near (0, 1), a disc near (0.5, 0.5) and a "
            "sphere at (1, 1).",
        ),
        _contract(
            "npr2",
            "The middle principal moment divided by the largest, 0.5 to 1. "
            "Plotted against NPR1 it is half of the standard shape "
            "triangle -- neither number means much alone.",
        ),
        _contract(
            "pbf",
            "The mean distance of the atoms from their own plane of best "
            "fit, in A. Near zero for a flat molecule and larger the more "
            "three-dimensional the conformer is; it needs real 3D "
            "coordinates, so a flat drawing cannot produce one.",
        ),
    ]
)


def contract_for(help_id: str) -> HelpTooltip | None:
    """What this fact means, or None if nothing has been written for it.

    **None IS A REAL ANSWER AND NOT A FAILURE.** Most facts in this
    application come from calculators whose results already carry their own
    evidence and limitations on the row; the registry exists for the values
    that have nowhere else to say what they are.
    """
    return CONTRACTS.get(help_id) if help_id else None
