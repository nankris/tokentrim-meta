import re
def evaluate(text):
    parts = re.findall(r'[+-]?\d+',text.replace(' ',''))
    if not parts: raise ValueError('empty expression')
    return sum(int(part) for part in parts)
def format_result(value): return str(value)
