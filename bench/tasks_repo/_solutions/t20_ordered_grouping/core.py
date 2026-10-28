def group_rows(rows, key):
    groups = {}
    for row in rows:
        groups.setdefault(row.get(key),[]).append(row)
    return list(groups.items())
def select_columns(row, columns):
    return {key:row[key] for key in columns if key in row}
