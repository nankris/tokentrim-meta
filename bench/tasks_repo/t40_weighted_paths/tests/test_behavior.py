import unittest
from core import shortest_path, edge_count
from copy import deepcopy
class PathTests(unittest.TestCase):
    def test_cost_and_direction(self):
        graph = {'s':{'t':9,'b':2,'a':1},'a':{'t':4},'b':{'t':1},'alone':{}}
        saved = deepcopy(graph)
        self.assertEqual(shortest_path(graph,'s','t'),(3,['s','b','t']))
        self.assertIsNone(shortest_path(graph,'t','s'))
        self.assertIsNone(shortest_path(graph,'s','alone'))
        self.assertEqual(shortest_path(graph,'t','t'),(0,['t']))
        self.assertIsNone(shortest_path(graph,'missing','missing'))
        self.assertEqual(graph,saved)
        self.assertEqual(edge_count(graph),5)
    def test_tie_rules_and_cycles(self):
        graph = {'s':{'b':1,'a':1},'b':{'t':1},'a':{'s':0,'t':1},'t':{}}
        self.assertEqual(shortest_path(graph,'s','t'),(2,['s','a','t']))
        graph['s']['t'] = 2
        self.assertEqual(shortest_path(graph,'s','t'),(2,['s','t']))
        self.assertEqual(shortest_path({'s':{'a':0},'a':{'s':0,'t':1}},'s','t'),(1,['s','a','t']))
        deeper = {'s':{'a':0},'a':{'c':0,'b':0},'b':{'t':1},'c':{'t':1}}
        self.assertEqual(shortest_path(deeper,'s','t'),(1,['s','a','b','t']))
    def test_validation(self):
        with self.assertRaises(ValueError): shortest_path({'s':{},'x':{'y':-1}},'s','s')
        self.assertIsNone(shortest_path({},'s','t'))

if __name__ == "__main__":
    unittest.main()
