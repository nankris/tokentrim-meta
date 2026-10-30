"""Shared helpers for REAL Meta Model API runs (spend-capped; no secrets written)."""
import json
from pathlib import Path

from tokentrim.cost import CostModel
from tokentrim.guard import SpendGuard

CONTRIB = "meta/muse-spark-1.3-contributor"
STANDARD = "meta/muse-spark-1.3"
GLOBAL_CAP_USD = 0.50


def make_guard(out_dir: Path, per_task_usd: float = 0.10, max_steps: int = 40) -> SpendGuard:
    """One persisted ledger for the whole real run; every script shares it and the $0.50 cap."""
    return SpendGuard(per_task_usd=per_task_usd, global_usd=GLOBAL_CAP_USD, max_steps=max_steps,
                      ledger_path=out_dir / "spend_ledger.json")


def costs() -> CostModel:
    return CostModel()


def write_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
