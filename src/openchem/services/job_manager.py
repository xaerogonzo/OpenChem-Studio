from __future__ import annotations


class JobManager:
    """Shared registry of in-flight async jobs, keyed by (kind, key).

    Not a scheduling engine -- ConformerService/DockingService/
    QuantumChemistryService each keep their own QRunnable/QProcess
    mechanics untouched. This only answers "is a job with this key already
    running," giving every caller the same single-flight guard
    QuantumChemistryService's own `_active_jobs` dict almost provided but
    didn't actually check before overwriting (see its request_calculation).
    `kind` namespaces per service ("conformer", "docking",
    "quantum_chemistry") so two services can never collide on the same key
    by accident.
    """

    def __init__(self) -> None:
        self._active: set[tuple[str, str]] = set()

    def try_start(self, kind: str, key: str) -> bool:
        """Registers (kind, key) as active and returns True, unless it's
        already active, in which case this is a no-op and returns False."""
        job_key = (kind, key)
        if job_key in self._active:
            return False
        self._active.add(job_key)
        return True

    def finish(self, kind: str, key: str) -> None:
        self._active.discard((kind, key))

    def is_active(self, kind: str, key: str) -> bool:
        return (kind, key) in self._active
