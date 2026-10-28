import csv
import io
import json
def render(rows, format, columns):
    if format == 'json': return json.dumps(list(rows),sort_keys=True)
    columns = list(columns)
    if format == 'text':
        return '\n'.join('\t'.join(str(row.get(c,'')) for c in columns) for row in rows)
    if format == 'csv':
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(columns)
        for row in rows: writer.writerow([row.get(c,'') for c in columns])
        return output.getvalue()
    raise ValueError('unsupported format')
def as_json(rows): return render(rows,'json',())
def as_text(rows, columns): return render(rows,'text',columns)
