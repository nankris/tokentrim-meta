from money import to_cents, format_cents
class Ledger:
    def __init__(self, opening): self.balances = {k:to_cents(v) for k,v in opening.items()}
    def balance(self, account): return format_cents(self.balances[account])
    def transfer(self, source, target, amount):
        cents = to_cents(amount)
        self.balances[source] -= cents
        self.balances[target] += cents
