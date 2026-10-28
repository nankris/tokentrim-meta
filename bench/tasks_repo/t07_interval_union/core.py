def merge_ranges(ranges):
    ranges.sort()
    merged = []
    for start, end in ranges:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], end)
        else: merged.append((start, end))
    return merged
def covered_length(ranges):
    return sum(end-start for start, end in merge_ranges(ranges))
