def encode_runs(values):
    result = []
    for value in values:
        if result and result[-1][0] == value:
            previous,count = result[-1]
            result[-1] = (previous,count+1)
        else: result.append((value,1))
    return result
def decode_runs(runs):
    result = []
    for value,count in runs:
        if not isinstance(count,int) or isinstance(count,bool) or count <= 0:
            raise ValueError('invalid run count')
        result.extend([value]*count)
    return result
def encoded_size(runs): return len(runs)
