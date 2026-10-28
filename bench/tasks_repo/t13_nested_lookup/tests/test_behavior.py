import unittest
from core import lookup
class LookupTests(unittest.TestCase):
    def test_paths(self):
        data = {'rows':[{'name':'a'}, {'name':None}], '0':False, '':{'x':7}}
        self.assertEqual(lookup(data,'rows.00.name'),'a')
        self.assertIsNone(lookup(data,'rows.1.name','missing'))
        self.assertIs(lookup(data,'0','missing'),False)
        self.assertIs(lookup(data,''),data)
        self.assertEqual(lookup(data,'.x'),7)
    def test_missing(self):
        sentinel = object()
        for path in ('x','rows.-1','rows.+0','rows.9','rows.٠','rows.0.x','rows.'):
            with self.subTest(path=path): self.assertIs(lookup({'rows':[3]},path,sentinel),sentinel)

if __name__ == "__main__":
    unittest.main()
