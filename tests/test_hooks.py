"""Subprocess coverage for fail-open hooks and reversible installation."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from tokentrim.hooks.install import COMMANDS
from tokentrim.hooks.loop_guard import LoopGuard

ROOT = Path(__file__).resolve().parents[1]
LOG = "collected 500 items\n" + "tests/test_demo.py::test_ok PASSED\n" * 500 + "500 passed\n"


class HooksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_cli(self, module, *args, data=""):
        result = subprocess.run([sys.executable, "-m", "tokentrim.hooks." + module, *map(str, args)],
                                input=data, text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def compress(self, *args, data=""):
        return self.run_cli("compress", "--store", self.root / "originals", *args, data=data)

    def test_compress_and_retrieve(self):
        result = self.compress(data=LOG)
        self.assertLess(len(result.stdout), len(LOG) // 2)
        self.assertIn("500 passed", result.stdout)
        self.assertEqual(len(result.stderr.splitlines()), 1)
        ref = re.search(r'retrieve_original\("([^"]+)"\)', result.stdout)[1]
        self.assertEqual(self.compress("--retrieve", ref).stdout, LOG)
        self.assertEqual(self.compress("--min-tokens", "999999", data=LOG).stdout, LOG)

    def test_fail_open(self):
        garbage = "{broken JSON\x00\n"
        self.assertEqual(self.compress(data=garbage).stdout, garbage)
        blocked = self.root / "blocked"
        blocked.write_text("file")
        result = self.run_cli("compress", "--store", blocked / "store", data=LOG)
        self.assertEqual(result.stdout, LOG)
        self.assertEqual(len(result.stderr.splitlines()), 1)
        self.assertEqual(self.compress("--retrieve", "missing").stdout, "")

    def test_claude_compress(self):
        for response in [LOG, {"stdout": LOG}, {"output": LOG}, {"content": LOG}]:
            result = self.compress("--claude-posttooluse", data=json.dumps({"tool_response": response}))
            hook = json.loads(result.stdout)["hookSpecificOutput"]
            self.assertEqual(hook["hookEventName"], "PostToolUse")
            self.assertIn("--retrieve orig_", hook["additionalContext"])
        for data in ["garbage", "[]", "null", '{}', '{"tool_response":"small"}']:
            self.assertEqual(self.compress("--claude-posttooluse", data=data).stdout, "")

    def test_loop_guard(self):
        guard = LoopGuard()
        self.assertIsNone(guard.observe("pytest", "Error: broken", 1))
        self.assertIn("happened 2 times for `pytest`", guard.observe("pytest", "Error: broken", 1))
        self.assertIsNone(guard.observe("pytest", "Error: broken", 1))
        self.assertIsNone(guard.observe("pytest", "success", 0))
        self.assertIsNone(guard.observe("pytest", "Error: broken", 1))
        self.assertIsNotNone(guard.observe("pytest", "Error: broken", 1))
        self.assertIsNone(guard.observe("other", "Error: broken", 1))

    def test_normalization(self):
        guard = LoopGuard()
        self.assertIsNone(guard.observe("cat /tmp/run123/a", "Error 123 at /tmp/x/a 0xabc", None))
        self.assertIsNotNone(guard.observe("cat /tmp/run456/a", "Error 456 at /tmp/y/b 0xdef", None))
        self.assertIsNone(guard.observe("cat /tmp/run456/a", "Error: different", 1))

    def test_loop_cli(self):
        state = self.root / "state.json"
        event = {"tool_name": "Bash", "tool_input": {"command": "pytest"},
                 "tool_response": {"stderr": "Error: broken", "exit_code": 1}}
        def run(data):
            return self.run_cli("loop_guard", "--claude-posttooluse", "--state", state, data=data).stdout
        self.assertEqual(run(json.dumps(event)), "")
        self.assertIn("happened 2 times", json.loads(run(json.dumps(event)))["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(run(json.dumps(event)), "")
        event["tool_response"]["exit_code"] = 0
        self.assertEqual(run(json.dumps(event)), "")
        self.assertEqual(json.loads(state.read_text()), {})
        self.assertEqual(run("invalid"), "")
        event["tool_name"] = "Read"
        self.assertEqual(run(json.dumps(event)), "")

    def test_install_uninstall(self):
        settings = self.root / ".claude/settings.json"
        settings.parent.mkdir()
        original = {"permissions": {"allow": ["Read"]}, "hooks": {"PostToolUse": [
            {"matcher": "Bash", "hooks": []},
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo existing"}]}]}}
        settings.write_text(json.dumps(original))
        def install(*args):
            return self.run_cli("install", "--project", self.root, *args)
        install("--with-hooks", "--dry-run")
        self.assertEqual(json.loads(settings.read_text()), original)
        self.assertFalse((self.root / ".agents").exists())
        install("--with-hooks")
        for target in (".agents", ".claude"):
            skill = self.root / target / "skills/tokentrim"
            self.assertTrue((skill / "SKILL.md").is_file())
            self.assertTrue((skill / "references/coding.md").is_file())
            self.assertTrue((skill / "scripts/analyze.py").is_file())
        self.assertEqual(json.loads(settings.with_suffix(".json.bak").read_text()), original)
        first = settings.read_text()
        install("--with-hooks")
        self.assertEqual(settings.read_text(), first)
        installed = json.loads(first)
        self.assertEqual(installed["permissions"], original["permissions"])
        commands = [h["command"] for e in installed["hooks"]["PostToolUse"] for h in e["hooks"]]
        for command in COMMANDS:
            self.assertEqual(commands.count(command), 1)
        install("--uninstall")
        self.assertEqual(json.loads(settings.read_text()), original)
        self.assertFalse((self.root / ".agents/skills/tokentrim").exists())
        self.assertFalse((self.root / ".claude/skills/tokentrim").exists())
        install("--target", "codex", "--with-hooks")
        self.assertTrue((self.root / ".agents/skills/tokentrim/SKILL.md").exists())
        self.assertEqual(json.loads(settings.read_text()), original)


if __name__ == "__main__":
    unittest.main()
