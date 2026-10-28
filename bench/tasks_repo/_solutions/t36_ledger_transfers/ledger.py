from money import to_cents, format_cents
class Ledger:
    def __init__(self, opening):
        self.balances = {k:to_cents(v) for k,v in opening.items()}
        if any(value < 0 for value in self.balances.values()): raise ValueError('negative balance')
    def balance(self, account): return format_cents(self.balances[account])
    def transfer(self, source, target, amount):
        cents = to_cents(amount)
        if cents <= 0: raise ValueError('amount must be positive')
        source_balance, target_balance = self.balances[source], self.balances[target]
        if source_balance < cents: raise ValueError('insufficient funds')
        if source != target:
            self.balances[source] = source_balance - cents
            self.balances[target] = target_balance + cents
