"""Real `ValidationRow` instances (tools/validation_rows.py) for this survey's measured reference
values -- the first actual construction of that class anywhere in the project; until now only its own
tests exercised the schema. Two groups, kept apart because they answer different questions:

* `TM_ROWS` -- melting points from compare_energetics.py's `MOLECULES`, for every row with a real
  numeric `transition_type == "melting"` value (TATB and dinitrodiazetidine are excluded: TATB's is an
  unreached estimate per Klapoetke, and no measured value for dinitrodiazetidine was ever found -- see
  that module's own notes).
* `HF_ROWS` -- condensed- and gas-phase enthalpies of formation used this session to check
  `keshavarz_nitroaromatic2009`, `mathieu2018_apc`, and `orca_atom_equivalents`'s predictions, PLUS the
  seven compounds `orca_atom_equivalents` was actually calibrated on. The calibration compounds are
  `partition="development"` -- they are literally inside the fit, not independent evidence -- while
  every compound a route was CHECKED against (TNT, RDX, HMX, PETN) is `partition="selection"`: examined
  while comparing candidate routes, never touched by any fit, but not a genuinely untouched holdout
  either (see docs/research/literature.toml's marrero2001 entry for why this survey does not yet have
  one). RDX carries two rows, not one: Klapoetke states its condensed DfH twice, in different places, at
  slightly different values (66.6 kJ/mol, p.232 prose; 85.0 kJ/mol, Table 9.6, p.249) -- both are real,
  both are recorded, and literature.toml's `mathieu2018_apc` entry explains why this is a units-reading
  difference on this session's part in an EARLIER pass, not a live contradiction in the source.

**Field conventions established here, not inherited from precedent** (this module is the first real use
of the schema): for a melting-point row, `temperature_k` is set equal to `value` itself -- the
transition's own temperature is the only "reference condition" a melting point has -- and `phase` is
`"solid"` (the state whose melting is being described). For an enthalpy row, `temperature_k` is 298.15
(standard reference temperature; every source used here states or implies it) and `phase` is `"gas"` or
`"solid"` as the value itself is.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass looks its module up here, same convention as
    spec.loader.exec_module(module)  # tests/test_validation_rows.py's own fixture
    return module


validation_rows = _load("validation_rows", ROOT / "tools" / "validation_rows.py")
ValidationRow = validation_rows.ValidationRow
compare_energetics = _load("compare_energetics", ROOT / "benchmarks" / "thermophysical" / "compare_energetics.py")


def _tm_rows() -> list[ValidationRow]:
    rows = []
    for name, spec in compare_energetics.MOLECULES.items():
        if spec.get("transition_type") != "melting" or spec.get("measured_tm_k") is None:
            continue
        partition = "development" if spec["role"] == "development" else "selection"
        rows.append(
            ValidationRow(
                row_id=f"tm_{name.lower()}",
                smiles=spec["smiles"],
                property="melting_point",
                value=spec["measured_tm_k"],
                units="K",
                source_id="agrawal2010" if "Agrawal" in spec["secondary_reference"] else "nist_webbook",
                record_id=name,
                partition=partition,
                temperature_k=spec["measured_tm_k"],
                phase="solid",
                transition_type=spec["transition_type"],
                value_source=spec["value_source"],
                primary_reference=spec.get("primary_reference", ""),
                secondary_reference=spec.get("secondary_reference", ""),
            )
        )
    return rows


TM_ROWS = _tm_rows()


HF_ROWS = [
    # --- checked against, never fitted on ------------------------------------------------------
    ValidationRow(
        row_id="hf_tnt_solid",
        smiles="Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
        property="enthalpy_formation_solid",
        value=-67.1,
        units="kJ/mol",
        source_id="klapotke2017",
        record_id="p.232 prose, -295.5 kJ/kg converted at TNT's molar mass",
        partition="selection",
        temperature_k=298.15,
        phase="solid",
        value_source="secondary",
        secondary_reference="klapotke2017 p.232/243: DfH = -295.5 kJ/kg",
    ),
    ValidationRow(
        row_id="hf_rdx_solid_prose",
        smiles="O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]",
        property="enthalpy_formation_solid",
        value=66.6,
        units="kJ/mol",
        source_id="klapotke2017",
        record_id="p.232 prose, +299.7 kJ/kg converted at RDX's molar mass",
        partition="selection",
        temperature_k=298.15,
        phase="solid",
        value_source="secondary",
        secondary_reference="klapotke2017 p.232: DfH = +299.7 kJ/kg",
        note="a second, independent Klapoetke reading exists -- see hf_rdx_solid_table96",
    ),
    ValidationRow(
        row_id="hf_rdx_solid_table96",
        smiles="O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]",
        property="enthalpy_formation_solid",
        value=85.0,
        units="kJ/mol",
        source_id="klapotke2017",
        record_id="Table 9.6, p.249",
        partition="selection",
        temperature_k=298.15,
        phase="solid",
        value_source="secondary",
        secondary_reference="klapotke2017 Tab. 9.6, p.249: DfH(s) = +85 kJ/mol",
        note="18.4 kJ/mol from hf_rdx_solid_prose -- consistent in sign/magnitude, not a real "
        "contradiction once compared in the same units (see literature.toml's mathieu2018_apc entry)",
    ),
    ValidationRow(
        row_id="hf_hmx_solid",
        smiles="O=[N+]([O-])N1CN(CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]",
        property="enthalpy_formation_solid",
        value=116.1,
        units="kJ/mol",
        source_id="klapotke2017",
        record_id="Table 9.16a, p.270",
        partition="selection",
        temperature_k=298.15,
        phase="solid",
        value_source="secondary",
        secondary_reference="klapotke2017 Tab. 9.16a, p.270: DfH = 116.1 kJ/mol",
    ),
    ValidationRow(
        row_id="hf_petn_solid",
        smiles="C(C(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-])O[N+](=O)[O-]",
        property="enthalpy_formation_solid",
        value=-539.0,
        units="kJ/mol",
        source_id="klapotke2017",
        record_id="Table 9.16b, p.270",
        partition="selection",
        temperature_k=298.15,
        phase="solid",
        value_source="secondary",
        secondary_reference="klapotke2017 Tab. 9.16b, p.270: DfH = -539 kJ/mol",
    ),
    # --- inside orca_atom_equivalents's own fit -- development, not independent evidence ------------
    ValidationRow(
        row_id="hf_dimethylnitramine_gas",
        smiles="CN(C)[N+](=O)[O-]",
        property="enthalpy_formation_gas",
        value=-5.0,
        units="kJ/mol",
        source_id="nist_webbook",
        record_id="CAS 4164-28-7",
        partition="development",
        temperature_k=298.15,
        phase="gas",
        value_source="secondary",
        primary_reference="Matyushin, V'yunova, Pepekin, Apin (1971), Bull. Acad. Sci. USSR, Div. Chem. Sci., 2320-2323",
        secondary_reference="NIST Chemistry WebBook, gas phase thermochemistry data, DfH = -5 +/- 1 kJ/mol",
        note="the only nitramine in orca_atom_equivalents's calibration set -- see that module's docstring",
    ),
    ValidationRow(
        row_id="hf_methane_gas",
        smiles="C",
        property="enthalpy_formation_gas",
        value=-74.6,
        units="kJ/mol",
        source_id="langes_handbook",
        record_id="Table 6.1",
        partition="development",
        temperature_k=298.15,
        phase="gas",
        value_source="secondary",
    ),
    ValidationRow(
        row_id="hf_ammonia_gas",
        smiles="N",
        property="enthalpy_formation_gas",
        value=-45.9,
        units="kJ/mol",
        source_id="langes_handbook",
        record_id="Table 6.1",
        partition="development",
        temperature_k=298.15,
        phase="gas",
        value_source="secondary",
    ),
    ValidationRow(
        row_id="hf_benzene_gas",
        smiles="c1ccccc1",
        property="enthalpy_formation_gas",
        value=82.6,
        units="kJ/mol",
        source_id="langes_handbook",
        record_id="Table 6.1",
        partition="development",
        temperature_k=298.15,
        phase="gas",
        value_source="secondary",
    ),
    ValidationRow(
        row_id="hf_methanol_gas",
        smiles="CO",
        property="enthalpy_formation_gas",
        value=-201.0,
        units="kJ/mol",
        source_id="langes_handbook",
        record_id="Table 6.1",
        partition="development",
        temperature_k=298.15,
        phase="gas",
        value_source="secondary",
    ),
    ValidationRow(
        row_id="hf_nitromethane_gas",
        smiles="C[N+](=O)[O-]",
        property="enthalpy_formation_gas",
        value=-74.3,
        units="kJ/mol",
        source_id="langes_handbook",
        record_id="Table 6.1",
        partition="development",
        temperature_k=298.15,
        phase="gas",
        value_source="secondary",
    ),
    ValidationRow(
        row_id="hf_methyl_nitrate_gas",
        smiles="CO[N+](=O)[O-]",
        property="enthalpy_formation_gas",
        value=-124.4,
        units="kJ/mol",
        source_id="langes_handbook",
        record_id="Table 6.1",
        partition="development",
        temperature_k=298.15,
        phase="gas",
        value_source="secondary",
    ),
]


#: The fit population `orca_atom_equivalents`'s atom equivalents were regressed on, keyed the way
#: `exclude_leaked` expects: (model, property) -> identity blocks. Built from HF_ROWS's own
#: `partition == "development"` rows rather than hand-listed again, so it cannot silently drift from
#: the actual calibration set.
def orca_atom_equivalents_fit_population() -> frozenset[str]:
    return frozenset(
        validation_rows.identity_block(row.smiles)
        for row in HF_ROWS
        if row.partition == "development" and row.property == "enthalpy_formation_gas"
    )
