from urllib.parse import urlencode
def encode_query(pairs):
    return urlencode([(str(key),str(value)) for key,value in pairs if value is not None])
def append_query(path, encoded):
    if not encoded: return path
    return path + ('&' if '?' in path else '?') + encoded
