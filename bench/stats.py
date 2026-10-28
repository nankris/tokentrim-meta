"""Seeded percentile bootstrap over tasks; paired resampling preserves task pairs."""
import math
import random
from statistics import fmean


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _validate(values, samples):
    if not values or samples < 1:
        raise ValueError("Need nonempty observations and positive bootstrap samples")
    if any(not math.isfinite(v) for v in values):
        raise ValueError("Observations must be finite")


def bootstrap_mean(values: list[float], *, seed: int = 42, samples: int = 2000) -> dict:
    _validate(values, samples)
    rng = random.Random(seed)
    draws = [fmean(rng.choices(values, k=len(values))) for _ in range(samples)]
    return {"mean": fmean(values), "ci95": [percentile(draws, .025), percentile(draws, .975)], "n": len(values)}


def paired_comparison(baseline: list[float], trimmed: list[float], *, seed: int = 42, samples: int = 2000) -> dict:
    if len(baseline) != len(trimmed):
        raise ValueError("Paired samples must have equal lengths")
    _validate(baseline, samples)
    _validate(trimmed, samples)
    difference = bootstrap_mean([t - b for b, t in zip(baseline, trimmed)], seed=seed, samples=samples)
    rng = random.Random(seed)
    savings = []
    for _ in range(samples):
        indices = rng.choices(range(len(baseline)), k=len(baseline))
        b = fmean(baseline[i] for i in indices)
        t = fmean(trimmed[i] for i in indices)
        if b != 0:
            savings.append(100 * (b - t) / b)
    base_mean = fmean(baseline)
    # A zero denominator makes relative savings undefined. Never silently discard such draws.
    relative = {"mean": 100 * (base_mean - fmean(trimmed)) / base_mean if base_mean else None,
                "ci95": [percentile(savings, .025), percentile(savings, .975)]
                if len(savings) == samples else None, "n": len(baseline)}
    return {"difference": difference, "percent_saving": relative}


def average_repeats(rows: list[dict]) -> list[dict]:
    """Average numeric outcomes within task/mode before task-level bootstrap."""
    grouped = {}
    for row in rows:
        grouped.setdefault((row["task_id"], row["mode"]), []).append(row)
    averaged = []
    for (task_id, mode), values in sorted(grouped.items()):
        result = {"task_id": task_id, "mode": mode}
        keys = set.intersection(*(set(v) for v in values))
        for key in keys:
            if key not in {"task_id", "mode", "repeat"} and all(isinstance(v[key], (int, float, bool)) for v in values):
                result[key] = fmean(float(v[key]) for v in values)
        averaged.append(result)
    return averaged


def cost_per_pass(costs, passed, *, seed=42, samples=2000):
    if len(costs) != len(passed) or not costs:
        raise ValueError("Costs and pass outcomes must be nonempty and paired")
    total_pass = fmean(float(x) for x in passed)
    mean = fmean(costs) / total_pass if total_pass else None
    rng, draws = random.Random(seed), []
    for _ in range(samples):
        indices = rng.choices(range(len(costs)), k=len(costs))
        denominator = fmean(float(passed[i]) for i in indices)
        if not denominator:
            return {"mean": mean, "ci95": None, "n": len(costs)}
        draws.append(fmean(costs[i] for i in indices) / denominator)
    return {"mean": mean, "ci95": [percentile(draws, .025), percentile(draws, .975)], "n": len(costs)}


def noninferiority(pass_diff_ci, margin_pp=-10):
    return {"margin_pp": margin_pp, "verdict": pass_diff_ci is not None and pass_diff_ci[0] > margin_pp}


def summarize(rows: list[dict], *, seed: int = 42, samples: int = 2000,
              reference_mode: str = "baseline") -> dict:
    metrics = {"tokens": "tokens", "dollars": "dollars", "pass_rate": "passed"}
    modes = list(dict.fromkeys(row["mode"] for row in rows))
    grouped = {mode: {} for mode in modes}
    for row in rows:
        mode, task_id = row["mode"], row["task_id"]
        if mode not in grouped or task_id in grouped[mode]:
            raise ValueError("Unknown mode or duplicate task/mode result")
        grouped[mode][task_id] = row
    if reference_mode not in grouped or any(set(v) != set(grouped[reference_mode]) for v in grouped.values()):
        raise ValueError("Modes must contain matching task ids")
    ids = sorted(grouped[reference_mode])
    summary = {mode: {} for mode in grouped}
    summary["paired"] = {}
    for metric, field in metrics.items():
        values = {mode: [float(grouped[mode][i][field]) for i in ids] for mode in grouped}
        for mode in grouped:
            summary[mode][metric] = bootstrap_mean(values[mode], seed=seed, samples=samples)
        if modes == ["baseline", "tokentrim"] or set(modes) == {"baseline", "tokentrim"}:
            summary["paired"][metric] = paired_comparison(values["baseline"], values["tokentrim"], seed=seed, samples=samples)
        else:
            summary["paired"][metric] = {mode: paired_comparison(values[reference_mode], values[mode], seed=seed, samples=samples)
                                          for mode in modes if mode != reference_mode}
    return summary
