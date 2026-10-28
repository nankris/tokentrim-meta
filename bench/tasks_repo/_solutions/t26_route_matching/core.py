def _segments(path):
    if not path.startswith('/'): raise ValueError('absolute path required')
    text = path.rstrip('/')
    return text[1:].split('/') if text else []
class Router:
    def __init__(self): self.routes = []
    def add(self, pattern, handler):
        parts, names = _segments(pattern), set()
        for i, part in enumerate(parts):
            if part.startswith((':','*')):
                name = part[1:]
                if not name or name in names: raise ValueError('invalid name')
                if part[0] == '*' and i != len(parts)-1: raise ValueError('wildcard must be final')
                names.add(name)
        self.routes.append((parts,handler))
    def match(self, path):
        parts = _segments(path)
        best, best_score = None, None
        for pattern, handler in self.routes:
            captures, score, index, matched = {}, [], 0, True
            for part in pattern:
                if part.startswith('*'):
                    captures[part[1:]] = '/'.join(parts[index:])
                    score.append(0); index = len(parts)
                elif index >= len(parts):
                    matched = False; break
                elif part.startswith(':'):
                    if not parts[index]: matched = False; break
                    captures[part[1:]] = parts[index]
                    score.append(1); index += 1
                elif part == parts[index]:
                    score.append(2); index += 1
                else:
                    matched = False; break
            if matched and index == len(parts):
                ranking = tuple(score + [3])
                if best_score is None or ranking > best_score:
                    best, best_score = (handler,captures), ranking
        return best
def route_label(pattern):
    return 'route ' + pattern
