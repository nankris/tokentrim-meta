"""Install or uninstall the TokenTrim skill and optional Claude hooks."""
import argparse
import copy
import json
from pathlib import Path
import shutil

# Only the loop guard is installed as a Claude Code PostToolUse hook. A PostToolUse hook can only ADD
# context (it cannot replace the tool output the model already sees), so a compression hook there would
# increase tokens. Compression is used as a pipe filter instead: `cmd | python3 -m tokentrim.hooks.compress`.
COMMANDS = ["python3 -m tokentrim.hooks.loop_guard --claude-posttooluse"]
LEGACY = ["python3 -m tokentrim.hooks.compress --claude-posttooluse"]
SOURCE = Path(__file__).resolve().parents[2] / "skills/tokentrim"


def merge_hooks(settings, uninstall):
    if uninstall:
        entries = settings.get("hooks", {}).get("PostToolUse", [])
        for index in range(len(entries) - 1, -1, -1):
            entry = entries[index]
            if entry.get("matcher") == "Bash":
                hooks = entry.get("hooks", [])
                kept = [h for h in hooks
                        if not (h.get("type") == "command" and h.get("command") in COMMANDS + LEGACY)]
                if kept != hooks:
                    entry["hooks"] = kept
                    if not kept:
                        entries.pop(index)
        return
    entries = settings.setdefault("hooks", {}).setdefault("PostToolUse", [])
    present = {h.get("command") for e in entries if e.get("matcher") == "Bash"
               for h in e.get("hooks", []) if h.get("type") == "command"}
    missing = [{"type": "command", "command": c} for c in COMMANDS if c not in present]
    if missing:
        entries.append({"matcher": "Bash", "hooks": missing})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("codex", "claude", "agents", "all"), default="all")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--with-hooks", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    root = (args.project or Path.home()).expanduser().resolve()
    targets = [".agents", ".claude"] if args.target == "all" else [
        ".claude" if args.target == "claude" else ".agents"]
    # Validate settings before making any changes to installed files.
    settings_path = root / ".claude/settings.json"
    settings = updated = None
    if ".claude" in targets and (args.with_hooks or args.uninstall):
        settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
        updated = copy.deepcopy(settings)
        merge_hooks(updated, args.uninstall)
    for target in targets:
        destination = root / target / "skills/tokentrim"
        if args.uninstall:
            if destination.exists():
                print(f"Remove {destination}")
                if not args.dry_run:
                    shutil.rmtree(destination)
            continue
        for source in sorted(SOURCE.rglob("*")):
            relative = source.relative_to(SOURCE)
            if not source.is_file() or (relative.parts[0] not in ("SKILL.md", "references", "scripts")):
                continue
            if "__pycache__" in relative.parts or source.suffix == ".pyc":
                continue
            path = destination / relative
            print(path)
            if not args.dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, path)
    if updated is not None and updated != settings:
        if settings_path.exists():
            backup = settings_path.with_suffix(".json.bak")
            print(backup)
            if not args.dry_run:
                shutil.copy2(settings_path, backup)
        print(settings_path)
        if not args.dry_run:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
