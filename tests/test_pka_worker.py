"""The persistent pKa sidecar (`chem/pka_worker.py`) and the runner's `--serve` mode.

Two kinds of test, because the new complexity is the process lifecycle and a mock
cannot show that. A FAKE runner script speaks the real protocol over REAL pipes and
can be told, per request, to misbehave. A STUB `pkasolver` package puts the real
`pka_runner.py --serve` loop under test without torch.

The suite runs with `OPENCHEM_PKA_WORKER=0` (`tests/conftest.py`), so every test that
goes through `compute_pka` here enables the worker explicitly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem import pka_providers as P
from openchem.chem import pka_worker as W

psutil = pytest.importorskip("psutil")

#: A child that speaks the worker's protocol and misbehaves on cue. The SMILES in a
#: request is the instruction: `ok`, `slow:<s>`, `sleep`, `exit`, `ok_then_exit`,
#: `badjson`, `wrongid`, `error`, `noise`, `stderr`; anything else answers `ok` (so a
#: real SMILES works through `compute_pka`). Without `--serve` it is a one-shot run.
FAKE_RUNNER = r'''
import json, os, sys, time

def payload(rid):
    return {"request_id": rid, "worker_pid": os.getpid(), "pkasolver_version": "fake",
            "pkas": [{"pka": 4.2, "atom_idx": 1, "stddev": 0.1, "site_smiles": "",
                      "protonated_smiles": "", "deprotonated_smiles": ""}]}

if "--serve" not in sys.argv:
    out = payload(None); out.pop("request_id"); out["one_shot"] = True
    print(json.dumps(out))
    sys.exit(0)

if os.environ.get("FAKE_NO_READY"):
    print(json.dumps({"ready": False, "error": "no model"}), flush=True)
    sys.exit(1)
print(json.dumps({"ready": True, "pkasolver_version": "fake"}), flush=True)
for line in sys.stdin:
    req = json.loads(line)
    rid, mode = req["request_id"], req["smiles"]
    if mode == "sleep":
        time.sleep(600)
    elif mode.startswith("slow:"):
        time.sleep(float(mode.split(":")[1]))
        print(json.dumps(payload(rid)), flush=True)
    elif mode == "exit":
        os._exit(3)
    elif mode == "badjson":
        print("{oops", flush=True)
    elif mode == "wrongid":
        print(json.dumps(payload("not-" + rid)), flush=True)
    elif mode == "error":
        print(json.dumps({"request_id": rid, "error": "boom"}), flush=True)
    elif mode == "noise":
        print("a banner on stdout", flush=True)
        print(json.dumps(payload(rid)), flush=True)
    elif mode == "stderr":
        sys.stderr.write("x" * 300000)
        sys.stderr.flush()
        print(json.dumps(payload(rid)), flush=True)
    elif mode == "ok_then_exit":
        print(json.dumps(payload(rid)), flush=True)
        sys.stdout.close()
        os._exit(0)
    else:
        print(json.dumps(payload(rid)), flush=True)
'''


@pytest.fixture
def fake_runner(tmp_path) -> Path:
    path = tmp_path / "fake_runner.py"
    path.write_text(FAKE_RUNNER, encoding="utf-8")
    return path


@pytest.fixture
def make_worker():
    made: list[W.PkaWorker] = []

    def build(**kwargs) -> W.PkaWorker:
        kwargs.setdefault("request_timeout_s", 60.0)
        worker = W.PkaWorker(**kwargs)
        made.append(worker)
        return worker

    yield build
    for worker in made:
        worker.shutdown()


def ask(worker: W.PkaWorker, runner: Path, mode: str, key: tuple = ("k",)) -> dict:
    return worker.predict(key, [sys.executable, str(runner), "--serve"], mode, P._parse_runner_output)


def wait_until(condition, timeout: float = 10.0) -> bool:
    """Poll. A killed process is gone a moment after `kill()` returns (on Windows the
    launcher's job is torn down asynchronously), so "is gone" is always asserted this way."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


# -- laziness ------------------------------------------------------------------------------


def test_importing_the_providers_starts_no_thread_and_no_process():
    """Run in a FRESH interpreter, because this process has already imported them."""
    code = (
        "import threading\n"
        "import openchem.chem.pka_providers, openchem.chem.pka_worker as w\n"
        "print(w._worker, [t.name for t in threading.enumerate()])\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.stdout.strip() == "None ['MainThread']", out.stdout + out.stderr


def test_a_new_worker_spawns_nothing_until_asked(make_worker):
    worker = make_worker()
    assert worker.state is W.WorkerState.STOPPED
    assert worker.child_pid is None
    assert worker.stats["spawns"] == 0
    assert worker._thread is None


# -- the happy path and what it reuses -----------------------------------------------------


def test_three_requests_are_served_by_one_child_lifetime(make_worker, fake_runner):
    worker = make_worker()
    pids = {ask(worker, fake_runner, "ok")["worker_pid"] for _ in range(3)}

    assert len(pids) == 1
    assert worker.stats["spawns"] == 1
    assert worker.stats["requests"] == 3
    assert worker.stats["generation"] == 1
    assert worker.state is W.WorkerState.READY
    # `child_pid` is the process we started; on Windows a venv interpreter is a launcher whose
    # CHILD is the process that answers, so the two pids legitimately differ.
    assert worker.child_pid is not None
    # Both halves of the cost are recorded separately, as measured not subtracted.
    assert worker.stats["last_startup_s"] is not None and worker.stats["last_predict_s"] is not None


def test_the_reply_carries_no_request_id_so_it_equals_a_one_shot_payload(make_worker, fake_runner):
    payload = ask(make_worker(), fake_runner, "ok")
    assert "request_id" not in payload
    assert set(payload) == {"worker_pid", "pkasolver_version", "pkas"}


def test_stdout_noise_is_skipped_and_a_flooded_stderr_does_not_deadlock(make_worker, fake_runner):
    worker = make_worker(request_timeout_s=30.0)
    assert ask(worker, fake_runner, "noise")["pkasolver_version"] == "fake"
    # 300 KB on stderr is several times a pipe buffer: unread, the child would block.
    assert ask(worker, fake_runner, "stderr")["pkasolver_version"] == "fake"
    assert worker.stats["spawns"] == 1


# -- failures: what the caller sees and what happens to the child --------------------------


def test_an_error_reply_fails_that_request_and_keeps_the_warm_child(make_worker, fake_runner):
    worker = make_worker()
    first = ask(worker, fake_runner, "ok")["worker_pid"]
    with pytest.raises(RuntimeError, match="pkasolver failed: boom"):
        ask(worker, fake_runner, "error")

    assert worker.stats["last_failure"] == W.FailureKind.PREDICTION_FAILED.value
    assert ask(worker, fake_runner, "ok")["worker_pid"] == first, "one bad molecule must not cost the warm model"


def test_a_crash_fails_the_current_request_and_the_next_one_starts_a_new_generation(make_worker, fake_runner):
    worker = make_worker()
    first = ask(worker, fake_runner, "ok")["worker_pid"]
    with pytest.raises(RuntimeError, match="produced no usable output"):
        ask(worker, fake_runner, "exit")

    assert worker.stats["last_failure"] == W.FailureKind.CRASHED.value
    second = ask(worker, fake_runner, "ok")
    assert second["worker_pid"] != first
    assert worker.stats["generation"] == 2 and worker.stats["spawns"] == 2


def test_a_child_that_closes_its_output_after_one_reply_is_replaced_without_a_failed_request(
    make_worker, fake_runner
):
    """The child died while idle. The next request has not been tried on it yet, so
    replacing it is not the retry the worker refuses to do."""
    worker = make_worker()
    first = ask(worker, fake_runner, "ok_then_exit")["worker_pid"]
    assert wait_until(lambda: not psutil.pid_exists(first))

    assert ask(worker, fake_runner, "ok")["worker_pid"] != first


def test_a_timeout_fails_the_request_kills_the_child_and_the_next_one_starts_clean(make_worker, fake_runner):
    worker = make_worker(request_timeout_s=1.5)
    first = ask(worker, fake_runner, "ok")["worker_pid"]
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="timed out after 1.5s"):
        ask(worker, fake_runner, "sleep")

    assert time.monotonic() - started < 10
    assert wait_until(lambda: not psutil.pid_exists(first)), "the timed-out child must be killed"
    assert wait_until(lambda: worker.stats["last_failure"] == W.FailureKind.TIMEOUT.value)
    assert ask(worker, fake_runner, "ok")["worker_pid"] != first


def test_a_garbled_reply_is_a_protocol_failure_that_ends_the_child(make_worker, fake_runner):
    worker = make_worker()
    first = ask(worker, fake_runner, "ok")["worker_pid"]
    with pytest.raises(RuntimeError, match="unreadable reply"):
        ask(worker, fake_runner, "badjson")

    assert wait_until(lambda: not psutil.pid_exists(first))
    assert ask(worker, fake_runner, "ok")["worker_pid"] != first


def test_a_reply_to_the_wrong_request_is_a_protocol_failure_that_ends_the_child(make_worker, fake_runner):
    worker = make_worker()
    first = ask(worker, fake_runner, "ok")["worker_pid"]
    with pytest.raises(RuntimeError, match="expected"):
        ask(worker, fake_runner, "wrongid")

    assert wait_until(lambda: not psutil.pid_exists(first))
    assert worker.stats["last_failure"] == W.FailureKind.PROTOCOL_FAILED.value


def test_a_sidecar_that_cannot_load_its_model_fails_the_request_with_its_reason(
    make_worker, fake_runner, monkeypatch
):
    monkeypatch.setenv("FAKE_NO_READY", "1")
    worker = make_worker()
    with pytest.raises(RuntimeError, match="pkasolver failed: no model"):
        ask(worker, fake_runner, "ok")

    assert worker.stats["last_failure"] == W.FailureKind.START_FAILED.value
    assert worker.child_pid is None
    monkeypatch.delenv("FAKE_NO_READY")
    assert ask(worker, fake_runner, "ok")["pkasolver_version"] == "fake"


def test_a_missing_interpreter_is_reported_in_the_one_shot_paths_words(make_worker, fake_runner):
    worker = make_worker()
    with pytest.raises(RuntimeError, match="Could not run the configured pkasolver interpreter"):
        worker.predict(("k",), ["/no/such/python", str(fake_runner), "--serve"], "ok", P._parse_runner_output)


def test_a_finished_request_ignores_a_late_completion():
    """The race the timeout creates: the caller has already failed the request, then a
    reply lands. The second completion must be dropped, not raise."""
    request = W._Request(smiles="x", key=("k",), command=[], parse=P._parse_runner_output)
    W.PkaWorker._complete(request, error=RuntimeError("timed out"))
    W.PkaWorker._complete(request, result={"pkas": []})
    W.PkaWorker._complete(request, error=RuntimeError("again"))

    with pytest.raises(RuntimeError, match="timed out"):
        request.future.result(timeout=0)


# -- idle, configuration and stopping ------------------------------------------------------


def test_an_idle_child_exits_and_the_next_request_starts_another(make_worker, fake_runner):
    worker = make_worker(idle_timeout_s=0.4)
    first = ask(worker, fake_runner, "ok")["worker_pid"]
    threads_with_child = threading.active_count()

    # `child_pid` clears as the stop begins; STOPPED is when it has finished.
    assert wait_until(lambda: worker.state is W.WorkerState.STOPPED, timeout=15), "idle expiry must stop the child"
    assert worker.child_pid is None
    assert wait_until(lambda: not psutil.pid_exists(first))
    assert threading.active_count() <= threads_with_child, "the stderr reader must not outlive its child"
    assert ask(worker, fake_runner, "ok")["worker_pid"] != first
    assert worker.stats["spawns"] == 2


def test_idle_is_measured_from_the_last_request_finishing(make_worker, fake_runner):
    worker = make_worker(idle_timeout_s=2.0)
    first = ask(worker, fake_runner, "ok")["worker_pid"]
    for _ in range(3):  # keep it busy for longer than one idle period
        time.sleep(0.9)
        assert ask(worker, fake_runner, "ok")["worker_pid"] == first


def test_a_changed_configuration_stops_the_old_child_before_the_new_one_serves(make_worker, fake_runner):
    worker = make_worker()
    old = ask(worker, fake_runner, "ok", key=("A",))["worker_pid"]
    new = ask(worker, fake_runner, "ok", key=("B",))["worker_pid"]

    assert new != old
    assert wait_until(lambda: not psutil.pid_exists(old)), "never two sidecars across a reconfiguration"
    assert worker.stats["spawns"] == 2


def test_an_in_flight_request_finishes_under_the_configuration_it_was_submitted_with(
    make_worker, fake_runner
):
    worker = make_worker()
    results: dict[str, dict] = {}

    def slow_under_a():
        results["a"] = ask(worker, fake_runner, "slow:1.0", key=("A",))

    thread = threading.Thread(target=slow_under_a)
    thread.start()
    assert wait_until(lambda: worker.state is W.WorkerState.BUSY)
    results["b"] = ask(worker, fake_runner, "ok", key=("B",))  # queued behind it
    thread.join(timeout=30)

    assert results["a"]["worker_pid"] != results["b"]["worker_pid"]
    assert worker.stats["spawns"] == 2


def test_stop_child_ends_the_process_and_leaves_the_worker_usable(make_worker, fake_runner):
    worker = make_worker()
    first = ask(worker, fake_runner, "ok")["worker_pid"]
    worker.stop_child()

    assert worker.child_pid is None and not psutil.pid_exists(first)
    assert ask(worker, fake_runner, "ok")["worker_pid"] != first


# -- shutdown ------------------------------------------------------------------------------


def test_shutdown_before_anything_started_spawns_nothing_and_is_safe_twice(make_worker, fake_runner):
    worker = make_worker()
    worker.shutdown()
    worker.shutdown()

    assert worker.stats["spawns"] == 0
    with pytest.raises(RuntimeError, match="shut down"):
        ask(worker, fake_runner, "ok")


def test_shutdown_wakes_an_idle_worker_at_once_and_leaves_no_sidecar(make_worker, fake_runner):
    worker = make_worker(idle_timeout_s=120.0)
    pid = ask(worker, fake_runner, "ok")["worker_pid"]
    thread = worker._thread

    started = time.monotonic()
    worker.shutdown()

    assert time.monotonic() - started < 10, "must not sleep out the 120 s idle timeout"
    assert not thread.is_alive()
    assert wait_until(lambda: not psutil.pid_exists(pid))
    worker.shutdown()  # twice


def test_shutdown_during_a_request_fails_that_request_and_the_ones_queued_behind_it(
    make_worker, fake_runner
):
    worker = make_worker(request_timeout_s=120.0)
    ask(worker, fake_runner, "ok")
    errors: list[BaseException] = []

    def run(mode: str) -> None:
        try:
            ask(worker, fake_runner, mode)
        except BaseException as exc:  # noqa: BLE001 - the point is to see which one
            errors.append(exc)

    busy = threading.Thread(target=run, args=("sleep",))
    busy.start()
    assert wait_until(lambda: worker.state is W.WorkerState.BUSY)
    queued = threading.Thread(target=run, args=("ok",))
    queued.start()
    time.sleep(0.2)

    worker.shutdown()
    busy.join(timeout=20)
    queued.join(timeout=20)

    assert not busy.is_alive() and not queued.is_alive(), "no caller may be left waiting"
    assert worker.stats["spawns"] == 1, "a request queued before shutdown must not start a new sidecar"
    assert len(errors) == 2 and all(isinstance(e, RuntimeError) and "shut down" in str(e) for e in errors)


def test_no_sidecar_survives_the_worker(make_worker, fake_runner):
    """The hard lifecycle assertion: stopped means no pKa child process."""
    worker = make_worker()
    pid = ask(worker, fake_runner, "ok")["worker_pid"]
    worker.shutdown()

    assert wait_until(lambda: not psutil.pid_exists(pid))
    assert worker.child_pid is None


# -- compute_pka through the worker --------------------------------------------------------


@pytest.fixture
def worker_enabled(monkeypatch, fake_runner):
    monkeypatch.setattr(P, "PERSISTENT_WORKER_ENABLED", True)
    monkeypatch.setattr(P, "_RUNNER", fake_runner)
    P.clear_pka_cache()
    W.shutdown_worker()
    yield
    W.shutdown_worker()
    P.clear_pka_cache()


def test_compute_pka_caches_per_structure_and_reuses_one_sidecar_for_new_ones(worker_enabled):
    """The three paths, separately: a cache hit spawns nothing, a new structure on a warm
    worker spawns nothing, and the first request of all starts the one sidecar."""
    worker = W.get_worker()
    assert worker.stats["spawns"] == 0

    P.compute_pka(Chem.MolFromSmiles("CC(=O)O"), sys.executable)
    assert worker.stats["spawns"] == 1 and worker.stats["requests"] == 1

    P.compute_pka(Chem.MolFromSmiles("CC(=O)O"), sys.executable)  # same structure: cache
    assert worker.stats["requests"] == 1

    P.compute_pka(Chem.MolFromSmiles("NCC(=O)O"), sys.executable)  # new structure: warm
    assert worker.stats["spawns"] == 1 and worker.stats["requests"] == 2


def test_use_cache_false_stays_one_shot_and_leaves_the_worker_alone(worker_enabled):
    worker = W.get_worker()
    P.compute_pka(Chem.MolFromSmiles("CC(=O)O"), sys.executable)
    pid, requests = worker.child_pid, worker.stats["requests"]

    # The fake runner marks a one-shot run in its payload, which `compute_pka` does not
    # surface, so observe the route: the worker saw no request and was not restarted.
    calls = []
    real_run = P.subprocess.run

    def spy(*args, **kwargs):
        calls.append(args[0])
        return real_run(*args, **kwargs)

    P.subprocess.run = spy
    try:
        P.compute_pka(Chem.MolFromSmiles("CC(=O)O"), sys.executable, use_cache=False)
    finally:
        P.subprocess.run = real_run

    assert len(calls) == 1 and "--serve" not in calls[0]
    assert worker.stats["requests"] == requests and worker.child_pid == pid


def test_the_one_shot_and_worker_routes_return_the_same_predictions(worker_enabled):
    mol = Chem.MolFromSmiles("CC(=O)O")
    via_worker = P.compute_pka(mol, sys.executable)
    via_one_shot = P.compute_pka(mol, sys.executable, use_cache=False)

    assert via_worker == via_one_shot


def test_switching_the_worker_off_restores_the_one_process_per_structure_route(monkeypatch, fake_runner):
    monkeypatch.setattr(P, "PERSISTENT_WORKER_ENABLED", False)
    monkeypatch.setattr(P, "_RUNNER", fake_runner)
    P.clear_pka_cache()
    W.shutdown_worker()

    P.compute_pka(Chem.MolFromSmiles("CC(=O)O"), sys.executable)

    assert W._worker is None, "the one-shot route must not even create a worker"
    P.clear_pka_cache()


# -- the real runner's --serve loop, on a stub pkasolver -----------------------------------

STUB_PKASOLVER = {
    "pkasolver/__init__.py": (
        "__version__ = 'stub-1'\n"
        "def run_with_mol_list(*a, **k):\n    return []\n"
    ),
    "pkasolver/query.py": (
        "import os, sys\n"
        "from types import SimpleNamespace\n"
        "from rdkit import Chem\n"
        "def _call_dimorphite_dl(*a, **k):\n    return []\n"
        "def calculate_microstate_pka_values(mol):\n"
        "    # What pkasolver's dependencies do: banners on stdout, from Python AND from native code.\n"
        "    print('BANNER from print')\n"
        "    os.write(1, b'BANNER from a native write\\n')\n"
        "    if mol.GetNumAtoms() == 3:\n"
        "        raise ValueError('three atoms are unlucky')\n"
        "    return [SimpleNamespace(pka=4.76, reaction_center_idx=3, pka_stddev=0.2,\n"
        "                            ph7_mol=mol, protonated_mol=mol, deprotonated_mol=mol)]\n"
    ),
}


@pytest.fixture
def stub_pkasolver(tmp_path, monkeypatch) -> Path:
    for relative, text in STUB_PKASOLVER.items():
        target = tmp_path / "stub" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "stub") + os.pathsep + os.environ.get("PYTHONPATH", ""))
    return tmp_path / "stub"


def test_the_real_serve_loop_answers_over_a_protocol_that_banners_cannot_reach(stub_pkasolver, make_worker):
    worker = make_worker(request_timeout_s=120.0)
    command = W.serve_command(sys.executable, str(P._RUNNER))

    first = worker.predict(("k",), command, "CC(=O)O", P._parse_runner_output)
    second = worker.predict(("k",), command, "NCC(=O)O", P._parse_runner_output)

    assert first["pkasolver_version"] == "stub-1"
    assert first["pkas"][0]["pka"] == 4.76 and first["pkas"][0]["atom_idx"] == 3
    assert second["pkas"][0]["site_smiles"], "microstates are tagged exactly as in the one-shot run"
    assert worker.stats["spawns"] == 1, "banners on stdout must not have broken or restarted anything"


def test_the_real_serve_loop_survives_a_bad_molecule_and_a_failing_prediction(stub_pkasolver, make_worker):
    worker = make_worker(request_timeout_s=120.0)
    command = W.serve_command(sys.executable, str(P._RUNNER))
    worker.predict(("k",), command, "CC(=O)O", P._parse_runner_output)
    pid = worker.child_pid

    with pytest.raises(RuntimeError, match="Could not parse SMILES"):
        worker.predict(("k",), command, "this is not smiles", P._parse_runner_output)
    with pytest.raises(RuntimeError, match="ValueError: three atoms are unlucky"):
        worker.predict(("k",), command, "CCC", P._parse_runner_output)

    assert worker.child_pid == pid, "neither failure may cost the warm model"
    assert worker.predict(("k",), command, "CC(=O)O", P._parse_runner_output)["pkas"]


def test_the_real_serve_loop_and_the_real_one_shot_run_give_the_same_payload(stub_pkasolver, make_worker):
    """The equivalence the whole change rests on, on the stub: one `predict`, two routes."""
    worker = make_worker(request_timeout_s=120.0)
    smiles = "CC(=O)Oc1ccccc1C(=O)O"
    via_worker = worker.predict(
        ("k",), W.serve_command(sys.executable, str(P._RUNNER)), smiles, P._parse_runner_output
    )
    via_one_shot = P._run_one_shot(sys.executable, smiles)

    assert via_worker == via_one_shot


def test_the_serve_loop_ends_when_its_stdin_closes_so_a_dead_app_cannot_orphan_it(stub_pkasolver):
    proc = subprocess.Popen(
        [sys.executable, str(P._RUNNER), "--serve"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    try:
        assert json.loads(proc.stdout.readline())["ready"] is True
        proc.stdin.close()
        assert proc.wait(timeout=60) == 0
    finally:
        if proc.poll() is None:
            proc.kill()


def test_a_malformed_request_line_is_an_error_reply_not_a_crash(stub_pkasolver):
    proc = subprocess.Popen(
        [sys.executable, str(P._RUNNER), "--serve"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    try:
        assert json.loads(proc.stdout.readline())["ready"] is True
        proc.stdin.write("this is not json\n")
        proc.stdin.flush()
        reply = json.loads(proc.stdout.readline())
        assert reply["request_id"] is None and "malformed request" in reply["error"]
        proc.stdin.write(json.dumps({"request_id": "1:1", "smiles": "CC(=O)O"}) + "\n")
        proc.stdin.flush()
        assert json.loads(proc.stdout.readline())["request_id"] == "1:1"
    finally:
        proc.kill()
