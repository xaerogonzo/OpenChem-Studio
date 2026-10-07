"""The census's scenarios, as builders of drive scripts (`OPENCHEM_DRIVE`).

A scenario is a list of steps plus the facts the runner needs to judge it: how fast
to sample, how long it may take, whether it forces a collection, and which probes
are on. Scripts are GENERATED rather than stored so the iteration count, warm-up
and checkpoint spacing are parameters the result records -- the runner writes the
generated script beside the result and hashes it, so a number always names the
exact script that produced it.

**NO SCENARIO HERE STARTS AN EXTERNAL PROCESS EXCEPT THE ONES NAMED `external-`.**
The lifecycle loops use one cheap, deterministic, in-process calculator on a fixed
molecule: 50 ORCA launches would measure the calculator, not the lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

#: One cheap, deterministic, in-process, per-atom calculator. Gasteiger charges at
#: the molecule's own state (`ph_dependent` off), so no microspecies search runs.
LIFECYCLE_CALCULATOR = "gasteiger_charge_at_ph"
LIFECYCLE_CALCULATOR_PARAMETERS = {"ph_dependent": False}

#: A fixed fixture, small enough that the calculator is not what is measured.
LIFECYCLE_SMILES = "CC(=O)Oc1ccccc1C(=O)O"  # aspirin
HEAVY_SMILES = (
    # Erythromycin A: 51 heavy atoms, 5 rings' worth of glycoside/macrocycle, 10 stereocentres
    # beyond what a descriptor panel's usual aspirin exercises. Frozen: do not edit.
    "CC[C@@H]1[C@@]([C@@H]([C@H](C(=O)[C@@H](C[C@@]([C@@H]([C@H]([C@@H]([C@H](C(=O)O1)C)"
    "O[C@H]2C[C@@]([C@H]([C@@H](O2)C)O)(C)OC)C)O[C@H]3[C@@H]([C@H](C[C@H](O3)C)N(C)C)O)(C)O)C)C)O)(C)O"
)

#: Checkpoints where memory is read and an object census is taken. Sparse on purpose:
#: each costs a full collection plus a walk of every tracked object.
DEFAULT_CHECKPOINTS = (1, 5, 10, 20, 30, 40, 50)
STARTUP_SETTLE_MS = 30000
DEFAULT_WARMUP = 5


@dataclass
class Scenario:
    id: str
    description: str
    steps: list[dict[str, Any]]
    cadence_s: float = 1.0
    timeout_s: float = 900.0
    forces_gc: bool = False
    probes: list[str] = field(default_factory=list)
    #: Which result summary the runner computes: idle | panels | lifecycle | generic.
    kind: str = "generic"
    parameters: dict[str, Any] = field(default_factory=dict)


def _s(do: str, **kwargs: Any) -> dict[str, Any]:
    return {"do": do, **kwargs}


def _boot(smiles: str = LIFECYCLE_SMILES, name: str = "census") -> list[dict[str, Any]]:
    return [
        _s("smiles", smiles=smiles, name=name),
        _s("select", molecule=-1),
        _s("panel", id="Properties"),
    ]


def _checkpoint(iteration: int, settle_ms: int = 1500, window_ms: int = 2500) -> list[dict[str, Any]]:
    """gc -> settle -> stamp -> hold still while the sampler reads -> census."""
    return [
        _s("gc", after_ms=settle_ms),
        _s("mark", name=f"cp-{iteration}", after_ms=window_ms),
        _s("object_census", tag=f"cp-{iteration}", collect=True),
    ]


def _loop(
    body: Callable[[int], list[dict[str, Any]]],
    iterations: int,
    checkpoints: tuple[int, ...],
    prologue: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    steps = list(prologue or _boot())
    # THE PAGES ARE STILL LOADING when the window is shown: a first no-op control
    # measured a 25 MiB step between iterations 5 and 10 and a Chromium helper tree
    # that more than doubled its USS, all of it start-up. Wait it out before the
    # baseline, and say so in the result (`startup_settle_ms`).
    steps += [_s("wait", after_ms=STARTUP_SETTLE_MS)]
    steps += [_s("gc", after_ms=1500), _s("mark", name="cp-0", after_ms=2500), _s("object_census", tag="cp-0")]
    for i in range(1, iterations + 1):
        steps += body(i)
        if i in checkpoints:
            steps += _checkpoint(i)
    return steps


# -- S0 controls --------------------------------------------------------------


def control_noop(iterations: int = 20) -> Scenario:
    steps = _loop(lambda i: [_s("wait", after_ms=300)], iterations, (1, 5, 10, 15, 20), prologue=[])
    steps.append(_s("quit"))
    return Scenario("control-noop", "No work: the slope must stay under the declared threshold.",
                    steps, forces_gc=True, probes=["object_census"], kind="lifecycle",
                    parameters={"iterations": iterations, "warmup": 5, "checkpoints": (1, 5, 10, 15, 20),
                                "expect": "flat"})


def control_bytes(iterations: int = 20, mb: float = 5.0) -> Scenario:
    steps = _loop(lambda i: [_s("control_inject", kind="bytes", mb=mb, after_ms=300)], iterations,
                  (1, 5, 10, 15, 20), prologue=[])
    steps.append(_s("quit"))
    return Scenario("control-bytes", f"Retain {mb} MiB per iteration: the slope must be ~{mb} MiB/iteration.",
                    steps, forces_gc=True, probes=["object_census"], kind="lifecycle",
                    parameters={"iterations": iterations, "warmup": 5, "checkpoints": (1, 5, 10, 15, 20),
                                "expect": "slope", "mib_per_iteration": mb})


def control_widgets(iterations: int = 20, count: int = 25) -> Scenario:
    steps = _loop(lambda i: [_s("control_inject", kind="widgets", count=count, after_ms=300)], iterations,
                  (1, 5, 10, 15, 20), prologue=[])
    steps.append(_s("quit"))
    return Scenario("control-widgets", f"Retain {count} QLabel per iteration: QLabel must grow monotonically.",
                    steps, forces_gc=True, probes=["object_census"], kind="lifecycle",
                    parameters={"iterations": iterations, "warmup": 5, "checkpoints": (1, 5, 10, 15, 20),
                                "expect": "widget_growth", "widget_class": "QLabel",
                                "per_iteration": count})


def control_child(seconds: float = 2.0) -> Scenario:
    steps = [
        _s("wait", after_ms=2000),
        _s("control_inject", kind="child", seconds=seconds, after_ms=int(seconds * 1000) + 3000),
        _s("quit"),
    ]
    return Scenario("control-child", "One short-lived child process: the process table must record it.",
                    steps, cadence_s=0.15, kind="generic", parameters={"expect": "child", "seconds": seconds})


def _overhead_base(seconds: int) -> list[dict[str, Any]]:
    steps = _boot()
    steps += [_s("calculator", id=LIFECYCLE_CALCULATOR, parameters=LIFECYCLE_CALCULATOR_PARAMETERS,
                 reveal=False, after_ms=3000)]
    return steps


def overhead(arm: str, seconds: int = 60) -> Scenario:
    """The same drive and duration for every arm; only the probe differs."""
    steps = _overhead_base(seconds)
    if arm == "census":
        steps.append(_s("mark", name="idle-start"))
        for k in range(5):
            steps += [_s("object_census", tag=f"o{k}", after_ms=seconds * 1000 // 5)]
    elif arm == "heartbeat":
        steps += [_s("mark", name="idle-start"), _s("loop_lag", action="start", tag="idle", interval_ms=10),
                  _s("wait", after_ms=seconds * 1000), _s("loop_lag", action="stop", tag="idle")]
    elif arm == "tracemalloc":
        steps += [_s("tracemalloc", action="start"), _s("mark", name="idle-start"),
                  _s("wait", after_ms=seconds * 1000), _s("tracemalloc", action="diff", tag="idle"),
                  _s("tracemalloc", action="stop")]
    else:  # sampler only
        steps += [_s("mark", name="idle-start"), _s("wait", after_ms=seconds * 1000)]
    steps.append(_s("quit"))
    return Scenario(f"overhead-{arm}", f"Probe-overhead arm: {arm}", steps, kind="idle",
                    probes=[] if arm == "sampler" else [arm], forces_gc=arm == "census",
                    parameters={"seconds": seconds, "arm": arm})


# -- S1 startup / idle ----------------------------------------------------------


def startup_idle(idle_seconds: int = 300) -> Scenario:
    steps = [_s("wait", after_ms=idle_seconds * 1000), _s("quit")]
    return Scenario("startup-idle", "Fresh process -> window ready -> idle. Sampler only.", steps,
                    kind="idle", timeout_s=idle_seconds + 240,
                    parameters={"idle_seconds": idle_seconds})


# -- S2 panels --------------------------------------------------------------------


def panels(settle_ms: int = 3000, sample_ms: int = 17000, expect: int | None = 12) -> Scenario:
    step = _s("panel_cycle", settle_ms=settle_ms, sample_ms=sample_ms)
    if expect is not None:
        step["expect"] = expect
    steps = _boot() + [step, _s("quit")]
    return Scenario("panels-idle", "Each right-hand dock shown in turn: transition vs steady CPU.",
                    steps, kind="panels", timeout_s=900,
                    parameters={"settle_ms": settle_ms, "sample_ms": sample_ms})


# -- S3 lifecycle loops -----------------------------------------------------------


def _scenario_loop(sid: str, text: str, body: Callable[[int], list[dict[str, Any]]], iterations: int,
                   checkpoints: tuple[int, ...], warmup: int, extra: list[dict[str, Any]] | None = None
                   ) -> Scenario:
    steps = _loop(body, iterations, checkpoints) + (extra or []) + [_s("quit")]
    return Scenario(sid, text, steps, forces_gc=True, probes=["object_census"], kind="lifecycle",
                    timeout_s=1800,
                    parameters={"iterations": iterations, "warmup": warmup, "checkpoints": checkpoints,
                                "calculator": LIFECYCLE_CALCULATOR, "smiles": LIFECYCLE_SMILES})


def lifecycle_edit(iterations: int = 50, checkpoints: tuple[int, ...] = DEFAULT_CHECKPOINTS,
                   warmup: int = DEFAULT_WARMUP) -> Scenario:
    """S3a: edit (a real EditStructureCommand), recalculate, undo."""
    def body(i: int) -> list[dict[str, Any]]:
        return [
            _s("restructure", order="reverse", after_ms=500),
            _s("calculator", id=LIFECYCLE_CALCULATOR, parameters=LIFECYCLE_CALCULATOR_PARAMETERS,
               reveal=False, after_ms=800),
            _s("menu", text="Undo", prefix=True, after_ms=400),
        ]
    return _scenario_loop("lifecycle-edit", "S3a import/select/edit/recalculate/undo", body, iterations,
                          checkpoints, warmup)


def lifecycle_inspector(iterations: int = 50, checkpoints: tuple[int, ...] = DEFAULT_CHECKPOINTS,
                        warmup: int = DEFAULT_WARMUP) -> Scenario:
    """S3b: open and close the Calculator Inspector (a QWebEngineView per open)."""
    def body(i: int) -> list[dict[str, Any]]:
        return [
            _s("inspect", id=LIFECYCLE_CALCULATOR, parameters=LIFECYCLE_CALCULATOR_PARAMETERS, after_ms=1500),
            _s("close_windows", which=["inspector"], after_ms=600),
        ]
    return _scenario_loop("lifecycle-inspector", "S3b Calculator Inspector open/close", body, iterations,
                          checkpoints, warmup)


def lifecycle_lewis(iterations: int = 50, checkpoints: tuple[int, ...] = DEFAULT_CHECKPOINTS,
                    warmup: int = DEFAULT_WARMUP) -> Scenario:
    """S3c: open and close the Full Lewis window."""
    def body(i: int) -> list[dict[str, Any]]:
        return [_s("lewis", details=True, after_ms=800), _s("close_windows", which=["lewis"], after_ms=400)]
    return _scenario_loop("lifecycle-lewis", "S3c Lewis window open/close", body, iterations,
                          checkpoints, warmup)


def lifecycle_results(iterations: int = 50, checkpoints: tuple[int, ...] = DEFAULT_CHECKPOINTS,
                      warmup: int = DEFAULT_WARMUP) -> Scenario:
    """S3d: float and re-dock the Results panel, with a result for it to read."""
    def body(i: int) -> list[dict[str, Any]]:
        return [
            _s("calculator", id=LIFECYCLE_CALCULATOR, parameters=LIFECYCLE_CALCULATOR_PARAMETERS,
               reveal=False, after_ms=500),
            _s("dock_float", panel="Results", on=True, after_ms=500),
            _s("dock_float", panel="Results", on=False, after_ms=500),
        ]
    return _scenario_loop("lifecycle-results", "S3d Results pop-out float/dock", body, iterations,
                          checkpoints, warmup)


def lifecycle_dialogs(iterations: int = 50, checkpoints: tuple[int, ...] = DEFAULT_CHECKPOINTS,
                      warmup: int = DEFAULT_WARMUP,
                      names: tuple[str, ...] = ("HelpDialog", "PeriodicTableDialog", "SettingsDialog")
                      ) -> Scenario:
    """S3e: open and close a few dialogs by name (the `dialog` step closes the last)."""
    def body(i: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name in names:
            out += [_s("dialog", name=name, after_ms=700), _s("close_windows", which=["dialog"], after_ms=300)]
        return out
    scenario = _scenario_loop("lifecycle-dialogs", "S3e dialogs open/close", body, iterations,
                              checkpoints, warmup)
    scenario.parameters["dialogs"] = list(names)
    return scenario


# -- S4 responsiveness --------------------------------------------------------------


def responsiveness() -> Scenario:
    steps = _boot() + [
        _s("loop_lag", action="start", tag="burst", interval_ms=10),
        _s("edit_burst", grow="CCO", edits=12, gap_ms=150, tag="burst", profile=False, after_ms=1000),
        _s("loop_lag", action="stop", tag="burst"),
        _s("edit_burst", grow="CCCO", edits=12, gap_ms=150, tag="profiled", profile=True, after_ms=1000),
        _s("quit"),
    ]
    return Scenario("responsiveness", "S4 edit burst with heartbeat, then profiled", steps,
                    probes=["heartbeat"], kind="generic", timeout_s=600)


# -- S5 heavy molecule ----------------------------------------------------------------


def heavy_molecule() -> Scenario:
    steps = _boot(HEAVY_SMILES, "erythromycin") + [
        _s("mark", name="phase:loaded", after_ms=4000),
        _s("loop_lag", action="start", tag="descriptors", interval_ms=10),
        _s("calculator", id=LIFECYCLE_CALCULATOR, parameters=LIFECYCLE_CALCULATOR_PARAMETERS, reveal=False,
           after_ms=6000),
        _s("loop_lag", action="stop", tag="descriptors"),
        _s("mark", name="phase:descriptors", after_ms=3000),
        _s("quit"),
    ]
    return Scenario("heavy-molecule", "S5 large molecule: load, descriptors (conformers/3D added once "
                    "their drive steps are pinned)", steps, probes=["heartbeat"], kind="generic",
                    timeout_s=900, parameters={"smiles": HEAVY_SMILES})


REGISTRY: dict[str, Callable[..., Scenario]] = {
    "control-noop": control_noop,
    "control-bytes": control_bytes,
    "control-widgets": control_widgets,
    "control-child": control_child,
    "overhead-sampler": lambda **kw: overhead("sampler", **kw),
    "overhead-census": lambda **kw: overhead("census", **kw),
    "overhead-heartbeat": lambda **kw: overhead("heartbeat", **kw),
    "overhead-tracemalloc": lambda **kw: overhead("tracemalloc", **kw),
    "startup-idle": startup_idle,
    "panels-idle": panels,
    "lifecycle-edit": lifecycle_edit,
    "lifecycle-inspector": lifecycle_inspector,
    "lifecycle-lewis": lifecycle_lewis,
    "lifecycle-results": lifecycle_results,
    "lifecycle-dialogs": lifecycle_dialogs,
    "responsiveness": responsiveness,
    "heavy-molecule": heavy_molecule,
}
