class LRUCache:
    def __init__(self, capacity): self.capacity = capacity
    def get(self, key, default=None): raise NotImplementedError('get')
    def put(self, key, value): raise NotImplementedError('put')
    def __len__(self): return 0
