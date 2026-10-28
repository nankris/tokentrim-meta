def read_records(text):
    lines = [line for line in text.splitlines() if line]
    if not lines: return []
    headers = lines[0].split(',')
    return [dict(zip(headers, line.split(','))) for line in lines[1:]]
def column_values(records, name):
    return [row[name] for row in records]
