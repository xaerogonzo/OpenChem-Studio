"""Resource census: launch the app on a drive script and watch it from OUTSIDE.

    uv run --no-sync --group perf python tools/perf_census.py list
    uv run --no-sync --group perf python tools/perf_census.py run startup-idle --runs 3
    uv run --no-sync --group perf python tools/perf_census.py controls
    uv run --no-sync --group perf python tools/perf_census.py report

**WHY THE SAMPLER IS A SEPARATE PROCESS.** An instrument inside the application
adds the cost it is trying to read. This tool owns a `psutil` thread in ITS OWN
process; the app gains nothing in a normal launch. What the sampler cannot see --
which widget, which timer, which cache -- the drive script's probes
(`openchem.app.drive_probes`) answer, at named checkpoints, and are never all on
for a baseline number.

**WHAT IT MEASURES, EXACTLY** (a number without its meaning is how a census lies):

* `rss` is the working set. `uss` is psutil's unique set size, labelled USS: it is
  NOT Windows "private bytes". USS is read every `uss_every` samples because it is
  slower than RSS.
* Tree RSS is a **non-unique sum** over the observed live process tree: Chromium
  helpers share pages, so the sum over-counts. USS is the honest total.
* CPU is derived from cumulative CPU seconds per process, so a process that exits
  keeps what it used. `cpu_pct_raw` is one core = 100; `cpu_pct_machine` divides by
  the logical CPU count and is the canonical idle metric.
* The process table is the OBSERVED live tree, not a perfect history: a child that
  lives less than one sampling interval can be missed. Cadence is per scenario.
* A memory SLOPE is a Theil-Sen fit over checkpoint medians, warm-up excluded, and
  is a "memory growth signal", not proof of a leak (see `interpret_growth`).

Outputs land in `benchmarks/perf/results/<scenario>/run-<k>/` (git-ignored): the
generated `script.json`, `samples.csv`, `processes.csv`, the app's `report.json`,
`summary.json` (environment, status, derived numbers) and the app's log.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:  # the `perf` group is not installed: the statistics below still import
    psutil = None  # type: ignore[assignment]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "benchmarks" / "perf"))
import scenarios as scenario_defs  # noqa: E402

SCHEMA_VERSION = 1
TOOL_VERSION = "1"
RESULTS = REPO / "benchmarks" / "perf" / "results"
SETTINGS_KEY = r"HKCU\Software\OpenChemStudio"

#: Declared BEFORE the controls ran. The synthetic signals are far above OS noise on
#: purpose: the goal is not to model the application, it is to prove each instrument
#: can tell an obvious planted signal from nothing.
NOOP_SLOPE_LIMIT_MIB_PER_ITERATION = 0.30
BYTES_SLOPE_TOLERANCE = (0.6, 1.4)  # fraction of the planted MiB/iteration


# -- environment ---------------------------------------------------------------------


def _run(cmd: list[str], timeout: float = 15.0) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return (out.stdout or out.stderr).strip()
    except Exception as exc:  # noqa: BLE001 - a missing tool is a fact about the machine
        return f"unavailable: {exc}"


def environment_snapshot() -> dict[str, Any]:
    """Everything needed to reconstruct the machine a number came from."""
    info: dict[str, Any] = {
        "commit": _run(["git", "rev-parse", "HEAD"]),
        "git_status_porcelain": _run(["git", "status", "--porcelain"]).splitlines(),
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "psutil": getattr(psutil, "__version__", None),
        "cpu_logical": psutil.cpu_count(logical=True) if psutil else None,
        "cpu_physical": psutil.cpu_count(logical=False) if psutil else None,
        "ram_gib": round(psutil.virtual_memory().total / 2**30, 1) if psutil else None,
        "java": _run(["java", "-version"]),
        "tool_version": TOOL_VERSION,
        "census_schema_version": SCHEMA_VERSION,
    }
    for module, attribute in (("PySide6", "__version__"), ("rdkit", "__version__"), ("openbabel", "__version__")):
        try:
            info[module] = getattr(__import__(module), attribute)
        except Exception:  # noqa: BLE001
            info[module] = None
    try:
        battery = psutil.sensors_battery() if psutil else None
        info["on_ac_power"] = None if battery is None else bool(battery.power_plugged)
    except Exception:  # noqa: BLE001
        info["on_ac_power"] = None
    if sys.platform == "win32":
        info["gpu"] = _run(["powershell", "-NoProfile", "-Command",
                            "(Get-CimInstance Win32_VideoController | "
                            "ForEach-Object { $_.Name + ' ' + $_.DriverVersion }) -join '; '"])
    return info


def settings_snapshot() -> str:
    """The app's settings store, as text, so a scenario can be shown NOT to have touched it."""
    if sys.platform != "win32":
        return ""
    return _run(["reg", "query", SETTINGS_KEY, "/s"])


# -- sampler -----------------------------------------------------------------------------


def classify(name: str, cmdline: str, is_root: bool) -> str:
    low = name.lower()
    joined = cmdline.lower()
    if "openchem.main" in joined:
        return "app"
    if "qtwebengineprocess" in low:
        return "QtWebEngine"
    if low.startswith("java"):
        return "Java/OPSIN"
    if "orca" in low:
        return "ORCA"
    if "vina" in low:
        return "Vina"
    return "launcher" if is_root else "other"


@dataclass
class _Seen:
    pid: int
    ppid: int
    started: float
    name: str
    klass: str
    first_seen: float
    last_seen: float
    peak_rss: int = 0
    peak_uss: int = 0
    cpu_s: float = 0.0
    process: Any = None


class Sampler(threading.Thread):
    """Samples the process tree under `root_pid` until `stop()`.

    Every psutil call tolerates a process disappearing: a dead child during a sample is
    normal, not a failed census. Processes are keyed by (pid, start time) so a reused
    PID cannot continue another process's series.
    """

    def __init__(self, root_pid: int, interval_s: float = 1.0, uss_every: int = 2) -> None:
        super().__init__(daemon=True)
        self.root_pid = root_pid
        self.interval_s = interval_s
        self.uss_every = max(1, uss_every)
        self.rows: list[dict[str, Any]] = []
        self.table: dict[tuple[int, float], _Seen] = {}
        self._stop = threading.Event()
        self.errors: list[str] = []
        self._logical = psutil.cpu_count(logical=True) or 1
        self._t0 = time.time()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            root = psutil.Process(self.root_pid)
        except psutil.Error as exc:
            self.errors.append(f"root gone: {exc}")
            return
        previous_cpu = 0.0
        previous_t = time.time()
        previous_app_cpu = 0.0
        tick = 0
        while not self._stop.is_set():
            started = time.time()
            read_uss = tick % self.uss_every == 0
            try:
                processes = [root] + root.children(recursive=True)
            except psutil.Error:
                processes = [root]
            agg = {"app": self._zero(), "kids": self._zero()}
            now = time.time()
            for proc in processes:
                self._read(proc, now, read_uss, agg)
            cum_cpu = sum(seen.cpu_s for seen in self.table.values())
            app_cpu = sum(seen.cpu_s for seen in self.table.values() if seen.klass == "app")
            dt = max(1e-6, now - previous_t)
            # The first sample has no interval behind it: its "rate" is the whole
            # process lifetime over a few milliseconds (205% on a first read).
            tree_raw = max(0.0, cum_cpu - previous_cpu) / dt * 100.0 if tick else 0.0
            app_raw = max(0.0, app_cpu - previous_app_cpu) / dt * 100.0 if tick else 0.0
            previous_cpu, previous_app_cpu, previous_t = cum_cpu, app_cpu, now
            row = {
                "epoch": round(now, 3), "elapsed_s": round(now - self._t0, 3),
                "tree_rss": agg["app"]["rss"] + agg["kids"]["rss"],
                "tree_uss": agg["app"]["uss"] + agg["kids"]["uss"] if read_uss else "",
                "app_rss": agg["app"]["rss"], "app_uss": agg["app"]["uss"] if read_uss else "",
                "kids_rss": agg["kids"]["rss"], "kids_uss": agg["kids"]["uss"] if read_uss else "",
                "app_threads": agg["app"]["threads"], "kids_threads": agg["kids"]["threads"],
                "app_handles": agg["app"]["handles"], "kids_handles": agg["kids"]["handles"],
                "child_count": agg["kids"]["n"],
                "tree_cpu_pct_raw": round(tree_raw, 2),
                "tree_cpu_pct_machine": round(tree_raw / self._logical, 3),
                "app_cpu_pct_raw": round(app_raw, 2),
                "app_cpu_pct_machine": round(app_raw / self._logical, 3),
                "tree_cpu_cum_s": round(cum_cpu, 3), "app_cpu_cum_s": round(app_cpu, 3),
            }
            self.rows.append(row)
            tick += 1
            self._stop.wait(max(0.0, self.interval_s - (time.time() - started)))

    @staticmethod
    def _zero() -> dict[str, int]:
        return {"rss": 0, "uss": 0, "threads": 0, "handles": 0, "n": 0}

    def _read(self, proc: psutil.Process, now: float, read_uss: bool, agg: dict[str, dict[str, int]]) -> None:
        try:
            with proc.oneshot():
                key = (proc.pid, proc.create_time())
                seen = self.table.get(key)
                if seen is None:
                    name = proc.name()
                    try:
                        cmd = " ".join(proc.cmdline())
                    except psutil.Error:
                        cmd = ""
                    seen = _Seen(proc.pid, proc.ppid(), key[1], name,
                                 classify(name, cmd, proc.pid == self.root_pid), now, now, process=proc)
                    self.table[key] = seen
                seen.last_seen = now
                rss = proc.memory_info().rss
                seen.peak_rss = max(seen.peak_rss, rss)
                times = proc.cpu_times()
                seen.cpu_s = float(times.user + times.system)
                threads = proc.num_threads()
                handles = proc.num_handles() if hasattr(proc, "num_handles") else 0
                uss = 0
                if read_uss:
                    uss = proc.memory_full_info().uss
                    seen.peak_uss = max(seen.peak_uss, uss)
        except psutil.Error:
            return
        bucket = agg["app"] if seen.klass in ("app", "launcher") else agg["kids"]
        bucket["rss"] += rss
        bucket["uss"] += uss
        bucket["threads"] += threads
        bucket["handles"] += handles
        bucket["n"] += 1

    def write(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        if self.rows:
            with (directory / "samples.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(self.rows[0]))
                writer.writeheader()
                writer.writerows(self.rows)
        with (directory / "processes.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["pid", "ppid", "name", "class", "started_epoch", "first_seen_epoch",
                             "last_seen_epoch", "observed_lifetime_s", "peak_rss", "peak_uss", "cpu_s"])
            for seen in sorted(self.table.values(), key=lambda s: s.first_seen):
                writer.writerow([seen.pid, seen.ppid, seen.name, seen.klass, round(seen.started, 3),
                                 round(seen.first_seen, 3), round(seen.last_seen, 3),
                                 round(seen.last_seen - seen.first_seen, 2), seen.peak_rss, seen.peak_uss,
                                 round(seen.cpu_s, 2)])


# -- statistics --------------------------------------------------------------------------------


def median_iqr(values: list[float]) -> dict[str, float]:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return {"median": float("nan"), "iqr": float("nan"), "min": float("nan"), "max": float("nan"), "n": 0}
    if len(clean) >= 4:
        quartiles = statistics.quantiles(clean, n=4, method="inclusive")
        iqr = quartiles[2] - quartiles[0]
    else:
        iqr = clean[-1] - clean[0]
    return {"median": statistics.median(clean), "iqr": iqr, "min": clean[0], "max": clean[-1], "n": len(clean)}


def theil_sen(points: list[tuple[float, float]]) -> float | None:
    """The median of every pairwise slope: one Windows memory spike cannot move it."""
    slopes = [
        (y2 - y1) / (x2 - x1)
        for i, (x1, y1) in enumerate(points) for (x2, y2) in points[i + 1:] if x2 != x1
    ]
    return statistics.median(slopes) if slopes else None


def window_median(rows: list[dict[str, Any]], key: str, start: float, end: float) -> float | None:
    values = [float(r[key]) for r in rows if start <= float(r["epoch"]) <= end and r[key] not in ("", None)]
    return statistics.median(values) if values else None


def window_cpu(rows: list[dict[str, Any]], key: str, start: float, end: float) -> dict[str, float] | None:
    """Mean and p95 of a CPU column over a window."""
    values = sorted(float(r[key]) for r in rows if start <= float(r["epoch"]) <= end)
    if not values:
        return None
    return {"mean": statistics.fmean(values), "p95": values[min(len(values) - 1, int(0.95 * len(values)))],
            "samples": len(values)}


MIB = 1024.0 * 1024.0


def interpret_growth(rss_mib_per_iter: float | None, objects_grew: bool, tracemalloc_grew: bool | None,
                     threshold: float = 0.15) -> str:
    """The reading rules, written down so a report cannot upgrade a signal into a verdict."""
    rss = rss_mib_per_iter is not None and rss_mib_per_iter > threshold
    if rss and objects_grew and tracemalloc_grew:
        return "strong memory-growth signal (objects + Python allocations + RSS)"
    if rss and objects_grew:
        return "memory-growth signal: objects and RSS grew; Python allocations not measured/flat"
    if objects_grew and not rss:
        return "retained Python objects without OS-level growth"
    if rss and not objects_grew:
        return "RSS growth without object growth: native/allocator/cache behaviour, needs other evidence"
    return "no growth signal above threshold"


# -- running --------------------------------------------------------------------------------------


def _script_hash(steps: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(steps, sort_keys=True).encode()).hexdigest()[:16]


def _kill_tree(pid: int) -> None:
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.Error:
        pass


def _app_python_command() -> list[str]:
    return [sys.executable, "-m", "openchem.main"]


def run_once(scenario: scenario_defs.Scenario, run_index: int, out_root: Path,
             environment: dict[str, Any], extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    run_dir = out_root / scenario.id / f"run-{run_index}"
    run_dir.mkdir(parents=True, exist_ok=True)
    script_path = run_dir / "script.json"
    script_path.write_text(json.dumps(scenario.steps, indent=1), encoding="utf-8")
    report_path = run_dir / "report.json"
    if report_path.exists():
        report_path.unlink()

    env = os.environ.copy()
    env.update({"OPENCHEM_DRIVE": str(script_path), "OPENCHEM_DRIVE_REPORT": str(report_path),
                "PYTHONUNBUFFERED": "1"})
    env.update(extra_env or {})
    settings_before = settings_snapshot()
    log = (run_dir / "app.log").open("w", encoding="utf-8")

    started = time.time()
    process = subprocess.Popen(_app_python_command(), cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
    sampler = Sampler(process.pid, scenario.cadence_s)
    sampler.start()
    status = "completed"
    try:
        process.wait(timeout=scenario.timeout_s)
    except subprocess.TimeoutExpired:
        status = "timeout"
        _kill_tree(process.pid)
    sampler.stop()
    sampler.join(timeout=10)
    _kill_tree(process.pid)
    log.close()
    sampler.write(run_dir)
    settings_after = settings_snapshot()

    report: dict[str, Any] = {}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = "probe_error"
    if status == "completed":
        if not report:
            status = "app_crashed"
        elif report.get("verdict") != "PASS":
            status = "drive_failed"
    if sampler.errors and status == "completed":
        status = "sampler_error"

    summary = {
        "census_schema_version": SCHEMA_VERSION,
        "scenario": scenario.id,
        "description": scenario.description,
        "kind": scenario.kind,
        "run": run_index,
        "status": status,
        "return_code": process.returncode,
        "wall_s": round(time.time() - started, 1),
        "script_sha256_16": _script_hash(scenario.steps),
        "cadence_s": scenario.cadence_s,
        "probes": scenario.probes,
        "gc_forced": scenario.forces_gc,
        "parameters": {**json.loads(json.dumps(scenario.parameters, default=list)),
                       "startup_settle_ms": scenario_defs.STARTUP_SETTLE_MS},
        "environment": environment,
        "settings_unchanged": settings_before == settings_after,
        "sampler_errors": sampler.errors,
        "samples": len(sampler.rows),
        "derived": derive(scenario, sampler, report, process.pid),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    return summary


# -- derived numbers -----------------------------------------------------------------------------------


def _process_lifetimes(sampler: Sampler) -> list[dict[str, Any]]:
    return [
        {"pid": s.pid, "name": s.name, "class": s.klass,
         "first_seen_s": round(s.first_seen - sampler._t0, 1),
         "observed_lifetime_s": round(s.last_seen - s.first_seen, 1),
         "peak_rss_mib": round(s.peak_rss / MIB, 1), "peak_uss_mib": round(s.peak_uss / MIB, 1)}
        for s in sorted(sampler.table.values(), key=lambda s: s.first_seen)
    ]


def derive(scenario: scenario_defs.Scenario, sampler: Sampler, report: dict[str, Any], root_pid: int) -> dict[str, Any]:
    rows = sampler.rows
    measurements = report.get("measurements", {}) if report else {}
    out: dict[str, Any] = {"processes": _process_lifetimes(sampler)}
    if not rows:
        return out
    root_seen = next((s for k, s in sampler.table.items() if k[0] == root_pid), None)
    ready = measurements.get("window_ready_epoch")
    if ready and root_seen:
        out["window_ready_latency_s"] = round(ready - root_seen.started, 2)
    out["peak"] = {
        "tree_rss_mib": round(max(float(r["tree_rss"]) for r in rows) / MIB, 1),
        "app_rss_mib": round(max(float(r["app_rss"]) for r in rows) / MIB, 1),
        "max_child_count": max(int(r["child_count"]) for r in rows),
        "app_threads": max(int(r["app_threads"]) for r in rows),
        "app_handles": max(int(r["app_handles"]) for r in rows),
    }
    out["marks"] = measurements.get("marks", [])
    if scenario.kind == "idle":
        out["idle"] = derive_idle(rows, ready or rows[0]["epoch"])
    elif scenario.kind == "panels":
        out["panels"] = derive_panels(rows, measurements)
    elif scenario.kind == "lifecycle":
        out["lifecycle"] = derive_lifecycle(scenario, rows, measurements)
    for key in ("loop_lag", "tracemalloc", "edit_burst", "cache_probe"):
        found = {k: v for k, v in measurements.items() if k.startswith(key)}
        if found:
            out[key] = found
    return out


def derive_idle(rows: list[dict[str, Any]], origin: float) -> dict[str, Any]:
    end = float(rows[-1]["epoch"])
    spans = {"plateau_10_20s": (origin + 10, origin + 20), "t60": (origin + 50, origin + 60),
             "last_30s": (end - 30, end)}
    rss = {name: window_median(rows, "app_rss", a, b) for name, (a, b) in spans.items()}
    uss = {name: window_median(rows, "app_uss", a, b) for name, (a, b) in spans.items()}
    out: dict[str, Any] = {
        "app_rss_mib": {k: None if v is None else round(v / MIB, 1) for k, v in rss.items()},
        "app_uss_mib": {k: None if v is None else round(v / MIB, 1) for k, v in uss.items()},
        "tree_cpu_pct_machine_after_30s": window_cpu(rows, "tree_cpu_pct_machine", origin + 30, end),
        "app_cpu_pct_machine_after_30s": window_cpu(rows, "app_cpu_pct_machine", origin + 30, end),
    }
    if rss["plateau_10_20s"] and rss["last_30s"]:
        out["rss_delta_plateau_to_end_mib"] = round((rss["last_30s"] - rss["plateau_10_20s"]) / MIB, 2)
    return out


def derive_panels(rows: list[dict[str, Any]], measurements: dict[str, Any]) -> dict[str, Any]:
    marks = {m["name"]: m["epoch"] for m in measurements.get("marks", [])}
    result: dict[str, Any] = {"ids": measurements.get("panel_cycle_ids", []), "per_panel": {}}
    ids = result["ids"]
    for index, panel in enumerate(ids):
        start, sample = marks.get(f"panel:{panel}:start"), marks.get(f"panel:{panel}:sample")
        following = marks.get(f"panel:{ids[index + 1]}:start") if index + 1 < len(ids) else marks.get("panel:end")
        if None in (start, sample, following):
            continue
        result["per_panel"][panel] = {
            "transition_tree_cpu_pct_machine": window_cpu(rows, "tree_cpu_pct_machine", start, sample),
            "steady_tree_cpu_pct_machine": window_cpu(rows, "tree_cpu_pct_machine", sample, following),
            "steady_app_cpu_pct_machine": window_cpu(rows, "app_cpu_pct_machine", sample, following),
            "app_rss_mib_at_steady": _mib(window_median(rows, "app_rss", sample, following)),
        }
    return result


def _mib(value: float | None) -> float | None:
    return None if value is None else round(value / MIB, 1)


def derive_lifecycle(scenario: scenario_defs.Scenario, rows: list[dict[str, Any]],
                     measurements: dict[str, Any]) -> dict[str, Any]:
    params = scenario.parameters
    warmup = int(params.get("warmup", 5))
    checkpoints = [0] + list(params.get("checkpoints", ()))
    marks = {m["name"]: m["epoch"] for m in measurements.get("marks", [])}
    series: list[dict[str, Any]] = []
    for iteration in checkpoints:
        stamp = marks.get(f"cp-{iteration}")
        if stamp is None:
            continue
        series.append({
            "iteration": iteration,
            "app_rss_mib": _mib(window_median(rows, "app_rss", stamp, stamp + 2.4)),
            "app_uss_mib": _mib(window_median(rows, "app_uss", stamp - 1.0, stamp + 3.0)),
            "tree_uss_mib": _mib(window_median(rows, "tree_uss", stamp - 1.0, stamp + 3.0)),
            "child_count": window_median(rows, "child_count", stamp, stamp + 2.4),
        })
    fit_points = [(p["iteration"], p["app_rss_mib"]) for p in series
                  if p["iteration"] >= warmup and p["app_rss_mib"] is not None]
    uss_points = [(p["iteration"], p["app_uss_mib"]) for p in series
                  if p["iteration"] >= warmup and p["app_uss_mib"] is not None]
    slope = theil_sen(fit_points)
    uss_slope = theil_sen(uss_points)
    census = {tag: v for tag, v in measurements.items() if tag.startswith("object_census[")}
    growth = object_growth(census, checkpoints, warmup)
    return {
        "series": series,
        "rss_slope_mib_per_iteration": None if slope is None else round(slope, 4),
        "uss_slope_mib_per_iteration": None if uss_slope is None else round(uss_slope, 4),
        "start_rss_mib": fit_points[0][1] if fit_points else None,
        "end_rss_mib": fit_points[-1][1] if fit_points else None,
        "high_water_rss_mib": max((p[1] for p in fit_points), default=None),
        "object_growth": growth,
        "reading": interpret_growth(uss_slope if uss_slope is not None else slope,
                                    bool(growth["monotonic_growers"]), None),
    }


def object_growth(census: dict[str, Any], checkpoints: list[int], warmup: int) -> dict[str, Any]:
    """Classes whose count rose monotonically across the post-warm-up checkpoints.

    A class is a CANDIDATE only for that, never merely for ending larger than it began:
    a cache fills once and plateaus, a leak keeps climbing.
    """
    ordered = [census.get(f"object_census[cp-{c}]") for c in checkpoints if c >= warmup]
    ordered = [c for c in ordered if c]
    if len(ordered) < 3:
        return {"monotonic_growers": {}, "note": "fewer than 3 post-warm-up census checkpoints"}
    growers: dict[str, list[int]] = {}
    for table in ("widgets", "qobject_wrappers"):
        names = set().union(*(c[table].keys() for c in ordered))
        for name in names:
            counts = [c[table].get(name, 0) for c in ordered]
            if all(b >= a for a, b in zip(counts, counts[1:])) and counts[-1] > counts[0]:
                growers[f"{table}:{name}"] = counts
    timers = [c["timers_active"] for c in ordered]
    return {"monotonic_growers": growers, "active_timers_by_checkpoint": timers,
            "widget_total_by_checkpoint": [c["widget_total"] for c in ordered],
            "qobject_wrappers_by_checkpoint": [c["qobject_wrappers_total"] for c in ordered]}


# -- controls --------------------------------------------------------------------------------------------


def check_controls(summaries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Each instrument against a signal planted at a known size, with limits declared above."""
    checks: list[dict[str, Any]] = []

    def get(name: str) -> dict[str, Any] | None:
        return summaries.get(name)

    noop = get("control-noop")
    if noop:
        slope = noop["derived"].get("lifecycle", {}).get("rss_slope_mib_per_iteration")
        checks.append({"control": "noop is flat", "measured_mib_per_iteration": slope,
                       "limit": NOOP_SLOPE_LIMIT_MIB_PER_ITERATION,
                       "pass": slope is not None and abs(slope) < NOOP_SLOPE_LIMIT_MIB_PER_ITERATION})
    planted = get("control-bytes")
    if planted:
        want = float(planted["parameters"].get("mib_per_iteration", 5.0))
        slope = planted["derived"].get("lifecycle", {}).get("rss_slope_mib_per_iteration")
        low, high = BYTES_SLOPE_TOLERANCE
        checks.append({"control": "planted bytes are seen by RSS", "planted_mib_per_iteration": want,
                       "measured_mib_per_iteration": slope,
                       "accepted_range": [low * want, high * want],
                       "pass": slope is not None and low * want <= slope <= high * want})
    widgets = get("control-widgets")
    if widgets:
        growth = widgets["derived"].get("lifecycle", {}).get("object_growth", {}).get("monotonic_growers", {})
        checks.append({"control": "retained QLabels are seen by the object census",
                       "growers": {k: v for k, v in growth.items() if "QLabel" in k},
                       "pass": any(k.endswith(":QLabel") for k in growth)})
    child = get("control-child")
    if child:
        seconds = float(child["parameters"].get("seconds", 2.0))
        python_children = [p for p in child["derived"]["processes"]
                           if p["class"] in ("other",) and p["name"].lower().startswith("python")]
        checks.append({"control": "a short-lived child is recorded", "children_observed": python_children,
                       "planted_lifetime_s": seconds, "pass": bool(python_children)})
    return checks


# -- command line -----------------------------------------------------------------------------------------


def _load_scenario(name: str, overrides: dict[str, Any]) -> scenario_defs.Scenario:
    builder = scenario_defs.REGISTRY.get(name)
    if builder is None:
        raise SystemExit(f"unknown scenario {name!r}; see `list`")
    return builder(**overrides)


def _parse_overrides(pairs: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        try:
            out[key] = json.loads(value)
        except json.JSONDecodeError:
            out[key] = value
    return out


def cmd_list(_: argparse.Namespace) -> int:
    for name in scenario_defs.REGISTRY:
        print(name)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    environment = environment_snapshot()
    if environment["git_status_porcelain"] and not args.allow_dirty:
        print("refusing: the source tree is dirty (the measured commit would not describe the "
              "code). Commit first, or pass --allow-dirty and say so in the report.", file=sys.stderr)
        return 2
    exit_code = 0
    for name in args.scenarios:
        overrides = _parse_overrides(args.set or [])
        scenario = _load_scenario(name, overrides)
        for run_index in range(1, args.runs + 1):
            summary = run_once(scenario, run_index, RESULTS, environment)
            print(f"{name} run {run_index}: {summary['status']} in {summary['wall_s']}s "
                  f"({summary['samples']} samples)")
            if summary["status"] != "completed":
                exit_code = 1
            if not summary["settings_unchanged"]:
                print("  !! the settings store changed during this run", file=sys.stderr)
                exit_code = 1
    return exit_code


def cmd_controls(args: argparse.Namespace) -> int:
    environment = environment_snapshot()
    summaries: dict[str, dict[str, Any]] = {}
    for name in ("control-noop", "control-bytes", "control-widgets", "control-child"):
        summaries[name] = run_once(_load_scenario(name, {}), 1, RESULTS, environment)
        print(f"{name}: {summaries[name]['status']}")
    checks = check_controls(summaries)
    (RESULTS / "controls.json").write_text(json.dumps(checks, indent=1), encoding="utf-8")
    for check in checks:
        print(("PASS " if check["pass"] else "FAIL ") + check["control"], json.dumps(
            {k: v for k, v in check.items() if k not in ("control", "pass")}))
    return 0 if checks and all(c["pass"] for c in checks) else 1


def cmd_report(args: argparse.Namespace) -> int:
    """Aggregate every run directory: median and IQR across runs, no app launch."""
    table: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(RESULTS.glob("*/run-*/summary.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))
        table.setdefault(summary["scenario"], []).append(summary)
    aggregate: dict[str, Any] = {}
    for scenario, runs in table.items():
        good = [r for r in runs if r["status"] == "completed"]
        entry: dict[str, Any] = {"runs": len(runs), "valid_runs": len(good),
                                 "statuses": [r["status"] for r in runs]}
        slopes = [r["derived"].get("lifecycle", {}).get("rss_slope_mib_per_iteration") for r in good]
        if any(s is not None for s in slopes):
            entry["rss_slope_mib_per_iteration"] = median_iqr([s for s in slopes if s is not None])
        latency = [r["derived"].get("window_ready_latency_s") for r in good]
        if any(v is not None for v in latency):
            entry["window_ready_latency_s"] = median_iqr([v for v in latency if v is not None])
        peak = [r["derived"].get("peak", {}).get("app_rss_mib") for r in good]
        if any(v is not None for v in peak):
            entry["peak_app_rss_mib"] = median_iqr([v for v in peak if v is not None])
        aggregate[scenario] = entry
    out = RESULTS / "aggregate.json"
    out.write_text(json.dumps(aggregate, indent=1), encoding="utf-8")
    print(json.dumps(aggregate, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list").set_defaults(func=cmd_list)
    run = sub.add_parser("run")
    run.add_argument("scenarios", nargs="+")
    run.add_argument("--runs", type=int, default=3)
    run.add_argument("--set", action="append", help="scenario parameter, e.g. --set iterations=10")
    run.add_argument("--allow-dirty", action="store_true")
    run.set_defaults(func=cmd_run)
    sub.add_parser("controls").set_defaults(func=cmd_controls)
    sub.add_parser("report").set_defaults(func=cmd_report)
    args = parser.parse_args(argv)
    RESULTS.mkdir(parents=True, exist_ok=True)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
