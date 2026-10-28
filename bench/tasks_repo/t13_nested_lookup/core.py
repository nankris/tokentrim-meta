def lookup(data, path, default=None):
    current = data
    for part in path.split('.'):
        if not isinstance(current,dict): return default
        current = current.get(part,default)
    return current or default
def keys_sorted(data):
    return sorted(data)
