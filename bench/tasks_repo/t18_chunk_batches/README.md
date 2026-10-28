# Chunk Batches

Add batches(iterable, size), a lazy iterator of independent lists of up to size elements, including a final short batch. Work with one-shot iterators and consume no more than one batch before yielding it. Reject nonpositive size with ValueError before consuming input. Empty input produces no batches.

Run `python -m unittest discover -s tests -q` from this directory.
