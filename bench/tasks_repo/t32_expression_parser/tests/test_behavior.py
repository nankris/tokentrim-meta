import unittest
from core import evaluate, format_result
class ExpressionTests(unittest.TestCase):
    def test_values(self):
        for text,expected in [('12 + 3 - 4',11),('2+3*4',14),('(2+3)*4',20),('20/2/2',5),('8-3-2',3),('- - +2',2),('3*-2',-6),('-(2 + 3) / 2',-2.5),('1\t+\n2',3),('007',7)]:
            with self.subTest(text=text): self.assertEqual(evaluate(text),expected)
        self.assertEqual(format_result(3),'3')
    def test_invalid(self):
        for text in ('',' ','1 2','1+','()','(1','1)','2(3)','1.5','2**3','abc','[1]','١'):
            with self.subTest(text=text), self.assertRaises(ValueError): evaluate(text)
        with self.assertRaises(ZeroDivisionError): evaluate('3/(2-2)')

if __name__ == "__main__":
    unittest.main()
