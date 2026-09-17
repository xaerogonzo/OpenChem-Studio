"""Which structure a per-atom result's indices refer to, and so which one to draw.

**NOT ATOM IDENTITY.** `atom_identity` answers "which atom of one structure is
which atom of another". This answers an earlier question: which structure is
authoritative for displaying THIS result. Most results describe the drawing or
a stored conformer. A result computed on a structure the application does not
store -- the dominant microspecies at a pH -- carries that structure itself
(`PerAtomDataset.structure_molblock`), and must be drawn from it.

Measured 2026-09-17, before this existed: the pH-dependent 3D charges were
drawn on the stored conformer. For a base the added proton was simply missing
from the picture; for an acid drawn as OC(=O)C the removed hydrogen renumbered
every later atom, so each value after it sat on the next atom.
"""

from __future__ import annotations

import hashlib

#: The result carries its own structure; its indices are that molblock's atoms.
EFFECTIVE_STRUCTURE = "effective_structure"
#: The result names a stored conformer (`atom_identity.dataset_conformer_id`),
#: looked up in the model -- the only route that existed before, and still the
#: right one for a result that describes a stored conformer as it is.
LEGACY_STORED_CONFORMER = "legacy_stored_conformer"
#: The result is keyed by the drawing, or its conformer is no longer stored.
NO_STRUCTURE = "none"


def structure_fingerprint(molblock: str) -> str:
    """SHA-256 over the exact molblock text, domain-separated from input fingerprints.

    A sibling of `calculation_input._fingerprint` rather than a call to
    `input_fingerprint`, which needs a model: an effective structure is not
    stored in one. Exact text, not a canonical form, for the reason that
    function gives.
    """
    digest = hashlib.sha256()
    for part in ("effective_structure", molblock):
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def display_structure(model, dataset) -> tuple[str | None, str]:
    """The molblock `dataset`'s indices refer to, and which route found it.

    An old result without `structure_molblock` falls back to its stored
    conformer. That is correct for everything that was computed on the stored
    conformer as it is. The one producer for which it was wrong -- the retired
    `geometry_partial_charge_at_ph` -- is dropped on load
    (`result_store.RETIRED_RESULT_IDS`), so no such result reaches this.
    """
    from openchem.chem.atom_identity import dataset_conformer_id

    own = getattr(dataset, "structure_molblock", "") or ""
    if own:
        return own, EFFECTIVE_STRUCTURE
    conformer_id = dataset_conformer_id(dataset)
    if conformer_id is None:
        return None, NO_STRUCTURE
    conformer = next((c for c in model.conformers if c.conformer_id == conformer_id), None)
    if conformer is None:
        return None, NO_STRUCTURE
    return conformer.molblock, LEGACY_STORED_CONFORMER
