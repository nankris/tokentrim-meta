import heapq
class PriorityQueue:
    def __init__(self): self.heap = []
    def push(self, priority, item): heapq.heappush(self.heap, (priority, item))
    def pop(self): return heapq.heappop(self.heap)[1]
    def __len__(self): return len(self.heap)
