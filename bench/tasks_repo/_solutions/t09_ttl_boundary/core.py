class TTLCache:
    def __init__(self, clock):
        self.clock, self.entries = clock, {}
    def put(self, key, value, ttl):
        if ttl <= 0:
            self.entries.pop(key, None)
        else:
            self.entries[key] = (value, self.clock()+ttl)
    def get(self, key, default=None):
        if key not in self.entries: return default
        value, expiry = self.entries[key]
        if self.clock() >= expiry:
            del self.entries[key]
            return default
        return value
