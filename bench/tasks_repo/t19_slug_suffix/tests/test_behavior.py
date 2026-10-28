import unittest
from core import unique_slug, slug_path
class SlugTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(unique_slug('  Café & Crème! ',set()),'cafe-creme')
        self.assertEqual(unique_slug('東京',set()),'item')
        self.assertEqual(unique_slug('A__B 42',set()),'a-b-42')
    def test_collisions_and_input(self):
        used = {'report','report-2','report-4'}
        self.assertEqual(unique_slug('Report',used),'report-3')
        self.assertEqual(used,{'report','report-2','report-4'})
        self.assertEqual(unique_slug('',{'item','item-2'}),'item-3')
        self.assertEqual(unique_slug('Report',{'REPORT'}),'report')
        self.assertEqual(slug_path('hello'),'/articles/hello')

if __name__ == "__main__":
    unittest.main()
