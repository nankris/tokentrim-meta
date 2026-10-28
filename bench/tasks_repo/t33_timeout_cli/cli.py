from settings import load_settings
def parse_cli(argv, defaults=None):
    if argv: raise ValueError('unknown argument')
    return load_settings(defaults or {})
def usage(): return 'request [--timeout SECONDS]'
