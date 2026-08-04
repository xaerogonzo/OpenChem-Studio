"""Dock known hERG blockers and non-blockers into the real channel.

8ZYO is astemizole-bound hERG, which makes astemizole a redocking
positive control as well as a test compound -- it should return to where
cryo-EM found it.

The question worth asking is not just "do blockers score better", because
Vina scores correlate with size before they correlate with anything
pharmacological. It is whether the poses touch **Tyr652 and Phe656**,
the two pore-facing residues every hERG structure-activity paper
implicates: an aromatic stack against Tyr652 and a hydrophobic contact
with Phe656 are the recognised signature of a pore blocker. hERG is a
homotetramer, so each appears four times, once per subunit.
"""

from __future__ import annotations

import json

from _config import vina_executable
from openchem.chem.binding_site import box_from_ligand
from openchem.chem.descriptor_providers import RDKitDescriptorProvider
from openchem.chem.docking_providers import VinaDockingProvider
from openchem.chem.pose_analysis import analyze_pose, receptor_atoms_from_structure
from openchem.chem.receptor_library import find
from openchem.services.progress import ProgressHandle
from openchem.services.receptor_library_service import fetch_structure
from rdkit import Chem
from rdkit.Chem import AllChem

VINA = vina_executable()
PREP = {"strip_waters": True, "strip_cofactors": True}

# Clinical classification only -- "withdrawn or labelled for QT
# prolongation" vs "no meaningful hERG liability". Deliberately NOT
# specific IC50 values: those vary by an order of magnitude between
# assays, and quoting one from memory is exactly the fabricated precision
# this project refuses.
LIGANDS = [
    ("astemizole",  "BLOCKER - withdrawn (also 8ZYO's own ligand)"),
    ("terfenadine", "BLOCKER - withdrawn"),
    ("cisapride",   "BLOCKER - withdrawn"),
    ("dofetilide",  "BLOCKER - class III antiarrhythmic, hERG is its target"),
    ("amiodarone",  "BLOCKER - QT prolongation on label"),
    ("verapamil",   "blocks hERG, but low torsadogenic risk clinically"),
    ("sotalol",     "BLOCKER - class III, QT prolongation on label"),
    ("metformin",   "NON-BLOCKER"),
    ("paracetamol", "NON-BLOCKER"),
    ("aspirin",     "NON-BLOCKER"),
]

smiles_by_name = json.load(open("herg_ligands.json"))

entry = find("8ZYO")
text, source_format = fetch_structure(entry.pdb_id)
site = box_from_ligand(text, source_format, entry.ligand_code)
receptor_atoms = receptor_atoms_from_structure(text, source_format, PREP)
print(f"{entry.target}  ({entry.pdb_id}, {entry.resolution_angstrom} A, {entry.method})")
print(f"box from {entry.ligand_name}: {site.describe()}")
print(f"receptor: {len(receptor_atoms)} atoms after prep\n")

provider = VinaDockingProvider(executable_path_resolver=lambda: VINA)
_descriptors = RDKitDescriptorProvider()

print(f"{'compound':<13} {'best':>6}  {'Tyr652':>6} {'Phe656':>6}  {'risk factors':<38} clinical")
print("-" * 108)
rows = []
for name, clinical in LIGANDS:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles_by_name[name]))
    if AllChem.EmbedMolecule(mol, randomSeed=0xBEEF) != 0:
        print(f"{name:<13} would not embed - skipped")
        continue
    AllChem.MMFFOptimizeMolecule(mol)

    poses = provider.dock(
        receptor_structure_text=text,
        receptor_source_format=source_format,
        ligand_mol=mol,
        box=site.box,
        num_poses=5,
        progress=ProgressHandle(),
        receptor_prep_options=PREP,
    )
    best = poses[0]
    interactions = analyze_pose(best.pose_molblock, receptor_atoms)

    # Count DISTINCT subunits contacted, not raw contact pairs -- a pore
    # blocker wedged in the central cavity touches the same residue in
    # several of the four subunits, and that symmetry is the signal.
    def subunits(residue_label: str) -> int:
        hits = set()
        for kind, entries in interactions.items():
            if kind == "clashes":
                continue
            for item in entries:
                if item["receptor_residue"] == residue_label:
                    hits.add(item.get("receptor_chain", ""))
        return len(hits)

    tyr = subunits("TYR652")
    phe = subunits("PHE656")

    # The always-available rule-based checklist, for comparison. It needs
    # no sidecar and no structure at all.
    alerts = _descriptors.compute_alerts(Chem.MolFromSmiles(smiles_by_name[name]), "x")
    herg_alert = next((a for a in alerts if "hERG" in a.name), None)
    factors = "; ".join(herg_alert.matched) if herg_alert and herg_alert.matched else "none"

    rows.append((name, best.binding_affinity_kcal_mol, tyr, phe, clinical))
    print(f"{name:<13} {best.binding_affinity_kcal_mol:>6.1f}  {tyr:>6} {phe:>6}  "
          f"{factors[:38]:<38} {clinical}")

blockers = [r for r in rows if r[4].startswith("BLOCKER")]
non = [r for r in rows if r[4].startswith("NON")]
if blockers and non:
    print(f"\nmean affinity  blockers {sum(r[1] for r in blockers)/len(blockers):+.2f}"
          f"   non-blockers {sum(r[1] for r in non)/len(non):+.2f}")
    print(f"mean Tyr652 subunits contacted  blockers "
          f"{sum(r[2] for r in blockers)/len(blockers):.1f}"
          f"   non-blockers {sum(r[2] for r in non)/len(non):.1f}")
