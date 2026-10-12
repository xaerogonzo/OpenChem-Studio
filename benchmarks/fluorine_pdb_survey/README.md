# Fluorine in the PDB: metal contacts and hydrogen-bond partners

Measured 2026-10-12 for `docs/VDW_RADII_ASSESSMENT.md` (the fluorine sections). It needs the network (RCSB search, data and file
services) and writes about 1 GB to the folder you name, which must be outside the repository:

    python benchmarks/fluorine_pdb_survey/stage1_select_entries.py  <folder>
    python benchmarks/fluorine_pdb_survey/stage2_measure_metal_contacts.py  <folder>
    python benchmarks/fluorine_pdb_survey/summarise.py  <folder>
    python benchmarks/fluorine_pdb_survey/stage3_close_contacts_and_hbond_control.py  <folder>

Stage 1 takes every entry (resolution 2.5 A or better) that holds a fluorine-containing ligand and one of Zn, Mg, Ca, Na, K, Fe,
Mn, Cu, Co, Ni. Stage 2 downloads each mmCIF (model 1, alternate location blank or A) and measures every ligand fluorine that has a
carbon of its own residue within 1.65 A against every metal within 4.0 A. Stage 3 prints the sphere of the closest contacts and the
hydrogen-bond control. The entry list changes as the PDB grows, so a rerun will not reproduce the numbers exactly.
