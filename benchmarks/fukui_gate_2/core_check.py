"""POST-GATE CHECK 3 (not the gate, decides nothing, changes nothing shipped): does the number of cores change which N-1 state the application's input reaches?

`route_check.py` ran the application's own three-job input on probe 1's geometry of benzaldehyde at 4 cores and reached the N-1 state 0.145 eV above the lowest one, where the gate's run
(made by the application, which gives ORCA `default_cores()` = 8 on this machine: `orca/cores` is not set) had reached the lowest. Two things differed besides the molecule's own geometry: the core count
and the process that launched ORCA. A parallel Fock build sums in a different order at a different core count, so a near-degenerate SCF could land differently for numerical reasons alone.
This runs the SAME input on the SAME geometry at several core counts and says which state each reached, in eV above the lowest state probe 1 found.

    python core_check.py <probe json> <output json> <species> [cores ...]      (default cores: 8 4 2 1)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cation_states_probe as probe
import route_check
from openchem.chem.orca_engine import _CALC_TYPE_KEYWORDS, OrcaQuantumEngineProvider, add_parallel_block, parse_hirshfeld_tables


def at_cores(name: str, atoms: list[str], cores: int, probe_rows: list[dict]) -> dict:
    species = probe.gate.ALL_SPECIES[name]
    method = probe.gate.METHOD_BASIS[species.level]
    header = f"! {method} {_CALC_TYPE_KEYWORDS['fukui']}".strip()
    text = OrcaQuantumEngineProvider()._build_fukui_input(header, atoms, species.charge, 1, diffuse=False)
    out, _work = probe.run(f"{name}_cores{cores}", add_parallel_block(text, cores))
    energies = [float(e) for e in probe.ENERGY.findall(out)]
    tables = parse_hirshfeld_tables(out)
    result = {"species": name, "cores": cores, "jobs_with_energy": len(energies), "tables": len(tables)}
    if len(energies) < 2 or len(tables) < 2:
        result["converged"] = False
        print(json.dumps(result), flush=True)
        return result
    neutral, cation = [q for _e, q in tables[0]], [q for _e, q in tables[1]]
    f_minus = [c - n for n, c in zip(neutral, cation)]
    distance, labelled = probe.f_minus_distance(name, species, f_minus)
    result.update({
        "converged": True, "n_energy": energies[0], "n_minus_1_energy": energies[1],
        "above_probe_lowest_ev": round((energies[1] - route_check.lowest_energy(probe_rows, name)) * probe.HARTREE_TO_EV, 3),
        "max_distance_to_published": round(distance, 4), "by_label": labelled,
    })
    print(json.dumps(result), flush=True)
    return result


def main() -> None:
    probe_rows = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["rows"]
    out_path, name = Path(sys.argv[2]), sys.argv[3]
    cores_list = [int(c) for c in sys.argv[4:]] or [8, 4, 2, 1]
    atoms = probe.optimized(name, probe.gate.ALL_SPECIES[name])
    rows = [at_cores(name, atoms, cores, probe_rows) for cores in cores_list]
    out_path.write_text(json.dumps({"scratch": str(probe.ROOT), "rows": rows}, indent=1), encoding="utf-8")
    print("\nSUMMARY: cores, N-1 state the application's input reached (eV above the probe's lowest), max |f- - published|")
    for row in rows:
        if row.get("converged"):
            print(f"{name} at {row['cores']} cores: +{row['above_probe_lowest_ev']:.3f} eV  max |f- - published| {row['max_distance_to_published']}")
        else:
            print(f"{name} at {row['cores']} cores: did not converge")


if __name__ == "__main__":
    main()
