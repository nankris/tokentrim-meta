class Job:
    def __init__(self):
        self.state = 'new'
        self.history = []
    def send(self, event):
        old = self.state
        if old == 'new' and event == 'start': self.state = 'running'
        elif old == 'running' and event == 'finish': self.state = 'done'
        elif old in ('new','running') and event == 'cancel': self.state = 'cancelled'
        else: raise ValueError('invalid event')
        self.history.append((old,event,self.state))
    def is_terminal(self): return self.state in ('done','cancelled')
