"""Redocking: the standard way to ask whether a docking setup is sane.

Take the ligand that was crystallised with the receptor, throw its
coordinates away, and dock it back through the box the catalogue derives.
If the setup is right it should land close to where crystallography put
it. If the box is in the wrong place, or the ligand code is wrong, or the
receptor prep is broken, the pose lands somewhere else and says so -- and
unlike a plain affinity number, that failure is unambiguous.

Reported as the distance between the docked pose's centroid and the
crystal ligand's. Not a symmetry-corrected RMSD, which would need an atom
correspondence this does not have; centroid displacement answers the
question actually being asked ("did it find the right pocket") and cannot
be quietly flattered by a good score.
"""

from __future__ import annotations

import json
import math

from openchem.chem.binding_site import _single_copy, box_from_ligand
from openchem.chem.docking_providers import VinaDockingProvider
from openchem.chem.pose_analysis import receptor_atoms_from_structure
from openchem.chem.receptor_library import find
from openchem.net import open_url
from openchem.services.progress import ProgressHandle
from openchem.services.receptor_library_service import fetch_structure
from rdkit import Chem
from rdkit.Chem import AllChem

#: Point this at your Vina executable, or read it from Settings under
#: "docking/vina_executable_path" -- kept as a plain constant so the
#: script runs standalone without constructing the app.
VINA = r"C:/Program Files (x86)/The Scripps Research Institute/Vina/vina_1.2.7_win.exe"
PREP = {"strip_waters": True, "strip_cofactors": True}

# A spread: two GPCRs, an enzyme with a textbook answer, a nuclear
# receptor, and the hERG channel whose astemizole is the compound this
# project's ADMET model is benchmarked on.
TARGETS = ["1HSG", "4DKL", "3EML", "2RH1", "8ZYO", "1ERE", "4EY7"]


def component_smiles(comp_id: str) -> str | None:
    """The ligand's own SMILES, from RCSB's chemical-component entry --
    so the docked molecule is exactly what was crystallised, not something
    transcribed by hand."""
    try:
        data = json.loads(
            open_url(f"https://data.rcsb.org/rest/v1/core/chemcomp/{comp_id}", timeout=45).read()
        )
    except Exception:
        return None
    for descriptor in data.get("rcsb_chem_comp_descriptor", {}), {}:
        smiles = descriptor.get("SMILES_stereo") or descriptor.get("SMILES")
        if smiles:
            return smiles
    for row in data.get("pdbx_chem_comp_descriptor", []) or []:
        if row.get("type") == "SMILES_CANONICAL":
            return row.get("descriptor")
    return None


provider = VinaDockingProvider(executable_path_resolver=lambda: VINA)
print(f"{'PDB':<6} {'ligand':<6} {'affinity':>9} {'centroid shift':>15}   verdict")
print("-" * 62)
for pdb_id in TARGETS:
    entry = find(pdb_id)
    text, source_format = fetch_structure(pdb_id)
    site = box_from_ligand(text, source_format, entry.ligand_code)

    smiles = component_smiles(entry.ligand_code)
    if not smiles:
        print(f"{pdb_id:<6} {entry.ligand_code:<6} no SMILES from RCSB - skipped")
        continue
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        print(f"{pdb_id:<6} {entry.ligand_code:<6} SMILES did not parse - skipped")
        continue
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE) != 0:
        print(f"{pdb_id:<6} {entry.ligand_code:<6} would not embed - skipped")
        continue
    AllChem.MMFFOptimizeMolecule(mol)

    try:
        poses = provider.dock(
            receptor_structure_text=text,
            receptor_source_format=source_format,
            ligand_mol=mol,
            box=site.box,
            num_poses=5,
            progress=ProgressHandle(),
            receptor_prep_options=PREP,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{pdb_id:<6} {entry.ligand_code:<6} docking failed: {str(exc)[:38]}")
        continue

    best = poses[0]
    docked = Chem.MolFromMolBlock(best.pose_molblock, sanitize=False)
    conf = docked.GetConformer()
    heavy = [
        conf.GetAtomPosition(a.GetIdx())
        for a in docked.GetAtoms()
        if a.GetSymbol() != "H"
    ]
    dx = sum(p.x for p in heavy) / len(heavy)
    dy = sum(p.y for p in heavy) / len(heavy)
    dz = sum(p.z for p in heavy) / len(heavy)

    # MUST use the same single-copy choice the box used. Comparing
    # against every copy's combined centroid is how this script first
    # reported estradiol 47 A "wrong" -- 1ERE has six copies, and their
    # shared centroid is in solvent, nowhere near the site the box (and
    # the pose) correctly used.
    crystal = [
        a
        for a in receptor_atoms_from_structure(text, source_format)
        if a.residue_name.strip().upper() == entry.ligand_code and a.element != "H"
    ]
    crystal = [a.position for a in _single_copy(crystal)]
    cx = sum(p[0] for p in crystal) / len(crystal)
    cy = sum(p[1] for p in crystal) / len(crystal)
    cz = sum(p[2] for p in crystal) / len(crystal)
    shift = math.dist((dx, dy, dz), (cx, cy, cz))

    verdict = "same pocket" if shift <= 3.0 else ("nearby" if shift <= 6.0 else "WRONG PLACE")
    print(f"{pdb_id:<6} {entry.ligand_code:<6} "
          f"{best.binding_affinity_kcal_mol:>7.1f}   {shift:>11.2f} A   {verdict}")
