import re
def evaluate(text):
    tokens, position = [], 0
    while position < len(text):
        if text[position].isspace(): position += 1; continue
        match = re.match(r'[0-9]+|[()+*/-]',text[position:])
        if not match: raise ValueError('invalid character')
        tokens.append(match.group()); position += len(match.group())
    index = 0
    def atom():
        nonlocal index
        if index == len(tokens): raise ValueError('missing operand')
        token = tokens[index]; index += 1
        if token in ('+','-'):
            value = atom()
            return value if token == '+' else -value
        if token == '(':
            value = expression()
            if index == len(tokens) or tokens[index] != ')': raise ValueError('missing close')
            index += 1
            return value
        if token.isdecimal(): return int(token)
        raise ValueError('expected operand')
    def term():
        nonlocal index
        value = atom()
        while index < len(tokens) and tokens[index] in ('*','/'):
            op = tokens[index]; index += 1
            right = atom()
            value = value * right if op == '*' else value / right
        return value
    def expression():
        nonlocal index
        value = term()
        while index < len(tokens) and tokens[index] in ('+','-'):
            op = tokens[index]; index += 1
            right = term()
            value = value + right if op == '+' else value - right
        return value
    value = expression()
    if index != len(tokens): raise ValueError('trailing tokens')
    return value
def format_result(value): return str(value)
