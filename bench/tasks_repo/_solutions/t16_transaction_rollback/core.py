from contextlib import contextmanager
from copy import deepcopy
class Store:
    def __init__(self, data): self.data = data
    @contextmanager
    def transaction(self):
        snapshot = deepcopy(self.data)
        try: yield self
        except BaseException:
            self.data.clear()
            self.data.update(snapshot)
            raise
    def get(self, key, default=None): return self.data.get(key,default)
