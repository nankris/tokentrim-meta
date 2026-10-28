import unittest
from core import render, as_json, as_text
class ExportTests(unittest.TestCase):
    def test_legacy(self):
        rows = [{'b':2,'a':1},{'a':None}]
        self.assertEqual(as_json(iter(rows)), '[{"a": 1, "b": 2}, {"a": null}]')
        self.assertEqual(as_text(iter(rows),['b','a']),'2\t1\n\tNone')
        self.assertEqual(render(iter(rows),'text',['a']), '1\nNone')
        self.assertEqual(render(iter(rows),'json',[]),as_json(rows))
    def test_csv(self):
        rows = [{'name':'a,b','note':'say "hi"'},{'name':'x\ny','note':None},{}]
        self.assertEqual(render(iter(rows),'csv',['name','note']),'name,note\r\n"a,b","say ""hi"""\r\n"x\ny",\r\n,\r\n')
        self.assertEqual(render([],'csv',['x']),'x\r\n')
        with self.assertRaises(ValueError): render([],'yaml',[])

if __name__ == "__main__":
    unittest.main()
