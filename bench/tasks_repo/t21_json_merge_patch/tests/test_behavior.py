import unittest
from core import merge_patch
from copy import deepcopy
class PatchTests(unittest.TestCase):
    def test_merge(self):
        target = {'a':{'x':1,'y':2},'b':[1,2],'keep':0}
        patch = {'a':{'x':None,'z':3},'b':[9],'missing':None}
        self.assertEqual(merge_patch(target,patch),{'a':{'y':2,'z':3},'b':[9],'keep':0})
        self.assertEqual(merge_patch([1],{'a':1}),{'a':1})
        self.assertIsNone(merge_patch({'a':1},None))
        self.assertEqual(merge_patch({'a':1},False),False)
    def test_no_aliases(self):
        target = {'keep':{'rows':[1]},'change':[2]}
        patch = {'change':[{'x':3}]}
        a,b = deepcopy(target),deepcopy(patch)
        result = merge_patch(target,patch)
        result['keep']['rows'].append(4)
        result['change'][0]['x'] = 5
        self.assertEqual((target,patch),(a,b))
        replacement = [1,{'a':[]}]
        result = merge_patch({},replacement)
        result[1]['a'].append(1)
        self.assertEqual(replacement,[1,{'a':[]}])

if __name__ == "__main__":
    unittest.main()
