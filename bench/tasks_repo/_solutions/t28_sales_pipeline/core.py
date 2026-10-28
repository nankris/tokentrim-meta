def _entries(rows):
    for row in rows:
        kind = row.get('kind','sale')
        if kind == 'void': continue
        if kind not in ('sale','refund'): raise ValueError('unknown kind')
        yield row['region'], row['amount'] * (-1 if kind == 'refund' else 1)
def sales_total(rows):
    return sum(amount for _,amount in _entries(rows))
def sales_by_region(rows):
    result = {}
    for region,amount in _entries(rows):
        result[region] = result.get(region,0) + amount
    return result
def report_title(month): return 'Sales: ' + month
