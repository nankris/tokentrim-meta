from decimal import Decimal
def invoice_total(lines):
    return Decimal(str(round(sum(float(price) * qty for price, qty in lines), 2)))
def invoice_label(number):
    return f'INV-{number:06d}'
