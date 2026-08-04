"""Every catalogue entry must download and produce a real box.

A `ligand_code` that does not appear in its own structure is a dead
entry -- the user picks a target, the box derivation raises, and the
catalogue has lied. Checking all 49 is the only way to know none does,
and it is cheap compared to a user hitting one.

Also reports what the box came out as, because "resolves" is not the same
as "sensible": a code that matched a single ion produces a box that is
technically valid and useless, and an atom count says so instantly.
"""

from __future__ import annotations

from openchem.chem.binding_site import BindingSiteError, box_from_ligand, ligand_codes_in
from openchem.chem.receptor_library import RECEPTOR_LIBRARY
from openchem.services.receptor_library_service import fetch_structure

ok, broken, suspicious = 0, [], []
for entry in RECEPTOR_LIBRARY:
    try:
        text, source_format = fetch_structure(entry.pdb_id)
    except Exception as exc:  # noqa: BLE001
        broken.append((entry, f"download failed: {exc}"))
        print(f"{entry.pdb_id}  DOWNLOAD FAILED  {exc}")
        continue
    try:
        site = box_from_ligand(text, source_format, entry.ligand_code)
    except BindingSiteError as exc:
        present = ligand_codes_in(text, source_format)[:6]
        broken.append((entry, f"{exc}; present: {present}"))
        print(f"{entry.pdb_id}  NO SUCH LIGAND {entry.ligand_code}  present={present}")
        continue
    ok += 1
    flag = ""
    # Under 6 atoms is an ion or a fragment, not a site definition.
    if site.atom_count < 6:
        flag = "  <-- SUSPICIOUSLY SMALL"
        suspicious.append((entry, site))
    sx, sy, sz = site.box.size
    print(f"{entry.pdb_id}  {source_format:<5} {entry.ligand_code:<4} "
          f"{site.atom_count:>3} atoms  box {sx:.0f}x{sy:.0f}x{sz:.0f}"
          f"{'  clamped' if site.size_was_clamped else '':<9}{flag}")

print(f"\n{ok}/{len(RECEPTOR_LIBRARY)} entries produced a box")
if broken:
    print(f"\nBROKEN ({len(broken)}):")
    for entry, why in broken:
        print(f"  {entry.pdb_id} {entry.target}: {why}")
if suspicious:
    print(f"\nSMALL LIGANDS ({len(suspicious)}) -- box floor is doing the work:")
    for entry, site in suspicious:
        print(f"  {entry.pdb_id} {entry.ligand_code} ({entry.ligand_name}): "
              f"{site.atom_count} atoms")
