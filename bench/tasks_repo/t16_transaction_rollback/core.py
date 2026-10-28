from contextlib import contextmanager
class Store:
    def __init__(self, data): self.data = data
    @contextmanager
    def transaction(self):
        snapshot = self.data.copy()
        try: yield self
        except Exception:
            self.data = snapshot
            raise
    def get(self, key, default=None): return self.data.get(key,default)
