def encode(payload):
    if len(payload) > 65535: raise ValueError('payload too large')
    return len(payload).to_bytes(2,'big') + bytes(payload) + bytes([sum(payload)%256])
def decode(frame):
    if len(frame) < 3: raise ValueError('invalid length')
    size = int.from_bytes(frame[:2],'big')
    if len(frame) != size+3: raise ValueError('invalid length')
    payload = bytes(frame[2:-1])
    if frame[-1] != sum(payload)%256: raise ValueError('checksum mismatch')
    return payload
def hex_preview(payload): return payload[:16].hex()
