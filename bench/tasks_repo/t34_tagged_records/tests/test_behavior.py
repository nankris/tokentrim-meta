import unittest
import json
from models import Record, record_count
from storage import dumps, loads
class RecordTests(unittest.TestCase):
    def test_normalization_and_independence(self):
        tags = [' x ','','x','X',' y ']
        record = Record(1,'hello',tags)
        self.assertEqual(record.tags,['x','X','y'])
        record.tags.append('z')
        self.assertEqual(tags,[' x ','','x','X',' y '])
        a,b = Record(2,'a'),Record(3,'b')
        a.tags.append('one')
        self.assertEqual(b.tags,[])
    def test_storage(self):
        records = [Record(7,'é',['a','b'])]
        document = json.loads(dumps(records))
        self.assertEqual(document,{'version':2,'records':[{'id':7,'text':'é','tags':['a','b']}]})
        self.assertEqual(loads(dumps(records)),records)
        legacy = loads('{"version":1,"records":[{"id":1,"text":"old"}]}')
        self.assertEqual((legacy[0].text,legacy[0].tags),('old',[]))
        self.assertEqual(record_count(legacy),1)
        normalized = loads('{"version":2,"records":[{"id":1,"text":"x","tags":[" a ","a"]}]}')
        self.assertEqual(normalized[0].tags,['a'])
        with self.assertRaises(ValueError): loads('{"version":3,"records":[]}')
        with self.assertRaises((KeyError,ValueError)): loads('{"version":2,"records":[{"id":1,"text":"x"}]}')

if __name__ == "__main__":
    unittest.main()
