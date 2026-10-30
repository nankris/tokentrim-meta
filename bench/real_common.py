"""Shared helpers for REAL Meta Model API runs (spend-capped; no secrets written)."""
import fcntl
import json
import os
from pathlib import Path
import tempfile
import threading

from tokentrim.cost import CostModel
from tokentrim.guard import SpendCapExceeded, SpendGuard

CONTRIB = "meta/muse-spark-1.3-contributor"
STANDARD = "meta/muse-spark-1.3"
WONDER = "meta/muse-wonder-1.0"
GLOBAL_CAP_USD = 0.50  # first (2026-10-30 v2) run; v3 runs pass their own caps


def make_guard(out_dir: Path, per_task_usd: float = 0.10, max_steps: int = 40) -> SpendGuard:
    """One persisted ledger for the whole real run; every script shares it and the $0.50 cap."""
    return SpendGuard(per_task_usd=per_task_usd, global_usd=GLOBAL_CAP_USD, max_steps=max_steps,
                      ledger_path=out_dir / "spend_ledger.json")


class SharedLedger:
    """Thread-safe persisted ledger with reservations, so concurrent runs can never overshoot.

    ``cap_usd`` is the hard ceiling on the ledger total (all scripts of one run share the file);
    ``run_cap_usd`` additionally limits how much this process may add (e.g. the $3 route pilot).
    A call reserves its worst-case projected cost before it is sent and releases it on record.
    """
    def __init__(self, path: Path, cap_usd: float, run_cap_usd: float | None = None):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.total = 0.0
        if self.path.exists():
            self.total = float(json.loads(self.path.read_text(encoding="utf-8")).get("global_usd", 0))
        self.start = self.total
        self.cap = cap_usd
        self.run_cap = run_cap_usd
        self.reserved = 0.0
        self.mine = 0.0

    def _file_total(self):
        if self.path.exists():
            return float(json.loads(self.path.read_text(encoding="utf-8")).get("global_usd", 0))
        return 0.0

    def _flock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = open(self.path.with_suffix(".lock"), "w")
        fcntl.flock(stream, fcntl.LOCK_EX)
        return stream

    def reserve(self, usd: float):
        with self.lock, self._flock():
            self.total = self._file_total()  # include spend by other processes sharing the ledger
            if self.total + self.reserved + usd > self.cap:
                raise SpendCapExceeded("global cap tripped")
            if self.run_cap is not None and self.mine + self.reserved + usd > self.run_cap:
                raise SpendCapExceeded("global cap tripped (this run's sub-cap)")
            self.reserved += usd

    def commit(self, reserved: float, actual: float):
        with self.lock, self._flock():
            self.reserved = max(0.0, self.reserved - reserved)
            self.total = self._file_total() + actual
            self.mine += actual
            fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".ledger-", text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump({"global_usd": self.total}, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, self.path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)


class TaskGuard:
    """SpendGuard-compatible per-run guard backed by a SharedLedger (one instance per worker run)."""
    def __init__(self, ledger: SharedLedger, per_task_usd: float, max_steps: int = 40):
        self.ledger, self.per_task_usd, self.max_steps = ledger, per_task_usd, max_steps
        self.task_id, self.task_spend, self.steps, self._pending = None, 0.0, 0, 0.0

    @property
    def global_spend(self):
        return self.ledger.total

    @property
    def global_usd(self):
        return self.ledger.cap

    def start_task(self, task_id):
        self.task_id, self.task_spend, self.steps = str(task_id), 0.0, 0

    def check(self, projected_usd):
        if self.steps >= self.max_steps:
            raise SpendCapExceeded("max_steps cap tripped")
        if self.task_spend + projected_usd > self.per_task_usd:
            raise SpendCapExceeded("per-task cap tripped")
        self.ledger.reserve(projected_usd)
        self._pending = projected_usd

    def record(self, actual_usd):
        self.ledger.commit(self._pending, actual_usd)
        self._pending = 0.0
        self.task_spend += actual_usd
        self.steps += 1

    def release(self):
        """Release a reservation whose call raised before usage was recorded."""
        if self._pending:
            self.ledger.commit(self._pending, 0.0)
            self._pending = 0.0


def costs() -> CostModel:
    return CostModel()


def write_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
