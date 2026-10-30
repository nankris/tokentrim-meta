"""Compress stdin reversibly, or provide a Claude PostToolUse context view."""
import argparse
import json
from pathlib import Path
import shlex
import sys

from ..optimizers.tool_output import ToolOutputCompressor
from ..store import OriginalStore


def response_text(response):
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return "\n".join(response[k] for k in ("stdout", "output", "content", "stderr")
                         if isinstance(response.get(k), str))
    return ""


def context(text):
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse", "additionalContext": text}})


def main():
    raw = ""
    hook = "--claude-posttooluse" in sys.argv
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--store", default=str(Path.home() / ".cache/tokentrim/originals"))
        parser.add_argument("--min-tokens", type=int, default=400)
        parser.add_argument("--retrieve")
        parser.add_argument("--claude-posttooluse", action="store_true")
        # Preserve arbitrary bytes on the fail-open path as well as ordinary UTF-8.
        sys.stdin.reconfigure(errors="surrogateescape")
        sys.stdout.reconfigure(errors="surrogateescape")
        if "--retrieve" not in sys.argv:
            raw = sys.stdin.read()
        args = parser.parse_args()
        store = OriginalStore(Path(args.store).expanduser())
        if args.retrieve:
            sys.stdout.write(store.get(args.retrieve))
            print("TokenTrim: retrieved original.", file=sys.stderr)
            return 0
        text = response_text(json.loads(raw).get("tool_response")) if hook else raw
        result = ToolOutputCompressor(store, min_tokens=args.min_tokens).compress(text)
        if hook:
            if result.ref:
                hint = (f"\nRetrieve: python3 -m tokentrim.hooks.compress --store "
                        f"{shlex.quote(args.store)} --retrieve {result.ref}")
                print(context(result.text + hint))
        else:
            sys.stdout.write(result.text)
            print(result.explanation or "TokenTrim: output left unchanged.", file=sys.stderr)
    except (Exception, SystemExit) as exc:
        if not hook:
            if isinstance(exc, SystemExit) and exc.code == 0:
                return 0
            sys.stdout.write(raw)
            print("TokenTrim: output left unchanged after an error.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
