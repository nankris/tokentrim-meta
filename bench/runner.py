"""Offline harness with optional execution of task checks in temporary copies."""
import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Callable

from tokentrim.clients.base import ModelClient, ModelResponse
from tokentrim.clients.fake import FakeModelClient
from tokentrim.middleware import TokenTrim
from tokentrim.pruner import ContextItem
from tokentrim.router import Step
from .stats import summarize
from .checker import CheckResult, EDIT_INSTRUCTIONS, real_checker, reference_self_test
from dataclasses import asdict

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TASKS = ROOT / "bench/tasks/example_tasks.jsonl"


@dataclass(frozen=True)
class Task:
    id: str
    repo: str
    prompt: str
    check: str
    files: list[str] = field(default_factory=list)
    solution: str | None = None
    category: str = "unspecified"
    difficulty: str = "easy"


def safe_path(path: str | Path, root: Path = ROOT) -> Path:
    """Constrain input/output paths and reject secret-like names, including symlinks."""
    candidate = Path(path)
    candidate = candidate if candidate.is_absolute() else root / candidate
    resolved = candidate.resolve()
    for value in (candidate, resolved):
        if any(part == ".local" or part.startswith(("colab_key", "colab_rsa", ".env", ".codex"))
               or part == ".ssh" or part.endswith(".pem") for part in value.parts):
            raise ValueError("Restricted path")
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Path must stay inside the repository root")
    return resolved


def load_tasks(path: str | Path) -> list[Task]:
    source = safe_path(path)
    text = source.read_text(encoding="utf-8")
    records = json.loads(text) if source.suffix == ".json" else [json.loads(line) for line in text.splitlines() if line.strip()]
    if not isinstance(records, list) or not records:
        raise ValueError("Task file must contain a nonempty list of tasks")
    tasks = []
    ids = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Each task must be an object")
        for key in ("id", "repo", "prompt", "check"):
            if not isinstance(record.get(key), str) or not record[key]:
                raise ValueError(f"Task requires a nonempty string {key}")
        if record["id"] in ids:
            raise ValueError(f"Duplicate task id: {record['id']}")
        files = record.get("files", [])
        if not isinstance(files, list) or any(not isinstance(f, str) for f in files):
            raise ValueError("files must be a list of relative paths")
        if record.get("difficulty", "easy") not in {"easy", "medium", "hard"}:
            raise ValueError("Invalid task difficulty")
        if Path(record["repo"]).is_absolute() or any(Path(f).is_absolute() for f in files):
            raise ValueError("Task repo and file paths must be relative")
        repo = safe_path(record["repo"])
        for filename in files:
            safe_path(filename, repo)
        task = Task(**{key: value for key, value in record.items() if key in Task.__dataclass_fields__})
        tasks.append(task)
        ids.add(task.id)
    return tasks


def fake_checker(task: Task, responses: list[ModelResponse], mode: str) -> bool:
    """Synthetic health check ONLY. Does not establish task correctness."""
    return bool(responses) and all(response.text.startswith("FAKE") for response in responses)


Checker = Callable[[Task, list[ModelResponse], str], bool | CheckResult]


def task_context(task: Task) -> list[ContextItem]:
    # Intentional naive ordering provides the same starting material to both modes.
    items = [ContextItem("old-tool", "tool_output", "\n".join(f"FAKE diagnostic line {n}: no edit performed" for n in range(80)), turn=0),
             ContextItem("system", "system", "You are a coding assistant. Follow the task and preserve tests. " + EDIT_INSTRUCTIONS, pinned=True),
             ContextItem("repo-map", "file", f"Repository: {task.repo}\nFiles: {', '.join(task.files)}", pinned=True),
             ContextItem("unused", "file", "FAKE unrelated context.\n" * 100)]
    repo = safe_path(task.repo)
    for n, filename in enumerate(task.files):
        content = safe_path(filename, repo).read_text(encoding="utf-8")
        items.append(ContextItem(f"file-{n}", "file", f"File: {filename}\n{content}", turn=1, referenced=True))
    items.append(ContextItem("user", "message", task.prompt, turn=1))
    return items


def run_benchmark(tasks_path: str | Path = DEFAULT_TASKS, out: str | Path = ROOT / "results/results.json", *,
                  client_factory: Callable[[], ModelClient] = FakeModelClient, checker: Checker = fake_checker,
                  token_budget: int = 4096, seed: int = 42, samples: int = 2000) -> dict:
    tasks = load_tasks(tasks_path)
    output_path = safe_path(out)
    protected = ROOT / "bench/tasks_repo"
    if output_path.is_relative_to(protected) or output_path == ROOT / "bench/tasks/tasks_40.jsonl":
        raise ValueError("Output path belongs to the separately managed task corpus")
    rows = []
    all_fake = True
    for task in tasks:
        initial = task_context(task)
        for mode in ("baseline", "tokentrim"):
            # Cold cache per task/mode; reuse within a task, never across competitors.
            client = client_factory()
            all_fake = all_fake and isinstance(client, FakeModelClient)
            pipeline = TokenTrim(client, token_budget=token_budget)
            responses = []
            items = list(initial)
            steps = [Step("read"), Step("edit", file_count=max(1, len(task.files)),
                                          estimated_edit_lines=10 if task.difficulty == "easy" else 100)]
            for turn, step in enumerate(steps, start=2):
                response, record = pipeline.complete(items, step, mode=mode)
                responses.append(response)
                items = items + [ContextItem(f"assistant-{turn}", "message", response.text, turn=turn, role="assistant"),
                                 ContextItem(f"followup-{turn}", "message", "Continue with the requested edit.", turn=turn)]
            usage = {key: sum(r.usage[key] for r in pipeline.records) for key in ("input", "cached_input", "output")}
            checked = checker(task, responses, mode)
            rows.append({"task_id": task.id, "mode": mode, "category": task.category, "difficulty": task.difficulty,
                         "usage": usage, "tokens": usage["input"] + usage["output"],
                         "dollars": sum(r.dollars for r in pipeline.records),
                         "passed": bool(checked),
                         **({"check": asdict(checked)} if isinstance(checked, CheckResult) else {}),
                         "steps": [r.to_dict() for r in pipeline.records]})
    result = {"metadata": {"schema_version": 1, "data_kind": "FAKE" if all_fake or checker is fake_checker else "CUSTOM",
                            "usage_simulated": all_fake, "checks_simulated": checker is fake_checker,
                            "notice": ("Usage is simulated. " if all_fake else "Usage is client-reported. ") +
                                      ("Checks are simulated; not evidence of task correctness." if checker is fake_checker
                                       else "Checks use the selected checker; see per-task outcomes."),
                            "task_count": len(tasks), "tasks_path": str(safe_path(tasks_path).relative_to(ROOT)),
                            "bootstrap": {"method": "paired task percentile", "confidence": .95, "samples": samples, "seed": seed},
                            "token_definition": "input (including cached input) + output; summed over steps per task",
                            "cost_definition": "USD estimates from configured prices; cached tokens are an input subset",
                            "cache_policy": "cold per task/mode; fake full stable-prefix hits are scoped to model",
                            "paired_difference": "tokentrim - baseline; pass-rate differences are proportions",
                            "percent_saving": "100 * (mean baseline - mean tokentrim) / mean baseline; undefined at zero"},
              "results": rows, "summary": summarize(rows, seed=seed, samples=samples)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["fake"], default="fake")
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS))
    parser.add_argument("--out", default="results/results.json")
    parser.add_argument("--budget", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--checker", choices=["fake", "real"], default="fake")
    parser.add_argument("--reference-self-test", action="store_true", help="Check all 40 references and unmodified repos")
    args = parser.parse_args()
    if args.reference_self_test:
        result = reference_self_test()
        print(f"Reference: {result['reference_passed']}/40 pass; unmodified: {result['unmodified_failed']}/40 fail")
        for row in result["results"]:
            if not row["reference"]["passed"] or not row["unmodified_failed"]:
                print(json.dumps(row, indent=2))
        return 0 if result["task_count"] == result["reference_passed"] == result["unmodified_failed"] == 40 else 1
    result = run_benchmark(args.tasks, args.out, checker=real_checker if args.checker == "real" else fake_checker,
                           token_budget=args.budget, seed=args.seed, samples=args.samples)
    print(f"Simulated-usage benchmark ({args.checker} checker): {result['metadata']['task_count']} tasks, both modes -> {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
