def convert(value, source, target):
    source, target = source.upper(), target.upper()
    if source not in ('C','F','K') or target not in ('C','F','K'):
        raise ValueError('unsupported conversion')
    if source == target: return value
    celsius = (value - 32) * 5 / 9 if source == 'F' else value - 273.15 if source == 'K' else value
    return celsius * 9 / 5 + 32 if target == 'F' else celsius + 273.15 if target == 'K' else celsius
def c_to_f(value): return convert(value,'C','F')
def f_to_c(value): return convert(value,'F','C')
def temperature_label(value, unit): return f'{value:.1f} °{unit}'
