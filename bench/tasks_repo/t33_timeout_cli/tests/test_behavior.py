import unittest
from settings import load_settings, describe
from cli import parse_cli
class TimeoutTests(unittest.TestCase):
    def test_loading_and_override(self):
        self.assertEqual(describe(load_settings({})),'timeout=30; retries=3')
        self.assertEqual(load_settings({'timeout':'1.25'}).timeout,1.25)
        defaults = {'timeout':9}
        self.assertEqual(parse_cli([],defaults).timeout,9)
        self.assertEqual(parse_cli(['--timeout','2','--timeout','3.5'],defaults).timeout,3.5)
        self.assertEqual(defaults,{'timeout':9})
    def test_invalid(self):
        for value in (0,-1,True,None,'no','nan','inf','-inf'):
            with self.subTest(value=value), self.assertRaises(ValueError): load_settings({'timeout':value})
        for argv in (['--timeout'],['--other','1'],['x'],['--timeout','0'],['--timeout','nan']):
            with self.subTest(argv=argv), self.assertRaises(ValueError): parse_cli(argv)

if __name__ == "__main__":
    unittest.main()
