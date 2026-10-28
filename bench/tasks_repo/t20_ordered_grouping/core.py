def group_rows(rows, key):
    raise NotImplementedError('grouping')
def select_columns(row, columns):
    return {key:row[key] for key in columns if key in row}
