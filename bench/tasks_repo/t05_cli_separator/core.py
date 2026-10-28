def parse_args(argv):
    verbose, paths = False, []
    for arg in argv:
        if arg in ('-v', '--verbose'): verbose = True
        elif arg == '--': continue
        elif arg.startswith('-') and arg != '-': raise ValueError(arg)
        else: paths.append(arg)
    return verbose, paths
def usage():
    return 'scan [-v] [--] PATH ...'
