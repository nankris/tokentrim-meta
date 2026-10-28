class Inventory:
    def __init__(self, stock): self.stock = dict(stock)
    def available(self, sku): return self.stock.get(sku,0)
    def reserve(self, token, items): raise NotImplementedError('reserve')
    def release(self, token): raise NotImplementedError('release')
