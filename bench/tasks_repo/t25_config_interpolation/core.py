def resolve_config(values):
    raise NotImplementedError('interpolation')
def display_config(values):
    return '\n'.join(f'{key}={values[key]}' for key in sorted(values))
