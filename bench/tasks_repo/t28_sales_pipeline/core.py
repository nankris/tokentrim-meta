def sales_total(rows):
    return sum(row['amount'] for row in rows)
def sales_by_region(rows):
    result = {}
    for row in rows:
        region = row['region']
        result[region] = result.get(region,0) + row['amount']
    return result
def report_title(month): return 'Sales: ' + month
