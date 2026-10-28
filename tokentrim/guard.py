"""Persistent local spend caps; values are accounting estimates."""
import json
import os
from pathlib import Path
import tempfile


class SpendCapExceeded(RuntimeError):
    pass


class SpendGuard:
    def __init__(self, per_task_usd=1.0, global_usd=120.0, ledger_path=None, max_steps=15):
        self.per_task_usd = per_task_usd
        self.global_usd = global_usd
        self.ledger_path = Path(ledger_path) if ledger_path else None
        self.max_steps = max_steps
        self.task_id = None
        self.task_spend = 0.0
        self.steps = 0
        self.global_spend = 0.0
        if self.ledger_path and self.ledger_path.exists():
            data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            self.global_spend = float(data.get("global_usd", 0))

    def start_task(self, task_id):
        self.task_id, self.task_spend, self.steps = str(task_id), 0.0, 0

    def check(self, projected_usd):
        if projected_usd < 0:
            raise ValueError("Projected spend must be nonnegative")
        if self.steps >= self.max_steps:
            raise SpendCapExceeded("max_steps cap tripped")
        if self.task_spend + projected_usd > self.per_task_usd:
            raise SpendCapExceeded("per-task cap tripped")
        if self.global_spend + projected_usd > self.global_usd:
            raise SpendCapExceeded("global cap tripped")

    def record(self, actual_usd):
        if actual_usd < 0:
            raise ValueError("Actual spend must be nonnegative")
        self.task_spend += actual_usd
        self.global_spend += actual_usd
        self.steps += 1
        if self.ledger_path:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(dir=self.ledger_path.parent, prefix=".ledger-", text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump({"global_usd": self.global_spend}, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, self.ledger_path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
