"""Write the drive scripts of the second Fukui gate (`PREREGISTRATION.md`) from the species and levels in `openchem.app.fukui_gate_2`.

    python benchmarks/fukui_gate_2/make_scripts.py                    # the floor, gate and reported-arm scripts
    python benchmarks/fukui_gate_2/make_scripts.py --repeat "furan@B3LYP/6-31G*" --attempt 2   # one job, again, unchanged

The scripts are generated so that the list of species and levels the gate runs is the one `fukui_gate_2` judges, and so a reviewer reads fifteen identical blocks as one function. They are
committed; running them is `OPENCHEM_DRIVE=<script>`.

Every block is the application's own path (CLAUDE.md): add the molecule from its SMILES, embed three conformers, ONE ORCA geometry optimization at the species' method (after which the optimized
conformer is the canonical one, which the script asserts), then ONE Fukui run at the same method on that geometry, then record the stored run. Nothing is started while another job runs (`qc_wait`).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from openchem.app import fukui_gate_2 as gate

ROOT = Path(__file__).resolve().parent
VISUAL = ROOT.parent / "visual"
ARTIFACTS = "benchmarks/fukui_gate_2/artifacts"
FUKUI = "Fukui functions (Hirshfeld)"
OPTIMIZE = "Geometry Optimization"
#: Thirty minutes: an optimization of a seventeen-atom molecule at B3LYP/6-31G* takes minutes, and giving up is an ERROR, never a silent move on.
WAIT = {"do": "qc_wait", "timeout_ms": 1800000}


def block(smiles: str, name: str, level: str, *, record: dict) -> list[dict]:
    """One molecule at one level: draw, optimize, check the optimized geometry is the canonical one, run Fukui, record."""
    method = gate.METHOD_BASIS[level]
    return [
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


def record_step(species: str, level: str, artifact: str, **extra) -> dict:
    return {"do": "fukui2_record", "species": species, "level": level, "artifact": artifact, **extra}


def floor_script() -> list[dict]:
    """The two floors, each on a molecule that is in neither gate: the same input twice (a1, a2) and the whole chain twice (a1, b)."""
    records = f"{ARTIFACTS}/floor_records.json"
    steps: list[dict] = []
    for name, species in gate.FLOOR_SPECIES.items():
        method = gate.METHOD_BASIS[species.level]
        steps += block(species.smiles, f"{name} a", species.level, record=record_step(name, species.level, records, label="a1", attempt=1))
        steps += [
            {"do": "qc_run", "calc_type": FUKUI, "method": method, "after_ms": 1000},
            dict(WAIT),
            record_step(name, species.level, records, label="a2", attempt=1),
        ]
        steps += block(species.smiles, f"{name} b", species.level, record=record_step(name, species.level, records, label="b", attempt=1))
    steps += [
        {"do": "fukui2_floor", "records": records, "artifact": f"{ARTIFACTS}/floor.json"},
        {"do": "expect_clean"},
        {"do": "quit"},
    ]
    return steps


def gate_script() -> list[dict]:
    records = f"{ARTIFACTS}/records.json"
    steps: list[dict] = [{"do": "fukui2_begin", "floor": f"{ARTIFACTS}/floor.json"}]
    for name, species in gate.SPECIES.items():
        steps += block(species.smiles, f"{name} {species.level}", species.level, record=record_step(name, species.level, records, attempt=1))
    steps += [
        {"do": "fukui2_judge", "records": records, "floor": f"{ARTIFACTS}/floor.json", "artifact": f"{ARTIFACTS}/verdict.json"},
        {"do": "expect_clean"},
        {"do": "quit"},
    ]
    return steps


def reported_script() -> list[dict]:
    """The reported arm: the species outside the decision at their own levels, and the 13 neutral and cation species at the application's default preset.
    Written to its own records file, read by `fukui2_report`, and never by the verdict."""
    records = f"{ARTIFACTS}/reported_records.json"
    steps: list[dict] = [{"do": "fukui2_begin", "floor": f"{ARTIFACTS}/floor.json"}]
    for name, species in gate.REPORTED_SPECIES.items():
        steps += block(species.smiles, f"{name} {species.level}", species.level, record=record_step(name, species.level, records, attempt=1))
    for name, species in gate.SPECIES.items():
        if species.level == gate.LEVEL_6_31GS:
            steps += block(species.smiles, f"{name} {gate.LEVEL_DEFAULT}", gate.LEVEL_DEFAULT, record=record_step(name, gate.LEVEL_DEFAULT, records, attempt=1))
    steps += [
        {"do": "fukui2_report", "records": records, "artifact": f"{ARTIFACTS}/reported.json"},
        # A state whose Hirshfeld charges do not sum to its charge is REFUSED by the calculation (`chem/fukui.py`) and logged as an error: that is what it
        # is built to do, each one is a finding listed as `unfinished` in the artifact, and the first gate's reported arm needed this declared too.
        {"do": "expect_clean", "allow": ["state's charges sum to"]},
        {"do": "quit"},
    ]
    return steps


def repeat_script(pair: str, attempt: int) -> list[dict]:
    """One job again, unchanged, as a further ATTEMPT (preregistration section 9): same species, same level, same steps."""
    name, level = pair.split("@", 1)
    species = gate.SPECIES[name]
    records = f"{ARTIFACTS}/records.json"
    steps: list[dict] = [{"do": "fukui2_begin", "floor": f"{ARTIFACTS}/floor.json"}]
    steps += block(species.smiles, f"{name} {level}", level, record=record_step(name, level, records, attempt=attempt))
    steps += [
        {"do": "fukui2_judge", "records": records, "floor": f"{ARTIFACTS}/floor.json", "artifact": f"{ARTIFACTS}/verdict.json"},
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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repeat", help='one job again, as "species@level"')
    parser.add_argument("--attempt", type=int, default=2)
    arguments = parser.parse_args()
    if arguments.repeat:
        name = arguments.repeat.split("@", 1)[0]
        write(VISUAL / f"fukui2_gate_repeat_{name.replace(' ', '_')}_{arguments.attempt}.json", repeat_script(arguments.repeat, arguments.attempt))
        return
    write(VISUAL / "fukui2_gate_floor.json", floor_script())
    write(VISUAL / "fukui2_gate_run.json", gate_script())
    write(VISUAL / "fukui2_gate_reported.json", reported_script())


if __name__ == "__main__":
    main()
