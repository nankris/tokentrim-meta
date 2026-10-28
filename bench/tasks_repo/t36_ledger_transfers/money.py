def to_cents(value): return int(float(value)*100)
def format_cents(value): return f'{value/100:.2f}'
def currency_label(): return 'credits'
