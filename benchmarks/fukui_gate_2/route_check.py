"""POST-GATE CHECK 2 (not the gate, decides nothing, changes nothing shipped): which cation state does the APPLICATION'S OWN INPUT reach?

`cation_states_probe.py` converged each N-1 state by hand (a `MORead` job from the neutral's orbitals, with the hole put in the HOMO, HOMO-1, ...). For benzaldehyde its plain-aufbau
start (hole 0) landed 0.145 eV ABOVE the lowest state it found, where the gate's run, made by the application, had landed on the lowest one. The two differ in two ways that were not separated:
the geometry (each is ORCA-optimized from its own embedding) and the form of the input (a separate `MORead` job against the application's compound input, whose second job reads the
first job's orbitals by default). This script removes the second difference: it takes the PROBE'S geometry, writes the application's own three-job input for it (`OrcaQuantumEngineProvider._build_fukui_input`,
the builder the service calls), runs it once in ORCA 6.1.1, and says which N-1 state the application's job reached, in eV above the lowest state the probe found for the same molecule.

    python route_check.py <probe json> <output json> [species ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cation_states_probe as probe
from openchem.chem.orca_engine import _CALC_TYPE_KEYWORDS, OrcaQuantumEngineProvider, add_parallel_block, parse_hirshfeld_tables

DEFAULT = ("benzaldehyde", "anilinium", "thiophene")


def lowest_energy(probe_rows: list[dict], name: str) -> float:
    row = next(r for r in probe_rows if r["species"] == name)
    return min(s["energy"] for s in row["states"] if s.get("converged"))


def one(name: str, probe_rows: list[dict]) -> dict:
    species = probe.gate.ALL_SPECIES[name]
    method = probe.gate.METHOD_BASIS[species.level]
    atoms = probe.optimized(name, species)
    header = f"! {method} {_CALC_TYPE_KEYWORDS['fukui']}".strip()
    text = OrcaQuantumEngineProvider()._build_fukui_input(header, atoms, species.charge, 1, diffuse=False)
    out, _work = probe.run(f"{name}_app_route", add_parallel_block(text, probe.CORES))
    energies = [float(e) for e in probe.ENERGY.findall(out)]
    tables = parse_hirshfeld_tables(out)
    result = {"species": name, "level": species.level, "jobs_with_energy": len(energies), "tables": len(tables)}
    if len(energies) < 2 or len(tables) < 2:
        result["converged"] = False
        print(json.dumps(result), flush=True)
        return result
    reference = lowest_energy(probe_rows, name)
    neutral, cation = [q for _e, q in tables[0]], [q for _e, q in tables[1]]
    f_minus = [c - n for n, c in zip(neutral, cation)]
    distance, labelled = probe.f_minus_distance(name, species, f_minus)
    squares = probe.S2.findall(out)
    result.update({
        "converged": True, "n_energy": energies[0], "n_minus_1_energy": energies[1], "above_probe_lowest_ev": round((energies[1] - reference) * probe.HARTREE_TO_EV, 3),
        "s2_cation": float(squares[0]) if squares else None, "f_minus": [round(v, 4) for v in f_minus], "max_distance_to_published": round(distance, 4), "by_label": labelled,
    })
    print(json.dumps(result), flush=True)
    return result


def main() -> None:
    probe_rows = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["rows"]
    out_path = Path(sys.argv[2])
    names = sys.argv[3:] or list(DEFAULT)
    rows = [one(name, probe_rows) for name in names]
    out_path.write_text(json.dumps({"scratch": str(probe.ROOT), "rows": rows}, indent=1), encoding="utf-8")
    print("\nSUMMARY: species, N-1 state the application's input reached (eV above the probe's lowest), max |f- - published|")
    for row in rows:
        if row.get("converged"):
            print(f"{row['species']}: +{row['above_probe_lowest_ev']:.3f} eV  S2 {row['s2_cation']}  max |f- - published| {row['max_distance_to_published']}")
        else:
            print(f"{row['species']}: did not converge")


if __name__ == "__main__":
    main()
