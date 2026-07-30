from __future__ import annotations

from rdkit import Chem

from openchem.chem.engine import InvalidStructureError


def protonate_at_ph(mol: Chem.Mol, ph: float) -> Chem.Mol:
    """Returns a new Mol representing the dominant ionization microspecies
    at `ph`, via Dimorphite-DL's curated SMARTS/pKa-range library
    (confirmed live: `protonate_smiles("CC(=O)O", ph_min=2, ph_max=2)` ->
    neutral carboxylic acid; the same call at pH 7.4/12 -> deprotonated
    carboxylate, matching acetic acid's real pKa ~4.76).

    Standalone and not charge-specific on purpose -- a future second
    consumer of "the pH-appropriate structure" can reuse this directly
    instead of duplicating the protonate-then-reparse pipeline.
    """
    import dimorphite_dl

    smiles = Chem.MolToSmiles(mol)
    variants = dimorphite_dl.protonate_smiles(smiles, ph_min=ph, ph_max=ph)
    if not variants:
        raise InvalidStructureError(f"Dimorphite-DL returned no protonation state for {smiles!r} at pH {ph}")
    protonated = Chem.MolFromSmiles(variants[0])
    if protonated is None:
        raise InvalidStructureError(f"Could not parse Dimorphite-DL output {variants[0]!r}")
    return protonated


def pka_predictor_available() -> bool:
    """Whether a numeric pKa model (pkasolver) is importable. Confirmed
    NOT available in this session's environment: pkasolver's own
    dependency chain (torch-geometric==2.0.1 -> torch-scatter/torch-sparse)
    has no pre-built wheel for this Python/platform and falls back to
    compiling from source, which requires an MSVC compiler this machine
    doesn't have. Always returns False for now -- exact numeric pKa is
    explicitly deferred, not silently unavailable (see `compute_pka`'s
    docstring and the Property Panel's pKa category, which falls back to
    Dimorphite-DL-only ionizable-group detection when this is False).
    """
    try:
        import torch  # noqa: F401
        import torch_geometric  # noqa: F401
        import pkasolver  # noqa: F401
    except ImportError:
        return False
    return True


def compute_pka(mol: Chem.Mol) -> list[tuple[int, float]] | None:
    """Returns (atom_idx, predicted_pKa) pairs via pkasolver, or `None` if
    `pka_predictor_available()` is False. Not implemented against a real
    pkasolver install this phase (see `pka_predictor_available`) --
    callers must treat `None` as "not installed," not "no ionizable atoms
    found."""
    if not pka_predictor_available():
        return None
    raise NotImplementedError(
        "pka_predictor_available() returned True but compute_pka's pkasolver "
        "integration was never implemented against a real install this phase "
        "(the install spike failed on this machine) -- implement against a "
        "real pkasolver environment before relying on this path."
    )
