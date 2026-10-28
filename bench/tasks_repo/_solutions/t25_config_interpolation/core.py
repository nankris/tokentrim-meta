def resolve_config(values):
    resolved, active = {}, set()
    def resolve(key):
        if key in resolved: return resolved[key]
        if key not in values: raise ValueError('unknown reference')
        if key in active: raise ValueError('reference cycle')
        active.add(key)
        text, out, i = values[key], [], 0
        while i < len(text):
            if text.startswith('$$',i):
                out.append('$'); i += 2
            elif text.startswith('${',i):
                end = text.find('}',i+2)
                if end < 0: raise ValueError('unclosed reference')
                out.append(resolve(text[i+2:end])); i = end+1
            else:
                out.append(text[i]); i += 1
        active.remove(key)
        resolved[key] = ''.join(out)
        return resolved[key]
    return {key:resolve(key) for key in values}
def display_config(values):
    return '\n'.join(f'{key}={values[key]}' for key in sorted(values))
