import unittest
from core import validate_user, validate_team, validate_project
class ValidationTests(unittest.TestCase):
    def test_all_models(self):
        for fn,name,count in ((validate_user,'name','age'),(validate_team,'name','size'),(validate_project,'title','seats')):
            with self.subTest(model=fn.__name__):
                data = {name:'  Alpha  ',count:0,'ignored':True}
                self.assertEqual(fn(data),[])
                self.assertEqual(data[name],'  Alpha  ')
                self.assertEqual(fn({}),[name+'_required',count+'_invalid'])
                for value in ('   ',4,None):
                    self.assertEqual(fn({name:value,count:1}),[name+'_required'])
                for value in (True,False,-1,1.5,'2',None):
                    self.assertEqual(fn({name:'ok',count:value}),[count+'_invalid'])
    def test_existing_valid(self):
        self.assertEqual(validate_user({'name':'A','age':20}),[])
        self.assertEqual(validate_team({'name':'B','size':3}),[])

if __name__ == "__main__":
    unittest.main()
