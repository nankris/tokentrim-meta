#!/usr/bin/env python3
"""Cost per successful task and token categories from a results JSONL (one row per task run).

Each row needs: arm, passed (bool), usd, and optionally uncached_tokens, cached_tokens, output_tokens,
truncated_calls, calls. Usage: python3 report.py results.jsonl
"""
import json
import sys
from collections import defaultdict


def main(path):
    arms = defaultdict(list)
    for line in open(path, encoding="utf-8"):
        if line.strip():
            row = json.loads(line)
            arms[row["arm"]].append(row)
    print("| arm | runs | pass | $ total | $ / successful task | uncached | cached | output | truncated calls |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for arm, rows in arms.items():
        ok = sum(bool(r.get("passed")) for r in rows)
        usd = sum(r.get("usd", 0) for r in rows)
        s = lambda k: sum(r.get(k, 0) for r in rows)
        per = f"{usd / ok:.5f}" if ok else "n/a"
        print(f"| {arm} | {len(rows)} | {ok}/{len(rows)} | {usd:.4f} | {per} | {s('uncached_tokens'):,} | "
              f"{s('cached_tokens'):,} | {s('output_tokens'):,} | {s('truncated_calls')}/{s('calls')} |")


if __name__ == "__main__":
    main(sys.argv[1])
