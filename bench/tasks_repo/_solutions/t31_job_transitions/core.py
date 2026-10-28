TRANSITIONS = {
    ('new','start'):'running', ('new','cancel'):'cancelled',
    ('running','finish'):'done', ('running','cancel'):'cancelled',
    ('running','pause'):'paused', ('paused','resume'):'running',
    ('paused','cancel'):'cancelled',
}
class Job:
    def __init__(self):
        self.state = 'new'
        self.history = []
    def send(self, event):
        old = self.state
        if (old,event) not in TRANSITIONS: raise ValueError('invalid event')
        self.state = TRANSITIONS[old,event]
        self.history.append((old,event,self.state))
    def is_terminal(self): return self.state in ('done','cancelled')
