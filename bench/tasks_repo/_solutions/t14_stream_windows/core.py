from collections import deque
def windows(iterable, size):
    if size <= 0: raise ValueError('size must be positive')
    window = deque(maxlen=size)
    for value in iterable:
        window.append(value)
        if len(window) == size: yield tuple(window)
def pair_deltas(values):
    return [b-a for a,b in windows(values,2)]
