"""Decision rules for the gnina default-dock test, as pure functions.

`PREREGISTRATION_GNINA_DOCK.md` is that text as code. Populations and the
verdict grammar are the CNN-rescore test's (`gnina_core`); this module only
compares Vina pose 1 to gnina pose 1 after a search. Nothing here knows about
WSL or files.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import gnina_core as rescore

SUCCESS_RMSD = rescore.SUCCESS_RMSD
MIN_NET = rescore.MIN_NET
ALPHA = rescore.ALPHA
MAX_UNSCORED = rescore.MAX_UNSCORED
SEED = rescore.SEED
EXHAUSTIVENESS = rescore.EXHAUSTIVENESS
NUM_MODES = 9
#: gnina v1.3.3 `--help`: `--cnn_scoring arg (=1)` is rescore (default).
CNN_SCORING = "rescore"
SCORE_ONLY = False
VERSION_NEEDLE = rescore.VERSION_NEEDLE
COMMIT_NEEDLE = rescore.COMMIT_NEEDLE
TRAINING_OVERLAP = rescore.TRAINING_OVERLAP
deciding_ids = rescore.deciding_ids
tally = rescore.tally
verdict = rescore.verdict
sign_test_one_sided = rescore.sign_test_one_sided
version_is_pinned = rescore.version_is_pinned
Outcome = rescore.Outcome
Tally = rescore.Tally


def help_default_is_rescore(text: str) -> bool:
    """True when `--help` still names rescore as the cnn_scoring default."""
    lowered = text.lower()
    if "--cnn_scoring" not in lowered:
        return False
    return "rescore" in lowered and ("(=1)" in text or "default" in lowered)


@dataclass(frozen=True)
class DockReceptor:
    pdb: str
    vina_rmsds: tuple[float | None, ...]
    gnina_rmsds: tuple[float | None, ...] | None


def top_correct(rmsds: Sequence[float | None] | None) -> bool | None:
    if not rmsds or rmsds[0] is None:
        return None
    return rmsds[0] <= SUCCESS_RMSD


def judge_dock(receptor: DockReceptor) -> Outcome:
    before = top_correct(receptor.vina_rmsds)
    if receptor.gnina_rmsds is None:
        return Outcome(receptor.pdb, before, None, None)
    after = top_correct(receptor.gnina_rmsds)
    return Outcome(receptor.pdb, before, after, 0 if after is not None else None)
