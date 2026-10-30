"""Nudge once when a normalized command repeats the same failure."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from .compress import context, response_text

ERROR = re.compile(r"error|exception|fail|traceback|fatal|panic|denied|not found|non-zero", re.I)


def normalize(text):
    text = re.sub(r"(?:[A-Za-z]:)?[/\\][^\s\"'<>]*tmp[^\s\"'<>]*", "<tmp>", text)
    text = re.sub(r"\b(?:0x[0-9a-f]+|[0-9a-f]{8,})\b", "<hex>", text, flags=re.I)
    text = re.sub(r"\d+", "<n>", text)
    return " ".join(text.split())


class LoopGuard:
    def __init__(self, threshold=2):
        self.threshold = threshold
        self.state = {}

    def observe(self, command: str, output: str, exit_code: int | None) -> str | None:
        cmd = normalize(command)
        errors = [line for line in output.splitlines() if ERROR.search(line)]
        if exit_code == 0 or (exit_code is None and not errors):
            self.state.pop(cmd, None)
            return None
        line = errors[-1] if errors else (output.strip().splitlines() or [str(exit_code)])[-1]
        signature = hashlib.sha256(normalize(line).encode()).hexdigest()[:10]
        failures = self.state.setdefault(cmd, {})
        count = failures.get(signature, 0) + 1
        failures[signature] = count
        if count == self.threshold:
            return (f"TokenTrim loop guard: the same failure ({signature}) happened {count} times "
                    f"for `{cmd}`; change approach instead of retrying unchanged.")
        return None


def main():
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--claude-posttooluse", action="store_true")
        parser.add_argument("--state", default=str(Path.home() / ".cache/tokentrim/loop_guard.json"))
        args = parser.parse_args()
        event = json.load(sys.stdin)
        if not args.claude_posttooluse or event.get("tool_name") != "Bash":
            return 0
        command = event.get("tool_input", {}).get("command")
        if not isinstance(command, str):
            return 0
        response = event.get("tool_response")
        output = response_text(response)
        code = response.get("exit_code", response.get("exitCode")) if isinstance(response, dict) else None
        if code is not None:
            code = int(code)
        if code is None:
            match = re.search(r"exit(?:ed with)? (?:code|status)[: =]+(-?\d+)", output, re.I)
            code = int(match[1]) if match else None
        path = Path(args.state).expanduser()
        guard = LoopGuard()
        if path.exists():
            guard.state = json.loads(path.read_text(encoding="utf-8"))
        nudge = guard.observe(command, output, code)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(guard.state), encoding="utf-8")
        if nudge:
            print(context(nudge))
    except (Exception, SystemExit):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
