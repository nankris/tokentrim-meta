"""Persistent spend ledger with RESERVATIONS: no call is sent unless its worst case fits under the caps.

Before every metered call, ``reserve(usd)`` writes a reservation into the ledger file under an exclusive
``flock`` (atomic replace). The check counts the committed total PLUS every live reservation from every
process and thread, so concurrent workers cannot overshoot. A reservation stays held through retries of
the same call. ``commit(token, actual)`` swaps the reservation for the cost priced from the API ``usage``;
``release(token)`` drops it when the call failed before any usage was billed. Reservations left by a dead
process are discarded (pid check). Two caps: the job cap (whole ledger) and a per-run cap (``run_id``).

FAIL CLOSED: any ledger problem (corrupt or malformed file, lock timeout, disk/OS error, an earlier commit that
could not be written) raises ``LedgerUnavailable`` and no call is sent. A corrupt file is never overwritten. If a
billed call cannot be committed, its amount goes to ``<ledger>.unrecorded.jsonl`` (best effort) and the ledger
refuses every new reservation until a human reconciles and deletes that file. (Optimizer errors are different:
they fail OPEN in the gateway, which forwards the original request; that request still needs a reservation.)

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

from .guard import LedgerUnavailable, SpendCapExceeded

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
    def __init__(self, path, job_cap_usd: float, run_cap_usd: float, run_id: str, lock_timeout: float = 30.0):
        self.path = Path(path)
        self.job_cap, self.run_cap, self.run_id = float(job_cap_usd), float(run_cap_usd), run_id
        self.lock_timeout = float(lock_timeout)
        self._lock = threading.Lock()
        self.calls = 0
        self.poisoned = None  # reason string once a billed call could not be recorded
        data = self._read()
        self.start_total = float(data.get("global_usd", 0.0))
        self.mine_at_start = float(data.get("runs", {}).get(run_id, 0.0))

    # -- file helpers (call with the flock held) --
    def _read(self) -> dict:
        try:
            if not self.path.exists():
                return {}
            text = self.path.read_text(encoding="utf-8")
            data = json.loads(text) if text.strip() else {}
        except (OSError, ValueError) as exc:
            raise LedgerUnavailable(f"spend ledger unreadable ({type(exc).__name__}); refusing to send") from None
        if not isinstance(data, dict):
            raise LedgerUnavailable("spend ledger malformed (not an object); refusing to send")
        try:
            float(data.get("global_usd", 0.0))
            assert isinstance(data.get("runs", {}), dict) and isinstance(data.get("reservations") or {}, dict)
            for v in (data.get("reservations") or {}).values():
                float(v["usd"]), int(v.get("pid", 0))
            for v in data.get("runs", {}).values():
                float(v)
        except (AssertionError, TypeError, ValueError, KeyError, AttributeError):
            raise LedgerUnavailable("spend ledger malformed (bad field types); refusing to send") from None
        return data

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
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            stream = open(self.path.with_suffix(".lock"), "w")
        except OSError as exc:
            raise LedgerUnavailable(f"spend ledger lock unavailable ({type(exc).__name__})") from None
        deadline = time.monotonic() + self.lock_timeout
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return stream
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    stream.close()
                    raise LedgerUnavailable(f"spend ledger lock timeout after {self.lock_timeout:.1f}s") from None
                time.sleep(0.01)
            except OSError as exc:
                stream.close()
                raise LedgerUnavailable(f"spend ledger lock failed ({type(exc).__name__})") from None

    def _unrecorded_path(self):
        return Path(str(self.path) + ".unrecorded.jsonl")

    def _check_usable(self):
        if self.poisoned:
            raise LedgerUnavailable(f"spend ledger disabled: {self.poisoned}")
        try:
            pending = self._unrecorded_path().exists() and self._unrecorded_path().stat().st_size > 0
        except OSError:
            pending = True
        if pending:
            raise LedgerUnavailable(f"unrecorded billed calls in {self._unrecorded_path().name}; reconcile the "
                                    f"ledger and delete that file before sending more calls")

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
        self._check_usable()
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
            try:
                self._write(data)
            except OSError as exc:  # reservation not durable -> do not send
                raise LedgerUnavailable(f"spend ledger write failed ({type(exc).__name__}); refusing to send") from None
            return token

    def commit(self, token: str, actual: float, note: str = ""):
        try:
            self._commit(token, actual, note)
        except Exception as exc:  # the call WAS billed: record it elsewhere and stop all further spending
            self.poisoned = f"commit of a billed call failed ({type(exc).__name__})"
            try:
                with open(self._unrecorded_path(), "a", encoding="utf-8") as side:
                    side.write(json.dumps({"t": round(time.time(), 3), "run": self.run_id, "usd": actual,
                                           "token": token}) + "\n")
            except OSError:
                pass
            raise LedgerUnavailable(self.poisoned) from None

    def _commit(self, token: str, actual: float, note: str = ""):
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
        """Drop a reservation after a call failed before billing. On error the reservation simply stays held
        (over-counting is the safe direction) and the ledger is disabled for this process."""
        try:
            with self._lock, self._locked():
                data = self._read()
                if token in (data.get("reservations") or {}):
                    data["reservations"].pop(token)
                    self._write(data)
        except Exception as exc:
            self.poisoned = f"release failed ({type(exc).__name__})"

    def remaining(self) -> float:
        data = self._read()
        held = sum(v["usd"] for v in self._live(data).values())
        return min(self.job_cap - float(data.get("global_usd", 0)) - held,
                   self.run_cap - float(data.get("runs", {}).get(self.run_id, 0)) - held)

    def status(self) -> str:
        return (f"ledger ${self.total():.4f} / job cap ${self.job_cap:.2f}; run '{self.run_id}' "
                f"${self.mine():.4f} / run cap ${self.run_cap:.2f}")
