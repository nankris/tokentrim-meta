import unittest
from core import resolve_config
class InterpolationTests(unittest.TestCase):
    def test_recursive_and_escape(self):
        values = {'url':'${host}/${path}', 'path':'${empty}api', 'host':'local', 'empty':'', 'literal':'$${missing}', 'copy':'${literal}', 'dollars':'$$${host} $x $'}
        saved = dict(values)
        self.assertEqual(resolve_config(values),{'url':'local/api','path':'api','host':'local','empty':'','literal':'${missing}','copy':'${missing}','dollars':'$local $x $'})
        self.assertEqual(values,saved)
    def test_errors_and_empty(self):
        for values in ({'a':'${a}'},{'ok':'x','a':'${b}','b':'${a}'},{'a':'${missing}'},{'a':'${x'}):
            with self.subTest(values=values), self.assertRaises(ValueError): resolve_config(values)
        self.assertEqual(resolve_config({}),{})
        self.assertEqual(resolve_config({'':'v','a':'${}'}),{'':'v','a':'v'})

if __name__ == "__main__":
    unittest.main()
