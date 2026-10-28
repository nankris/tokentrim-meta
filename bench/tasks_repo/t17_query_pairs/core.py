def encode_query(pairs):
    raise NotImplementedError('query encoding is not available')
def append_query(path, encoded):
    if not encoded: return path
    return path + ('&' if '?' in path else '?') + encoded
