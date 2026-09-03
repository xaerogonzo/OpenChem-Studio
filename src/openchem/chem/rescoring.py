"""A SECOND score for a pose that has already been found.

[source:su2019] evaluates four separate abilities and puts AutoDock Vina
strong at *docking power* ("close to 90%") while naming it among the
*"not-so-good scoring functions in the scoring/ranking power tests"*.
Measured locally on 5C1M at exhaustiveness 25, that split arrives as a
number: one molecule across three seeds spreads 0.06 kcal/mol while three
different analogues spread 0.13, so the difference between three MOLECULES
was about twice what one molecule shows against nothing but a seed change.

So the pose is worth keeping and the number attached to it is what a second
opinion is for. This module attaches one, and takes considerable care that
it is never mistaken for a better version of the first.

**WHAT THIS MODULE DOES NOT CLAIM.** That Vinardo ranks better here is
unmeasured. [source:quiroga2016] reports Vinardo outperforming Vina "in all
tests performed, for all datasets analyzed" -- a statement about the
authors' datasets, evaluated against CASF-2013, whose core set is also
where Vinardo's own parameters were selected (its §3.1: 122 of the 195
PDBbind Core 2013 structures). Whether it helps on any particular receptor
is a measurement, and until `benchmarks/docking/` supplies one the second
score is stored, labelled and displayed but never ranked on.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Callable

from openchem.chem.vina_engine import VinaEngine, select_vina_engine
from openchem.domain.docking import (
    AS_DOCKED,
    REFINE_THEN_SCORE,
    RESCORE_PROTOCOLS,
    PoseScore,
)
from openchem.plugins.interfaces import PoseRescorer, RescoreRequest

logger = logging.getLogger("openchem.chemistry")

#: DECLARED USER-FACING. `tests/test_calculator_reachability.py` fails if
#: nothing a user can press reaches this module.
USER_FACING_PROVIDER = (
    "The rescore column in the Docking panel's pose table, through the "
    "panel's 'Rescore poses' control"
)

#: The scoring functions this rescorer will ask a Vina engine for.
#:
#: **"vina" IS IN THE LIST ON PURPOSE, AND IT IS NOT A REDUNDANT ENTRY.**
#: Rescoring the TOP pose with the function that produced it reproduces
#: that pose's own affinity, which makes it the acceptance test for the
#: entire path -- receptor file, pose file, invocation, parser. Measured
#: on fentanyl in 5C1M, five poses: pose 0's dock affinity and its
#: `--score_only --scoring vina` value agree to 0.000.
#:
#: **AND IT ONLY HOLDS FOR THE TOP POSE, WHICH IS A FINDING RATHER THAN A
#: CAVEAT.** Vina reports
#:
#:     affinity = (inter + intra - unbound) / (1 + w_rot * N_rot)
#:
#: and a DOCKING run computes `unbound` ONCE for the whole run -- measured
#: at -0.861 with a spread of 0.013 across five poses, which is pose 0's
#: own internal energy to four decimals -- while `--score_only` uses each
#: pose's OWN intra as its unbound reference (verified: it reports
#: `unbound == intra` on every pose). So for pose i the two differ by
#: exactly `(U - intra_i) / D`. Measured against that formula on five
#: poses, worst residual 0.005 kcal/mol, with the real difference reaching
#: 0.41 on pose 1.
#:
#: The divisor came out of the same data rather than being assumed:
#: `inter/total` is 1.3507 on all five poses, so `w_rot * N_rot = 0.3507`,
#: and at Vina's own `w_rot = 0.05846` that is N_rot = 6.00 -- which RDKit
#: independently gives as fentanyl's rotatable-bond count.
#:
#: **This is a THIRD reason a rescore must never be compared with a
#: docking affinity**, on top of the scale difference and the protocol:
#: even the SAME function is not on the same reference.
SUPPORTED_RESCORE_FUNCTIONS = ("vina", "vinardo")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class VinaPoseRescorer(PoseRescorer):
    """Rescores with one of Vina 1.2.x's own scoring functions, through the
    same engine abstraction the search uses.

    **It needs no new install**, which is why it is the first
    implementation rather than the roadmap's named candidate: the Vina
    binary that produced the pose already ships `--score_only`,
    `--local_only` and `--scoring vinardo`, so the whole axis can be built
    and proved before anything has to be downloaded, registered for or
    compiled.

    **It is not the interesting rescorer and is not meant to be.** Vinardo
    is Vina-derived -- it shares Vina's component terms and differs in
    weights, radii and the removal of one Gaussian -- so it is a closer
    relative than a genuinely independent function would be. A
    knowledge-based rescorer from another family is the implementation that
    will show whether `PoseRescorer` is an abstraction or a Vina-shaped
    hole, and `RescoreRequest` carries the receptor's structure text and
    the pose molblocks for exactly that reason.
    """

    rescorer_id = "vina-rescore"
    units = "kcal/mol"

    def __init__(
        self,
        score_function: str = "vinardo",
        executable_path_resolver: Callable[[], str] | None = None,
        engine: VinaEngine | None = None,
    ) -> None:
        if score_function not in SUPPORTED_RESCORE_FUNCTIONS:
            raise ValueError(
                f"Unsupported rescoring function {score_function!r}; "
                f"expected one of {', '.join(SUPPORTED_RESCORE_FUNCTIONS)}."
            )
        self.score_function = score_function
        self._executable_path_resolver = executable_path_resolver
        self._fixed_engine = engine

    def _resolve_engine(self) -> VinaEngine | None:
        """Re-resolved on every call, never cached at construction -- the
        same reasoning `VinaDockingProvider._resolve_engine` records: a
        user can configure an executable path mid-session and a
        construction-time resolution would not see it until a restart."""
        if self._fixed_engine is not None:
            return self._fixed_engine
        configured = self._executable_path_resolver() if self._executable_path_resolver else ""
        return select_vina_engine(configured or None)

    def is_available(self) -> bool:
        return self._resolve_engine() is not None

    def rescore(self, request: RescoreRequest, protocol: str) -> list[PoseScore]:
        if protocol not in RESCORE_PROTOCOLS:
            raise ValueError(f"Unknown rescore protocol {protocol!r}.")

        engine = self._resolve_engine()
        if engine is None:
            return [
                self._unavailable(protocol, "No Vina backend is available to rescore with.")
                for _ in request.pose_pdbqt_paths
            ]

        engine_id = getattr(engine, "engine_id", "unknown")
        version = engine.version()
        # ONCE, not per pose: the receptor file is the same for all of them,
        # and hashing a 300 KB file per pose would be work proportional to
        # something it does not depend on.
        receptor_hash = _sha256(request.receptor_pdbqt.read_bytes())

        scores: list[PoseScore] = []
        for pose_path in request.pose_pdbqt_paths:
            scores.append(
                self._score_one(
                    engine, request, pose_path, protocol, engine_id, version, receptor_hash
                )
            )
        return scores

    def _score_one(
        self,
        engine: VinaEngine,
        request: RescoreRequest,
        pose_path: Path,
        protocol: str,
        engine_id: str,
        version: str,
        receptor_hash: str,
    ) -> PoseScore:
        common = {
            "function": self.score_function,
            "protocol": protocol,
            "units": self.units,
            "engine": engine_id,
            "engine_version": version,
            "receptor_pdbqt_sha256": receptor_hash,
            "pose_pdbqt_sha256": _sha256(pose_path.read_bytes()),
        }
        try:
            value = engine.score_pose(
                request.receptor_pdbqt,
                pose_path,
                request.box,
                self.score_function,
                refine=protocol == REFINE_THEN_SCORE,
            )
        except NotImplementedError as exc:
            # The engine that ran the search cannot score without searching.
            # That is a property of the backend, not a fault in this run or
            # this molecule, so it renders neutral rather than red.
            return PoseScore(
                inapplicable=True,
                error=str(exc),
                error_summary="Backend cannot rescore",
                **common,
            )
        except Exception as exc:  # noqa: BLE001 - a rescore must never fail a docking job
            logger.exception("Rescoring a pose with %s failed", self.score_function)
            return PoseScore(
                error=f"{self.score_function} rescoring failed: {exc}",
                error_summary="Rescore failed",
                **common,
            )
        return PoseScore(value=value, **common)

    def _unavailable(self, protocol: str, reason: str) -> PoseScore:
        return PoseScore(
            function=self.score_function,
            protocol=protocol,
            units=self.units,
            inapplicable=True,
            error=reason,
            error_summary="No backend",
        )


__all__ = [
    "AS_DOCKED",
    "REFINE_THEN_SCORE",
    "SUPPORTED_RESCORE_FUNCTIONS",
    "USER_FACING_PROVIDER",
    "VinaPoseRescorer",
]
