import csv
import io
def read_records(text):
    rows = (row for row in csv.reader(io.StringIO(text, newline='')) if row)
    headers = next(rows, None)
    if headers is None: return []
    if len(set(headers)) != len(headers): raise ValueError('duplicate header')
    result = []
    for row in rows:
        if len(row) != len(headers): raise ValueError('wrong field count')
        result.append(dict(zip(headers,row)))
    return result
def column_values(records, name):
    return [row[name] for row in records]
