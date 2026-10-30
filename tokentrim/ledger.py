"""Persistent spend ledger with RESERVATIONS: no call is sent unless its worst case fits under the caps.

Before every metered call, ``reserve(usd)`` writes a reservation into the ledger file under an exclusive
``flock`` (atomic replace). The check counts the committed total PLUS every live reservation from every
process and thread, so concurrent workers cannot overshoot. A reservation stays held through retries of
the same call. ``commit(token, actual)`` swaps the reservation for the cost priced from the API ``usage``;
``release(token)`` drops it when the call failed before any usage was billed. Reservations left by a dead
process are discarded (pid check). Two caps: the job cap (whole ledger) and a per-run cap (``run_id``).

File: {"global_usd", "job_cap_usd", "runs": {run_id: usd}, "reservations": {token: {usd, run, pid}}};
an append-only ``<ledger>.events.jsonl`` logs each commit (amounts only; never content or secrets).
"""
import fcntl
import itertools
import json
import os
from pathlib import Path
import tempfile
import threading
import time

from .guard import SpendCapExceeded

_counter = itertools.count()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class SpendLedger:
    def __init__(self, path, job_cap_usd: float, run_cap_usd: float, run_id: str):
        self.path = Path(path)
        self.job_cap, self.run_cap, self.run_id = float(job_cap_usd), float(run_cap_usd), run_id
        self._lock = threading.Lock()
        self.calls = 0
        data = self._read()
        self.start_total = float(data.get("global_usd", 0.0))
        self.mine_at_start = float(data.get("runs", {}).get(run_id, 0.0))

    # -- file helpers (call with the flock held) --
    def _read(self) -> dict:
        if self.path.exists():
            text = self.path.read_text(encoding="utf-8")
            return json.loads(text) if text.strip() else {}
        return {}

    def _write(self, data: dict):
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".ledger-", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=1, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = open(self.path.with_suffix(".lock"), "w")
        fcntl.flock(stream, fcntl.LOCK_EX)
        return stream

    @staticmethod
    def _live(data: dict) -> dict:
        res = data.get("reservations") or {}
        return {k: v for k, v in res.items() if _alive(int(v.get("pid", 0)))}

    # -- public API --
    def total(self) -> float:
        return float(self._read().get("global_usd", 0.0))

    def mine(self) -> float:
        return float(self._read().get("runs", {}).get(self.run_id, 0.0))

    def reserve(self, usd: float) -> str:
        if usd < 0:
            raise ValueError("reservation must be nonnegative")
        with self._lock, self._locked():
            data = self._read()
            live = self._live(data)
            held = sum(v["usd"] for v in live.values())
            held_run = sum(v["usd"] for v in live.values() if v.get("run") == self.run_id)
            total = float(data.get("global_usd", 0.0))
            run_total = float(data.get("runs", {}).get(self.run_id, 0.0))
            if total + held + usd > self.job_cap + 1e-9:
                raise SpendCapExceeded(f"job cap ${self.job_cap:.2f} would be exceeded (spent ${total:.4f}, "
                                       f"reserved ${held:.4f}, this call worst case ${usd:.4f})")
            if run_total + held_run + usd > self.run_cap + 1e-9:
                raise SpendCapExceeded(f"run cap ${self.run_cap:.2f} would be exceeded (run spent "
                                       f"${run_total:.4f}, reserved ${held_run:.4f}, call ${usd:.4f})")
            token = f"{os.getpid()}-{next(_counter)}"
            live[token] = {"usd": usd, "run": self.run_id, "pid": os.getpid(), "t": round(time.time(), 1)}
            data["reservations"] = live
            data.setdefault("job_cap_usd", self.job_cap)
            self._write(data)
            return token

    def commit(self, token: str, actual: float, note: str = ""):
        with self._lock, self._locked():
            data = self._read()
            (data.get("reservations") or {}).pop(token, None)
            data["global_usd"] = float(data.get("global_usd", 0.0)) + actual
            data["job_cap_usd"] = self.job_cap
            runs = data.setdefault("runs", {})
            runs[self.run_id] = float(runs.get(self.run_id, 0.0)) + actual
            self._write(data)
            self.calls += 1
            with open(str(self.path) + ".events.jsonl", "a", encoding="utf-8") as events:
                events.write(json.dumps({"t": round(time.time(), 3), "run": self.run_id, "usd": actual,
                                         "note": note[:80]}) + "\n")

    def release(self, token: str):
        with self._lock, self._locked():
            data = self._read()
            if token in (data.get("reservations") or {}):
                data["reservations"].pop(token)
                self._write(data)

    def remaining(self) -> float:
        data = self._read()
        held = sum(v["usd"] for v in self._live(data).values())
        return min(self.job_cap - float(data.get("global_usd", 0)) - held,
                   self.run_cap - float(data.get("runs", {}).get(self.run_id, 0)) - held)

    def status(self) -> str:
        return (f"ledger ${self.total():.4f} / job cap ${self.job_cap:.2f}; run '{self.run_id}' "
                f"${self.mine():.4f} / run cap ${self.run_cap:.2f}")
