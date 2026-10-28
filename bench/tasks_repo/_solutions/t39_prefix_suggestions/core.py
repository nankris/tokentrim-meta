class SuggestionIndex:
    def __init__(self): self.counts = {}
    def add(self, word): self.counts[word] = self.counts.get(word,0)+1
    def remove(self, word):
        if word not in self.counts: return False
        self.counts[word] -= 1
        if self.counts[word] == 0: del self.counts[word]
        return True
    def suggest(self, prefix, limit=5):
        if limit < 0: raise ValueError('negative limit')
        matches = (word for word in self.counts if word.startswith(prefix))
        return sorted(matches,key=lambda word:(-self.counts[word],word))[:limit]
def highlight(word, prefix):
    return '[' + word[:len(prefix)] + ']' + word[len(prefix):]
