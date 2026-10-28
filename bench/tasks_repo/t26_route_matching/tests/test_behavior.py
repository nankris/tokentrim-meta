import unittest
from core import Router
class RouterTests(unittest.TestCase):
    def test_specificity(self):
        r = Router()
        r.add('/*all','fallback'); r.add('/users/:id','user'); r.add('/users/new','new')
        r.add('/users/*tail','tail'); r.add('/users','index')
        self.assertEqual(r.match('/users/new/'),('new',{}))
        self.assertEqual(r.match('/users/42'),('user',{'id':'42'}))
        self.assertEqual(r.match('/users/a/b'),('tail',{'tail':'a/b'}))
        self.assertEqual(r.match('/users/'),('index',{}))
        self.assertEqual(r.match('/'),('fallback',{'all':''}))
    def test_ties_and_lexicographic_choice(self):
        r = Router()
        r.add('/:x/fixed','param'); r.add('/literal/:y','literal'); r.add('/literal/:z','later')
        self.assertEqual(r.match('/literal/fixed'),('literal',{'y':'fixed'}))
        self.assertIsNone(r.match('/absent'))
        self.assertIsNone(r.match('/literal//x'))
        self.assertEqual(r.match('/literal/a%20b'),('literal',{'y':'a%20b'}))
    def test_validation_and_zero_tail(self):
        r = Router()
        for pattern in ('relative','/:','/*','/:x/:x','/*tail/end'):
            with self.subTest(pattern=pattern), self.assertRaises(ValueError): r.add(pattern,'bad')
        r.add('/a/*tail',7)
        self.assertEqual(r.match('/a'),(7,{'tail':''}))
        r.add('/',8)
        self.assertEqual(r.match('/'),(8,{}))
        with self.assertRaises(ValueError): r.match('relative')

if __name__ == "__main__":
    unittest.main()
