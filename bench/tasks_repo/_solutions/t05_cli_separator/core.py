def parse_args(argv):
    verbose, paths, literal = False, [], False
    for arg in argv:
        if literal: paths.append(arg)
        elif arg in ('-v', '--verbose'): verbose = True
        elif arg == '--': literal = True
        elif arg.startswith('-') and arg != '-': raise ValueError(arg)
        else: paths.append(arg)
    return verbose, paths
def usage():
    return 'scan [-v] [--] PATH ...'
