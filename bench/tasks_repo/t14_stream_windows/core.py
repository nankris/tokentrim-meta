def windows(iterable, size):
    values = list(iterable)
    for index in range(0, len(values), size):
        yield tuple(values[index:index+size])
def pair_deltas(values):
    return [b-a for a,b in windows(values,2)]
