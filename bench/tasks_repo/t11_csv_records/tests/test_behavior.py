import unittest
from core import read_records, column_values
class CSVTests(unittest.TestCase):
    def test_quoting(self):
        text = '\nname,note\n"Doe, Jo","a""b\nnext"\n\nx,\n'
        self.assertEqual(read_records(text), [{'name':'Doe, Jo','note':'a"b\nnext'},{'name':'x','note':''}])
    def test_shape(self):
        for text in ('a,a\n1,2', 'a,b\n1', 'a\n1,2'):
            with self.subTest(text=text), self.assertRaises(ValueError): read_records(text)
        self.assertEqual(read_records('\n\n'),[])
        self.assertEqual(read_records('a,b\n x , y '),[{'a':' x ','b':' y '}])
        self.assertEqual(column_values([{'a':'x'}],'a'),['x'])

if __name__ == "__main__":
    unittest.main()
