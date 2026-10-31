"""v5.1(3): ledger/budget/auth errors fail CLOSED (no call is sent); optimizer errors fail OPEN."""
import json
import multiprocessing as mp
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tokentrim.gateway import Gateway, GatewayConfig
from tokentrim.guard import LedgerUnavailable, SpendCapExceeded
from tokentrim.ledger import SpendLedger
from tokentrim.upstream import ChatUpstream, MockChatUpstream

PAYLOAD = {"model": "muse-spark-1.3-contributor", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 50}


class Metered(MockChatUpstream):
    """Mock that behaves like a metered upstream (requires a ledger) and counts sends."""
    metered = True

    def __init__(self, **kw):
        super().__init__(**kw)
        self.sent = 0

    def _send(self, payload):
        self.sent += 1
        return super()._send(payload)


def _proc_worker(path, cap, n, q):
    led = SpendLedger(path, cap, cap, f"p{os.getpid()}", lock_timeout=60)
    ok = 0
    for _ in range(n):
        try:
            tok = led.reserve(0.01)
            led.commit(tok, 0.01)
            ok += 1
        except SpendCapExceeded:
            pass
    q.put(ok)


class FailClosedTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "ledger.json"

    def ledger(self, **kw):
        return SpendLedger(self.path, 1.0, 1.0, "t", **kw)

    def assert_not_sent(self, up, exc=LedgerUnavailable):
        with self.assertRaises(exc):
            Gateway(up, GatewayConfig(tool_output=True)).complete(dict(PAYLOAD))
        self.assertEqual(up.sent, 0)

    def test_corrupt_file_blocks_and_is_not_overwritten(self):
        led = self.ledger()
        self.path.write_text("{not json")
        self.assert_not_sent(Metered(ledger=led))
        self.assertEqual(self.path.read_text(), "{not json")

    def test_malformed_fields_block(self):
        led = self.ledger()
        self.path.write_text(json.dumps({"global_usd": "lots", "runs": {}}))
        self.assert_not_sent(Metered(ledger=led))
        self.path.write_text(json.dumps([1, 2]))
        self.assert_not_sent(Metered(ledger=led))

    def test_lock_timeout_blocks(self):
        import fcntl
        led = self.ledger(lock_timeout=0.2)
        holder = open(self.path.with_suffix(".lock"), "w")
        fcntl.flock(holder, fcntl.LOCK_EX)
        try:
            self.assert_not_sent(Metered(ledger=led))
        finally:
            holder.close()
        up = Metered(ledger=led)
        Gateway(up, GatewayConfig()).complete(dict(PAYLOAD))  # lock free again -> works
        self.assertEqual(up.sent, 1)

    def test_disk_error_on_reserve_blocks(self):
        led = self.ledger()
        with mock.patch.object(SpendLedger, "_write", side_effect=OSError(28, "No space left on device")):
            self.assert_not_sent(Metered(ledger=led))

    def test_disk_error_on_commit_poisons_ledger(self):
        led = self.ledger()
        up = Metered(ledger=led)
        real = SpendLedger._write
        calls = {"n": 0}

        def flaky(self_, data):
            calls["n"] += 1
            if calls["n"] == 2:  # 1 = reserve, 2 = commit
                raise OSError(5, "I/O error")
            return real(self_, data)
        with mock.patch.object(SpendLedger, "_write", flaky):
            with self.assertRaises(LedgerUnavailable):
                Gateway(up, GatewayConfig()).complete(dict(PAYLOAD))
        self.assertEqual(up.sent, 1)  # it was billed...
        side = Path(str(self.path) + ".unrecorded.jsonl")
        self.assertTrue(side.exists())  # ...so it is recorded on the side
        self.assert_not_sent_again(up, led)
        fresh = Metered(ledger=self.ledger())  # even a new ledger object refuses until reconciled
        self.assert_not_sent(fresh)
        side.unlink()
        Gateway(fresh, GatewayConfig()).complete(dict(PAYLOAD))
        self.assertEqual(fresh.sent, 1)

    def assert_not_sent_again(self, up, led):
        before = up.sent
        with self.assertRaises(LedgerUnavailable):
            Gateway(up, GatewayConfig()).complete(dict(PAYLOAD))
        self.assertEqual(up.sent, before)

    def test_no_ledger_on_metered_upstream_blocks(self):
        self.assert_not_sent(Metered(ledger=None))
        with mock.patch.dict(os.environ, {"META_API_KEY": "x-test-not-a-key"}):
            up = ChatUpstream(ledger=None)
            with mock.patch.object(ChatUpstream, "_send", side_effect=AssertionError("must not send")):
                with self.assertRaises(LedgerUnavailable):
                    up.create(dict(PAYLOAD))

    def test_cap_exceeded_blocks(self):
        led = SpendLedger(self.path, 1e-7, 1.0, "t")
        self.assert_not_sent(Metered(ledger=led), SpendCapExceeded)

    def test_auth_error_is_not_retried_or_forwarded_unreserved(self):
        led = self.ledger()
        up = Metered(ledger=led)
        from tokentrim.upstream import UpstreamError
        with mock.patch.object(MockChatUpstream, "_send", side_effect=UpstreamError("HTTP 401: unauthorized")):
            with self.assertRaises(UpstreamError):
                Gateway(up, GatewayConfig(tool_output=True)).complete(dict(PAYLOAD))
        data = json.loads(self.path.read_text())
        self.assertEqual(data.get("reservations"), {})  # released, nothing billed
        self.assertEqual(float(data.get("global_usd", 0)), 0.0)

    def test_optimizer_error_fails_open(self):
        led = self.ledger()
        up = Metered(ledger=led)
        with mock.patch("tokentrim.transforms.optimize", side_effect=RuntimeError("boom")):
            data, report = Gateway(up, GatewayConfig(tool_output=True)).complete(dict(PAYLOAD))
        self.assertEqual(up.sent, 1)
        self.assertEqual(up.calls[0]["messages"], PAYLOAD["messages"])  # original request forwarded
        self.assertTrue(report.fail_open)

    def test_concurrent_threads_never_overshoot(self):
        cap = 0.5
        ledgers = [SpendLedger(self.path, cap, cap, "t") for _ in range(4)]  # separate objects, same file
        ok = []

        def work(led):
            for _ in range(40):
                try:
                    tok = led.reserve(0.013)
                    led.commit(tok, 0.013)
                    ok.append(1)
                except SpendCapExceeded:
                    pass
        threads = [threading.Thread(target=work, args=(ledgers[i % 4],)) for i in range(12)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        total = json.loads(self.path.read_text())["global_usd"]
        self.assertLessEqual(total, cap + 1e-9)
        self.assertEqual(len(ok), int(cap / 0.013 + 1e-9))

    def test_concurrent_processes_never_overshoot(self):
        cap = 0.3
        q = mp.get_context("fork").Queue()
        procs = [mp.get_context("fork").Process(target=_proc_worker, args=(str(self.path), cap, 20, q))
                 for _ in range(6)]
        [p.start() for p in procs]
        [p.join(120) for p in procs]
        ok = sum(q.get(timeout=5) for _ in procs)
        total = json.loads(self.path.read_text())["global_usd"]
        self.assertLessEqual(total, cap + 1e-9)
        self.assertEqual(ok, 30)
        self.assertAlmostEqual(total, 0.30, places=9)


if __name__ == "__main__":
    unittest.main()
