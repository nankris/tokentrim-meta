from settings import load_settings
def parse_cli(argv, defaults=None):
    values = dict(defaults or {})
    index = 0
    while index < len(argv):
        if argv[index] != '--timeout' or index + 1 == len(argv): raise ValueError('invalid argument')
        values['timeout'] = argv[index+1]
        index += 2
    return load_settings(values)
def usage(): return 'request [--timeout SECONDS]'
