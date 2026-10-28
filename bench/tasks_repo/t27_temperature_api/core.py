def c_to_f(value): return value * 9 / 5 + 32
def f_to_c(value): return (value - 32) * 5 / 9
def convert(value, source, target):
    if source == 'C' and target == 'F': return c_to_f(value)
    if source == 'F' and target == 'C': return f_to_c(value)
    raise ValueError('unsupported conversion')
def temperature_label(value, unit): return f'{value:.1f} °{unit}'
