class SuggestionIndex:
    def add(self, word): raise NotImplementedError('add')
    def remove(self, word): raise NotImplementedError('remove')
    def suggest(self, prefix, limit=5): raise NotImplementedError('suggest')
def highlight(word, prefix):
    return '[' + word[:len(prefix)] + ']' + word[len(prefix):]
