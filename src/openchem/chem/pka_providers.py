"""Numeric pKa via pkasolver, plus pH-dependent protonation via Dimorphite-DL.

HOW ACCURATE IT ACTUALLY IS, measured rather than assumed, because the
single acetic-acid number the setup dialog used to report made it look
worse than it is. Twenty-four compounds with standard literature values
in water at 25 C, run against the real installed sidecar:

    MAE 0.29 pKa units   median 0.14   22 of 24 within 1.0 unit
      bases  n=10  MAE 0.13   max 0.39
      acids  n=14  MAE 0.41   max 2.70

That is at or better than pkasolver's own published performance, and
better than the 0.5-1 unit a medicinal chemist would treat as usable.

ACETIC ACID IS ONE OF ITS WORSE CASES (-0.57, third worst of the 24),
which is exactly why the dialog now probes an acid, a phenol and a base
instead of that one compound.

THE REAL WEAKNESS IS ELECTRON-POOR PHENOLS, and it is worth knowing
before trusting a number:

    2,4-dinitrophenol   literature 4.09   predicted 6.79   +2.70
    4-nitrophenol       literature 7.15   predicted 8.19   +1.04

Both are strongly acidic phenols whose acidity comes from nitro-group
resonance stabilising the phenolate, and the model consistently
under-predicts that. Ordinary phenols are fine (phenol +0.04,
4-methylphenol -0.08). Treat a nitro-substituted phenol's predicted pKa
as an upper bound.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from rdkit import Chem

from openchem.chem.engine import InvalidStructureError

logger = logging.getLogger("openchem.chemistry")

# Settings key holding the path to a Python interpreter that has pkasolver
# installed. Configured via Tools -> External Tools, same as ORCA's and
# Vina's executables.
PKASOLVER_PYTHON_SETTING = "pka/pkasolver_python_path"

_RUNNER = Path(__file__).resolve().parent / "pka_runner.py"

# A pkasolver call loads a 105 MB ensemble of models per invocation, so it
# is slow but bounded -- generous enough not to fail a legitimate run on a
# cold filesystem cache, short enough not to hang the UI forever.
_TIMEOUT_SECONDS = 300


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


def pka_predictor_available(interpreter_path: str | None) -> bool:
    """Whether a usable pkasolver environment is configured.

    pkasolver runs OUT OF PROCESS, in its own virtual environment, for a
    concrete reason established by a real install spike (Phase 23): it
    requires `numpy<2` and `scipy<1.14`, while this project runs numpy 2.x,
    and it is not pip-installable at all on Python 3.12 (its setup.py uses
    `versioneer`, which calls the `configparser.SafeConfigParser` removed
    in 3.12). Running it as an external tool -- exactly how this app
    already treats ORCA and Vina -- keeps those pins, ~105 MB of model
    weights, and all of torch out of this project's dependency tree.

    Only checks that the interpreter exists; whether pkasolver actually
    imports there is answered by running it (see `describe_pka_status`),
    since a stale or half-built environment should surface as a real error
    message rather than a silent False.
    """
    if not interpreter_path:
        return False
    return Path(interpreter_path).is_file()


def compute_pka(mol: Chem.Mol, interpreter_path: str | None) -> list[tuple[int, float]] | None:
    """Returns (reaction_center_atom_idx, predicted_pKa) pairs from
    pkasolver, or `None` if no pkasolver environment is configured --
    callers must treat `None` as "not installed," not "no ionizable atoms
    found."

    **The atom index is NOT reliable against `mol`'s own numbering.**
    Confirmed live: for ibuprofen pkasolver reports reaction centre 12,
    which is a carbon in our input molecule, while the acidic proton is on
    the carboxyl oxygen; aniline reports index 0 (a ring carbon) for both
    of its pKa values. The index refers to pkasolver's internal
    protonated/deprotonated microstate representation, not the caller's
    mol. Consumers should therefore use the pKa VALUES (which are
    accurate -- see `describe_pka_status`) and must not key a per-atom
    visualization off these indices without first establishing a real
    atom mapping, or they will highlight the wrong atoms.

    Raises `RuntimeError` when a pkasolver environment IS configured but
    the run fails, so a broken install is reported rather than silently
    degrading to the same state as "not installed."
    """
    if not pka_predictor_available(interpreter_path):
        return None

    smiles = Chem.MolToSmiles(mol)
    try:
        completed = subprocess.run(
            [str(interpreter_path), str(_RUNNER), smiles],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"pkasolver timed out after {_TIMEOUT_SECONDS}s") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not run the configured pkasolver interpreter: {exc}") from exc

    payload = _parse_runner_output(completed.stdout, completed.stderr, completed.returncode)
    return [(int(entry["atom_idx"]), float(entry["pka"])) for entry in payload["pkas"]]


def _parse_runner_output(stdout: str, stderr: str, returncode: int) -> dict:
    # pkasolver's dependencies print progress/citation banners to stdout,
    # so the JSON payload is the LAST line rather than the whole stream.
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "error" in payload:
            raise RuntimeError(f"pkasolver failed: {payload['error']}")
        if "pkas" in payload:
            return payload
    raise RuntimeError(
        f"pkasolver produced no usable output (exit {returncode}). "
        f"stderr: {stderr.strip()[:400] or '<empty>'}"
    )


def describe_pka_status(interpreter_path: str) -> str:
    """One-line human-readable status for the External Tools dialog --
    mirrors `tool_download_service.describe_vina_status`. Actually runs a
    tiny prediction rather than just checking the path, since a configured
    but broken environment is the failure mode worth surfacing here.
    """
    # Checked before running anything: a path that is not an interpreter
    # produces an OS error naming neither the path nor the problem, and
    # the app knows where it installed the real one.
    from openchem.services.pkasolver_setup import default_install_root
    from openchem.services.sidecar_env import interpreter_problem, recovery_hint

    if interpreter_path and interpreter_path.strip():
        problem = interpreter_problem(interpreter_path)
        if problem is not None:
            return f"Not usable: {problem}{recovery_hint(default_install_root())}"
    if not pka_predictor_available(interpreter_path):
        return "Not configured — numeric pKa unavailable (ionizable-group detection still works)"
    # Three probes, not one. This used to report acetic acid alone, whose
    # -0.57 error is the third worst of the 24 compounds benchmarked below
    # -- so the single number a user saw was close to the model's worst
    # advert, and read as "inaccurate" when the measured MAE is 0.29.
    # An acid, a phenol and a base together show the real spread.
    probes = (("acetic acid", "CC(=O)O", 4.76), ("phenol", "Oc1ccccc1", 9.99),
              ("benzylamine", "NCc1ccccc1", 9.34))
    parts, errors = [], []
    for name, smiles, literature in probes:
        try:
            pkas = compute_pka(Chem.MolFromSmiles(smiles), interpreter_path)
        except RuntimeError as exc:
            return f"Configured but not working: {exc}"
        if not pkas:
            return f"Configured, but returned no pKa for {name} — check the install"
        nearest = min((v for _i, v in pkas), key=lambda v: abs(v - literature))
        errors.append(abs(nearest - literature))
        parts.append(f"{name} {nearest:.2f} (lit {literature:.2f})")
    return (
        "Found: pkasolver — "
        + "; ".join(parts)
        + f". Off by {sum(errors)/len(errors):.2f} on average here; "
        "0.29 over the 24-compound check in this module's docstring."
    )
