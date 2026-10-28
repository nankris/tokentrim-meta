import unicodedata
def word_counts(text):
    counts, chars = {}, []
    def flush():
        if chars:
            word = ''.join(chars)
            counts[word] = counts.get(word, 0) + 1
            chars.clear()
    for char in unicodedata.normalize('NFC', text).casefold():
        if char.isalpha() or (chars and unicodedata.category(char).startswith('M')):
            chars.append(char)
        else:
            flush()
    flush()
    return counts
def most_common(counts):
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))
