def encode(payload):
    return len(payload).to_bytes(2,'big') + payload
def decode(frame):
    size = int.from_bytes(frame[:2],'big')
    if len(frame) != size+2: raise ValueError('invalid length')
    return frame[2:]
def hex_preview(payload): return payload[:16].hex()
