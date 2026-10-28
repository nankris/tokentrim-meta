from decimal import Decimal, ROUND_HALF_UP
def invoice_total(lines):
    cent = Decimal('0.01')
    return sum(((Decimal(price) * qty).quantize(cent, rounding=ROUND_HALF_UP)
                for price, qty in lines), Decimal('0.00'))
def invoice_label(number):
    return f'INV-{number:06d}'
