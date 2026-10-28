def split_fields(line):
    fields, buf = [], []
    escaped = False
    for char in line:
        if escaped:
            buf.append(char)
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == ',':
            fields.append(''.join(buf))
            buf = []
        else:
            buf.append(char)
    if escaped:
        buf.append('\\')
    fields.append(''.join(buf))
    return fields

def join_preview(fields):
    return ' | '.join(fields)
