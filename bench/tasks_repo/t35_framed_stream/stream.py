from codec import decode
class FrameReader:
    def feed(self, chunk): return [decode(chunk)] if chunk else []
    def finish(self): return None
