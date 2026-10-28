import unittest
from core import PriorityQueue
class QueueTests(unittest.TestCase):
    def test_payloads_and_ties(self):
        q = PriorityQueue()
        a,b,c = {'a':1},{'b':2},object()
        q.push(2,a); q.push(2,b); q.push(1,c)
        self.assertEqual(len(q),3)
        self.assertIs(q.pop(),c)
        self.assertIs(q.pop(),a)
        q.push(2,c)
        self.assertIs(q.pop(),b)
        self.assertIs(q.pop(),c)
        self.assertEqual(len(q),0)
    def test_strings_and_empty(self):
        q = PriorityQueue()
        q.push(-1,'z'); q.push(-1,'a')
        self.assertEqual([q.pop(),q.pop()],['z','a'])
        with self.assertRaises(IndexError): q.pop()

if __name__ == "__main__":
    unittest.main()
