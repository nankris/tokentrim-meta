import heapq
from itertools import count
class PriorityQueue:
    def __init__(self):
        self.heap = []
        self.sequence = count()
    def push(self, priority, item):
        heapq.heappush(self.heap, (priority, next(self.sequence), item))
    def pop(self): return heapq.heappop(self.heap)[2]
    def __len__(self): return len(self.heap)
