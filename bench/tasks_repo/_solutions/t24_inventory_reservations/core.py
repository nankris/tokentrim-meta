class Inventory:
    def __init__(self, stock):
        self.stock = dict(stock)
        self.reservations = {}
    def available(self, sku): return self.stock.get(sku,0)
    def reserve(self, token, items):
        items = dict(items)
        if token in self.reservations:
            if self.reservations[token] != items: raise ValueError('token conflict')
            return
        if any(sku not in self.stock or qty < 0 or qty > self.stock[sku] for sku,qty in items.items()):
            raise ValueError('unavailable stock')
        for sku,qty in items.items(): self.stock[sku] -= qty
        self.reservations[token] = items
    def release(self, token):
        if token not in self.reservations: return False
        for sku,qty in self.reservations.pop(token).items(): self.stock[sku] += qty
        return True
