"""A persistent pkasolver sidecar: pay the model load once, not once per structure.

WHY THIS EXISTS, MEASURED 2026-10-08 (tree a3e64f5c, before this module). A
fresh `pka_runner.py` process spent ~2.2-2.5 s loading pkasolver's 50-model
ensemble plus ~0.8 s starting and exiting, and 0.33-1.19 s on the prediction
itself (three cold processes; `benchmarks/perf/results/followup-2026-10-08/step0`).
So a NEW structure cost 3-5 s of which under a third was prediction. The very
first spawn of a session took 31 s, which is the file cache being cold and is
NOT something a worker removes -- it pays that once per worker lifetime, as the
first spawn always did. (The census's "8-38 s per call" was that cold start.)

THREE DIFFERENT "FAST" PATHS, WHICH THE REPORTS MUST NOT COLLAPSE:

    same structure, any pH   cache hit (`pka_providers._PAYLOADS`; pH is not in
                             its key) -- this module is never reached
    new structure, worker up warm: the prediction only
    worker stopped           cold: spawn + model load + the prediction

THE SHAPE IS AN ACTOR, NOT A LOCK. One owner thread is the only code that reads
or writes the child's stdin/stdout, and it works through a request queue. A
stateful pipe has exactly one owner, so there is no lock to order, no second
thread to race a shutdown against, and no request that can interleave with
another's reply.

    caller -> request queue -> owner thread -> `pka_runner.py --serve` -> reply -> caller

**TIMEOUTS WORK BY KILLING THE CHILD, BECAUSE `readline()` CANNOT BE
INTERRUPTED.** Windows pipes have no `select`. The CALLER waits on a Future for
the deadline; on expiry it fails the request and terminates the process -- and
nothing else. It never closes a stream (the owner owns those). The owner's
blocked `readline()` then returns EOF and the owner recovers on its own, so it
can never hang on a dead child. A reply that arrives after its request timed
out finds a finished Future and is discarded.

**THERE IS NO TRANSPARENT RETRY.** A crash, EOF, protocol error or timeout fails
the request that met it, with the same `RuntimeError` text the one-shot path
gives, and the NEXT request starts a fresh child. Replaying the current request
would hide a runner that really crashes behind a second cold start.

`stop_child()` and `shutdown()` are different things: the first ends the
current process only (idle expiry, a crash, a changed configuration) and leaves
the worker usable; the second ends the worker.

This module is pure Python and Qt-free (`tests/test_layering.py`); the
application calls `shutdown_worker()` from `QApplication.aboutToQuit` and
`atexit` backs it up. A crashed application cannot orphan a sidecar either:
the child leaves its loop when its stdin closes.
"""

from __future__ import annotations

import atexit
import collections
import enum
import json
import logging
import queue
import subprocess
import threading
import time
from concurrent.futures import Future, InvalidStateError
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger("openchem.chemistry")

#: How long an idle sidecar is kept: measured from the COMPLETION of the last
#: request, not from the spawn or the submission. Two minutes is long enough to
#: cover a session of changing structures and short enough to give back the
#: ~310 MiB resident (~1.76 GiB committed) when the user has moved on.
IDLE_TIMEOUT_SECONDS = 120.0

#: The longest a single request may take, cold start included. The same
#: figure the one-shot path always used.
REQUEST_TIMEOUT_SECONDS = 300.0

#: How long `shutdown()` waits for the owner thread before killing the child.
_SHUTDOWN_JOIN_SECONDS = 5.0

#: A graceful stop (closing stdin) gets this long before the child is killed.
_GRACEFUL_STOP_SECONDS = 3.0

#: How many trailing stderr lines are kept to explain a crash. Enough for a Python
#: traceback; bounded so a chatty child cannot grow the parent's memory.
_STDERR_TAIL_LINES = 40

#: Windows only: do not flash a console window for the sidecar. `0` elsewhere,
#: because `Popen` rejects the flag off Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

ParseOutput = Callable[[str, str, int], dict]


def _kill(proc: subprocess.Popen) -> None:
    """Terminate `proc`. Safe on a process that has already gone.

    NOTE FOR WHOEVER IS TEMPTED TO KILL A TREE: on Windows a virtual environment's
    `python.exe` is a launcher whose CHILD is the real interpreter, so the pid we
    hold is not the pid that answers. That looked like an orphan risk and is not
    one, measured 2026-10-08 on both this project's venv and the pkasolver venv:
    the launcher runs its child in a kill-on-close job, so `Popen.kill()` ends both
    (the real process was gone within 1.5 s in each case). `taskkill /T` was written,
    found unnecessary and removed.
    """
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass


class WorkerState(enum.Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    BUSY = "busy"
    STOPPING = "stopping"


class FailureKind(enum.Enum):
    """Why the worker's last request did not succeed. Kept for diagnostics; callers
    only ever see the `RuntimeError` text."""

    START_FAILED = "start_failed"
    PROTOCOL_FAILED = "protocol_failed"
    PREDICTION_FAILED = "prediction_failed"
    TIMEOUT = "timeout"
    CRASHED = "crashed"
    SHUTDOWN = "shutdown"


class _Failure(Exception):
    """Raised inside the owner thread to fail the current request."""

    def __init__(self, kind: FailureKind, error: BaseException, *, stop_child: bool) -> None:
        super().__init__(str(error))
        self.kind = kind
        self.error = error
        self.stop_child = stop_child


@dataclass(eq=False)
class _Request:
    """One structure's question, carrying everything the owner needs so that a
    change of configuration while it waits cannot reroute it."""

    smiles: str
    #: The configuration this request was SUBMITTED under. The owner runs it on a
    #: child of exactly this key, and the caller stores the answer under it --
    #: never under whatever the key is by the time it finishes.
    key: tuple
    command: list[str]
    parse: ParseOutput
    future: Future = field(default_factory=Future)
    request_id: str = ""
    #: Set by the caller when it gives up, so the owner records the failure as a timeout
    #: rather than as the crash its kill looks like from the inside.
    timed_out: bool = False


#: The queue item that ends the owner thread. A sentinel rather than a flag the owner
#: polls, so shutdown wakes an idle owner at once instead of after its idle timeout.
_STOP = object()


class _StopChild:
    """A request to end the current child, run by the owner (the only thread allowed to
    touch the streams) and acknowledged through `done`."""

    def __init__(self) -> None:
        self.done = threading.Event()


class PkaWorker:
    """See the module docstring."""

    def __init__(
        self,
        *,
        idle_timeout_s: float = IDLE_TIMEOUT_SECONDS,
        request_timeout_s: float = REQUEST_TIMEOUT_SECONDS,
        spawn: Callable[[list[str]], subprocess.Popen] | None = None,
    ) -> None:
        self._idle_timeout_s = idle_timeout_s
        self._request_timeout_s = request_timeout_s
        self._spawn = spawn or self._default_spawn
        self._queue: queue.Queue = queue.Queue()
        #: Guards the fields the caller thread touches (`_proc`, `_current`,
        #: `_closed`, `_thread`). The streams are NOT under it: they are the
        #: owner's alone.
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._state = WorkerState.STOPPED
        self._proc: subprocess.Popen | None = None
        self._proc_key: tuple | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: collections.deque[str] = collections.deque(maxlen=_STDERR_TAIL_LINES)
        self._current: _Request | None = None
        self._generation = 0
        self._seq = 0
        self._last_done = time.monotonic()
        #: Diagnostics for the census and the tests. Written by the owner only.
        self.stats: dict[str, object] = {
            "spawns": 0, "requests": 0, "generation": 0, "pid": None,
            "last_startup_s": None, "last_predict_s": None, "last_failure": None,
        }

    # -- public --------------------------------------------------------------------------

    @property
    def state(self) -> WorkerState:
        return self._state

    @property
    def child_pid(self) -> int | None:
        proc = self._proc
        return proc.pid if proc is not None and proc.poll() is None else None

    def predict(self, key: tuple, command: list[str], smiles: str, parse: ParseOutput) -> dict:
        """The runner's payload for `smiles`, run on a child started with `command`
        (which must end in `--serve`). Raises `RuntimeError`, with the one-shot
        path's wording, on every failure. Blocks; safe from any thread."""
        request = _Request(smiles=smiles, key=key, command=list(command), parse=parse)
        with self._lock:
            if self._closed:
                raise RuntimeError("the pKa worker is shut down (the application is exiting)")
            self._ensure_owner_locked()
            self._queue.put(request)
        try:
            return request.future.result(timeout=self._request_timeout_s)
        except TimeoutError:
            error = RuntimeError(f"pkasolver timed out after {self._request_timeout_s:g}s")
            request.timed_out = True
            self._complete(request, error=error)
            self._kill_if_current(request)
            raise error from None

    def stop_child(self) -> None:
        """End the current sidecar only; the worker stays usable and the next request
        starts a fresh child. Runs on the owner thread (which alone may touch the
        streams) and returns once the child is gone."""
        with self._lock:
            if self._closed or self._thread is None or not self._thread.is_alive():
                return
            command = _StopChild()
            self._queue.put(command)
        command.done.wait(timeout=_SHUTDOWN_JOIN_SECONDS + 2 * _GRACEFUL_STOP_SECONDS)

    def shutdown(self) -> None:
        """End the worker for good. Idempotent and safe in every state: never
        started, idle, busy, crashed, or already stopped. Wakes an idle owner
        at once instead of letting it sleep out its idle timeout."""
        with self._lock:
            already = self._closed
            self._closed = True
            thread = self._thread
            proc = self._proc
        if not already:
            self._queue.put(_STOP)
        # A BUSY owner is blocked in readline(); killing the child is what wakes it.
        if proc is not None:
            _kill(proc)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=_SHUTDOWN_JOIN_SECONDS)
            if thread.is_alive():
                logger.warning("the pKa worker thread did not stop within %.0f s", _SHUTDOWN_JOIN_SECONDS)

    # -- owner thread --------------------------------------------------------------------

    def _ensure_owner_locked(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._owner_loop, name="pka-worker", daemon=True)
            self._thread.start()

    def _owner_loop(self) -> None:
        try:
            while True:
                try:
                    item = self._queue.get(timeout=self._wait_seconds())
                except queue.Empty:
                    # Idle expiry. Only the child goes: this thread stays a cheap
                    # controller and the next request simply starts a new one.
                    self._stop_child(graceful=True)
                    continue
                if item is _STOP:
                    break
                if isinstance(item, _StopChild):
                    self._stop_child(graceful=True)
                    item.done.set()
                    continue
                if item.future.done():
                    continue  # abandoned while queued: it already timed out
                if self._closed:
                    # Shutdown began after this was queued. Starting a child just to
                    # fail it would be absurd: fail it now, and the caller is released.
                    self._complete(item, error=RuntimeError("the pKa worker shut down before this request ran"))
                    continue
                self._serve(item)
                self._last_done = time.monotonic()
        finally:
            self._stop_child(graceful=False)
            self._fail_queued()

    def _wait_seconds(self) -> float | None:
        """How long the owner may sleep: until the idle deadline when a child is up,
        indefinitely when none is (a request or the stop sentinel wakes it)."""
        if self._proc is None:
            return None
        return max(0.0, self._last_done + self._idle_timeout_s - time.monotonic())

    def _fail_queued(self) -> None:
        """Requests still queued when the owner exits are failed, never abandoned
        to wait out their own timeouts."""
        error = RuntimeError("the pKa worker shut down before this request ran")
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if isinstance(item, _StopChild):
                item.done.set()
            elif item is not _STOP:
                self._complete(item, error=error)

    def _serve(self, request: _Request) -> None:
        with self._lock:
            self._current = request
        try:
            if self._proc is not None and (self._proc_key != request.key or self._proc.poll() is not None):
                # Never two sidecars across a reconfiguration; and a child that died while
                # idle is replaced here, before the request has been tried on it -- that is
                # not the retry the module refuses to do.
                self._stop_child(graceful=True)
            if self._proc is None:
                self._start_child(request)
            payload = self._round_trip(request)
        except _Failure as failure:
            kind = FailureKind.TIMEOUT if request.timed_out else failure.kind
            self.stats["last_failure"] = kind.value
            if failure.stop_child:
                self._stop_child(graceful=False)
            self._complete(request, error=failure.error)
        else:
            self._complete(request, result=payload)
        finally:
            with self._lock:
                self._current = None
            if self._state is WorkerState.BUSY:
                self._state = WorkerState.READY

    def _start_child(self, request: _Request) -> None:
        self._state = WorkerState.STARTING
        started = time.monotonic()
        try:
            proc = self._spawn(request.command)
        except OSError as exc:
            self._state = WorkerState.STOPPED
            raise _Failure(
                FailureKind.START_FAILED,
                RuntimeError(f"Could not run the configured pkasolver interpreter: {exc}"),
                stop_child=False,
            ) from exc
        self._generation += 1
        self._seq = 0
        self._stderr_tail.clear()
        with self._lock:
            self._proc = proc
            self._proc_key = request.key
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, args=(proc,), name="pka-worker-stderr", daemon=True
        )
        self._stderr_thread.start()
        self.stats.update(spawns=int(self.stats["spawns"]) + 1, generation=self._generation, pid=proc.pid)
        # A caller's timeout or a shutdown that landed while the process was being
        # spawned found no child to kill; honour it now rather than wait on the handshake.
        if request.future.done() or self._closed:
            raise _Failure(
                FailureKind.SHUTDOWN if self._closed else FailureKind.TIMEOUT,
                RuntimeError("the pKa worker shut down while the sidecar was starting" if self._closed
                         else "the request timed out while the sidecar was starting"),
                stop_child=True,
            )
        # The READY handshake is the real STARTING -> READY boundary: the model is
        # loaded when the child says so, not when the process exists.
        hello = self._read_json(request, expect_request_id=None)
        if not hello.get("ready"):
            raise _Failure(
                FailureKind.START_FAILED, self._parse_error(request, hello), stop_child=True
            )
        self.stats["last_startup_s"] = round(time.monotonic() - started, 3)
        self._state = WorkerState.READY

    def _round_trip(self, request: _Request) -> dict:
        self._state = WorkerState.BUSY
        self._seq += 1
        request.request_id = f"{self._generation}:{self._seq}"
        started = time.monotonic()
        proc = self._proc
        try:
            proc.stdin.write(json.dumps({"request_id": request.request_id, "smiles": request.smiles}) + "\n")
            proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise _Failure(
                FailureKind.CRASHED, self._eof_error(request), stop_child=True
            ) from exc
        reply = self._read_json(request, expect_request_id=request.request_id)
        self.stats["last_predict_s"] = round(time.monotonic() - started, 3)
        self.stats["requests"] = int(self.stats["requests"]) + 1
        reply.pop("request_id", None)
        try:
            # The ONE parser. It raises RuntimeError("pkasolver failed: ...") for an
            # error reply and returns the payload otherwise, exactly as for a one-shot run.
            return request.parse(json.dumps(reply), "", 0)
        except RuntimeError as exc:
            kind = FailureKind.PREDICTION_FAILED if "error" in reply else FailureKind.PROTOCOL_FAILED
            # A valid error reply leaves a warm child alone; an unusable one does not.
            raise _Failure(kind, exc, stop_child=kind is FailureKind.PROTOCOL_FAILED) from exc

    def _read_json(self, request: _Request, *, expect_request_id: str | None) -> dict:
        """The next protocol line. Lines that are not JSON objects are stdout noise
        and skipped; an object that does not parse, or answers a different request,
        is a protocol failure and ends the child."""
        proc = self._proc
        while True:
            try:
                line = proc.stdout.readline()
            except (OSError, ValueError) as exc:  # stream closed under us by a kill
                raise _Failure(FailureKind.CRASHED, self._eof_error(request), stop_child=True) from exc
            if line == "":
                kind = FailureKind.SHUTDOWN if self._closed else FailureKind.CRASHED
                error = (
                    RuntimeError("the pKa worker shut down while this request was running")
                    if self._closed else self._eof_error(request)
                )
                raise _Failure(kind, error, stop_child=True)
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise _Failure(
                    FailureKind.PROTOCOL_FAILED,
                    RuntimeError(f"pkasolver sent an unreadable reply: {line[:200]!r}"),
                    stop_child=True,
                ) from exc
            if expect_request_id is not None and message.get("request_id") != expect_request_id:
                raise _Failure(
                    FailureKind.PROTOCOL_FAILED,
                    RuntimeError(
                        f"pkasolver answered request {message.get('request_id')!r}, "
                        f"expected {expect_request_id!r}"
                    ),
                    stop_child=True,
                )
            return message

    def _eof_error(self, request: _Request) -> RuntimeError:
        """The one-shot path's own sentence for a child that produced nothing, so a
        crash reads the same whichever route found it."""
        proc = self._proc
        returncode = proc.poll() if proc is not None else None
        if returncode is None and proc is not None:
            try:
                returncode = proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                returncode = -1
        try:
            request.parse("", "\n".join(self._stderr_tail), -1 if returncode is None else returncode)
        except RuntimeError as exc:
            return exc
        return RuntimeError("pkasolver produced no usable output")

    @staticmethod
    def _parse_error(request: _Request, hello: dict) -> RuntimeError:
        try:
            request.parse(json.dumps({"error": hello.get("error", "the sidecar did not become ready")}), "", 1)
        except RuntimeError as exc:
            return exc
        return RuntimeError("pkasolver did not become ready")

    # -- child lifecycle -----------------------------------------------------------------

    @staticmethod
    def _default_spawn(command: list[str]) -> subprocess.Popen:
        return subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_NO_WINDOW,
        )

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        """Owns stderr. Without a reader a chatty child fills the pipe and blocks;
        with one, the tail is available to explain a crash. Ends at EOF, which the
        child's exit or a kill produces, so it cannot outlive the process."""
        try:
            for line in proc.stderr:
                self._stderr_tail.append(line.rstrip())
        except (OSError, ValueError):
            pass

    def _kill_if_current(self, request: _Request) -> None:
        """A caller's way to break a blocked read: terminate the process IF it is
        still working on this request. No stream is touched -- the owner closes them."""
        with self._lock:
            proc = self._proc if self._current is request else None
        if proc is not None:
            _kill(proc)

    def _stop_child(self, *, graceful: bool) -> None:
        """Owner-side: end the current child and release everything it held."""
        with self._lock:
            proc, self._proc, self._proc_key = self._proc, None, None
            stderr_thread, self._stderr_thread = self._stderr_thread, None
        if proc is None:
            self._state = WorkerState.STOPPED
            return
        self._state = WorkerState.STOPPING
        try:
            if graceful and proc.poll() is None:
                try:
                    proc.stdin.close()  # EOF is the child's cue to leave its loop
                    proc.wait(timeout=_GRACEFUL_STOP_SECONDS)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    pass
            _kill(proc)
            try:
                proc.wait(timeout=_GRACEFUL_STOP_SECONDS)
            except subprocess.TimeoutExpired:
                logger.warning("the pKa sidecar (pid %s) did not exit after being killed", proc.pid)
        finally:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except (OSError, ValueError):
                    pass
            if stderr_thread is not None:
                stderr_thread.join(timeout=2.0)
            self.stats["pid"] = None
            self._state = WorkerState.STOPPED

    @staticmethod
    def _complete(request: _Request, *, result: dict | None = None, error: BaseException | None = None) -> None:
        """Finish a request exactly once. A request that already timed out is
        terminal; a late answer or a second failure is dropped here."""
        try:
            if error is not None:
                request.future.set_exception(error)
            else:
                request.future.set_result(result)
        except InvalidStateError:
            pass


# -- the process-wide worker ---------------------------------------------------------------

_worker: PkaWorker | None = None
_worker_lock = threading.Lock()
_atexit_registered = False


def get_worker() -> PkaWorker:
    """The shared worker, created on first use -- importing this module, starting
    the application and opening a panel all spawn nothing."""
    global _worker, _atexit_registered
    with _worker_lock:
        if _worker is None:
            _worker = PkaWorker()
            if not _atexit_registered:
                atexit.register(shutdown_worker)
                _atexit_registered = True
        return _worker


def shutdown_worker() -> None:
    """End the shared worker, if there is one. Idempotent; a later `get_worker()`
    makes a new one (which is how tests start clean)."""
    global _worker
    with _worker_lock:
        worker, _worker = _worker, None
    if worker is not None:
        worker.shutdown()


def worker_snapshot() -> dict | None:
    """The shared worker's state and counters, or None when none has been created.
    For the census and the driven checks: it NEVER creates a worker, so asking does
    not change what is measured."""
    with _worker_lock:
        worker = _worker
    if worker is None:
        return None
    return {"state": worker.state.value, "child_pid": worker.child_pid, **worker.stats}


def serve_command(interpreter_path: str, runner_path: str) -> list[str]:
    """The command line that starts a sidecar in persistent mode."""
    return [str(interpreter_path), str(runner_path), "--serve"]


__all__ = [
    "IDLE_TIMEOUT_SECONDS", "REQUEST_TIMEOUT_SECONDS", "FailureKind", "PkaWorker", "WorkerState",
    "get_worker", "serve_command", "shutdown_worker", "worker_snapshot",
]
