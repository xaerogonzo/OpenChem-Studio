"""The resource census's own instruments, and the in-app probes it reads.

An instrument is trusted only after it has seen a signal planted at a known size, and
the end-to-end version of that (`tools/perf_census.py controls`, which launches the
real app) lives outside the suite because it takes minutes. What IS here is what
must hold for those controls to mean anything: the statistics, the reading rules, the
object census seeing what is put in front of it, and the scenario scripts naming only
steps the driver has.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))
import perf_census as census  # noqa: E402

sys.path.insert(0, str(_ROOT / "benchmarks" / "perf"))
import scenarios  # noqa: E402


# -- statistics -----------------------------------------------------------------


def test_theil_sen_recovers_a_planted_slope_and_ignores_one_spike():
    points = [(i, 100.0 + 5.0 * i) for i in range(0, 50, 5)]
    assert census.theil_sen(points) == pytest.approx(5.0)
    spiked = list(points)
    spiked[4] = (spiked[4][0], spiked[4][1] + 400.0)
    # One Windows memory spike moves a least-squares fit; the median of slopes holds.
    assert census.theil_sen(spiked) == pytest.approx(5.0, abs=0.5)


def test_theil_sen_of_one_point_is_none_not_zero():
    assert census.theil_sen([(1, 2.0)]) is None


def test_median_iqr_reports_spread_and_survives_an_empty_list():
    stats = census.median_iqr([1.0, 2.0, 3.0, 4.0, 5.0])
    assert stats["median"] == 3.0 and stats["n"] == 5 and stats["iqr"] == 2.0
    assert census.median_iqr([])["n"] == 0


# -- the reading rules ------------------------------------------------------------


def test_rss_growth_alone_is_never_called_a_leak():
    reading = census.interpret_growth(1.0, objects_grew=False, tracemalloc_grew=None)
    assert "leak" not in reading.lower()
    assert "native" in reading


def test_objects_without_rss_and_all_three_are_told_apart():
    assert "without OS-level growth" in census.interpret_growth(0.0, True, None)
    assert census.interpret_growth(1.0, True, True).startswith("strong")
    assert census.interpret_growth(0.0, False, None).startswith("no growth")


def _census(widgets: dict[str, int], timers: int = 1) -> dict:
    return {"widgets": widgets, "qobject_wrappers": dict(widgets), "widget_total": sum(widgets.values()),
            "qobject_wrappers_total": sum(widgets.values()), "timers_active": timers}


def test_a_class_is_a_candidate_only_if_it_keeps_climbing():
    tables = {
        f"object_census[cp-{c}]": _census({"Grows": 10 + c, "Plateaus": 50 if c else 10, "Shrinks": 30 - c})
        for c in (5, 10, 20, 30)
    }
    growth = census.object_growth(tables, [5, 10, 20, 30], warmup=5)["monotonic_growers"]
    assert "widgets:Grows" in growth
    # A cache fills once and stays: ending larger than it began is not enough.
    assert "widgets:Plateaus" not in growth
    assert "widgets:Shrinks" not in growth


def test_too_few_checkpoints_say_so_instead_of_reporting_no_growth():
    growth = census.object_growth({"object_census[cp-5]": _census({"A": 1})}, [5], warmup=5)
    assert growth["monotonic_growers"] == {} and "fewer than 3" in growth["note"]


# -- the process classifier -------------------------------------------------------------


@pytest.mark.parametrize(
    "name, cmdline, root, expected",
    [
        ("python.exe", "python -m openchem.main", False, "app"),
        ("QtWebEngineProcess.exe", "", False, "QtWebEngine"),
        ("java.exe", "java -jar opsin.jar", False, "Java/OPSIN"),
        ("orca.exe", "", False, "ORCA"),
        ("vina.exe", "", False, "Vina"),
        ("python.exe", "python -c pass", False, "other"),
        ("uv.exe", "uv run", True, "launcher"),
    ],
)
def test_process_classes(name, cmdline, root, expected):
    assert census.classify(name, cmdline, root) == expected


# -- the controls judge a planted signal ----------------------------------------------------


def _summary(parameters: dict, lifecycle: dict | None = None, processes: list | None = None) -> dict:
    return {"parameters": parameters, "derived": {"lifecycle": lifecycle or {}, "processes": processes or []}}


def test_controls_pass_on_a_planted_signal_and_fail_on_a_missed_one():
    ok = census.check_controls({
        "control-noop": _summary({}, {"rss_slope_mib_per_iteration": 0.05}),
        "control-bytes": _summary({"mib_per_iteration": 5.0}, {"rss_slope_mib_per_iteration": 4.9}),
        "control-widgets": _summary({}, {"object_growth": {"monotonic_growers": {"widgets:QLabel": [1, 2, 3]}}}),
        "control-child": _summary({"seconds": 2.0}, processes=[{"class": "other", "name": "python.exe"}]),
    })
    assert all(check["pass"] for check in ok) and len(ok) == 4

    bad = census.check_controls({
        "control-noop": _summary({}, {"rss_slope_mib_per_iteration": 2.0}),
        "control-bytes": _summary({"mib_per_iteration": 5.0}, {"rss_slope_mib_per_iteration": 0.1}),
        "control-widgets": _summary({}, {"object_growth": {"monotonic_growers": {}}}),
        "control-child": _summary({"seconds": 2.0}, processes=[]),
    })
    assert not any(check["pass"] for check in bad)


# -- the sampler, on a process it can plant a signal in ----------------------------------------


def test_sampler_sees_a_short_lived_child_and_a_planted_allocation():
    psutil = pytest.importorskip("psutil")
    import subprocess

    code = (
        "import time, subprocess, sys\n"
        "keep = bytearray(60*1024*1024)\n"
        "for i in range(0, len(keep), 4096): keep[i] = 1\n"
        "subprocess.run([sys.executable, '-c', 'import time; time.sleep(0.8)'])\n"
        "time.sleep(1.0)\n"
    )
    process = subprocess.Popen([sys.executable, "-c", code])
    sampler = census.Sampler(process.pid, interval_s=0.1)
    sampler.start()
    process.wait(timeout=30)
    sampler.stop()
    sampler.join(timeout=5)
    assert sampler.rows, "the sampler recorded nothing"
    assert max(float(r["tree_rss"]) for r in sampler.rows) > 50 * 1024 * 1024
    names = [seen.name.lower() for seen in sampler.table.values()]
    assert sum(1 for n in names if n.startswith("python")) >= 2, "the child was missed"
    assert psutil  # imported for the skip


# -- the in-app probes ---------------------------------------------------------------------------


def test_object_census_sees_retained_widgets_and_an_active_timer(qapp):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QLabel

    from openchem.app import drive_probes

    before = drive_probes.object_census()
    held = [QLabel("x") for _ in range(7)]
    timer = QTimer()
    timer.setInterval(777)
    timer.start()
    try:
        after = drive_probes.object_census()
        assert after["widgets"].get("QLabel", 0) - before["widgets"].get("QLabel", 0) == 7
        assert any(t["interval_ms"] == 777 and not t["single_shot"] for t in after["timers_active_detail"])
        assert after["gc_forced"] is True
    finally:
        timer.stop()
        del held


def test_heartbeat_reports_a_stall_it_was_made_to_see(qapp):
    from PySide6.QtWidgets import QApplication

    from openchem.app import drive_probes

    probe = drive_probes.HeartbeatProbe(interval_ms=5)
    probe.start()
    deadline = time.perf_counter() + 0.15
    while time.perf_counter() < deadline:
        QApplication.processEvents()
    time.sleep(0.12)  # block the loop
    QApplication.processEvents()
    result = probe.stop()
    assert result["stall_ms"]["max"] >= 80.0
    assert result["stalls_over_ms"]["50.0"] >= 1


def test_allocation_probe_names_this_file_and_declares_its_blind_spot():
    from openchem.app import drive_probes

    probe = drive_probes.AllocationProbe()
    probe.start()
    try:
        # Allocated inside `openchem`'s own path is what the filter keeps; a tests/ line is
        # outside it, so the diff is empty rather than wrong.
        result = probe.diff()
    finally:
        probe.stop()
    assert "limitation" in result and "native" in result["limitation"]


def test_cache_probe_walks_attributes_only():
    from openchem.app import drive_probes

    class Holder:
        class Inner:
            items = {"a": 1, "b": 2}

        inner = Inner()

    assert drive_probes.cache_size(drive_probes.resolve_attribute_path(Holder, "inner.items"))["len"] == 2
    with pytest.raises(AttributeError):
        drive_probes.resolve_attribute_path(Holder, "inner.missing")


# -- the scenarios speak the driver's language ------------------------------------------------------


def test_every_scenario_step_is_one_the_driver_implements():
    from openchem.app.debug_drive import _Driver

    for name, builder in scenarios.REGISTRY.items():
        scenario = builder()
        for step in scenario.steps:
            assert hasattr(_Driver, f"_do_{step['do']}"), f"{name}: unknown step {step['do']!r}"
        assert scenario.steps[-1]["do"] == "quit", f"{name} does not end in quit"
        json.dumps(scenario.steps)  # a script must serialise


def test_lifecycle_scenarios_use_no_external_process_calculator():
    # The loops must measure lifecycle, not 50 ORCA launches.
    for name, builder in scenarios.REGISTRY.items():
        if not name.startswith("lifecycle-"):
            continue
        for step in builder().steps:
            if step["do"] in ("calculator", "inspect"):
                assert step["id"] == scenarios.LIFECYCLE_CALCULATOR
            assert step["do"] not in ("qc_run", "screen_run", "dock_run", "tautomer_run")


def test_the_dirty_tree_guard_names_what_it_refuses_over(monkeypatch, capsys):
    monkeypatch.setattr(census, "environment_snapshot", lambda: {"git_status_porcelain": [" M x.py"]})
    args = census.argparse.Namespace(scenarios=["control-noop"], runs=1, set=None, allow_dirty=False)
    assert census.cmd_run(args) == 2
    assert "dirty" in capsys.readouterr().err


# -- the heavy-molecule phases ------------------------------------------------------------------


def test_heavy_molecule_asserts_conformers_so_it_cannot_pass_empty():
    steps = scenarios.heavy_molecule().steps
    names = [step["do"] for step in steps]
    assert names.index("conformers") < names.index("expect_conformers") < names.index("view_3d")
    assert {"phase:loaded", "phase:descriptors", "phase:conformers", "phase:viewer-open",
            "phase:viewer-away"} <= {s.get("name") for s in steps if s["do"] == "mark"}


def test_expect_conformers_fails_the_run_when_none_were_made():
    from types import SimpleNamespace

    from openchem.app.debug_drive import _Driver

    molecule = SimpleNamespace(conformers=[])
    window = SimpleNamespace(
        _session=SimpleNamespace(project=SimpleNamespace(find_molecule=lambda uuid: molecule)),
        _property_panel=SimpleNamespace(_selected_molecule_uuid="u"),
    )
    driver = _Driver(window, [])
    driver._do_expect_conformers({"min": 1, "tag": "t"})
    assert driver._assertions[-1]["ok"] is False
    molecule.conformers = [object()]
    driver._do_expect_conformers({"min": 1, "tag": "t"})
    assert driver._assertions[-1]["ok"] is True
