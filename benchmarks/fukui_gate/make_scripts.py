"""Write the drive scripts of the Fukui gate (`PREREGISTRATION.md`) from the species and levels in `openchem.app.fukui_gate`.

    python benchmarks/fukui_gate/make_scripts.py                    # the floor script and the gate script
    python benchmarks/fukui_gate/make_scripts.py --repeat "CO@HF/6-31G**" --attempt 2   # one job, again, unchanged

The scripts are generated so that the list of species and levels the gate runs is the one `fukui_gate` judges, and so a
reviewer reads fourteen identical blocks as one function. They are committed; running them is `OPENCHEM_DRIVE=<script>`.

Every block is the application's own path (CLAUDE.md): add the molecule from its SMILES, embed three conformers, ONE ORCA
geometry optimization at the level's method (after which the optimized conformer is the canonical one, which the script
asserts), then ONE Fukui run at the same method on that geometry, then record the stored run. Nothing is started while
another job runs (`qc_wait`).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from openchem.app import fukui_gate as gate

ROOT = Path(__file__).resolve().parent
VISUAL = ROOT.parent / "visual"
ARTIFACTS = "benchmarks/fukui_gate/artifacts"
FUKUI = "Fukui functions (Hirshfeld)"
OPTIMIZE = "Geometry Optimization"
WAIT = {"do": "qc_wait", "timeout_ms": 900000}


def block(smiles: str, name: str, level: str, *, record: dict, extra_fukui: dict | None = None) -> list[dict]:
    """One molecule at one level: draw, optimize, check the optimized geometry is the canonical one, run Fukui, record."""
    method = gate.METHOD_BASIS[level]
    steps = [
        {"do": "smiles", "smiles": smiles, "name": name, "after_ms": 2500},
        {"do": "select", "molecule": -1, "after_ms": 2500},
        {"do": "conformers", "count": 3, "after_ms": 15000},
        {"do": "qc_run", "calc_type": OPTIMIZE, "method": method, "after_ms": 1000},
        dict(WAIT),
        {"do": "conformer_report", "tag": f"{name}-optimized-geometry-is-the-canonical-one",
         "expect": {"canonical_method": "orca_opt", "canonical_mapped": True}},
        {"do": "qc_run", "calc_type": FUKUI, "method": method, "after_ms": 1000},
        dict(WAIT),
        record,
    ]
    return steps


def record_step(species: str, level: str, artifact: str, **extra) -> dict:
    return {"do": "fukui_gate_record", "species": species, "level": level, "artifact": artifact, **extra}


def floor_script() -> list[dict]:
    """Water at B3LYP/6-31G**, a molecule that is not in the gate: the same input twice (a1, a2) and the whole chain twice (a1, b)."""
    level = gate.DFT_B
    records = f"{ARTIFACTS}/floor_records.json"
    method = gate.METHOD_BASIS[level]
    steps = block("O", "water a", level, record=record_step("water", level, records, label="a1", attempt=1))
    steps += [
        {"do": "qc_run", "calc_type": FUKUI, "method": method, "after_ms": 1000},
        dict(WAIT),
        record_step("water", level, records, label="a2", attempt=1),
    ]
    steps += block("O", "water b", level, record=record_step("water", level, records, label="b", attempt=1))
    steps += [
        {"do": "fukui_gate_floor", "records": records, "artifact": f"{ARTIFACTS}/floor.json"},
        {"do": "expect_clean"},
        {"do": "quit"},
    ]
    return steps


def gate_script() -> list[dict]:
    records = f"{ARTIFACTS}/records.json"
    steps: list[dict] = [{"do": "fukui_gate_begin", "floor": f"{ARTIFACTS}/floor.json"}]
    for level in gate.DECIDED_LEVELS:
        for name, species in gate.SPECIES.items():
            steps += block(species.smiles, f"{name} {level}", level, record=record_step(name, level, records, attempt=1))
    steps += [
        {"do": "fukui_gate_judge", "records": records, "floor": f"{ARTIFACTS}/floor.json", "artifact": f"{ARTIFACTS}/verdict.json"},
        {"do": "expect_clean"},
        {"do": "quit"},
    ]
    return steps


def reported_script() -> list[dict]:
    """The reported arm: the diffuse-basis levels for every species, and formaldehyde at the application's default level.
    Written to its own records file, read by `fukui_gate_report`, and never by the verdict."""
    records = f"{ARTIFACTS}/reported_records.json"
    steps: list[dict] = [{"do": "fukui_gate_begin", "floor": f"{ARTIFACTS}/floor.json"}]
    for level in gate.REPORTED_LEVELS:
        for name, species in gate.SPECIES.items():
            steps += block(species.smiles, f"{name} {level}", level, record=record_step(name, level, records, attempt=1))
    steps += block(gate.SPECIES["H2CO"].smiles, f"H2CO {gate.DEFAULT_LEVEL}", gate.DEFAULT_LEVEL,
                   record=record_step("H2CO", gate.DEFAULT_LEVEL, records, attempt=1))
    steps += [
        {"do": "fukui_gate_report", "records": records, "artifact": f"{ARTIFACTS}/reported.json"},
        # The diffuse levels run unbound anions, and the application REFUSES a state whose Hirshfeld charges do not sum to its charge
        # (`chem/fukui.py`). That refusal is what it is built to do and each one is a finding, listed as `unfinished` in the artifact, so it
        # is not an unexpected error. The first run of this arm (preregistration 11.4) ended FAIL on exactly these seven logged errors
        # and was repeated with them declared, so the verdict line says what the run found and not what the script had not expected.
        {"do": "expect_clean", "allow": ["state's charges sum to"]},
        {"do": "quit"},
    ]
    return steps


def repeat_script(pair: str, attempt: int) -> list[dict]:
    """One job again, unchanged, as a further ATTEMPT (preregistration section 8): same species, same level, same steps."""
    name, level = pair.split("@", 1)
    species = gate.SPECIES[name]
    records = f"{ARTIFACTS}/records.json"
    steps = [{"do": "fukui_gate_begin", "floor": f"{ARTIFACTS}/floor.json"}]
    steps += block(species.smiles, f"{name} {level}", level, record=record_step(name, level, records, attempt=attempt))
    steps += [
        {"do": "fukui_gate_judge", "records": records, "floor": f"{ARTIFACTS}/floor.json", "artifact": f"{ARTIFACTS}/verdict.json"},
        {"do": "expect_clean"},
        {"do": "quit"},
    ]
    return steps


def write(path: Path, steps: list[dict]) -> None:
    # one step per line, as the existing scripts are, so a diff reads as a list of steps
    lines = ["  " + json.dumps(step) for step in steps]
    path.write_text("[\n" + ",\n".join(lines) + "\n]\n", encoding="utf-8", newline="\n")
    print("wrote", path.relative_to(ROOT.parent.parent), f"({len(steps)} steps)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", help='"CO@HF/6-31G**": write the script for one more attempt of that job')
    parser.add_argument("--attempt", type=int, default=2)
    args = parser.parse_args()
    if args.repeat:
        write(VISUAL / "fukui_gate_repeat.json", repeat_script(args.repeat, args.attempt))
        return
    write(VISUAL / "fukui_gate_floor.json", floor_script())
    write(VISUAL / "fukui_gate_run.json", gate_script())
    write(VISUAL / "fukui_gate_reported.json", reported_script())


if __name__ == "__main__":
    main()
