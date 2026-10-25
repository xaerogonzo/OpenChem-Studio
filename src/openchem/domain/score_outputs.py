"""The approved outputs a derived score may name (`docs/DERIVED_SCORES_DESIGN.md` section 3), and the two rules that live on them.

A formula never names a calculator, a result id or a label somebody typed: it names an INPUT, and each input is bound to one entry of the
table below. An entry is an output the application already produces that a person has approved for this use, with the unit it carries
and a tag for the quantity it estimates.

**WHAT MAY BE APPROVED** (`tools/sweep_score_outputs.py` lists the candidates, `tests/test_score_outputs.py` holds the entries to the
registry):

* a number the producer TYPED as a number. Most report calculators carry theirs as text already rounded by the person's decimal-places
  setting (`'63.60'`), and a score built on one would change when that setting did, so none of those is here; the producer has to type its
  value before it can be approved;
* from the always-on descriptors, or from a calculator that is STABLE or LIMITED and offered by default (an EXPERIMENTAL or hidden
  calculator's output would put one unvalidated thing on top of another);
* of ONE input, which the entry names (`ApprovedOutput.input`): the DRAWING for nearly all of them, and for the geometry outputs (the ten shape descriptors, eight of Geometry Analysis's sizes, HOMA's two extremes, the
  dipole's magnitude and five surface numbers) the GEOMETRY of the conformer every
  calculation already gets (`chem/calculation_input.canonical_conformer`: the newest ORCA-optimised one, otherwise the lowest force-field energy). The always-on descriptors
  used to run on both and store two results under one id, which is why an output now has exactly one input and a result of the other is never read for it
  (`docs/DERIVED_SCORES_DESIGN.md`, section 11);
* whose id does not depend on the structure (a torsion is named by its atoms and a ring by its size, so neither is an id);
* whose unit this language can say truthfully (`MPa^0.5` and `cm3/mol / 100` cannot be written, so Hansen's parameters and McGowan's
  volume wait).

**THE UNIT IS CHECKED ON EVERY READ, NEVER CONVERTED.** An entry declares the unit in the language of `score_units` AND the exact string the
result carries (`carried_as`), because the application spells one unit several ways (`A` and `Å`, `Å²` and `A^2`, and no unit at all for a
logarithm). A result carrying any other string is refused, so a producer that changes its units turns a score into a refusal and not into a
different number.

**CONSENSUS IS UNEXPRESSIBLE** (section 6). Each entry carries an endpoint tag, and a definition with two inputs of one tag is refused: two
estimates of one quantity, combined, are a consensus predictor, which this project has measured and refused. The tag is a person's judgement
and can be wrong; the rule stops the application offering a consensus, it does not stop a person writing one somewhere else.

Pure: no Qt, no chemistry.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from openchem.domain.calculator import DRAWING, GEOMETRY
from openchem.domain.score_constants import Constant, check_constants, constant_values
from openchem.domain.score_formula import (
    FormulaError,
    Problem,
    Refusal,
    check_input_names,
)
from openchem.domain.score_units import Unit, parse_unit

#: The calculation input an approved output is read from unless its entry says otherwise. An output has exactly ONE input, so it has exactly one current result to read.
READ_FROM = DRAWING

#: The reviewed list of endpoint tags, each with the quantity it names. A tag is shared by every output that estimates that quantity, which is
#: what makes a consensus of them refusable. Closed: a new tag is a review, and `tests/test_score_outputs.py` fails a tag nothing uses.
ENDPOINTS: dict[str, str] = {
    "molecular_weight": "the average molecular mass",
    "exact_mass": "the monoisotopic mass",
    "logp_octanol_water": "the octanol-water partition coefficient of the neutral molecule, as a logarithm",
    "polar_surface_area": "the topological polar surface area",
    "labute_surface_area": "Labute's approximate accessible surface area",
    "hbond_donor_count": "the number of hydrogen-bond donors",
    "hbond_acceptor_count": "the number of hydrogen-bond acceptors",
    "rotatable_bond_count": "the number of rotatable bonds",
    "heavy_atom_count": "the number of non-hydrogen atoms",
    "ring_count": "the number of rings",
    "stereocentre_count": "the number of stereocentres",
    "fraction_sp3_carbon": "the fraction of carbon atoms that are sp3",
    "qed_drug_likeness": "the quantitative estimate of drug-likeness",
    "synthetic_accessibility": "the synthetic accessibility score",
    "bertz_complexity": "the Bertz topological complexity index",
    "natural_product_likeness": "the natural-product-likeness score",
    "aqueous_solubility_intrinsic": "the intrinsic aqueous solubility, in any of its units",
    "oxygen_balance_co2": "the oxygen balance to carbon dioxide",
    "oxygen_balance_co": "the oxygen balance to carbon monoxide",
    "molecular_polarizability": "the isotropic molecular polarizability, as a volume",
    "aromatic_ring_count": "the number of aromatic rings, as RDKit's CalcNumAromaticRings counts them (biphenylene is 2 and azulene 0)",
    # PROVISIONAL: the eight Topology Analysis tags below were accepted "for now" (2026-10-15, #351) and are meant to be revisited. A tag is never stored in a definition or a project file, so changing
    # one is cheap, except that MERGING two can turn a saved score into a refused one: `docs/DERIVED_SCORES_DESIGN.md`, decision 6.
    "balaban_j_index": "the Balaban J index, as RDKit computes it, of the molecular graph without hydrogens",
    "harary_index": "the Harary index: half the sum of the reciprocal topological distances between atoms, of the molecular graph without hydrogens",
    "hyper_wiener_index": "the hyper-Wiener index: half the sum of every topological distance and its square, of the molecular graph without hydrogens",
    "platt_index": "the Platt index: the sum over bonds of the two atoms' degrees less two, of the molecular graph without hydrogens",
    "randic_index": "the Randic connectivity index: the sum over bonds of one over the square root of the product of the two atoms' degrees, without hydrogens",
    "szeged_index": "the Szeged index: the sum over bonds of the atoms nearer one end times the atoms nearer the other, of the molecular graph without hydrogens",
    "wiener_index": "the Wiener index: half the sum of all topological distances between atoms, of the molecular graph without hydrogens",
    "wiener_polarity": "the Wiener polarity number: the count of atom pairs exactly three bonds apart, in the molecular graph without hydrogens",
    # PROVISIONAL, like the sixteen above (the ten shape descriptors, 2026-10-17). Each is measured on a CONFORMER, hydrogens included, and is one quantity of its own: the three principal
    # moments are three different numbers, so they carry three tags, and a formula may combine them (a ratio of two of them is a legitimate thing to write). Their definitions were checked against RDKit's
    # numbers by reproducing each (`docs/DERIVED_SCORES_DESIGN.md`, section 11).
    "principal_moment_1": "the smallest principal moment of inertia of the conformer (mass-weighted, amu*Å^2)",
    "principal_moment_2": "the middle principal moment of inertia of the conformer (mass-weighted, amu*Å^2)",
    "principal_moment_3": "the largest principal moment of inertia of the conformer (mass-weighted, amu*Å^2)",
    "normalized_pmi_ratio_1": "the smallest principal moment of the conformer over the largest (NPR1)",
    "normalized_pmi_ratio_2": "the middle principal moment of the conformer over the largest (NPR2)",
    "radius_of_gyration": "the mass-weighted radius of gyration of the conformer, in Å",
    "asphericity": "the asphericity of the conformer's mass-weighted gyration tensor, as RDKit computes it",
    "spherocity_index": "the spherocity index of the conformer: three times the smallest covariance eigenvalue of its atom positions over their sum",
    "inertial_shape_factor": "the inertial shape factor of the conformer: the middle moment over the product of the other two, in 1/(amu*Å^2)",
    "plane_of_best_fit": "the mean distance of the conformer's atoms from their best-fit plane, in Å",
    # PROVISIONAL, like the ten above (eight of Geometry Analysis's sizes, 2026-10-17). Each is measured on the conformer every calculation uses, hydrogens included, and is one quantity of its own. The two radii
    # from the centroid are of the UNWEIGHTED centroid of the atom positions; the six projection numbers are of the shadow the atoms cast as circles of Bondi's van der Waals radii
    # (`chem/projection_geometry.py`, whose search for the extremes is tested against a denser sweep). Left out by decision: the smallest radius from the centroid (0 for a molecule whose centroid is on an
    # atom, and the least stable of the sizes across the conformers of one molecule) and the three force-field energies (no meaning between molecules).
    "max_radius_from_centroid": "the largest distance from the centroid of the conformer's atom positions (every atom, hydrogens included, unweighted) to an atom, in Å",
    "mean_radius_from_centroid": "the mean distance of the conformer's atoms from the centroid of their positions (every atom, hydrogens included, unweighted), in Å",
    "min_projection_area": "the smallest area of the shadow the conformer's atoms cast, each a circle of its Bondi van der Waals radius, over every viewing direction, in Å^2",
    "max_projection_area": "the largest area of the shadow the conformer's atoms cast, each a circle of its Bondi van der Waals radius, over every viewing direction, in Å^2",
    "min_projection_radius": "the radius of the smallest circle that encloses the conformer's shadow in its smallest-area view (the round hole it passes through), in Å",
    "max_projection_radius": "the radius of the smallest circle that encloses the conformer's shadow in its largest-area view, in Å",
    "size_perpendicular_to_min_projection": "the extent of the conformer along its smallest-area viewing direction, from surface to surface (van der Waals radii included), in Å",
    "size_perpendicular_to_max_projection": "the extent of the conformer along its largest-area viewing direction, from surface to surface (van der Waals radii included), in Å",
    # PROVISIONAL, like the eighteen above (the two HOMA extremes, 2026-10-17). Each is one ring's own HOMA (Krygowski 1993, Table I, the multi-bond form) of the structure's smallest set of rings, never a sum or a mean,
    # and each is read only from an ORCA-optimised geometry: on a force-field conformer the bond lengths are the force field's own (`ApprovedOutput.needs_quantum_geometry`).
    "highest_ring_homa": "the highest HOMA (Krygowski 1993) of any ring in the structure's smallest set of rings, one ring's own value, on an ORCA-optimised geometry",
    "lowest_ring_homa": "the lowest HOMA (Krygowski 1993) of any ring in the structure's smallest set of rings, one ring's own value, on an ORCA-optimised geometry",
    # PROVISIONAL, like the geometry tags above (the dipole and five surface numbers, 2026-10-18). Each is measured on the conformer every calculation uses, hydrogens included, from Bondi's van der Waals radii (the surface
    # numbers) or Gasteiger's partial charges (the dipole), and is read only at the settings that make it one quantity: a neutral species for the dipole, the 1.4 Å probe and the structure as it is for the
    # accessible areas (`ApprovedOutput.run_with`). Left out by decision: the dipole's three components (the dipole in the conformer's own frame), the dipole under any other charge model (aspirin: 0.89 D from
    # Gasteiger, 4.76 D from EEM, 3.60 D from QEq), and ASA+ and ASA- (the area of the atoms whose Gasteiger charge is above or below nothing, which tiny charges decide: `docs/DERIVED_SCORES_DESIGN.md`, section 11).
    "dipole_magnitude": "the magnitude of the molecular dipole of the conformer, from Gasteiger (PEOE) partial charges, about the centre of mass, of a species with no net charge, in Debye",
    "accessible_surface_area": "the area of the surface traced by the centre of a probe of radius 1.4 Å (a water molecule's) rolling over the conformer's atoms, each a sphere of its Bondi van der Waals radius, in Å^2",
    "hydrophobic_accessible_surface_area": "the part of the conformer's accessible area (1.4 Å probe) that lies on atoms that are not polar, meaning not N, O or F nor a hydrogen bonded to one of them, in Å^2",
    "polar_accessible_surface_area": "the part of the conformer's accessible area (1.4 Å probe) that lies on N, O and F atoms and the hydrogens bonded to them, in Å^2",
    "van_der_waals_surface_area": "the area of the surface of the conformer's fused van der Waals spheres (Bondi's radii, no probe), in Å^2",
    "van_der_waals_volume": "the volume enclosed by the conformer's fused van der Waals spheres (Bondi's radii), in Å^3",
    # PROVISIONAL, like the eight above (eight counts, 2026-10-16; two more share the tags `ring_count` and `stereocentre_count`). The ring counts are of the rings RDKit's ring information lists, which is why a cage has
    # more rings than independent cycles.
    "bond_count": "the number of bonds between non-hydrogen atoms",
    "carbocyclic_ring_count": "the number of rings made only of carbon atoms, of the rings RDKit's ring information lists",
    "chain_atom_count": "the number of non-hydrogen atoms that are in no ring",
    "chain_bond_count": "the number of bonds between non-hydrogen atoms that are in no ring",
    "fused_ring_count": "the number of rings that share at least one bond with another ring, of the rings RDKit's ring information lists",
    "heterocyclic_ring_count": "the number of rings with at least one atom that is not carbon, of the rings RDKit's ring information lists",
    "ring_atom_count": "the number of non-hydrogen atoms that are in a ring",
    "ring_bond_count": "the number of bonds between non-hydrogen atoms that are in a ring",
}


@dataclass(frozen=True)
class ApprovedOutput:
    """One output a formula may name."""

    #: The batch column id, reused and not invented, because saved tables and exports already depend on it:
    #: `descriptor:<id>` or `calculator:<calculator id>:<fact label>`.
    output_id: str
    #: What the number is, in the language of `score_units` (`1` for a count, a ratio or a logarithm).
    unit: str
    #: The exact string the result carries as its units, and the only one accepted. `""` is allowed only for the unit `1`.
    carried_as: str
    #: A key of `ENDPOINTS`.
    endpoint: str
    #: The date this was approved (ISO), because the version it first shipped in is not known when it is written.
    approved: str
    #: The calculation input the number is read from: `drawing` (`READ_FROM`) or `geometry`, the conformer every calculation uses. A result stored under the other input is never read for this output.
    input: str = READ_FROM
    #: What must hold of HOW the calculator measured it, beyond the input: `""` asks nothing more, `AS_STORED` that it measured the stored conformer itself (not a copy it relaxed, nor a conformer it chose), and
    #: `AS_STORED_UNSCALED` that, and that its van der Waals radii were not scaled. Only Geometry Analysis has options that change what it measures, and its record says which were used (`score_value.not_applicable_reason`).
    measured_as: str = ""
    #: True when the producer measures EVERY fragment of the structure (Geometry Analysis's scope is the whole structure). A structure of several fragments (a salt, a hydrate) then has no shape of its
    #: own, because the embedder packs the pieces together at an arbitrary offset, and a score declines it. False for the always-on shape descriptors, which are computed on the ChEMBL parent compound
    #: (`chem/components.py`; the largest component, labelled, when there is no single parent, and a refusal when no component is larger), so a salt is already handled where they are made.
    whole_structure: bool = False
    #: True when the number reads BOND LENGTHS, which are a measurement only on a geometry a quantum calculation optimised: on a force-field conformer they are the force field's own (HOMA of naphthalene's rings is
    #: 0.94 on the MMFF94 conformer and 0.74 on an ORCA B3LYP/def2-SVP geometry). A score reads such a number only from a conformer whose method is a quantum optimisation (`conformer.QUANTUM_OPTIMIZED_METHODS`),
    #: and the evidence names the level of theory.
    needs_quantum_geometry: bool = False
    #: What must hold of the SETTINGS the calculator ran with, which its record says: `""` asks nothing, `GASTEIGER_NEUTRAL` that the dipole came from Gasteiger's charges and is of a species with no net charge,
    #: `DEFAULT_PROBE_AS_DRAWN` that the accessible area used the default 1.4 Å probe and is of the structure as it is, and `AS_DRAWN` only the second (the van der Waals numbers touch no probe). A result made
    #: any other way is declined, naming how (`score_value.not_applicable_reason`); it is not converted, because the numbers differ (aspirin's accessible area is 7% lower at a 1.2 Å probe).
    run_with: str = ""


def _entry(output_id: str, unit: str, carried_as: str, endpoint: str) -> ApprovedOutput:
    return ApprovedOutput(output_id, unit, carried_as, endpoint, "2026-10-14")


#: `ApprovedOutput.measured_as`: the number must be of the stored conformer itself, as it is.
AS_STORED = "as_stored"

#: `ApprovedOutput.measured_as`: of the stored conformer as it is, and with the van der Waals radii unscaled (the six projection numbers).
AS_STORED_UNSCALED = "as_stored_unscaled"

#: Every value `ApprovedOutput.measured_as` may take; a guard holds each entry to it.
MEASURED_AS = frozenset({"", AS_STORED, AS_STORED_UNSCALED})


#: `ApprovedOutput.run_with`: the dipole must come from Gasteiger's charges and be of a species with no net charge.
GASTEIGER_NEUTRAL = "gasteiger_neutral"

#: `ApprovedOutput.run_with`: the accessible area must have used the default probe and be of the structure as it is, not of the major microspecies at a pH.
DEFAULT_PROBE_AS_DRAWN = "default_probe_as_drawn"

#: `ApprovedOutput.run_with`: the number must be of the structure as it is, not of the major microspecies at a pH (the van der Waals numbers touch no probe, so any probe is fine).
AS_DRAWN = "as_drawn"

#: Every value `ApprovedOutput.run_with` may take; a guard holds each entry to it.
RUN_WITH = frozenset({"", GASTEIGER_NEUTRAL, DEFAULT_PROBE_AS_DRAWN, AS_DRAWN})


def _geometry_entry(
    output_id: str, unit: str, carried_as: str, endpoint: str, measured_as: str = "", whole_structure: bool = False, needs_quantum_geometry: bool = False,
    run_with: str = "", approved: str = "2026-10-17",
) -> ApprovedOutput:
    """An output measured on the conformer every calculation gets, and read from the result stored under its geometry fingerprint."""
    return ApprovedOutput(output_id, unit, carried_as, endpoint, approved, GEOMETRY, measured_as, whole_structure, needs_quantum_geometry, run_with)


#: The table. Sorted by id, so a review diff reads as additions. Every entry resolves, through the registry, to a finite number carrying
#: `carried_as` on the census panel (`tests/test_score_outputs.py`), and a rename of a fact label turns that red and says which scores it breaks.
APPROVED: tuple[ApprovedOutput, ...] = (
    _entry("calculator:bbb_descriptors:Aromatic rings", "1", "", "aromatic_ring_count"),
    # The dipole is measured on the whole structure like the sizes, so a salt is declined: where one ion sits beside the other is arbitrary (metformin hydrochloride: 0.56 to 2.58 D over ten embeddings).
    _geometry_entry("calculator:dipole_moment:Dipole", "D", "Debye", "dipole_magnitude", whole_structure=True, run_with=GASTEIGER_NEUTRAL, approved="2026-10-18"),
    _geometry_entry("calculator:geometry_analysis:Max projection area", "Å^2", "A^2", "max_projection_area", AS_STORED_UNSCALED, True),
    _geometry_entry("calculator:geometry_analysis:Max projection radius", "Å", "A", "max_projection_radius", AS_STORED_UNSCALED, True),
    _geometry_entry("calculator:geometry_analysis:Max radius (from centroid)", "Å", "A", "max_radius_from_centroid", AS_STORED, True),
    _geometry_entry("calculator:geometry_analysis:Mean radius (from centroid)", "Å", "A", "mean_radius_from_centroid", AS_STORED, True),
    _geometry_entry("calculator:geometry_analysis:Min projection area", "Å^2", "A^2", "min_projection_area", AS_STORED_UNSCALED, True),
    _geometry_entry("calculator:geometry_analysis:Min projection radius", "Å", "A", "min_projection_radius", AS_STORED_UNSCALED, True),
    _geometry_entry("calculator:geometry_analysis:Size perpendicular to the max projection", "Å", "A", "size_perpendicular_to_max_projection", AS_STORED_UNSCALED, True),
    _geometry_entry("calculator:geometry_analysis:Size perpendicular to the min projection", "Å", "A", "size_perpendicular_to_min_projection", AS_STORED_UNSCALED, True),
    _geometry_entry("calculator:homa_aromaticity:Highest HOMA of any ring", "1", "", "highest_ring_homa", needs_quantum_geometry=True),
    _geometry_entry("calculator:homa_aromaticity:Lowest HOMA of any ring", "1", "", "lowest_ring_homa", needs_quantum_geometry=True),
    _entry("calculator:oxygen_balance:Oxygen balance (CO basis)", "%", "%", "oxygen_balance_co"),
    _entry("calculator:oxygen_balance:Oxygen balance (CO₂ basis)", "%", "%", "oxygen_balance_co2"),
    _entry("calculator:polarizability:Molecular polarizability", "Å^3", "A^3", "molecular_polarizability"),
    _entry("calculator:solubility:Predicted intrinsic solubility (mg/mL)", "mg/mL", "mg/mL", "aqueous_solubility_intrinsic"),
    _entry("calculator:solubility:Predicted intrinsic solubility (mol/L)", "mol/L", "mol/L", "aqueous_solubility_intrinsic"),
    # The surface numbers are measured on the whole structure like the sizes. The three accessible areas need the default probe; the van der Waals area and volume do not touch a probe.
    _geometry_entry("calculator:surface_analysis:ASA (solvent accessible)", "Å^2", "Å²", "accessible_surface_area", whole_structure=True, run_with=DEFAULT_PROBE_AS_DRAWN, approved="2026-10-18"),
    _geometry_entry("calculator:surface_analysis:ASA_H (hydrophobic)", "Å^2", "Å²", "hydrophobic_accessible_surface_area", whole_structure=True, run_with=DEFAULT_PROBE_AS_DRAWN, approved="2026-10-18"),
    _geometry_entry("calculator:surface_analysis:ASA_P (polar)", "Å^2", "Å²", "polar_accessible_surface_area", whole_structure=True, run_with=DEFAULT_PROBE_AS_DRAWN, approved="2026-10-18"),
    _geometry_entry("calculator:surface_analysis:van der Waals surface area", "Å^2", "Å²", "van_der_waals_surface_area", whole_structure=True, run_with=AS_DRAWN, approved="2026-10-18"),
    _geometry_entry("calculator:surface_analysis:van der Waals volume", "Å^3", "Å³", "van_der_waals_volume", whole_structure=True, run_with=AS_DRAWN, approved="2026-10-18"),
    # Shares the tag of `descriptor:num_stereocenters`: the same on every census row (`identical_pairs`), and different only where a centre is stereogenic without being asymmetric (cubane 0 against 8).
    _entry("calculator:topology_analysis:Asymmetric atom count", "1", "", "stereocentre_count"),
    _entry("calculator:topology_analysis:Balaban index", "1", "", "balaban_j_index"),
    _entry("calculator:topology_analysis:Bond count", "1", "", "bond_count"),
    _entry("calculator:topology_analysis:Carbo ring count", "1", "", "carbocyclic_ring_count"),
    _entry("calculator:topology_analysis:Chain atom count", "1", "", "chain_atom_count"),
    _entry("calculator:topology_analysis:Chain bond count", "1", "", "chain_bond_count"),
    # Shares the tag of `descriptor:ring_count`: the same on every census row (`identical_pairs`), and different only on a cage (cubane 5 independent cycles against RDKit's 6 rings).
    _entry("calculator:topology_analysis:Cyclomatic number", "1", "", "ring_count"),
    _entry("calculator:topology_analysis:Fused ring count", "1", "", "fused_ring_count"),
    _entry("calculator:topology_analysis:Harary index", "1", "", "harary_index"),
    _entry("calculator:topology_analysis:Hetero ring count", "1", "", "heterocyclic_ring_count"),
    _entry("calculator:topology_analysis:Hyper Wiener index", "1", "", "hyper_wiener_index"),
    _entry("calculator:topology_analysis:Platt index", "1", "", "platt_index"),
    _entry("calculator:topology_analysis:Randic index", "1", "", "randic_index"),
    _entry("calculator:topology_analysis:Ring atom count", "1", "", "ring_atom_count"),
    _entry("calculator:topology_analysis:Ring bond count", "1", "", "ring_bond_count"),
    _entry("calculator:topology_analysis:Szeged index", "1", "", "szeged_index"),
    _entry("calculator:topology_analysis:Wiener index", "1", "", "wiener_index"),
    _entry("calculator:topology_analysis:Wiener polarity", "1", "", "wiener_polarity"),
    _geometry_entry("descriptor:asphericity", "1", "", "asphericity"),
    _entry("descriptor:bertz_ct", "1", "", "bertz_complexity"),
    _entry("descriptor:esol_logs", "1", "", "aqueous_solubility_intrinsic"),
    _entry("descriptor:exact_mass", "g/mol", "g/mol", "exact_mass"),
    _entry("descriptor:fsp3", "1", "", "fraction_sp3_carbon"),
    _entry("descriptor:heavy_atom_count", "1", "", "heavy_atom_count"),
    _geometry_entry("descriptor:inertial_shape_factor", "1/amu*Å^2", "1/(amu·Å²)", "inertial_shape_factor"),
    _entry("descriptor:labute_asa", "Å^2", "Å²", "labute_surface_area"),
    _entry("descriptor:mol_logp", "1", "", "logp_octanol_water"),
    _entry("descriptor:mol_wt", "g/mol", "g/mol", "molecular_weight"),
    _entry("descriptor:np_likeness", "1", "", "natural_product_likeness"),
    _geometry_entry("descriptor:npr1", "1", "", "normalized_pmi_ratio_1"),
    _geometry_entry("descriptor:npr2", "1", "", "normalized_pmi_ratio_2"),
    _entry("descriptor:num_hba", "1", "", "hbond_acceptor_count"),
    _entry("descriptor:num_hbd", "1", "", "hbond_donor_count"),
    _entry("descriptor:num_rotatable_bonds", "1", "", "rotatable_bond_count"),
    _entry("descriptor:num_stereocenters", "1", "", "stereocentre_count"),
    _geometry_entry("descriptor:pbf", "Å", "Å", "plane_of_best_fit"),
    _geometry_entry("descriptor:pmi1", "amu*Å^2", "amu·Å²", "principal_moment_1"),
    _geometry_entry("descriptor:pmi2", "amu*Å^2", "amu·Å²", "principal_moment_2"),
    _geometry_entry("descriptor:pmi3", "amu*Å^2", "amu·Å²", "principal_moment_3"),
    _entry("descriptor:qed", "1", "", "qed_drug_likeness"),
    _geometry_entry("descriptor:radius_of_gyration", "Å", "Å", "radius_of_gyration"),
    _entry("descriptor:ring_count", "1", "", "ring_count"),
    _entry("descriptor:sa_score", "1", "", "synthetic_accessibility"),
    _geometry_entry("descriptor:spherocity_index", "1", "", "spherocity_index"),
    _entry("descriptor:tpsa", "Å^2", "Å²", "polar_surface_area"),
)

#: The table by id.
_BY_ID: dict[str, ApprovedOutput] = {entry.output_id: entry for entry in APPROVED}


def approved_output(output_id: str) -> ApprovedOutput | None:
    """The entry for `output_id`, or None when it is not approved."""
    return _BY_ID.get(output_id)


def output_title(output_id: str) -> str:
    """What an output is called without its namespace: a descriptor's id (`tpsa`), or a calculator's fact label (`Oxygen balance (CO basis)`)."""
    kind, _, rest = output_id.partition(":")
    return rest if kind == "descriptor" else rest.partition(":")[2]


def unit_of(output: ApprovedOutput) -> Unit:
    """The unit of an entry, parsed. Raises `UnitError` for an entry whose unit is not written correctly, which a test forbids."""
    return parse_unit(output.unit)


def check_inputs(inputs: Sequence[tuple[str, str]], constants: Sequence[Constant] = ()) -> dict[str, Unit]:
    """The units of a definition's inputs and constants, or a `FormulaError`.

    `inputs` is `(name, output id)` in the order the definition lists them. Refused, in this order: a bad name or too many inputs; an output
    that is not approved; one output bound under two names; two outputs of one endpoint (section 6), which says why; and then a constant
    that is not usable (`score_constants.check_constants`). The result is what `score_formula.check_definition` takes as `input_units`.
    """
    check_input_names([name for name, _ in inputs])
    units: dict[str, Unit] = {}
    bound: dict[str, str] = {}
    by_endpoint: dict[str, tuple[str, str]] = {}
    for name, output_id in inputs:
        output = approved_output(output_id)
        if output is None:
            raise FormulaError(
                Problem.OUTPUT,
                f"{name}: {output_id!r} is not an approved output. A formula may name only the outputs the application has approved for scores.",
            )
        if output_id in bound:
            raise FormulaError(
                Problem.INPUTS, f"{name} and {bound[output_id]} are the same output ({output_id}); use one name for it"
            )
        bound[output_id] = name
        if output.endpoint in by_endpoint:
            other_name, other_id = by_endpoint[output.endpoint]
            raise FormulaError(
                Problem.CONSENSUS,
                f"{other_name} ({other_id}) and {name} ({output_id}) both estimate {ENDPOINTS[output.endpoint]}. Two estimates of one quantity, "
                "combined, are a consensus predictor, which this project has measured and does not offer; choose one.",
            )
        by_endpoint[output.endpoint] = (name, output_id)
        units[name] = unit_of(output)
    units.update(check_constants(constants, list(units)))
    return units


def accept_value(output: ApprovedOutput, value: object, carried_as: str) -> float:
    """The number a result carries for `output`, or a `Refusal`: never a conversion, never a coerced value.

    Refused: a value that is not a number the producer typed (a bool, a string), a non-finite one, and a result carrying any units string but
    the one the entry declares.
    """
    if isinstance(value, str):
        # The case a person reaches by an ordinary action: a calculator with several methods or options types only its DEFAULT answer (`Polarizability`: Jensen on the drawing), and the others
        # stay text, so running Miller's method leaves a score over it with this reason, which has to say why and not name a Python type.
        raise Refusal(
            output.output_id,
            "the result is text, not a number a score may read: only a calculator's default answer is typed as a number, so another method or option of it gives none",
        )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Refusal(output.output_id, f"the result is not a number ({type(value).__name__})")
    number = float(value)
    if not math.isfinite(number):
        raise Refusal(output.output_id, "the result is not a finite number")
    if carried_as != output.carried_as:
        raise Refusal(
            output.output_id,
            f"the result carries the unit {carried_as!r} and the approved unit is {output.carried_as!r}; nothing is converted",
        )
    return number


def values_by_name(
    inputs: Sequence[tuple[str, str]], read: Mapping[str, tuple[object, str]], constants: Sequence[Constant] = ()
) -> dict[str, float]:
    """The values to evaluate a formula with, one per input name and one per constant, from what was read for each output id as
    `(value, carried units)`.

    An output with nothing read for it is a `Refusal` naming it: never a zero, never a skipped term (section 7).
    """
    values: dict[str, float] = {}
    for name, output_id in inputs:
        output = approved_output(output_id)
        if output is None:
            raise Refusal(output_id, "not an approved output")
        if output_id not in read:
            raise Refusal(output_id, f"{name} has no current result to read")
        value, carried = read[output_id]
        values[name] = accept_value(output, value, carried)
    values.update(constant_values(constants))
    return values
