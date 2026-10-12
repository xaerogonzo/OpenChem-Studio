"""The execution policy of every calculator that ships, and what each is based on.

**MEASURED 2026-10-12, through the same Qt-free path the command line uses, on three molecules:
ethanol (3 heavy atoms), aspirin (13) and atorvastatin (41), each with one seeded conformer.**
`benchmarks/calculator_cost/` holds the scripts and the figures. Four findings shaped the table,
and a table written from default-settings timings alone would have been wrong on all four:

* **Sixty-one registry calculators ran in under 1.3 s at their defaults.** That says nothing
  about a setting a model might choose.
* **Cost scales with a parameter in four of them, measurably.** `hbond_vs_ph` takes 0.6 s at a 0.5 pH step and
  16.7 s at 0.01; molecular dynamics is 0.17 s at 1,000 steps and 16.6 s at 100,000; Geometry (3D)
  with `conformer_policy=always` is 4.0 s at 20 conformers and 29.7 s at 200 where `never` stays
  at 1.1 s; the stereoisomer enumerator is 1.1 s at a 2,000-structure cap and 2.9 s at 10,000. The tautomer and
  resonance enumerators carry the same cap as a precaution (0.8 s and 0.00 s at 10,000: they did not
  scale on the molecules tried), and the three pH sweeps that need the pKa sidecar carry `hbond_vs_ph`'s
  step floor by analogy, unmeasured because the sidecar is unconfigured. The
  policies below carry the measured bounds, so a request outside them is approved by a person
  rather than refused or run.
* **Alignment is slow on realistic molecules.** A 41-heavy-atom molecule took 0.6 s aligned to a
  13-heavy-atom reference and **31 s aligned to a 28-heavy-atom one**; that second pair took 46 s with
  MCS, and 74 to 104 s on `Accurate` and 109 to 163 s with both across four runs (the `Accurate` runs
  differ more between runs than anything else here). It is `CONFIRM`.
* **Four calculators only refused at their defaults** (`lewis_adduct`, `detonation`,
  `alignment_3d`, `markush_enumeration`: each needs an input), so the sweep timed a refusal. They
  were re-measured with real inputs: 0.004 s, 0.001 s, 0.6 s to 31 s and 0.002 s.

**WHAT WAS NOT MEASURED IS FILED AS NOT MEASURED, NOT AS CHEAP.** ADMET-AI (a model load in its own
interpreter), OPSIN (a JVM), and Markush enumeration (output size is set by a pattern the caller
writes) are `CONFIRM` for that reason, and say so. The pkasolver sidecar was unconfigured in the
sweep, so its figure is the one the roadmap recorded when the cross-check shipped (a cold call of
2.9 to 3.1 s, cached per structure afterwards, `docs/ROADMAP.md` 2026-09-14), cited as that.

Attached to the definitions by `bootstrap`, never looked up by id at decision time: see
`domain.execution_policy`.
"""

from __future__ import annotations

from types import MappingProxyType

from openchem.domain.execution_policy import AiRun, ExecutionPolicy, ResourceClass

_SWEEP = "benchmarks/calculator_cost/results.json, 2026-10-12"
_PANEL = (
    f"worst of ethanol, aspirin and atorvastatin (41 heavy atoms) at default settings ({_SWEEP})"
)
_PKASOLVER = (
    "a cold pkasolver call took 2.9 to 3.1 s and is cached per structure afterwards "
    "(docs/ROADMAP.md, 2026-09-14); the sidecar was unconfigured in "
    f"{_SWEEP}, so this is the recorded figure, not a new one"
)

#: A pH sweep's step is its cost: 0.6 s at 0.5, 3.0 s at 0.1, 6.1 s at 0.05, 16.7 s at 0.01 for
#: `hbond_vs_ph` over -2 to 16 (benchmarks/calculator_cost).
_PH_STEP_FLOOR = (("ph_step", 0.1, None),)

#: Measured and instant at defaults, on the whole panel. Run with real inputs where the default
#: run only refused (`lewis_adduct`, `detonation`).
_INSTANT = (
    "atom_sasa", "atomic_polarizability", "bird_aromaticity", "crippen_logp_contrib",
    "crippen_mr_contrib", "detonation", "dipole_moment", "elemental_analysis",
    "functional_groups", "geometry_partial_charge", "griffin_hlb", "hansen_solubility",
    "hbond_sites", "homa_aromaticity", "huckel_analysis", "huckel_pi_density",
    "interaction_analysis", "joback_properties", "lewis_adduct", "lewis_sites", "locants",
    "major_microspecies", "mass_spectrum", "nmr_database", "orbital_electronegativity",
    "oxidation_states", "oxygen_balance", "polar_surface_area", "polarizability",
    "regulatory_screen", "ring_systems", "stereo_descriptors", "stereocenters",
    "steric_analysis", "structural_frameworks", "substance_analysis", "substructure_search",
    "surface_analysis", "topology_analysis", "topology_distance_degree",
    "topology_eccentricity", "torsion_table", "tsei_projection",
)

#: Registry calculators that read a pKa from the pkasolver sidecar. The map in `bootstrap`
#: (`_CALCULATOR_INTERPRETER_SETTING`) is what binds them; `tests/test_execution_policy.py`
#: fails if a calculator it names does not declare the tool here.
_PKASOLVER_AUTO = (
    "pka", "ionisable_sites", "cns_mpo", "bbb_descriptors", "gasteiger_charge_at_ph",
)
_PKASOLVER_SWEEP = ("logd", "pka_microspecies", "isoelectric_point")


def _auto(resource, measured, *, tools=(), bounds=(), excluded=()):
    return ExecutionPolicy(
        resource, AiRun.AUTO, external_tools=frozenset(tools),
        auto_bounds=tuple(bounds), auto_excluded=tuple(excluded), measured=measured,
    )


def _confirm(why, *, tools=(), writes=False):
    return ExecutionPolicy(
        ResourceClass.LONG, AiRun.CONFIRM, external_tools=frozenset(tools),
        writes_outside_results=writes, why_confirm=why,
    )


_table: dict[str, ExecutionPolicy] = {}

for _id in _INSTANT:
    _table[_id] = _auto(ResourceClass.INSTANT, _PANEL)

for _id in _PKASOLVER_AUTO:
    _table[_id] = _auto(ResourceClass.SHORT, _PKASOLVER, tools=("pkasolver",))
for _id in _PKASOLVER_SWEEP:
    _table[_id] = _auto(ResourceClass.SHORT, _PKASOLVER, tools=("pkasolver",), bounds=_PH_STEP_FLOOR)

_table["hbond_vs_ph"] = _auto(
    ResourceClass.SHORT,
    f"3.0 s over -2 to 16 at a 0.1 pH step, 6.1 s at 0.05, 16.7 s at 0.01 ({_SWEEP})",
    bounds=_PH_STEP_FLOOR,
)
_table["molecular_dynamics"] = _auto(
    ResourceClass.SHORT,
    f"0.17 s at 1,000 steps, 0.84 s at 5,000, 3.3 s at 20,000, 16.6 s at 100,000 on atorvastatin ({_SWEEP})",
    bounds=(("steps", None, 5000),),
)
_table["geometry_analysis"] = _auto(
    ResourceClass.SHORT,
    "1.1 s at its defaults, whatever the conformer count, while conformer_policy is `never`; "
    f"4.0 s at 20 generated conformers and 29.7 s at 200 under `always` ({_SWEEP})",
    excluded=(("conformer_policy", frozenset({"if_2d", "always"})),),
)
for _id in ("stereoisomers", "tautomers", "resonance_forms"):
    _table[_id] = _auto(
        ResourceClass.SHORT,
        f"stereoisomers on a 14-centre polyol: 1.1 s at a 2,000-structure cap, 2.9 s at 10,000; "
        f"tautomers 0.8 s at 10,000 ({_SWEEP})",
        bounds=(("max_structures", None, 2000),),
    )

_table["alignment_3d"] = _confirm(
    "Aligning a 41-heavy-atom molecule to a 28-heavy-atom reference took 31 s at its defaults, 46 s with the "
    "MCS method, and 74 to 104 s on Accurate and 109 to 163 s with both across four runs "
    "(benchmarks/calculator_cost); the same molecule aligned to a 13-heavy-atom reference took 0.6 s, so the time depends on the pair and cannot be "
    "promised in advance."
)
_table["iupac_name"] = _confirm(
    "It starts Java (OPSIN), reaches the network and writes temporary files; its time was not measured.",
    tools=("opsin_java", "network"), writes=True,
)
_table["markush_enumeration"] = _confirm(
    "How much it produces is set by the pattern it is given, up to 100,000 structures; only a small "
    "enumeration (0.002 s) was measured."
)
_table["admet_ml"] = _confirm(
    "It loads a model in its own interpreter (ADMET-AI) and its time was not measured.",
    tools=("admet_ai",),
)
_table["solubility"] = _confirm(
    "It uses both the pkasolver and the ADMET-AI interpreters, and the ADMET one was not measured.",
    tools=("pkasolver", "admet_ai"),
)

_table["docking.vina"] = _confirm(
    "AutoDock Vina runs for as long as the search takes and writes pose files.", tools=("vina",), writes=True,
)
for _id in (
    "orca.sp", "orca.opt", "orca.opt_freq", "orca.nmr", "orca.nmr_coupling", "orca.delta_scf",
    "orca.led", "orca.tautomer_distribution",
):
    _table[_id] = _confirm(
        "ORCA runs for minutes to hours depending on the molecule and method, and writes its own files.",
        tools=("orca",), writes=True,
    )
_table["lewis_hsab"] = _confirm(
    "Its values come from an ORCA run, so running it means running ORCA.", tools=("orca",), writes=True,
)

#: Calculator id -> policy, for every calculator that ships. Read-only.
BUILTIN_POLICIES = MappingProxyType(_table)
