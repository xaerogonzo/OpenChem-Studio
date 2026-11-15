"""Real ORCA on open-shell species at the multiplicity a person might leave in the panel (docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md, section 3).

For each (species, multiplicity) it builds the input through the application's own provider (`OrcaQuantumEngineProvider.build_input`, B3LYP def2-SVP Opt from the
ETKDG conformer), runs ORCA, and prints the final energy, the optimised bond or "ORCA refused: <its message>".

    uv run --no-sync python benchmarks/open_shell/orca_spin_states.py D:/ORCA/orca.exe <scratch folder>

Run 2026-11-15, ORCA 6.1.1: O2 triplet 1.2002 A, -150.144946 Eh; O2 at multiplicity 1 -150.081721 Eh (+39.7 kcal/mol, r 1.2014 A, no message); CH2 triplet -39.086062,
CH2 at multiplicity 1 -39.019324 (+41.9); methyl and NO at multiplicity 1: exit 55, "multiplicity (1) is odd and number of electrons (9|15) is odd -> impossible".
"""
import os
import re
import subprocess
import sys
from pathlib import Path

from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from openchem.chem.conformer_providers import GenerationOptions, RDKitConformerProvider, search_conformers
from openchem.chem.orca_engine import OrcaQuantumEngineProvider

CASES = [("O2_m3", "[O][O]", 3), ("O2_m1", "[O][O]", 1), ("O2_m5", "[O][O]", 5), ("CH3_m1", "[CH3]", 1), ("CH3_m2", "[CH3]", 2), ("NO_m1", "[N]=O", 1), ("NO_m2", "[N]=O", 2),
         ("CH2_m3", "[CH2]", 3), ("CH2_m1", "[CH2]", 1), ("OH_m2", "[OH]", 2),
         ("SS_m1", "S=S", 1), ("SS_m3", "S=S", 3), ("SO_m1", "S=O", 1), ("SO_m3", "S=O", 3), ("N2_m1", "N#N", 1), ("N2_m3", "N#N", 3)]


def main(orca: str, folder: str) -> None:
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    provider = OrcaQuantumEngineProvider()
    for name, smiles, multiplicity in CASES:
        mol = search_conformers(RDKitConformerProvider(random_seed=1), Chem.MolFromSmiles(smiles), True, GenerationOptions(max_embeddings=10, embedding_batch_size=5)).pool[0][0]
        (out / f"{name}.inp").write_text(provider.build_input(mol, 0, multiplicity, "B3LYP def2-SVP", "opt"))
        text = subprocess.run([orca, f"{name}.inp"], cwd=out, capture_output=True, text=True, timeout=600,
                              env={**os.environ, "PATH": str(Path(orca).parent) + os.pathsep + os.environ["PATH"]}).stdout  # ORCA starts its own helpers by name
        energy = re.findall(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", text)
        bond = re.findall(r"B\(\w+\s+\d+,\w+\s+\d+\)\s+(?:\S+\s+){3}(\S+)", text)
        error = re.findall(r"Error : (.*)", text)
        print(f"{name:8} E={energy[-1] if energy else '-':>16}  final bond={bond[-1] if bond else '-':>7}  {'ORCA refused: ' + error[0] if error else ''}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
