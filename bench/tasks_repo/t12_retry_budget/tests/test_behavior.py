import unittest
from core import run_with_retry
class RetryTests(unittest.TestCase):
    def test_success(self):
        events = iter([ValueError('one'), ValueError('two'), 0])
        sleeps = []
        def op():
            value = next(events)
            if isinstance(value,Exception): raise value
            return value
        self.assertEqual(run_with_retry(op,3,(ValueError,),sleeps.append),0)
        self.assertEqual(sleeps,[1,2])
    def test_exhaustion_and_filter(self):
        error = ValueError('last')
        calls, sleeps = [], []
        def fail():
            calls.append(1)
            raise error
        with self.assertRaises(ValueError) as caught: run_with_retry(fail,2,(ValueError,),sleeps.append)
        self.assertIs(caught.exception,error)
        self.assertEqual((len(calls),sleeps),(2,[1]))
        calls.clear(); sleeps.clear()
        with self.assertRaises(ValueError): run_with_retry(fail,3,(OSError,),sleeps.append)
        self.assertEqual((len(calls),sleeps),(1,[]))
    def test_invalid(self):
        for n in (0,-1):
            with self.assertRaises(ValueError): run_with_retry(lambda:1,n,(Exception,),lambda n:None)

if __name__ == "__main__":
    unittest.main()
