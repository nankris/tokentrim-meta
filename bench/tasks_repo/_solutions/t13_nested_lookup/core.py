def lookup(data, path, default=None):
    current = data
    if path == '': return current
    for part in path.split('.'):
        if isinstance(current,dict):
            if part not in current: return default
            current = current[part]
        elif isinstance(current,list):
            if not part or any(c not in '0123456789' for c in part): return default
            index = int(part)
            if index >= len(current): return default
            current = current[index]
        else: return default
    return current
def keys_sorted(data):
    return sorted(data)
