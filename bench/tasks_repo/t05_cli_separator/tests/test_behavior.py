import unittest
from core import parse_args
class ArgsTests(unittest.TestCase):
    def test_separator(self):
        self.assertEqual(parse_args(['--','-v','--','-x']), (False,['-v','--','-x']))
        self.assertEqual(parse_args(['a','-v','--','-b']), (True,['a','-b']))
    def test_existing_options(self):
        self.assertEqual(parse_args([]), (False,[]))
        self.assertEqual(parse_args(['-','a','--verbose','b']), (True,['-','a','b']))
        with self.assertRaises(ValueError): parse_args(['--unknown'])

if __name__ == "__main__":
    unittest.main()
