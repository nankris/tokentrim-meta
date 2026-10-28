from itertools import islice
def batches(iterable, size):
    if size <= 0: raise ValueError('size must be positive')
    source = iter(iterable)
    while True:
        batch = list(islice(source,size))
        if not batch: return
        yield batch
def batch_label(index):
    return f'batch-{index:04d}'
