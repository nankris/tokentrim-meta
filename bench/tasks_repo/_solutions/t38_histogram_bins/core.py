from bisect import bisect_right
def histogram(values, edges):
    edges = list(edges)
    if any(a >= b for a,b in zip(edges,edges[1:])): raise ValueError('edges must increase')
    counts = [0]*(len(edges)+1)
    for value in values: counts[bisect_right(edges,value)] += 1
    return counts
def total_count(counts): return sum(counts)
