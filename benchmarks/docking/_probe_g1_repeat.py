"""One-off: repeat G1 dock for selected receptors (delete after use)."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import prep_box_survey as survey  # noqa: E402
from _config import vina_executable  # noqa: E402
from engine_g1_survey import G1_EXHAUSTIVENESS, G1_SEED  # noqa: E402
from engine_pilot import ARM_NAME  # noqa: E402
from openchem.chem.docking_providers import VinaDockingProvider  # noqa: E402


def main() -> None:
    provider = VinaDockingProvider(executable_path_resolver=vina_executable)
    artifacts = pathlib.Path(__file__).parent / "artifacts_prep_box" / "results.jsonl"
    recorded: dict[str, dict] = {}
    for line in artifacts.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("arm") == ARM_NAME:
            recorded[row["pdb"]] = row

    for pdb in ("5KIR", "7B6W"):
        print(f"=== {pdb} 5 repeats seed {G1_SEED} ===")
        tops: list[tuple[float, float]] = []
        for i in range(5):
            row = survey.run_one(provider, pdb, ARM_NAME, G1_SEED, G1_EXHAUSTIVENESS)
            p0 = row["poses"][0]
            tops.append((p0["affinity"], p0["rmsd"]))
            print(f"  run {i + 1}: aff={p0['affinity']} rmsd={p0['rmsd']}")
        print("  unique top affinities:", sorted({t[0] for t in tops}))
        print("  unique top rmsds:", sorted({t[1] for t in tops}))
        rec = recorded[pdb]["poses"][0]
        print(f"  survey recorded: aff={rec['affinity']} rmsd={rec['rmsd']}")


if __name__ == "__main__":
    main()
