# Cli Separator

Fix parse_args(argv), which returns (verbose, paths). Recognize -v and --verbose until the first standalone --. After that separator every token is a literal path, including another --. Before it, reject other dash-prefixed options except the literal stdin path -. Preserve path order and support options mixed with paths.

Run `python -m unittest discover -s tests -q` from this directory.
