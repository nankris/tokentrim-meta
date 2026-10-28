from codec import decode
class FrameReader:
    def __init__(self): self.buffer = bytearray()
    def feed(self, chunk):
        self.buffer.extend(chunk)
        result = []
        while len(self.buffer) >= 2:
            total = int.from_bytes(self.buffer[:2],'big') + 3
            if len(self.buffer) < total: break
            frame = bytes(self.buffer[:total])
            try: payload = decode(frame)
            except ValueError:
                self.buffer.clear()
                raise
            del self.buffer[:total]
            result.append(payload)
        return result
    def finish(self):
        if self.buffer: raise ValueError('truncated frame')
