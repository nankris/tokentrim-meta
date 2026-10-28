import heapq
def shortest_path(graph, start, end):
    nodes = set(graph)
    for edges in graph.values():
        nodes.update(edges)
        if any(cost < 0 for cost in edges.values()): raise ValueError('negative cost')
    if start not in nodes or end not in nodes: return None
    initial = (0,0,(start,))
    best, queue = {start:initial}, [initial]
    while queue:
        cost,hops,path = heapq.heappop(queue)
        node = path[-1]
        if best.get(node) != (cost,hops,path): continue
        if node == end: return cost,list(path)
        for neighbor,weight in graph.get(node,{}).items():
            candidate = (cost+weight,hops+1,path+(neighbor,))
            if neighbor not in best or candidate < best[neighbor]:
                best[neighbor] = candidate
                heapq.heappush(queue,candidate)
    return None
def edge_count(graph): return sum(len(edges) for edges in graph.values())
