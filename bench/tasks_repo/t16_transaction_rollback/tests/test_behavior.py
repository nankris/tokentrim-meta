import unittest
from core import Store
class Abort(BaseException): pass
class TransactionTests(unittest.TestCase):
    def test_deep_rollback_and_identity(self):
        data = {'rows':[1]}
        store = Store(data)
        error = Abort('stop')
        with self.assertRaises(Abort) as caught:
            with store.transaction() as active:
                self.assertIs(active,store)
                store.data['rows'].append(2)
                store.data['new'] = True
                raise error
        self.assertIs(caught.exception,error)
        self.assertIs(store.data,data)
        self.assertEqual(data,{'rows':[1]})
    def test_nested(self):
        store = Store({'rows':[]})
        with store.transaction():
            store.data['rows'].append('outer')
            try:
                with store.transaction():
                    store.data['rows'].append('inner')
                    raise ValueError()
            except ValueError: pass
            self.assertEqual(store.get('rows'),['outer'])
        with self.assertRaises(ValueError):
            with store.transaction():
                with store.transaction(): store.data['rows'].append('committed inner')
                raise ValueError()
        self.assertEqual(store.data,{'rows':['outer']})

if __name__ == "__main__":
    unittest.main()
