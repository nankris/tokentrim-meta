import json
from models import Record
def dumps(records):
    return json.dumps({'version':1,'records':[{'id':r.id,'text':r.text} for r in records]})
def loads(text):
    data = json.loads(text)
    if data['version'] != 1: raise ValueError('unknown version')
    return [Record(row['id'],row['text']) for row in data['records']]
