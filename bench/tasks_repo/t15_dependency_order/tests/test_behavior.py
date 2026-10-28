import unittest
from core import build_order, job_count
from copy import deepcopy
class GraphTests(unittest.TestCase):
    def test_order(self):
        graph = {'z':['b'], 'b':['a','a'], 'c':[], 'd':['external']}
        saved = deepcopy(graph)
        self.assertEqual(build_order(graph),['a','b','c','external','d','z'])
        self.assertEqual(graph,saved)
        self.assertEqual(job_count(graph),6)
        self.assertEqual(build_order({}),[])
    def test_dynamic_ready_set(self):
        self.assertEqual(build_order({'z':[], 'b':['a'], 'a':[]}),['a','b','z'])
    def test_cycles(self):
        for graph in ({'a':['a']}, {'ok':[], 'a':['b'],'b':['a']}, {'a':['b'],'b':['c'],'c':['a']}):
            with self.subTest(graph=graph), self.assertRaises(ValueError): build_order(graph)

if __name__ == "__main__":
    unittest.main()
