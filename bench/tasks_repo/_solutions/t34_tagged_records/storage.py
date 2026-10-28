import json
from models import Record
def dumps(records):
    return json.dumps({'version':2,'records':[{'id':r.id,'text':r.text,'tags':r.tags} for r in records]})
def loads(text):
    data = json.loads(text)
    version = data['version']
    if version not in (1,2): raise ValueError('unknown version')
    return [Record(row['id'],row['text'],row['tags'] if version == 2 else ()) for row in data['records']]
