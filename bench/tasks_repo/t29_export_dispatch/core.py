import json
def as_json(rows): return json.dumps(list(rows),sort_keys=True)
def as_text(rows, columns):
    return '\n'.join('\t'.join(str(row.get(c,'')) for c in columns) for row in rows)
def render(rows, format, columns):
    if format == 'json': return as_json(rows)
    if format == 'text': return as_text(rows,columns)
    raise ValueError('unsupported format')
