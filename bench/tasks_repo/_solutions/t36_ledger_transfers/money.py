from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
def to_cents(value):
    try:
        number = Decimal(value)
        if not number.is_finite(): raise ValueError('nonfinite money')
        with localcontext() as context:
            context.prec = max(28,len(number.as_tuple().digits)+abs(number.adjusted())+4)
            return int((number*100).to_integral_value(rounding=ROUND_HALF_UP))
    except (InvalidOperation,TypeError): raise ValueError('invalid money') from None
def format_cents(value):
    sign = '-' if value < 0 else ''
    major, minor = divmod(abs(value),100)
    return f'{sign}{major}.{minor:02d}'
def currency_label(): return 'credits'
