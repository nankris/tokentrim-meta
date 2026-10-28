class Router:
    def __init__(self): self.routes = []
    def add(self, pattern, handler): raise NotImplementedError('routes')
    def match(self, path): raise NotImplementedError('matching')
def route_label(pattern):
    return 'route ' + pattern
