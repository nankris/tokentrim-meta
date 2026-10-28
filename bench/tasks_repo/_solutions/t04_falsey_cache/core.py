class Memo:
    def __init__(self, loader):
        self.loader = loader
        self.values = {}
    def get(self, key):
        if key not in self.values:
            self.values[key] = self.loader(key)
        return self.values[key]
    def clear(self):
        self.values.clear()
